"""
Scrape dev.to users by numeric ID; store contacts in app.db at the repo root (SQLite).

Resume from scraper_parameter for this platform (Dev.to key: last_id).
When today's *located* saves (country != noloc) hit 1.5× the active mail
daily-cap sum, the scraper idles until the next Tokyo midnight — it does not
exit (dashboard keeps sending). noloc saves do not count toward the cap.
"""

from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path

import requests

import core.db as app_db
from core.github_enrich import (
    build_social_links,
    fetch_json,
    github_token,
    place_from_text,
    profile_bio,
    profile_location,
    profile_name,
    social_accounts_path,
)
from core.locations import detect_country, format_place, is_skipped_country

SOURCE = "devto"
DEVTO_BASE = "https://dev.to"
API_USER_BY_ID = f"{DEVTO_BASE}/api/users"
RESULT_DIR = app_db.PROJECT_ROOT
INITIAL_USER_ID = 1
REQUEST_DELAY_SEC = 1.0
# Idle poll while paused or waiting for the next Tokyo day after hitting the save cap.
# Keep this well under SCRAPE_HEARTBEAT_STALE_SEC so the dashboard stays "alive".
SCRAPE_IDLE_POLL_SEC = 5.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) scraping_dev_bot/1.0"
}


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
_GITHUB_AUTH_WARNING_EMITTED = False


def scrape_mail_cap_ratio() -> float:
    return app_db.scrape_mail_cap_ratio()


def fallback_mail_daily_limit() -> int:
    return max(1, int(os.environ.get("MAIL_DAILY_LIMIT", "20")))


def _heartbeat(conn, *, loop: str) -> None:
    app_db.touch_scrape_heartbeat(conn, loop=loop)
    conn.commit()


def poll_scrape_control(conn) -> dict:
    """Read pause/cap from SQLite (dashboard writes these) and refresh heartbeat."""
    paused = app_db.is_scrape_paused(conn)
    day, saved_today, save_limit = current_scrape_budget(conn)
    at_cap = saved_today >= save_limit
    loop = (
        app_db.SCRAPE_LOOP_IDLING
        if (not paused and at_cap)
        else app_db.SCRAPE_LOOP_RUNNING
    )
    _heartbeat(conn, loop=loop)
    return {
        "paused": paused,
        "at_cap": at_cap,
        "day": day,
        "saved_today": saved_today,
        "save_limit": save_limit,
        "loop": loop,
    }


def current_scrape_budget(conn) -> tuple[str, int, int]:
    """Return (tokyo_day, located_saved_today, daily_limit). noloc excluded."""
    day = app_db.local_day_prefix()
    limit = app_db.scrape_daily_save_limit(
        conn,
        ratio=scrape_mail_cap_ratio(),
        fallback_mail_cap=fallback_mail_daily_limit(),
    )
    saved_today = app_db.count_users_saved_today(conn, day)
    return day, saved_today, limit


def fetch_user(user_id: int) -> dict | None:
    try:
        url = f"{API_USER_BY_ID}/{user_id}"
        response = requests.get(url, headers=HEADERS, timeout=20)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching dev.to user {user_id}: {e}")
        return None


def fetch_github_user(username: str) -> dict | None:
    global _GITHUB_AUTH_WARNING_EMITTED

    normalized = normalize_github_username(username)
    if not normalized:
        print(f"Skipping invalid GitHub username: {username!r}")
        return None
    try:
        token = github_token()
        if not token:
            raise ValueError(
                "GitHub token is not set. Add it on the dashboard Settings page."
            )
        url = f"https://api.github.com/users/{normalized}"
        headers = {
            "Authorization": f"token {token}",
            "User-Agent": "scraping_dev_bot/1.0",
        }
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code == 401:
            if not _GITHUB_AUTH_WARNING_EMITTED:
                print(
                    "GitHub API auth failed (401): the token on the Settings page is invalid "
                    "or expired. Skipping GitHub lookups for now."
                )
                _GITHUB_AUTH_WARNING_EMITTED = True
            return None
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except Exception as e:
        if "401" not in str(e) and "Unauthorized" not in str(e):
            print(f"Error fetching GitHub user {normalized}: {e}")
        return None


def _store_github_profile(
    conn,
    user_id: int,
    github_username: str,
    github_data: dict,
) -> None:
    """Keep bio, display name, and listed social links from a profile already fetched.

    The social-accounts call runs only for users who will be saved. A failed call
    leaves socials unset so a later pass can retry.
    """
    time.sleep(REQUEST_DELAY_SEC)
    status, payload = fetch_json(requests.Session(), social_accounts_path(github_username))
    accounts = None
    if status == "ok" and isinstance(payload, list):
        accounts = payload
    elif status == "missing":
        accounts = []
    app_db.update_github_profile(
        conn,
        user_id,
        bio=profile_bio(github_data),
        github_name=profile_name(github_data),
        socials=None if accounts is None else build_social_links(github_data, accounts),
        github_location=profile_location(github_data),
    )


def normalize_github_username(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""

    value = value.split("?", 1)[0].split("#", 1)[0]
    value = value.replace("https://", "").replace("http://", "")
    value = value.replace("www.", "")
    value = value.replace("github.com/", "").replace("github.com", "")
    value = value.replace("/users/", "/").replace("/user/", "/")
    value = value.strip("/").strip()

    if "/" in value:
        value = value.split("/", 1)[0]

    value = value.strip()
    if not value:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9-]+", value):
        return ""
    return value


def country_slug(country: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", country.strip().lower()).strip("_") or "noloc"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape dev.to users by ID into app.db at the project root. "
            "Resume from this platform's scraper_parameter last_id."
        )
    )
    parser.add_argument(
        "--result-dir",
        type=str,
        default=str(RESULT_DIR),
        help="Directory that contains app.db (default: project root)",
    )
    parser.add_argument(
        "--from-id",
        type=int,
        default=None,
        help=(
            "Start scanning from this user ID (does not lower the saved high-water "
            "last_id). Omit to resume normally."
        ),
    )
    parser.add_argument(
        "--set-last-id",
        type=int,
        default=None,
        help="Set this platform's last_id parameter and recount total_saved, then exit.",
    )
    parser.add_argument(
        "--rebuild-state",
        action="store_true",
        help="Recount users and print this platform's parameters, then exit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result_dir = Path(args.result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)
    app_db.init_db(result_dir)

    if args.rebuild_state or args.set_last_id is not None:
        with app_db.get_conn(result_dir) as conn:
            total = app_db.recount_total_saved(conn)
            state = app_db.get_scrape_state(conn, SOURCE)
            if args.set_last_id is not None:
                if args.set_last_id < 0:
                    raise ValueError("--set-last-id must be >= 0")
                state = app_db.set_scrape_state(conn, last_id=args.set_last_id, platform_id=SOURCE)
                print(
                    f"Set last_id={state['last_id']}, "
                    f"total_saved={state['total_saved']} (users={total})."
                )
            else:
                print(
                    f"Rebuilt state: last_id={state['last_id']}, "
                    f"total_saved={state['total_saved']}"
                )
            counts = app_db.country_counts(conn)
            print(f"Countries: {len(counts)}")
        return

    if not github_token():
        raise ValueError(
            "GitHub token is not set. Add it on the dashboard Settings page."
        )

    with app_db.get_conn(result_dir) as conn:
        state = app_db.get_scrape_state(conn, SOURCE)
        total_check = int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])

    # Guard against accidental restart from ID 1 after state loss.
    if args.from_id is None and state["last_id"] < 1000 and total_check >= 20:
        raise SystemExit(
            f"Refusing to resume from last_id={state['last_id']} while "
            f"{total_check} users exist in {app_db.db_path(result_dir)}.\n"
            "State looks reset/corrupted. Repair with:\n"
            "  python -m scrapers.devto --rebuild-state\n"
            "  python -m scrapers.devto --set-last-id <last_good_id>\n"
            "Then run again (optionally with --from-id)."
        )

    resume_id = max(state["last_id"] + 1, INITIAL_USER_ID)

    if args.from_id is not None:
        if args.from_id < INITIAL_USER_ID:
            raise ValueError(f"--from-id must be >= {INITIAL_USER_ID}")
        user_id = args.from_id
        if user_id < resume_id:
            print(
                f"Warning: --from-id {user_id} is behind high-water resume point "
                f"{resume_id}. Re-scanned users may hit INSERT OR IGNORE. "
                f"Saved last_id will remain >= {state['last_id']}."
            )
        print(
            f"Manual scan start: from-id={user_id} "
            f"(high-water last_id={state['last_id']})"
        )
    else:
        user_id = resume_id

    saved_this_run = 0
    db_file = app_db.db_path(result_dir)

    print(f"DB: {db_file.resolve()}")
    print(
        f"Starting from user ID {user_id} "
        f"(last_id={state['last_id']}, total_saved={state['total_saved']}, "
        f"Ctrl+C to stop)"
    )

    # Long-lived connection for the scrape loop (WAL allows dashboard concurrently).
    conn = app_db.connect(result_dir)
    try:
        purged = app_db.purge_excluded_users(conn)
        conn.commit()
        if purged:
            print(f"[scrape] purged {purged} user(s) from exclude-regions.txt")
        day, saved_today, save_limit = current_scrape_budget(conn)
        print(
            f"[scrape] daily located-save budget {saved_today}/{save_limit} "
            f"(Tokyo day {day}, ratio={scrape_mail_cap_ratio():g}× mail cap; "
            "noloc excluded)"
        )
        wait_reason = ""

        while True:
            extra_purged = app_db.purge_excluded_users(conn)
            if extra_purged:
                conn.commit()
                print(f"[scrape] purged {extra_purged} user(s) from exclude-regions.txt")
            ctrl = poll_scrape_control(conn)
            if ctrl["day"] != day:
                day = ctrl["day"]
                saved_today = ctrl["saved_today"]
                save_limit = ctrl["save_limit"]
                wait_reason = ""
                print(
                    f"[scrape] new Tokyo day {day}: "
                    f"located budget {saved_today}/{save_limit}"
                )

            if ctrl["paused"]:
                if wait_reason != "paused":
                    print("[scrape] paused from dashboard; waiting")
                    wait_reason = "paused"
                time.sleep(SCRAPE_IDLE_POLL_SEC)
                continue

            saved_today = ctrl["saved_today"]
            save_limit = ctrl["save_limit"]
            if ctrl["at_cap"]:
                remaining = app_db.seconds_until_next_tokyo_midnight()
                sleep_for = min(SCRAPE_IDLE_POLL_SEC, remaining)
                if wait_reason != "cap":
                    print(
                        f"[scrape] daily located-save cap reached "
                        f"({saved_today}/{save_limit}); "
                        "idling until next Tokyo day or the dashboard cap is raised"
                    )
                    wait_reason = "cap"
                time.sleep(sleep_for)
                continue

            if wait_reason:
                print(
                    f"[scrape] resumed located budget {saved_today}/{save_limit} "
                    f"(Tokyo day {day})"
                )
                wait_reason = ""

            print(f"Processing user ID {user_id}...")
            try:
                user = fetch_user(user_id)
                if user:
                    location = user.get("location")
                    country = country_slug(detect_country(location))
                    if is_skipped_country(country):
                        print(f"  skip blocked country: {country}")
                    else:
                        save_location = "" if country == "noloc" else format_place(location, country)
                        github_username = (user.get("github_username") or "").strip()
                        github_username = normalize_github_username(github_username)

                        if github_username:
                            github_data = fetch_github_user(github_username)
                            gmail = (
                                (github_data.get("email") or "").strip()
                                if github_data
                                else ""
                            )
                            if gmail:
                                if country == "noloc":
                                    placed = place_from_text(profile_location(github_data))
                                    if placed.skipped:
                                        print(f"  skip blocked country: {placed.country}")
                                        gmail = ""
                                    elif placed.country != "noloc":
                                        country = placed.country
                                        save_location = placed.location
                            if gmail:
                                name = user.get("name") or ""
                                username = user.get("username") or ""
                                site_link = f"{DEVTO_BASE}/{username}"
                                inserted, _uid = app_db.insert_user(
                                    conn,
                                    email=gmail,
                                    name=name,
                                    link=site_link,
                                    github=github_username,
                                    location=save_location,
                                    country=country,
                                    source=SOURCE,
                                    platform_user_id=user_id,
                                )
                                if _uid is not None:
                                    _store_github_profile(conn, _uid, github_username, github_data)
                                conn.commit()
                                if inserted:
                                    saved_this_run += 1
                                    if country != "noloc":
                                        saved_today += 1
                                    state = app_db.get_scrape_state(conn, SOURCE)
                                    ccount = int(
                                        conn.execute(
                                            "SELECT COUNT(*) AS n FROM users WHERE country = ?",
                                            (country,),
                                        ).fetchone()["n"]
                                    )
                                    print(
                                        f"  saved -> {country} "
                                        f"({save_location or 'no location'}) "
                                        f"[{country}={ccount}, total={state['total_saved']}, "
                                        f"located_today={saved_today}/{save_limit}]"
                                    )
                                else:
                                    print(f"  skip duplicate email: {gmail}")
            finally:
                app_db.advance_last_id(conn, user_id, SOURCE)
                conn.commit()
                state = app_db.get_scrape_state(conn, SOURCE)

            user_id += 1
            time.sleep(REQUEST_DELAY_SEC)

    except KeyboardInterrupt:
        state = app_db.get_scrape_state(conn, SOURCE)
        print(
            f"\nStopped. last_id={state['last_id']}, "
            f"total_saved={state['total_saved']} "
            f"(+{saved_this_run} this run)."
        )
        print(f"Re-run the script to resume from ID {state['last_id'] + 1}.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
