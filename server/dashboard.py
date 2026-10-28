"""
Local mail dashboard: browse users and render mail templates.

Build the React UI, then run one server (API + static):

  cd frontend && npm run build
  uvicorn server.dashboard:app
  http://127.0.0.1:8007
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

import core.db as app_db
from core.locations import (
    UnknownLocation,
    add_excluded_country,
    excluded_country_slugs,
    is_skipped_country,
    suggest_places,
)
from core.github_enrich import (
    format_expiration_label,
    github_token_accepted,
    inspect_github_token,
    mask_token,
    token_expires_soon,
)
from mail.send import (
    TEMPLATES_DIR,
    create_template,
    delete_template,
    list_templates,
    load_template_pool,
    pick_message,
    templates_dir_mtime,
    update_template,
)
from mail.regions import decorate_template, suggestion_catalog

RESULT_DIR = Path(os.environ.get("RESULT_DIR", str(app_db.PROJECT_ROOT)))
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", "frontend/dist"))


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'").strip('"')


load_dotenv()


def daily_limit() -> int:
    return max(1, int(os.environ.get("MAIL_DAILY_LIMIT", "20")))


def local_day_prefix() -> str:
    return app_db.local_day_prefix()


def _overview(conn) -> dict[str, Any]:
    row = conn.execute(
        "SELECT COUNT(*) AS n, MAX(id) AS last_id FROM users"
    ).fetchone()
    return {
        "last_id": int(row["last_id"] or 0),
        "total_users": int(row["n"]),
        "day": local_day_prefix(),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_db.init_db(RESULT_DIR)
    with app_db.get_conn(RESULT_DIR) as conn:
        purged = app_db.purge_excluded_users(conn)
    if purged:
        print(f"[dashboard] purged {purged} user(s) from exclude-regions.txt")
    print(f"[dashboard] DB={app_db.db_path(RESULT_DIR).resolve()}")
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        print(f"[dashboard] UI={index.resolve()}")
    else:
        print(
            f"[dashboard] UI missing at {index.resolve()} — "
            "run: cd frontend && npm run build"
        )
    yield


app = FastAPI(title="Dev.to Mail Dashboard", lifespan=lifespan)


class PauseBody(BaseModel):
    paused: bool


class ScrapeCapBody(BaseModel):
    cap_mode: Literal["auto", "manual"] = "auto"
    daily_cap: int | None = Field(default=None, ge=1)


class MailAccountBody(BaseModel):
    email: EmailStr
    sender_name: str = Field(..., min_length=1, max_length=120)
    app_password: str | None = None
    active: bool = True


class MailAccountUpdateBody(BaseModel):
    sender_name: str = Field(..., min_length=1, max_length=120)
    app_password: str | None = None
    active: bool | None = None


class GithubTokenBody(BaseModel):
    token: str = Field(..., min_length=1, max_length=500)


class UserPatchBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=app_db.DISPLAY_NAME_MAX_LEN)
    outcome: Literal["Waiting", "Replied", "Rejected"] | None = None
    location: str | None = Field(default=None, max_length=300)


class ContactBody(BaseModel):
    channel: Literal["email", "social"]
    status: Literal["not_sent", "sent", "failed"]
    sender_email: str | None = None
    url: str | None = None
    template: str | None = Field(default=None, max_length=200)


class TemplateBody(BaseModel):
    region: str = Field(..., min_length=1, max_length=40)
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=20000)


@app.post("/api/mail-accounts")
def api_mail_account_add(body: MailAccountBody) -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        account = app_db.upsert_mail_account(
            conn,
            email=body.email,
            app_password="",
            sender_name=_require_sender_name(body.sender_name),
            active=True,
        )
    return {"ok": True, "account": account}


@app.put("/api/mail-accounts/{email}")
def api_mail_account_update(email: str, body: MailAccountUpdateBody) -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        existing = app_db.get_mail_account_by_email(conn, email)
        if existing is None:
            raise HTTPException(404, "Mail account not found")
        account = app_db.upsert_mail_account(
            conn,
            email=email,
            app_password="",
            sender_name=_require_sender_name(body.sender_name),
            active=True,
        )
    return {"ok": True, "account": account}


@app.delete("/api/mail-accounts/{email}")
def api_mail_account_delete(email: str) -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        deleted = app_db.delete_mail_account(conn, email)
        if not deleted:
            raise HTTPException(404, "Mail account not found")
    return {"ok": True, "deleted": email}


@app.get("/")
def home() -> FileResponse:
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise HTTPException(
            503,
            "Frontend build missing. Run: cd frontend && npm run build",
        )
    return FileResponse(index)


@app.get("/api/overview")
def api_overview() -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        return _overview(conn)


@app.get("/api/countries")
def api_countries() -> list[dict[str, Any]]:
    with app_db.get_conn(RESULT_DIR) as conn:
        return [
            row
            for row in app_db.country_stats(conn)
            if not is_skipped_country(row.get("country"))
        ]


@app.post("/api/countries/{country}/exclude")
def api_country_exclude(country: str) -> dict[str, Any]:
    try:
        slug = add_excluded_country(country)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with app_db.get_conn(RESULT_DIR) as conn:
        deleted = app_db.delete_users_by_countries(conn, {slug})
        app_db._purged_exclude_slugs = excluded_country_slugs()
    return {"ok": True, "country": slug, "deleted": deleted}


def _with_socials(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if user is None:
        return None
    raw = user.get("socials")
    links: list[dict[str, str]] = []
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                links.append({
                    "provider": str(item.get("provider") or "generic").strip().lower() or "generic",
                    "url": url,
                    "status": app_db.contact_status(str(item.get("status") or "")),
                })
    user["socials"] = links
    return user


# Presence filters on users.socials JSON. Checked values are AND-ed.
SOCIAL_ACCOUNT_FILTERS = ("linkedin", "telegram", "discord", "whatsapp")

_HAS_SOCIAL_SQL = (
    "EXISTS ("
    "SELECT 1 FROM json_each("
    "CASE WHEN json_valid(socials) THEN socials ELSE '[]' END"
    ") WHERE lower(coalesce(json_extract(value, '$.provider'), '')) = ?"
    ")"
)


def social_account_clauses(has_social: list[str] | None) -> tuple[list[str], list[Any]]:
    """SQL fragments requiring each requested social provider to be present."""
    wanted: list[str] = []
    seen: set[str] = set()
    for item in has_social or []:
        name = str(item or "").strip().lower()
        if name not in SOCIAL_ACCOUNT_FILTERS or name in seen:
            continue
        seen.add(name)
        wanted.append(name)
    return [_HAS_SOCIAL_SQL] * len(wanted), wanted


@app.get("/api/users")
def api_users(
    country: str | None = None,
    pool: str | None = None,
    status: str | None = None,
    q: str | None = None,
    has_social: list[str] = Query(default=[]),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    where: list[str] = []
    params: list[Any] = []
    country_slug = (country or "").strip().lower()
    query_text = (q or "").strip()
    if country_slug and is_skipped_country(country_slug):
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "users": [],
        }
    if country_slug:
        where.append("country = ?")
        params.append(country_slug)
    elif len(query_text) < 2:
        # Global lookup is search-only so we do not dump the whole users table.
        return {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "users": [],
        }
    else:
        skipped = sorted(excluded_country_slugs())
        if skipped:
            where.append(
                "lower(country) NOT IN (" + ",".join("?" for _ in skipped) + ")"
            )
            params.extend(skipped)
    where.append("suppressed = 0")
    if status:
        where.append("mail_status = ?")
        params.append(status.strip().lower())
    if query_text:
        where.append(
            "(LOWER(name) LIKE ? OR LOWER(display_name) LIKE ? "
            "OR email LIKE ? COLLATE NOCASE "
            "OR LOWER(link) LIKE ? OR LOWER(github) LIKE ? OR LOWER(location) LIKE ?)"
        )
        like = f"%{query_text.lower()}%"
        params.extend([like, like, like, like, like, like])
    social_where, social_params = social_account_clauses(has_social)
    where.extend(social_where)
    params.extend(social_params)

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    offset = (page - 1) * page_size

    with app_db.get_conn(RESULT_DIR) as conn:
        total = int(
            conn.execute(
                f"SELECT COUNT(*) AS n FROM users{clause}", params
            ).fetchone()["n"]
        )
        rows = conn.execute(
            f"""
            SELECT u.id, u.email, u.name, u.display_name, u.link, u.github, u.github_bio,
                   u.socials, u.location,
                   u.country, u.source, u.mail_status, u.social_status, u.outcome,
                   u.created_at, u.updated_at,
                   u.sender_email, u.mail_template
            FROM users u
            {clause}
            ORDER BY u.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
        users = [_with_socials(app_db.row_to_dict(r)) for r in rows]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "users": users,
    }


@app.get("/api/locations/suggest")
def api_location_suggest(
    q: str = "",
    limit: int = Query(12, ge=1, le=20),
) -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        stored = app_db.distinct_locations(conn)
        marks = app_db.suppressed_location_marks(conn)
    return {
        "suggestions": suggest_places(
            q,
            suppressed_locations=marks,
            stored=stored,
            limit=limit,
        )
    }


def _sender_display_name(sender: str, stored_name: str = "") -> str:
    name = (stored_name or "").strip()
    if name:
        return name
    local = (sender or "").split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
    return " ".join(part.capitalize() for part in local.split())


def _require_sender_name(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise HTTPException(400, "Sender name is required.")
    return name


@app.get("/api/users/{user_id}/mail-preview")
def api_mail_preview(
    user_id: int,
    sender: str = "",
    template: str = "",
) -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        row = conn.execute(
            "SELECT id, name, display_name, link, country FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        accounts = app_db.get_mail_accounts(conn)
        senders = [item["email"] for item in accounts]
        chosen = (sender or "").strip() or (senders[0] if senders else "")
        stored_name = ""
        for item in accounts:
            if item["email"] == chosen:
                stored_name = str(item.get("sender_name") or "")
                break
    if row is None:
        raise HTTPException(404, "User not found")
    try:
        pool = load_template_pool(TEMPLATES_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    filename, subject, body = pick_message(
        pool,
        row["country"] or "",
        app_db.greeting_name(row["display_name"], row["name"]),
        _sender_display_name(chosen, stored_name),
        row["link"] or "",
        filename=template,
    )
    return {
        "filename": filename,
        "subject": subject,
        "body": body,
        "sender": chosen,
        "senders": senders,
        "templates": [
            {
                "filename": item["filename"],
                "region": item.get("region") or "",
                "subject": item.get("subject") or "",
                "body": item.get("body") or "",
            }
            for item in pool
        ],
    }


@app.post("/api/users/{user_id}/contact")
def api_user_contact(user_id: int, body: ContactBody) -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        try:
            user = app_db.set_user_contact(
                conn,
                user_id,
                channel=body.channel,
                status=body.status,
                sender_email=body.sender_email,
                social_url=body.url,
                template=body.template,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if user is None:
            raise HTTPException(404, "User not found")
    return {"ok": True, "user": _with_socials(user)}


@app.patch("/api/users/{user_id}")
def api_user_patch(user_id: int, body: UserPatchBody) -> dict[str, Any]:
    fields = body.model_fields_set
    if not fields:
        raise HTTPException(400, "No changes")
    with app_db.get_conn(RESULT_DIR) as conn:
        user = None
        if "location" in fields:
            try:
                result = app_db.apply_user_location(conn, user_id, body.location or "")
            except UnknownLocation as exc:
                raise HTTPException(400, str(exc)) from exc
            if result is None:
                raise HTTPException(404, "User not found")
            return {
                "ok": True,
                "action": result["action"],
                "user": _with_socials(result["user"]),
                "location": result["location"],
                "country": result["country"],
            }
        if "display_name" in fields:
            try:
                user = app_db.update_user_display_name(conn, user_id, body.display_name or "")
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            if user is None:
                raise HTTPException(404, "User not found")
        if "outcome" in fields:
            try:
                user = app_db.update_user_outcome(conn, user_id, body.outcome or "")
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            if user is None:
                raise HTTPException(404, "User not found")
    return {"ok": True, "user": user}


@app.post("/api/users/{user_id}/suppress")
def api_user_suppress(user_id: int) -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        user = app_db.suppress_user(conn, user_id)
        if user is None:
            raise HTTPException(404, "User not found")
    return {"ok": True}


def _scraper_payload(conn) -> dict[str, Any]:
    return app_db.scrape_control_snapshot(
        conn,
        ratio=app_db.scrape_mail_cap_ratio(),
        fallback_mail_cap=daily_limit(),
    )


@app.get("/api/scraper")
def api_scraper() -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        return _scraper_payload(conn)


@app.post("/api/scraper/pause")
def api_scraper_pause(body: PauseBody) -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        app_db.set_scrape_paused(conn, body.paused)
        return {"ok": True, "scraper": _scraper_payload(conn)}


@app.put("/api/scraper/cap")
def api_scraper_cap(body: ScrapeCapBody) -> dict[str, Any]:
    if body.cap_mode == "manual" and body.daily_cap is None:
        raise HTTPException(400, "daily_cap is required when cap_mode is manual")
    with app_db.get_conn(RESULT_DIR) as conn:
        if body.cap_mode == "auto":
            app_db.set_scrape_daily_cap_override(conn, None)
        else:
            app_db.set_scrape_daily_cap_override(conn, int(body.daily_cap))
        return {"ok": True, "scraper": _scraper_payload(conn)}


GITHUB_TOKEN_CHECK_TTL = timedelta(minutes=10)


def _require_github_token(value: str) -> str:
    token = (value or "").strip()
    if (
        len(token) < 20
        or any(ch.isspace() for ch in token)
        or "…" in token
        or "..." in token
    ):
        raise HTTPException(400, "Paste the GitHub token itself.")
    return token


def _store_github_check(conn, result: dict[str, str]) -> None:
    app_db.set_meta(conn, "github_token_status", result["status"])
    app_db.set_meta(
        conn,
        "github_token_checked_at",
        datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
    if result["status"] != "unreachable":
        app_db.set_meta(conn, "github_token_expires_at", result.get("expires_at") or "")


def _refresh_github_token(conn, token: str) -> None:
    _store_github_check(conn, inspect_github_token(token))


def _reject_github_token(status: str, *, had_token: bool) -> str:
    if had_token:
        kept = " The current token was kept."
    else:
        kept = " It was not saved."
    if status == "expired":
        reason = "That token is already expired."
    elif status == "invalid":
        reason = "GitHub rejected that token."
    elif status == "unreachable":
        reason = "GitHub could not be reached."
    else:
        reason = "That token cannot be used."
    return reason + kept


def _github_token_view(conn, *, refresh: bool = False) -> dict[str, Any]:
    token = app_db.get_meta(conn, "github_token", "").strip()
    if not token:
        return {
            "configured": False,
            "masked": "",
            "status": "missing",
            "expires_at": "",
            "expires_label": "",
            "expired": False,
            "checked_at": "",
        }
    checked_raw = app_db.get_meta(conn, "github_token_checked_at", "")
    stale = True
    if checked_raw and not refresh:
        try:
            checked = datetime.fromisoformat(checked_raw)
        except ValueError:
            checked = None
        if checked is not None:
            if checked.tzinfo is None:
                checked = checked.replace(tzinfo=timezone.utc)
            stale = datetime.now(timezone.utc) - checked > GITHUB_TOKEN_CHECK_TTL
    if stale:
        _refresh_github_token(conn, token)
    status = app_db.get_meta(conn, "github_token_status", "") or "unreachable"
    expires_at = app_db.get_meta(conn, "github_token_expires_at", "")
    return {
        "configured": True,
        "masked": mask_token(token),
        "status": status,
        "expires_at": expires_at,
        "expires_label": format_expiration_label(expires_at),
        "expired": status == "expired",
        "expires_soon": status == "ok" and token_expires_soon(expires_at),
        "checked_at": app_db.get_meta(conn, "github_token_checked_at", ""),
    }


@app.get("/api/github-token")
def api_github_token() -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        return _github_token_view(conn)


@app.post("/api/github-token")
def api_github_token_save(body: GithubTokenBody) -> dict[str, Any]:
    token = _require_github_token(body.token)
    result = inspect_github_token(token)
    if not github_token_accepted(result["status"]):
        with app_db.get_conn(RESULT_DIR) as conn:
            had_token = bool(app_db.get_meta(conn, "github_token", "").strip())
        raise HTTPException(400, _reject_github_token(result["status"], had_token=had_token))
    with app_db.get_conn(RESULT_DIR) as conn:
        app_db.set_meta(conn, "github_token", token)
        _store_github_check(conn, result)
        return _github_token_view(conn)


@app.post("/api/github-token/check")
def api_github_token_check() -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        if not app_db.get_meta(conn, "github_token", "").strip():
            raise HTTPException(400, "No GitHub token is saved.")
        return _github_token_view(conn, refresh=True)


@app.delete("/api/github-token")
def api_github_token_delete() -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        for key in (
            "github_token",
            "github_token_status",
            "github_token_expires_at",
            "github_token_checked_at",
        ):
            conn.execute("DELETE FROM app_meta WHERE key = ?", (key,))
        return _github_token_view(conn)


@app.get("/api/mail-accounts")
def api_mail_accounts() -> dict[str, Any]:
    with app_db.get_conn(RESULT_DIR) as conn:
        accounts = app_db.get_mail_accounts(conn)
        sent_by_sender_total = app_db.count_sent_by_sender_total(conn)
        for account in accounts:
            email = str(account.get("email") or "")
            account["active"] = bool(account.get("active"))
            account["sent_total"] = sent_by_sender_total.get(email.strip().lower(), 0)
    return {"accounts": accounts}


def _template_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(404, "Template not found")
    return HTTPException(400, str(exc))


@app.get("/api/template-regions")
def api_template_regions() -> dict[str, Any]:
    templates = list_templates(TEMPLATES_DIR)
    with app_db.get_conn(RESULT_DIR) as conn:
        user_counts = app_db.country_counts(conn)
    return suggestion_catalog(user_counts=user_counts, templates=templates)


@app.get("/api/templates")
def api_templates() -> dict[str, Any]:
    return {
        "templates": [
            decorate_template(item) for item in list_templates(TEMPLATES_DIR)
        ]
    }


@app.post("/api/templates")
def api_template_create(body: TemplateBody) -> dict[str, Any]:
    try:
        item = create_template(body.region, body.subject, body.body, TEMPLATES_DIR)
    except (ValueError, OSError) as exc:
        raise _template_http_error(exc) from exc
    return {"ok": True, "template": decorate_template(item)}


@app.put("/api/templates/{filename}")
def api_template_update(filename: str, body: TemplateBody) -> dict[str, Any]:
    try:
        item = update_template(
            filename,
            region=body.region,
            subject=body.subject,
            body=body.body,
            templates_dir=TEMPLATES_DIR,
        )
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise _template_http_error(exc) from exc
    return {"ok": True, "template": decorate_template(item)}


@app.delete("/api/templates/{filename}")
def api_template_delete(filename: str) -> dict[str, Any]:
    try:
        delete_template(filename, TEMPLATES_DIR)
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise _template_http_error(exc) from exc
    return {"ok": True, "deleted": filename}


_assets_dir = FRONTEND_DIST / "assets"
if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="frontend-assets")
