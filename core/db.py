"""
Shared SQLite access for the scraper and the dashboard.

Single shared DB at the repo root: app.db (WAL + busy_timeout).
One file for every platform. launch.pids stays next to launch.py.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILENAME = "app.db"
LEGACY_DB_FILENAME = "devto.db"
TOKYO_TZ = timezone(timedelta(hours=9))

MAIL_STATUSES = ("not_sent", "queued", "sent", "failed")
OUTCOMES = ("Waiting", "Replied", "Rejected")
QUEUE_STATUSES = ("queued", "sending", "sent", "failed", "cancelled")
# If the scraper process has not written a heartbeat within this window,
# the dashboard treats it as stopped (idle poll is 5–60s; HTTP timeouts ~20s).
SCRAPE_HEARTBEAT_STALE_SEC = 90.0
SCRAPE_LOOP_RUNNING = "running"
SCRAPE_LOOP_IDLING = "idling"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL COLLATE NOCASE,
    name TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    link TEXT NOT NULL DEFAULT '',
    github TEXT NOT NULL DEFAULT '',
    github_bio TEXT,
    socials TEXT,
    location TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'devto',
    platform_user_id TEXT,
    mail_status TEXT NOT NULL DEFAULT 'not_sent',
    social_status TEXT NOT NULL DEFAULT 'not_sent',
    sender_email TEXT NOT NULL DEFAULT '',
    mail_template TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT 'Waiting',
    suppressed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(email)
);

CREATE INDEX IF NOT EXISTS idx_users_country ON users(country);
CREATE INDEX IF NOT EXISTS idx_users_mail_status ON users(mail_status);
CREATE INDEX IF NOT EXISTS idx_users_name ON users(name);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_location ON users(location);

CREATE TABLE IF NOT EXISTS suppressed_locations (
    location TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scraper_parameter (
    platform_id TEXT PRIMARY KEY,
    parameter TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS queue_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'queued',
    queued_at TEXT NOT NULL,
    sent_at TEXT,
    sender_email TEXT NOT NULL DEFAULT '',
    template TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    UNIQUE(user_id)
);

CREATE INDEX IF NOT EXISTS idx_queue_status ON queue_items(status);
CREATE INDEX IF NOT EXISTS idx_queue_queued_at ON queue_items(queued_at);

CREATE TABLE IF NOT EXISTS mail_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    app_password TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    daily_cap INTEGER NOT NULL DEFAULT 20,
    sender_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mail_accounts_email ON mail_accounts(email);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mail_templates (
    filename TEXT PRIMARY KEY,
    region TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def db_path(result_dir: Path | None = None) -> Path:
    root = PROJECT_ROOT if result_dir is None else Path(result_dir)
    return root / DB_FILENAME


def _relocate_legacy_db(path: Path) -> None:
    """Move an older devto.db up to the shared app.db once."""
    if path.exists():
        return
    candidates = [
        path.parent / LEGACY_DB_FILENAME,
        path.parent / "result" / "devto" / LEGACY_DB_FILENAME,
        path.parent / "result" / LEGACY_DB_FILENAME,
        path.parent / "devto" / LEGACY_DB_FILENAME,
    ]
    for legacy in candidates:
        if not legacy.is_file() or legacy.resolve() == path.resolve():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        legacy.replace(path)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{legacy}{suffix}")
            if sidecar.is_file():
                sidecar.replace(Path(f"{path}{suffix}"))
        return


def _stable_tokyo_datetime() -> datetime | None:
    for key in ("STABLE_TOKYO_NOW", "TOKYO_NOW", "FIXED_TOKYO_NOW", "APP_NOW"):
        value = os.environ.get(key)
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TOKYO_TZ)
        return parsed.astimezone(TOKYO_TZ)
    return None


def current_tokyo_datetime() -> datetime:
    override = _stable_tokyo_datetime()
    if override is not None:
        return override
    return datetime.now(TOKYO_TZ)


def tokyo_now() -> str:
    return current_tokyo_datetime().isoformat()


def utc_now() -> str:
    return tokyo_now()


def local_day_prefix(now: datetime | None = None) -> str:
    if now is None:
        now = current_tokyo_datetime()
    if now.tzinfo is None:
        now = now.replace(tzinfo=TOKYO_TZ)
    else:
        now = now.astimezone(TOKYO_TZ)
    return now.strftime("%Y-%m-%d")


def connect(result_dir: Path | None = None) -> sqlite3.Connection:
    path = db_path(result_dir)
    _relocate_legacy_db(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(result_dir: Path | None = None) -> Path:
    path = db_path(result_dir)
    conn = connect(result_dir)
    try:
        conn.executescript(SCHEMA_SQL)
        if conn.execute(
            "SELECT value FROM app_meta WHERE key = 'scrape_paused'"
        ).fetchone() is None:
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES ('scrape_paused', '0')"
            )
        # migration: add sender_email column to existing queue_items when missing
        columns = [r[1] for r in conn.execute("PRAGMA table_info(queue_items)").fetchall()]
        if 'sender_email' not in columns:
            conn.execute(
                "ALTER TABLE queue_items ADD COLUMN sender_email TEXT NOT NULL DEFAULT ''"
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_sender_email ON queue_items(sender_email)")

        # migration: add daily_cap to existing mail_accounts when missing
        account_columns = [r[1] for r in conn.execute("PRAGMA table_info(mail_accounts)").fetchall()]
        if 'daily_cap' not in account_columns:
            conn.execute(
                "ALTER TABLE mail_accounts ADD COLUMN daily_cap INTEGER NOT NULL DEFAULT 20"
            )

        ensure_display_name_column(conn)
        ensure_user_source_columns(conn)
        ensure_github_column(conn)
        ensure_github_as_source(conn)
        ensure_github_profile_columns(conn)
        ensure_outcome_column(conn)
        ensure_sender_email_column(conn)
        ensure_mail_template_column(conn)
        ensure_mail_templates(conn)
        ensure_static_scrape_cap(conn)
        drop_unused_outcome_columns(conn)
        ensure_suppressed_column(conn)
        ensure_suppressed_locations(conn)
        ensure_manual_contact(conn)
        ensure_social_link_status(conn)
        ensure_social_provider_names(conn)
        ensure_drop_source_socials(conn)
        ensure_scraper_parameters(conn)
        ensure_mail_sender_name(conn)
        reset_mail_state_to_pending(conn)
        conn.commit()
    finally:
        conn.close()
    return path


def ensure_display_name_column(conn: sqlite3.Connection) -> None:
    """Add display_name and backfill from scraped name on existing databases."""
    user_columns = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "display_name" in user_columns:
        return
    conn.execute(
        "ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''"
    )
    conn.execute("UPDATE users SET display_name = name")


def _user_columns(conn: sqlite3.Connection) -> list[str]:
    return [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]


def normalize_platform_user_id(value: int | str | None) -> str | None:
    """Platform id for a later fetch. Empty when the site does not provide one."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def ensure_user_source_columns(conn: sqlite3.Connection) -> None:
    """Add source and a nullable platform id. Rename the Dev.to id column in place."""
    columns = _user_columns(conn)
    if "source" not in columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN source TEXT NOT NULL DEFAULT 'devto'"
        )
    conn.execute(
        "UPDATE users SET source = 'devto' WHERE source IS NULL OR TRIM(source) = ''"
    )
    columns = _user_columns(conn)
    if "platform_user_id" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN platform_user_id TEXT")
    columns = _user_columns(conn)
    if "devto_user_id" in columns:
        conn.execute(
            """
            UPDATE users
            SET platform_user_id = CAST(devto_user_id AS TEXT)
            WHERE devto_user_id IS NOT NULL
              AND (platform_user_id IS NULL OR TRIM(platform_user_id) = '')
            """
        )
        conn.execute("ALTER TABLE users DROP COLUMN devto_user_id")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_source ON users(source)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_platform_user_id ON users(platform_user_id)"
    )


def compose_source(source: str, github: str = "") -> str:
    """Origin platform, plus github when that account is stored."""
    parts: list[str] = []
    for item in (source or "devto").split(","):
        name = item.strip().lower()
        if name and name not in parts:
            parts.append(name)
    if not parts:
        parts.append("devto")
    if (github or "").strip() and "github" not in parts:
        parts.append("github")
    return ",".join(parts)


def ensure_github_as_source(conn: sqlite3.Connection) -> None:
    """A stored GitHub account is a source, recorded beside the origin platform."""
    conn.execute(
        """
        UPDATE users
        SET source = TRIM(source) || ',github'
        WHERE TRIM(github) != ''
          AND lower(',' || source || ',') NOT LIKE '%,github,%'
        """
    )


def ensure_github_column(conn: sqlite3.Connection) -> None:
    """GitHub account the public email was read from. Empty on older rows."""
    if "github" in _user_columns(conn):
        return
    conn.execute(
        "ALTER TABLE users ADD COLUMN github TEXT NOT NULL DEFAULT ''"
    )


def ensure_github_profile_columns(conn: sqlite3.Connection) -> None:
    """Bio and social links from GitHub. NULL means that profile has not been read yet."""
    columns = _user_columns(conn)
    if "github_bio" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN github_bio TEXT")
    if "socials" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN socials TEXT")


def ensure_suppressed_column(conn: sqlite3.Connection) -> None:
    """Hidden users stay in the table so a later scrape cannot insert them again."""
    if "suppressed" in _user_columns(conn):
        return
    conn.execute(
        "ALTER TABLE users ADD COLUMN suppressed INTEGER NOT NULL DEFAULT 0"
    )


CONTACT_STATUSES = ("not_sent", "sent", "failed")


def social_url_key(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def contact_status(value: str | None, default: str = "not_sent") -> str:
    text = (value or "").strip().lower()
    if text in CONTACT_STATUSES:
        return text
    return default


def load_social_links(raw: str | None) -> list[dict[str, str]]:
    """Stored socials JSON. A missing status stays blank so a caller can fill it."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        key = social_url_key(url)
        if key in seen:
            continue
        seen.add(key)
        provider = str(item.get("provider") or "generic").strip().lower() or "generic"
        status = str(item.get("status") or "").strip().lower()
        links.append({
            "provider": provider,
            "url": url,
            "status": status if status in CONTACT_STATUSES else "",
        })
    return links


def merge_social_link_status(
    links: list[dict[str, str]] | None,
    stored_raw: str | None,
    fallback: str = "not_sent",
) -> list[dict[str, str]]:
    """Keep {provider, url, status}. A URL already stored keeps its status."""
    previous = {
        social_url_key(item["url"]): item["status"]
        for item in load_social_links(stored_raw)
        if item["status"]
    }
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in links or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        key = social_url_key(url)
        if key in seen:
            continue
        seen.add(key)
        provider = str(item.get("provider") or "generic").strip().lower() or "generic"
        incoming = str(item.get("status") or "").strip().lower()
        status = previous.get(key) or (
            incoming if incoming in CONTACT_STATUSES else contact_status(fallback)
        )
        merged.append({"provider": provider, "url": url, "status": status})
    return merged


def ensure_manual_contact(conn: sqlite3.Connection) -> None:
    """One pool. Email and social each have not_sent, sent, or failed.

    Queued automatic sends return to not_sent. Stored app passwords are wiped once.
    """
    if "social_status" not in _user_columns(conn):
        conn.execute(
            "ALTER TABLE users ADD COLUMN social_status TEXT NOT NULL DEFAULT 'not_sent'"
        )
    conn.execute(
        """
        UPDATE users
        SET mail_status = 'not_sent'
        WHERE lower(coalesce(mail_status, '')) IN ('queued', 'sending')
        """
    )
    if get_meta(conn, "app_passwords_cleared_v1") != "1":
        conn.execute("UPDATE mail_accounts SET app_password = ''")
        set_meta(conn, "app_passwords_cleared_v1", "1")


def ensure_social_link_status(conn: sqlite3.Connection) -> None:
    """Copy the old whole-user social status onto each stored link, once."""
    if get_meta(conn, "social_link_status_v1") == "1":
        return
    rows = conn.execute(
        """
        SELECT id, socials, social_status FROM users
        WHERE socials IS NOT NULL AND TRIM(socials) != ''
        """
    ).fetchall()
    for row in rows:
        links = merge_social_link_status(
            load_social_links(row["socials"]),
            None,
            contact_status(row["social_status"]),
        )
        conn.execute(
            "UPDATE users SET socials = ? WHERE id = ?",
            (json.dumps(links, ensure_ascii=False), int(row["id"])),
        )
    set_meta(conn, "social_link_status_v1", "1")


def ensure_social_provider_names(conn: sqlite3.Connection) -> None:
    """Store a known site name on each link. A GitHub URL stays a source, not a social."""
    if get_meta(conn, "social_provider_names_v2") == "1":
        return
    from core.github_enrich import classify_provider

    rows = conn.execute(
        """
        SELECT id, socials FROM users
        WHERE socials IS NOT NULL AND TRIM(socials) NOT IN ('', '[]')
        """
    ).fetchall()
    for row in rows:
        original = load_social_links(row["socials"])
        if not original:
            continue
        renamed: list[dict[str, str]] = []
        changed = False
        for link in original:
            provider = classify_provider(link["provider"], link["url"])
            if provider == "github":
                changed = True
                continue
            status = link["status"] or "not_sent"
            if provider != link["provider"] or status != link["status"]:
                changed = True
            renamed.append({"provider": provider, "url": link["url"], "status": status})
        if changed:
            conn.execute(
                "UPDATE users SET socials = ? WHERE id = ?",
                (json.dumps(renamed, ensure_ascii=False), int(row["id"])),
            )
    set_meta(conn, "social_provider_names_v2", "1")


def ensure_drop_source_socials(conn: sqlite3.Connection) -> None:
    """A source profile is not also a social link."""
    if get_meta(conn, "social_source_links_v1") == "1":
        return
    from core.github_enrich import SOURCE_PROVIDERS, classify_provider

    rows = conn.execute(
        """
        SELECT id, socials, link, github FROM users
        WHERE socials IS NOT NULL AND TRIM(socials) NOT IN ('', '[]')
        """
    ).fetchall()
    for row in rows:
        original = load_social_links(row["socials"])
        if not original:
            continue
        source_keys = set()
        for raw in (row["link"],):
            key = social_url_key(raw or "")
            if key:
                source_keys.add(key)
        account = (row["github"] or "").strip()
        if account:
            source_keys.add(social_url_key(f"https://github.com/{account}"))
        kept: list[dict[str, str]] = []
        changed = False
        for link in original:
            provider = classify_provider(link["provider"], link["url"])
            if provider in SOURCE_PROVIDERS or social_url_key(link["url"]) in source_keys:
                changed = True
                continue
            status = link["status"] or "not_sent"
            if provider != link["provider"] or status != link["status"]:
                changed = True
            kept.append({"provider": provider, "url": link["url"], "status": status})
        if changed:
            conn.execute(
                "UPDATE users SET socials = ? WHERE id = ?",
                (json.dumps(kept, ensure_ascii=False), int(row["id"])),
            )
    set_meta(conn, "social_source_links_v1", "1")


def ensure_suppressed_locations(conn: sqlite3.Connection) -> None:
    """Locations that should hide a user, backfilled from people already suppressed."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS suppressed_locations (
            location TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """
    )
    rows = conn.execute(
        """
        SELECT location, country FROM users
        WHERE suppressed = 1 AND TRIM(location) != ''
        """
    ).fetchall()
    for row in rows:
        mark_suppressed_location(conn, row["location"], row["country"])


def ensure_outcome_column(conn: sqlite3.Connection) -> None:
    """Tracked-tab result. Existing rows start as Waiting."""
    if "outcome" in _user_columns(conn):
        return
    conn.execute(
        "ALTER TABLE users ADD COLUMN outcome TEXT NOT NULL DEFAULT 'Waiting'"
    )


def ensure_sender_email_column(conn: sqlite3.Connection) -> None:
    """Account that sent the mail. Older sent rows copy it from the queue."""
    if "sender_email" not in _user_columns(conn):
        conn.execute(
            "ALTER TABLE users ADD COLUMN sender_email TEXT NOT NULL DEFAULT ''"
        )
    conn.execute(
        """
        UPDATE users
        SET sender_email = (
            SELECT q.sender_email
            FROM queue_items q
            WHERE q.user_id = users.id
              AND q.status = 'sent'
              AND TRIM(COALESCE(q.sender_email, '')) != ''
            ORDER BY q.sent_at DESC, q.id DESC
            LIMIT 1
        )
        WHERE TRIM(COALESCE(sender_email, '')) = ''
          AND EXISTS (
            SELECT 1 FROM queue_items q
            WHERE q.user_id = users.id
              AND q.status = 'sent'
              AND TRIM(COALESCE(q.sender_email, '')) != ''
          )
        """
    )


def drop_unused_outcome_columns(conn: sqlite3.Connection) -> None:
    """opened and replied were replaced by outcome."""
    columns = _user_columns(conn)
    if "opened" in columns:
        conn.execute("ALTER TABLE users DROP COLUMN opened")
    if "replied" in columns:
        conn.execute("ALTER TABLE users DROP COLUMN replied")


def ensure_mail_template_column(conn: sqlite3.Connection) -> None:
    """Remember which template was used. Edited subject and body are not stored."""
    if "mail_template" in _user_columns(conn):
        return
    conn.execute(
        "ALTER TABLE users ADD COLUMN mail_template TEXT NOT NULL DEFAULT ''"
    )


def ensure_mail_templates(conn: sqlite3.Connection) -> None:
    """Copy a leftover templates/*.txt directory into SQLite once, if one exists.

    After that, the database is the copy that backup and reinstall restore.
    """
    if get_meta(conn, "mail_templates_seeded_v1") == "1":
        return
    count = conn.execute("SELECT COUNT(*) AS n FROM mail_templates").fetchone()["n"]
    if int(count or 0) == 0:
        from mail.send import TEMPLATES_DIR, list_templates

        now = utc_now()
        for item in list_templates(TEMPLATES_DIR):
            conn.execute(
                """
                INSERT INTO mail_templates (filename, region, subject, body, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item["filename"],
                    item["region"],
                    item["subject"],
                    item["body"],
                    now,
                ),
            )
    set_meta(conn, "mail_templates_seeded_v1", "1")
    ensure_mail_template_updated_at(conn)


def ensure_mail_template_updated_at(conn: sqlite3.Connection) -> None:
    """Templates with no saved edit time are dated today."""
    conn.execute(
        """
        UPDATE mail_templates
        SET updated_at = ?
        WHERE TRIM(COALESCE(updated_at, '')) = ''
        """,
        (utc_now(),),
    )


def list_mail_templates(conn: sqlite3.Connection) -> list[dict[str, str]]:
    ensure_mail_template_updated_at(conn)
    rows = conn.execute(
        """
        SELECT filename, region, subject, body, updated_at
        FROM mail_templates
        ORDER BY filename
        """
    ).fetchall()
    return [
        {
            "filename": row["filename"],
            "region": row["region"],
            "subject": row["subject"],
            "body": row["body"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def _template_parts(region: str, subject: str, body: str) -> tuple[str, str, str]:
    from mail.send import parse_template_text, serialize_template_text
    from mail.regions import canonical_template_region

    slug = canonical_template_region(region)
    parsed = parse_template_text(
        f"{slug} (1).txt",
        serialize_template_text(subject, body),
    )
    return slug, parsed["subject"], parsed["body"]


def create_mail_template(
    conn: sqlite3.Connection,
    region: str,
    subject: str,
    body: str,
) -> dict[str, str]:
    from mail.send import next_template_filename_for

    slug, subject_text, body_text = _template_parts(region, subject, body)
    names = [
        row["filename"]
        for row in conn.execute("SELECT filename FROM mail_templates").fetchall()
    ]
    filename = next_template_filename_for(slug, names)
    now = utc_now()
    conn.execute(
        """
        INSERT INTO mail_templates (filename, region, subject, body, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (filename, slug, subject_text, body_text, now),
    )
    return {
        "filename": filename,
        "region": slug,
        "subject": subject_text,
        "body": body_text,
        "updated_at": now,
    }


def update_mail_template(
    conn: sqlite3.Connection,
    filename: str,
    *,
    region: str,
    subject: str,
    body: str,
) -> dict[str, str]:
    from mail.send import next_template_filename_for, require_template_filename

    current_name = require_template_filename(filename)
    row = conn.execute(
        "SELECT filename, region FROM mail_templates WHERE filename = ?",
        (current_name,),
    ).fetchone()
    if row is None:
        raise FileNotFoundError(current_name)
    slug, subject_text, body_text = _template_parts(region, subject, body)
    now = utc_now()
    if slug == row["region"]:
        conn.execute(
            """
            UPDATE mail_templates
            SET subject = ?, body = ?, updated_at = ?
            WHERE filename = ?
            """,
            (subject_text, body_text, now, current_name),
        )
        return {
            "filename": current_name,
            "region": slug,
            "subject": subject_text,
            "body": body_text,
            "updated_at": now,
        }

    names = [
        item["filename"]
        for item in conn.execute("SELECT filename FROM mail_templates").fetchall()
    ]
    new_name = next_template_filename_for(slug, names)
    conn.execute(
        """
        INSERT INTO mail_templates (filename, region, subject, body, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (new_name, slug, subject_text, body_text, now),
    )
    conn.execute("DELETE FROM mail_templates WHERE filename = ?", (current_name,))
    conn.execute(
        "UPDATE users SET mail_template = ? WHERE mail_template = ?",
        (new_name, current_name),
    )
    conn.execute(
        "UPDATE queue_items SET template = ? WHERE template = ?",
        (new_name, current_name),
    )
    return {
        "filename": new_name,
        "region": slug,
        "subject": subject_text,
        "body": body_text,
        "updated_at": now,
    }


def delete_mail_template(conn: sqlite3.Connection, filename: str) -> None:
    from mail.send import require_template_filename

    current_name = require_template_filename(filename)
    row = conn.execute(
        "SELECT filename FROM mail_templates WHERE filename = ?",
        (current_name,),
    ).fetchone()
    if row is None:
        raise FileNotFoundError(current_name)
    remaining = conn.execute(
        "SELECT COUNT(*) AS n FROM mail_templates WHERE filename != ?",
        (current_name,),
    ).fetchone()["n"]
    if int(remaining or 0) == 0:
        raise ValueError("Cannot delete the last template")
    conn.execute("DELETE FROM mail_templates WHERE filename = ?", (current_name,))


def ensure_mail_sender_name(conn: sqlite3.Connection) -> None:
    """Each sender address keeps its own name for [Your Name].

    The first time this runs, a leftover SENDER_NAME fills addresses that
    do not have one yet. Later edits stay on the row.
    """
    columns = [r[1] for r in conn.execute("PRAGMA table_info(mail_accounts)").fetchall()]
    if "sender_name" not in columns:
        conn.execute(
            "ALTER TABLE mail_accounts ADD COLUMN sender_name TEXT NOT NULL DEFAULT ''"
        )
    if get_meta(conn, "sender_name_backfill_v1") == "1":
        return
    legacy = os.environ.get("SENDER_NAME", "").strip()
    if legacy:
        conn.execute(
            """
            UPDATE mail_accounts
            SET sender_name = ?
            WHERE TRIM(COALESCE(sender_name, '')) = ''
            """,
            (legacy,),
        )
    set_meta(conn, "sender_name_backfill_v1", "1")


def reset_mail_state_to_pending(conn: sqlite3.Connection) -> None:
    """One-time: every user is pending, and the old drip queue is cleared."""
    if get_meta(conn, "mail_pool_reset_v1") == "1":
        return
    now = utc_now()
    conn.execute(
        "UPDATE users SET mail_status = 'not_sent', updated_at = ?",
        (now,),
    )
    conn.execute("DELETE FROM queue_items")
    set_meta(conn, "mail_pool_reset_v1", "1")


@contextmanager
def get_conn(result_dir: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(result_dir)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_scraper_parameter(conn: sqlite3.Connection, platform_id: str) -> dict[str, Any]:
    """JSON object stored for one scraper. Missing or invalid rows are {}."""
    platform = (platform_id or "").strip()
    if not platform:
        return {}
    row = conn.execute(
        "SELECT parameter FROM scraper_parameter WHERE platform_id = ?",
        (platform,),
    ).fetchone()
    if row is None:
        return {}
    try:
        parsed = json.loads(row["parameter"] or "")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def set_scraper_parameter(
    conn: sqlite3.Connection,
    platform_id: str,
    parameter: dict[str, Any],
) -> dict[str, Any]:
    """Replace the JSON parameter document for one platform."""
    platform = (platform_id or "").strip()
    if not platform:
        raise ValueError("platform_id is required")
    if not isinstance(parameter, dict):
        raise ValueError("parameter must be a JSON object")
    payload = json.dumps(parameter, separators=(",", ":"), sort_keys=True)
    now = utc_now()
    conn.execute(
        """
        INSERT INTO scraper_parameter (platform_id, parameter, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(platform_id) DO UPDATE SET
            parameter = excluded.parameter,
            updated_at = excluded.updated_at
        """,
        (platform, payload, now),
    )
    return parameter


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def ensure_scraper_parameters(conn: sqlite3.Connection) -> None:
    """Fold the old scrape_state cursor into scraper_parameter, then drop that table."""
    if _table_exists(conn, "scrape_state"):
        if (
            conn.execute(
                "SELECT platform_id FROM scraper_parameter WHERE platform_id = 'devto'"
            ).fetchone()
            is None
        ):
            row = conn.execute(
                "SELECT last_id FROM scrape_state WHERE id = 1"
            ).fetchone()
            last_id = int(row["last_id"]) if row is not None else 0
            set_scraper_parameter(conn, "devto", {"last_id": last_id})
        conn.execute("DROP TABLE scrape_state")
        return
    if (
        conn.execute(
            "SELECT platform_id FROM scraper_parameter WHERE platform_id = 'devto'"
        ).fetchone()
        is None
    ):
        set_scraper_parameter(conn, "devto", {"last_id": 0})


def get_scrape_state(
    conn: sqlite3.Connection, platform_id: str = "devto"
) -> dict[str, int]:
    params = get_scraper_parameter(conn, platform_id)
    last_id = max(0, int(params["last_id"])) if "last_id" in params else 0
    total_saved = int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])
    return {"last_id": last_id, "total_saved": total_saved}


def set_scrape_state(
    conn: sqlite3.Connection,
    *,
    last_id: int | None = None,
    total_saved: int | None = None,
    platform_id: str = "devto",
) -> dict[str, int]:
    """Save last_id for one platform. total_saved is accepted and ignored; the count is users."""
    del total_saved
    if last_id is not None:
        params = get_scraper_parameter(conn, platform_id)
        params["last_id"] = max(0, int(last_id))
        set_scraper_parameter(conn, platform_id, params)
    return get_scrape_state(conn, platform_id)


def advance_last_id(
    conn: sqlite3.Connection, user_id: int, platform_id: str = "devto"
) -> int:
    state = get_scrape_state(conn, platform_id)
    new_last = max(state["last_id"], int(user_id))
    if new_last != state["last_id"]:
        set_scrape_state(conn, last_id=new_last, platform_id=platform_id)
    return new_last


def recount_total_saved(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])


def country_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT country, COUNT(*) AS n FROM users GROUP BY country ORDER BY n DESC"
    ).fetchall()
    return {str(r["country"]): int(r["n"]) for r in rows}


def country_stats(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Per-country totals and how many users already have mail_status=sent."""
    rows = conn.execute(
        """
        SELECT country,
               COUNT(*) AS n,
               SUM(CASE WHEN lower(mail_status) = 'sent' THEN 1 ELSE 0 END) AS sent
        FROM users
        WHERE suppressed = 0
        GROUP BY country
        ORDER BY n DESC, country ASC
        """
    ).fetchall()
    return [
        {
            "country": str(r["country"]),
            "count": int(r["n"]),
            "sent": int(r["sent"] or 0),
        }
        for r in rows
    ]


def delete_users_by_countries(
    conn: sqlite3.Connection,
    countries: set[str] | frozenset[str],
) -> int:
    """Delete users in the given country slugs (and their queue rows). Returns deleted user count."""
    slugs = sorted({(c or "").strip().lower() for c in countries if (c or "").strip()})
    if not slugs:
        return 0
    placeholders = ",".join("?" for _ in slugs)
    user_ids = [
        int(r["id"])
        for r in conn.execute(
            f"SELECT id FROM users WHERE lower(country) IN ({placeholders})",
            slugs,
        ).fetchall()
    ]
    if not user_ids:
        return 0
    id_placeholders = ",".join("?" for _ in user_ids)
    conn.execute(
        f"DELETE FROM queue_items WHERE user_id IN ({id_placeholders})",
        user_ids,
    )
    conn.execute(
        f"DELETE FROM users WHERE id IN ({id_placeholders})",
        user_ids,
    )
    recount_total_saved(conn)
    return len(user_ids)


_purged_exclude_slugs: frozenset[str] | None = None


def purge_excluded_users(conn: sqlite3.Connection) -> int:
    """Delete users whose country was added to exclude-regions.txt since last purge."""
    global _purged_exclude_slugs
    from core.locations import excluded_country_slugs

    slugs = excluded_country_slugs()
    extra = slugs if _purged_exclude_slugs is None else slugs - _purged_exclude_slugs
    deleted = delete_users_by_countries(conn, extra) if extra else 0
    _purged_exclude_slugs = slugs
    return deleted


def insert_user(
    conn: sqlite3.Connection,
    *,
    email: str,
    name: str,
    link: str,
    location: str,
    country: str,
    source: str = "devto",
    platform_user_id: int | str | None = None,
    github: str = "",
) -> tuple[bool, int | None]:
    """Insert user if email is new. Returns (inserted, user_id)."""
    email = (email or "").strip()
    if not email:
        return False, None
    now = utc_now()
    scraped_name = name or ""
    github_account = (github or "").strip()
    source_value = compose_source(source, github_account)
    platform_id = normalize_platform_user_id(platform_user_id)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO users (
            email, name, display_name, link, github, location, country, source,
            platform_user_id, mail_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_sent', ?, ?)
        """,
        (
            email,
            scraped_name,
            scraped_name,
            link or "",
            github_account,
            location or "",
            country,
            source_value,
            platform_id,
            now,
            now,
        ),
    )
    if cur.rowcount:
        return True, int(cur.lastrowid)

    row = conn.execute(
        "SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email,)
    ).fetchone()
    return False, int(row["id"]) if row else None


def update_github_profile(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    bio: str,
    github_name: str,
    socials: list[dict[str, str]] | None,
    github_location: str = "",
) -> None:
    """Store a fetched GitHub profile. Does not change updated_at.

    socials=None leaves the column NULL so a later pass can retry.
    The GitHub display name replaces users.name only when that name is empty
    or is still the Dev.to slug. A hand-edited display_name is left as-is.
    GitHub's location fills a noloc row when it names a country. A location
    that is already stored is left as-is.
    """
    row = conn.execute(
        "SELECT name, display_name, link, location, country, socials FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return
    from core.github_enrich import adopted_names, place_from_text

    name, display_name = adopted_names(
        row["name"],
        row["display_name"],
        row["link"],
        github_name,
    )
    location = row["location"] or ""
    country = (row["country"] or "").strip().lower() or "noloc"
    if country == "noloc":
        placed = place_from_text(github_location)
        if placed.country != "noloc" and not placed.skipped:
            location = placed.location
            country = placed.country
    bio_text = (bio or "").strip()
    if socials is None:
        conn.execute(
            """
            UPDATE users
            SET github_bio = ?, name = ?, display_name = ?, location = ?, country = ?
            WHERE id = ?
            """,
            (bio_text, name, display_name, location, country, int(user_id)),
        )
    else:
        conn.execute(
            """
            UPDATE users
            SET github_bio = ?, socials = ?, name = ?, display_name = ?,
                location = ?, country = ?
            WHERE id = ?
            """,
            (
                bio_text,
                json.dumps(
                    merge_social_link_status(socials, row["socials"]),
                    ensure_ascii=False,
                ),
                name,
                display_name,
                location,
                country,
                int(user_id),
            ),
        )
    conn.commit()


def suppressed_location_marks(conn: sqlite3.Connection) -> set[str]:
    """Formatted locations that hide whoever is moved onto them."""
    rows = conn.execute("SELECT location FROM suppressed_locations").fetchall()
    return {str(row["location"]).strip() for row in rows if str(row["location"]).strip()}


def mark_suppressed_location(
    conn: sqlite3.Connection,
    location: str | None,
    country: str | None = None,
) -> str:
    """Remember a place so a later edit to the same place suppresses that user."""
    from core.locations import format_place

    text = (location or "").strip()
    slug = (country or "").strip().lower()
    if text and slug and slug != "noloc":
        formatted = format_place(text, slug)
        if formatted:
            text = formatted
    if not text:
        return ""
    conn.execute(
        """
        INSERT OR IGNORE INTO suppressed_locations (location, created_at)
        VALUES (?, ?)
        """,
        (text, utc_now()),
    )
    return text


def suppress_user(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    """Hide a user from both pools. The row stays so the email cannot be inserted again.

    A non-empty location is marked, so editing someone else onto that place
    suppresses them too.
    """
    row = conn.execute(
        "SELECT id, location, country FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return None
    mark_suppressed_location(conn, row["location"], row["country"])
    conn.execute(
        "UPDATE users SET suppressed = 1, updated_at = ? WHERE id = ?",
        (utc_now(), int(user_id)),
    )
    updated = conn.execute(
        "SELECT id, email, suppressed FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    return row_to_dict(updated)


def distinct_locations(conn: sqlite3.Connection) -> list[dict[str, str]]:
    """Stored places, one row per location text and country."""
    rows = conn.execute(
        """
        SELECT location, country
        FROM users
        WHERE TRIM(location) != ''
        GROUP BY location, country
        """
    ).fetchall()
    return [
        {"location": str(row["location"]), "country": str(row["country"])}
        for row in rows
    ]


def delete_user(conn: sqlite3.Connection, user_id: int) -> bool:
    """Delete one user and their queue row. Returns whether a user row was removed."""
    uid = int(user_id)
    conn.execute("DELETE FROM queue_items WHERE user_id = ?", (uid,))
    cur = conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    if not cur.rowcount:
        return False
    recount_total_saved(conn)
    return True


def _public_user(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, email, name, display_name, link, github, github_bio, socials,
               location, country, source, mail_status, social_status, sender_email,
               mail_template, outcome, created_at, updated_at
        FROM users WHERE id = ?
        """,
        (int(user_id),),
    ).fetchone()
    return row_to_dict(row)


def apply_user_location(
    conn: sqlite3.Connection,
    user_id: int,
    location: str,
) -> dict[str, Any] | None:
    """Set a user's place from free text.

    An excluded country deletes the user. A location marked by a suppressed
    user updates the place and suppresses this user too. Unrecognized text
    raises UnknownLocation and leaves the row unchanged.
    """
    from core.locations import place_decision

    existing = conn.execute(
        "SELECT id FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    if existing is None:
        return None
    decision = place_decision(
        location,
        suppressed_locations=suppressed_location_marks(conn),
    )
    action = decision["action"]
    if action == "delete":
        delete_user(conn, user_id)
        return {
            "action": "delete",
            "user": None,
            "location": decision["location"],
            "country": decision["country"],
        }
    now = utc_now()
    conn.execute(
        """
        UPDATE users
        SET location = ?, country = ?, updated_at = ?
        WHERE id = ?
        """,
        (decision["location"], decision["country"], now, int(user_id)),
    )
    if action == "suppress":
        suppress_user(conn, user_id)
    return {
        "action": action,
        "user": _public_user(conn, user_id),
        "location": decision["location"],
        "country": decision["country"],
    }


DISPLAY_NAME_MAX_LEN = 200


def greeting_name(display_name: str | None, original_name: str | None = None) -> str:
    """Name used in mail templates: edited display_name, else scraped name."""
    text = (display_name or "").strip()
    if text:
        return text
    return (original_name or "").strip()


def update_user_display_name(
    conn: sqlite3.Connection,
    user_id: int,
    display_name: str,
) -> dict[str, Any] | None:
    """Set the greeting name. Empty value resets to the original scraped name.

    Sent users keep the name already written into the email.
    """
    row = conn.execute(
        "SELECT id, name, display_name, mail_status FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return None
    if (row["mail_status"] or "").lower() == "sent":
        raise ValueError("Display name is fixed after the email is sent")
    text = (display_name or "").strip()
    if len(text) > DISPLAY_NAME_MAX_LEN:
        text = text[:DISPLAY_NAME_MAX_LEN].rstrip()
    if not text:
        text = str(row["name"] or "")
    now = utc_now()
    conn.execute(
        "UPDATE users SET display_name = ?, updated_at = ? WHERE id = ?",
        (text, now, int(user_id)),
    )
    updated = conn.execute(
        """
        SELECT id, email, name, display_name, link, location, country, mail_status,
               created_at, updated_at
        FROM users WHERE id = ?
        """,
        (int(user_id),),
    ).fetchone()
    return row_to_dict(updated)


def update_user_outcome(
    conn: sqlite3.Connection,
    user_id: int,
    outcome: str,
) -> dict[str, Any] | None:
    """Set the tracked-tab result. Unknown values are rejected."""
    value = (outcome or "").strip()
    if value not in OUTCOMES:
        raise ValueError(f"outcome must be one of: {', '.join(OUTCOMES)}")
    row = conn.execute(
        "SELECT id FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return None
    now = utc_now()
    conn.execute(
        "UPDATE users SET outcome = ?, updated_at = ? WHERE id = ?",
        (value, now, int(user_id)),
    )
    updated = conn.execute(
        """
        SELECT id, email, name, display_name, link, location, country, source,
               mail_status, outcome, created_at, updated_at
        FROM users WHERE id = ?
        """,
        (int(user_id),),
    ).fetchone()
    return row_to_dict(updated)


def mail_template_name(value: str | None) -> str:
    """Keep a template filename. Reject paths and anything that is not a name."""
    name = (value or "").strip()
    if not name or name != Path(name).name or len(name) > 200:
        return ""
    return name


def set_user_contact(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    channel: str,
    status: str,
    sender_email: str | None = None,
    social_url: str | None = None,
    template: str | None = None,
) -> dict[str, Any] | None:
    """Record a manual email or one social link. Sent mail stores the sender."""
    kind = (channel or "").strip().lower()
    value = (status or "").strip().lower()
    if kind not in {"email", "social"}:
        raise ValueError("channel must be email or social")
    if value not in CONTACT_STATUSES:
        raise ValueError("status must be not_sent, sent, or failed")
    row = conn.execute(
        "SELECT id, sender_email, socials FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return None
    now = utc_now()
    if kind == "social":
        target = social_url_key(social_url or "")
        if not target:
            raise ValueError("Social link is required")
        links = load_social_links(row["socials"])
        found = False
        for link in links:
            if social_url_key(link["url"]) == target:
                link["status"] = value
                found = True
            elif not link["status"]:
                link["status"] = "not_sent"
        if not found:
            raise ValueError("Social link not found")
        conn.execute(
            "UPDATE users SET socials = ?, updated_at = ? WHERE id = ?",
            (json.dumps(links, ensure_ascii=False), now, int(user_id)),
        )
    else:
        sender = (sender_email or "").strip()
        if value == "sent" and not sender:
            raise ValueError("Sender is required")
        template_name = mail_template_name(template)
        if value == "sent":
            conn.execute(
                """
                UPDATE users
                SET mail_status = ?, sender_email = ?, mail_template = ?, updated_at = ?
                WHERE id = ?
                """,
                (value, sender, template_name, now, int(user_id)),
            )
        elif value == "failed" and template_name:
            conn.execute(
                """
                UPDATE users
                SET mail_status = ?, mail_template = ?, updated_at = ?
                WHERE id = ?
                """,
                (value, template_name, now, int(user_id)),
            )
        elif value == "not_sent":
            conn.execute(
                """
                UPDATE users
                SET mail_status = ?, mail_template = '', updated_at = ?
                WHERE id = ?
                """,
                (value, now, int(user_id)),
            )
        else:
            conn.execute(
                "UPDATE users SET mail_status = ?, updated_at = ? WHERE id = ?",
                (value, now, int(user_id)),
            )
    return _public_user(conn, user_id)


def upsert_user_last_wins(
    conn: sqlite3.Connection,
    *,
    email: str,
    name: str,
    link: str,
    location: str,
    country: str,
    source: str = "devto",
    platform_user_id: int | str | None = None,
    github: str = "",
) -> None:
    """Migration helper: insert or overwrite contact fields (keep mail_status)."""
    email = (email or "").strip()
    if not email:
        return
    now = utc_now()
    scraped_name = name or ""
    github_account = (github or "").strip()
    source_value = compose_source(source, github_account)
    platform_id = normalize_platform_user_id(platform_user_id)
    existing = conn.execute(
        "SELECT id FROM users WHERE email = ? COLLATE NOCASE",
        (email,),
    ).fetchone()
    if existing is None:
        conn.execute(
            """
            INSERT INTO users (
                email, name, display_name, link, github, location, country, source,
                platform_user_id, mail_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_sent', ?, ?)
            """,
            (
                email,
                scraped_name,
                scraped_name,
                link or "",
                github_account,
                location or "",
                country,
                source_value,
                platform_id,
                now,
                now,
            ),
        )
    else:
        current = conn.execute(
            "SELECT source, github FROM users WHERE id = ?",
            (int(existing["id"]),),
        ).fetchone()
        source_value = compose_source(
            f"{current['source']},{source}",
            github_account or current["github"] or "",
        )
        conn.execute(
            """
            UPDATE users SET
                name = ?, link = ?, location = ?, country = ?, source = ?,
                platform_user_id = COALESCE(?, platform_user_id),
                github = CASE WHEN ? != '' THEN ? ELSE github END,
                updated_at = ?
            WHERE id = ?
            """,
            (
                name or "",
                link or "",
                location or "",
                country,
                source_value,
                platform_id,
                github_account,
                github_account,
                now,
                int(existing["id"]),
            ),
        )


def get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute(
        "SELECT value FROM app_meta WHERE key = ?", (key,)
    ).fetchone()
    return str(row["value"]) if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def is_scrape_paused(conn: sqlite3.Connection) -> bool:
    return get_meta(conn, "scrape_paused", "0") in ("1", "true", "True", "yes")


def set_scrape_paused(conn: sqlite3.Connection, paused: bool) -> None:
    set_meta(conn, "scrape_paused", "1" if paused else "0")


DEFAULT_SCRAPE_DAILY_CAP = 50


def scrape_cap_enabled(conn: sqlite3.Connection) -> bool:
    """False means scrape with no daily limit. Missing flag stays on."""
    raw = get_meta(conn, "scrape_cap_enabled", "").strip().lower()
    return raw not in {"0", "false", "no"}


def get_scrape_daily_cap(conn: sqlite3.Connection) -> int:
    """Static located-save cap. Mail account caps are not part of this."""
    raw = get_meta(conn, "scrape_daily_cap", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SCRAPE_DAILY_CAP
    if value <= 0:
        return DEFAULT_SCRAPE_DAILY_CAP
    return value


def set_scrape_cap(conn: sqlite3.Connection, *, enabled: bool, cap: int) -> None:
    set_meta(conn, "scrape_cap_enabled", "1" if enabled else "0")
    set_meta(conn, "scrape_daily_cap", str(max(1, int(cap))))


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TOKYO_TZ)
    return parsed


def touch_scrape_heartbeat(
    conn: sqlite3.Connection,
    *,
    loop: str = SCRAPE_LOOP_RUNNING,
) -> None:
    status = (
        loop
        if loop in (SCRAPE_LOOP_RUNNING, SCRAPE_LOOP_IDLING)
        else SCRAPE_LOOP_RUNNING
    )
    set_meta(conn, "scrape_heartbeat_at", tokyo_now())
    set_meta(conn, "scrape_loop", status)


def scrape_heartbeat_age_sec(
    conn: sqlite3.Connection, *, now: datetime | None = None
) -> float | None:
    parsed = _parse_iso_datetime(get_meta(conn, "scrape_heartbeat_at", ""))
    if parsed is None:
        return None
    if now is None:
        now = current_tokyo_datetime()
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TOKYO_TZ)
    else:
        now = now.astimezone(TOKYO_TZ)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TOKYO_TZ)
    else:
        parsed = parsed.astimezone(TOKYO_TZ)
    return max(0.0, (now - parsed).total_seconds())


def scrape_process_alive(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    stale_after_sec: float = SCRAPE_HEARTBEAT_STALE_SEC,
) -> bool:
    age = scrape_heartbeat_age_sec(conn, now=now)
    return age is not None and age <= float(stale_after_sec)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def _created_on_tokyo_day(created_at: str | None, day_prefix: str) -> bool:
    if not created_at:
        return False
    try:
        parsed = datetime.fromisoformat(created_at)
    except ValueError:
        parsed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TOKYO_TZ)
    else:
        parsed = parsed.astimezone(TOKYO_TZ)
    return parsed.strftime("%Y-%m-%d") == day_prefix


def count_users_saved_today(conn: sqlite3.Connection, day_prefix: str) -> int:
    """Count located users saved on Tokyo day day_prefix (excludes noloc)."""
    rows = conn.execute("SELECT created_at, country FROM users").fetchall()
    return sum(
        1
        for row in rows
        if (row["country"] or "").strip().lower() != "noloc"
        and _created_on_tokyo_day(row["created_at"], day_prefix)
    )


def ensure_static_scrape_cap(conn: sqlite3.Connection) -> None:
    """Keep a stored number. A previous mail-ratio cap is copied once, then left alone."""
    if get_meta(conn, "scrape_cap_static_v1") == "1":
        return
    raw = get_meta(conn, "scrape_daily_cap", "").strip()
    try:
        existing = int(raw)
    except ValueError:
        existing = 0
    if existing <= 0:
        set_meta(conn, "scrape_daily_cap", str(_legacy_mail_ratio_cap(conn)))
    if get_meta(conn, "scrape_cap_enabled", "").strip() == "":
        set_meta(conn, "scrape_cap_enabled", "1")
    set_meta(conn, "scrape_cap_static_v1", "1")


def _legacy_mail_ratio_cap(conn: sqlite3.Connection) -> int:
    """One-time copy of the old 1.5× mail-cap budget."""
    raw = os.environ.get("SCRAPE_MAIL_CAP_RATIO", "1.5").strip()
    try:
        ratio = float(raw)
    except ValueError:
        ratio = 1.5
    ratio = max(0.1, ratio)
    fallback = os.environ.get("MAIL_DAILY_LIMIT", "20").strip()
    try:
        fallback_cap = max(1, int(fallback))
    except ValueError:
        fallback_cap = 20
    cap = get_active_daily_cap_sum(conn)
    if cap <= 0:
        cap = fallback_cap
    return max(1, int(cap * ratio))


def scrape_daily_save_limit(conn: sqlite3.Connection) -> int | None:
    """Max located saves per Tokyo day. None means no daily cap."""
    if not scrape_cap_enabled(conn):
        return None
    return get_scrape_daily_cap(conn)


def scrape_control_snapshot(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    stale_after_sec: float = SCRAPE_HEARTBEAT_STALE_SEC,
) -> dict[str, Any]:
    """Status + caps for the dashboard scraper page."""
    if now is None:
        now = current_tokyo_datetime()
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TOKYO_TZ)
    else:
        now = now.astimezone(TOKYO_TZ)

    state = get_scrape_state(conn)
    day = local_day_prefix(now)
    saved_today = count_users_saved_today(conn, day)
    enabled = scrape_cap_enabled(conn)
    cap = get_scrape_daily_cap(conn)
    daily_limit = cap if enabled else None
    paused = is_scrape_paused(conn)
    alive = scrape_process_alive(
        conn, now=now, stale_after_sec=stale_after_sec
    )
    loop = get_meta(conn, "scrape_loop", SCRAPE_LOOP_RUNNING)
    heartbeat_at = get_meta(conn, "scrape_heartbeat_at", "")
    heartbeat_age = scrape_heartbeat_age_sec(conn, now=now)
    at_cap = daily_limit is not None and saved_today >= daily_limit

    if not alive:
        status = "stopped"
    elif paused:
        status = "paused"
    elif at_cap or (enabled and loop == SCRAPE_LOOP_IDLING):
        status = "idling"
    else:
        status = "running"

    return {
        "status": status,
        "alive": alive,
        "paused": paused,
        "last_id": state["last_id"],
        "total_users": state["total_saved"],
        "saved_today": saved_today,
        "daily_limit": daily_limit,
        "daily_cap": cap,
        "cap_enabled": enabled,
        "day": day,
        "seconds_until_midnight": seconds_until_next_tokyo_midnight(now),
        "heartbeat_at": heartbeat_at or None,
        "heartbeat_age_sec": heartbeat_age,
    }


def seconds_until_next_tokyo_midnight(now: datetime | None = None) -> float:
    if now is None:
        now = current_tokyo_datetime()
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TOKYO_TZ)
    else:
        now = now.astimezone(TOKYO_TZ)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1.0, (tomorrow - now).total_seconds())


def computed_mail_cap(
    created_at: str,
    *,
    now: datetime | None = None,
) -> int:
    """Daily cap from Tokyo calendar age of the account (not rolling 24h).
    The create calendar day *and* the following Tokyo day stay at 10, so an
    account added on Aug 10 keeps cap 10 through Aug 11 and becomes 20 at
    midnight Aug 11→12:

      days 0–1: 10
      days 2–3: 20
      days 4–7: 30
      days 8–14: 40
      days 15–30: 50
      day 31+: 100
    """
    try:
        then = datetime.fromisoformat(created_at)
    except ValueError:
        then = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if then.tzinfo is None:
        then = then.replace(tzinfo=TOKYO_TZ)
    else:
        then = then.astimezone(TOKYO_TZ)

    if now is None:
        now = current_tokyo_datetime()
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TOKYO_TZ)
    else:
        now = now.astimezone(TOKYO_TZ)

    days = (now.date() - then.date()).days
    if days < 0:
        days = 0
    if days < 2:
        return 10
    if days < 4:
        return 20
    if days < 8:
        return 30
    if days < 15:
        return 40
    if days < 31:
        return 50
    return 100


def get_mail_accounts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, email, active, sender_name, created_at, updated_at FROM mail_accounts "
        "ORDER BY created_at ASC, id ASC"
    ).fetchall()
    accounts = []
    for row in rows:
        acct = row_to_dict(row)
        acct["daily_cap"] = computed_mail_cap(str(row["created_at"]))
        accounts.append(acct)
    return accounts


def get_active_daily_cap_sum(
    conn: sqlite3.Connection, *, now: datetime | None = None
) -> int:
    rows = conn.execute(
        "SELECT created_at FROM mail_accounts WHERE active = 1"
    ).fetchall()
    return sum(computed_mail_cap(str(row["created_at"]), now=now) for row in rows)


def upsert_mail_account(
    conn: sqlite3.Connection,
    *,
    email: str,
    app_password: str,
    sender_name: str,
    active: bool = True,
    daily_cap: int = 20,
) -> dict[str, Any]:
    email = (email or '').strip().lower()
    sender_name = (sender_name or '').strip()
    daily_cap = max(1, int(daily_cap))
    if not email:
        raise ValueError('email is required')
    if not sender_name:
        raise ValueError('sender name is required')

    now = utc_now()
    if not app_password:
        app_password = ''

    conn.execute(
        """
        INSERT INTO mail_accounts (
            email, app_password, active, daily_cap, sender_name, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            app_password = excluded.app_password,
            active = excluded.active,
            daily_cap = excluded.daily_cap,
            sender_name = excluded.sender_name,
            updated_at = excluded.updated_at
        """,
        (email, app_password, 1 if active else 0, daily_cap, sender_name, now, now),
    )
    row = conn.execute(
        "SELECT id, email, active, sender_name, daily_cap, created_at, updated_at FROM mail_accounts WHERE email = ?",
        (email,),
    ).fetchone()
    return row_to_dict(row) if row else {}


def mail_sender_name(conn: sqlite3.Connection, email: str) -> str:
    account = get_mail_account_by_email(conn, email)
    if not account:
        return ""
    return str(account.get("sender_name") or "").strip()


def get_mail_account_by_email(conn: sqlite3.Connection, email: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, email, app_password, active, daily_cap, sender_name, created_at, updated_at
        FROM mail_accounts WHERE email = ?
        """,
        ((email or '').strip().lower(),),
    ).fetchone()
    return row_to_dict(row) if row else None


def delete_mail_account(conn: sqlite3.Connection, email: str) -> bool:
    normalized = (email or '').strip().lower()
    result = conn.execute(
        "DELETE FROM mail_accounts WHERE email = ?",
        (normalized,),
    )
    return result.rowcount > 0


def count_sent_by_sender_total(conn: sqlite3.Connection) -> dict[str, int]:
    """Mails marked sent, grouped by the sender stored on the user."""
    rows = conn.execute(
        """
        SELECT LOWER(TRIM(sender_email)) AS sender_email, COUNT(*) AS n
        FROM users
        WHERE mail_status = 'sent' AND TRIM(COALESCE(sender_email, '')) != ''
        GROUP BY LOWER(TRIM(sender_email))
        """
    ).fetchall()
    return {str(r['sender_email']): int(r['n']) for r in rows}
