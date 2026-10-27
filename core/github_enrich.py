"""Read public GitHub profile fields used for outreach.

One user lookup already carries bio, display name, and twitter_username.
Social links the person listed on the profile need a second request.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

GITHUB_API = "https://api.github.com"
REQUEST_DELAY_SEC = 1.0
MAX_ATTEMPTS = 5

_X_HOSTS = ("x.com", "twitter.com", "mobile.twitter.com")
# Known profile hosts. The first host match wins, so a specific site stays above a broader one.
_HOST_PROVIDERS = (
    ("discord", ("discord.gg", "discord.com", "discordapp.com")),
    ("telegram", ("t.me", "telegram.me", "telegram.org")),
    ("whatsapp", ("wa.me", "whatsapp.com", "chat.whatsapp.com", "wa.link")),
    ("linkedin", ("linkedin.com",)),
    ("github", ("github.com",)),
    ("facebook", ("facebook.com", "fb.com", "fb.me")),
    ("instagram", ("instagram.com",)),
    ("youtube", ("youtube.com", "youtu.be")),
    ("reddit", ("reddit.com",)),
    ("twitch", ("twitch.tv",)),
    ("stackoverflow", ("stackoverflow.com", "stackexchange.com")),
    ("bluesky", ("bsky.app", "bsky.social")),
    ("mastodon", ("mastodon.social", "mastodon.online")),
    ("threads", ("threads.net", "threads.com")),
    ("tiktok", ("tiktok.com",)),
    ("medium", ("medium.com",)),
    ("devto", ("dev.to",)),
    ("gitlab", ("gitlab.com",)),
    ("leetcode", ("leetcode.com", "leetcode.cn")),
    ("codepen", ("codepen.io",)),
    ("huggingface", ("huggingface.co",)),
    ("npm", ("npmjs.com",)),
    ("behance", ("behance.net",)),
    ("dribbble", ("dribbble.com",)),
    ("kaggle", ("kaggle.com",)),
    ("hackerrank", ("hackerrank.com",)),
    ("patreon", ("patreon.com",)),
    ("substack", ("substack.com",)),
    ("hashnode", ("hashnode.com", "hashnode.dev")),
    ("orcid", ("orcid.org",)),
    ("linktree", ("linktr.ee",)),
    ("codeberg", ("codeberg.org",)),
    ("scholar", ("scholar.google.com",)),
    ("buymeacoffee", ("buymeacoffee.com",)),
    ("kofi", ("ko-fi.com",)),
    ("upwork", ("upwork.com",)),
    ("credly", ("credly.com",)),
    ("vk", ("vk.com",)),
    ("xing", ("xing.com",)),
    ("keybase", ("keybase.io",)),
    ("matrix", ("matrix.to",)),
    ("steam", ("steamcommunity.com",)),
    ("researchgate", ("researchgate.net",)),
    ("gdev", ("g.dev",)),
    ("weibo", ("weibo.com",)),
    ("zhihu", ("zhihu.com",)),
    ("bilibili", ("bilibili.com",)),
    ("spotify", ("open.spotify.com", "spotify.com")),
    ("figma", ("figma.com",)),
    ("codewars", ("codewars.com",)),
    ("goodreads", ("goodreads.com",)),
    ("farcaster", ("warpcast.com", "farcaster.xyz")),
)


def load_dotenv(path: str | Path = ".env") -> None:
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


def github_token() -> str:
    """Token saved on the Settings page, with the environment as a fallback."""
    stored = _stored_github_token()
    if stored:
        return stored
    load_dotenv()
    return os.environ.get("GITHUB_TOKEN", "").strip()


def _stored_github_token() -> str:
    try:
        import core.db as app_db

        with app_db.get_conn() as conn:
            return app_db.get_meta(conn, "github_token", "").strip()
    except Exception:
        return ""


def parse_github_expiration(value: str) -> str:
    """Turn GitHub's token-expiration header into UTC ISO-8601.

    The header is omitted when the token does not expire. An unrecognized
    value stays blank rather than becoming a guessed date.
    """
    text = (value or "").strip()
    if not text:
        return ""
    normalized = text.replace("UTC", "+0000").replace("GMT", "+0000")
    parsed = None
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


TOKYO = timezone(timedelta(hours=9))


def format_expiration_label(expires_at: str) -> str:
    """Clock time in Tokyo (UTC+9), with no guessed value when the date is blank."""
    parsed = _expiration_datetime(expires_at)
    if parsed is None:
        return ""
    return parsed.astimezone(TOKYO).strftime("%Y-%m-%d %H:%M JST")


def token_expires_soon(expires_at: str, *, now: datetime | None = None) -> bool:
    """True when the token expires in less than seven days and is not already past."""
    parsed = _expiration_datetime(expires_at)
    if parsed is None:
        return False
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    remaining = parsed - moment
    return timedelta(0) < remaining < timedelta(days=7)


def github_token_accepted(status: str) -> bool:
    """A replacement is stored only when GitHub accepts it and it is not past expiry."""
    return status in ("ok", "no_expiration")


def _expiration_datetime(expires_at: str) -> datetime | None:
    text = (expires_at or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def github_token_health(
    *,
    http_status: int,
    expires_at: str,
    now: datetime | None = None,
) -> str:
    """ok, expired, invalid, no_expiration, or unreachable."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    expiry = None
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
        except ValueError:
            expiry = None
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    past = expiry is not None and expiry <= moment
    if http_status == 401:
        return "expired" if past else "invalid"
    if past:
        return "expired"
    if http_status == 200 and expiry is not None:
        return "ok"
    if http_status == 200:
        return "no_expiration"
    return "unreachable"


def inspect_github_token(token: str, *, now: datetime | None = None) -> dict[str, str]:
    """Read GitHub-Authentication-Token-Expiration from an authenticated call.

    A classic personal access token has no separate token-info endpoint.
    GitHub puts the expiry on authenticated responses, and omits it when
    the token does not expire. 401 means the token is rejected.
    """
    secret = (token or "").strip()
    if not secret:
        return {"status": "missing", "expires_at": "", "expires_label": ""}
    try:
        response = requests.get(
            f"{GITHUB_API}/rate_limit",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {secret}",
                "User-Agent": "scraping_dev_bot/1.0",
            },
            timeout=15,
        )
    except requests.RequestException:
        return {"status": "unreachable", "expires_at": "", "expires_label": ""}
    expires_at = parse_github_expiration(
        response.headers.get("GitHub-Authentication-Token-Expiration", "")
    )
    status = github_token_health(
        http_status=response.status_code,
        expires_at=expires_at,
        now=now,
    )
    return {
        "status": status,
        "expires_at": expires_at,
        "expires_label": format_expiration_label(expires_at),
    }


def mask_token(token: str) -> str:
    secret = (token or "").strip()
    if len(secret) <= 8:
        return "••••"
    return f"{secret[:4]}…{secret[-4:]}"


def github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "scraping_dev_bot/1.0",
    }
    token = github_token()
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def user_path(username: str) -> str:
    return f"/users/{quote(username, safe='')}"


def social_accounts_path(username: str) -> str:
    return f"{user_path(username)}/social_accounts"


def github_get(session: requests.Session, path: str) -> requests.Response:
    return session.get(
        f"{GITHUB_API}{path}",
        headers=github_headers(),
        timeout=20,
    )


def retry_after_sec(response: requests.Response) -> float:
    raw = (response.headers.get("Retry-After") or "").strip()
    try:
        return max(REQUEST_DELAY_SEC, float(raw))
    except ValueError:
        return 30.0


def devto_slug(link: str | None) -> str:
    path = urlparse(link or "").path.strip("/")
    if not path or "/" in path:
        return path.split("/")[0] if path else ""
    return path


def should_adopt_github_name(current_name: str | None, link: str | None, github_name: str | None) -> bool:
    """GitHub's display name replaces a Dev.to slug. A real Dev.to name stays."""
    github_name = (github_name or "").strip()
    if not github_name:
        return False
    current = (current_name or "").strip()
    if not current:
        return True
    slug = devto_slug(link)
    return bool(slug) and current.lower() == slug.lower()


def adopted_names(
    current_name: str | None,
    display_name: str | None,
    link: str | None,
    github_name: str | None,
) -> tuple[str, str]:
    """Return (name, display_name). An edited greeting is not overwritten."""
    name = (current_name or "").strip()
    greeting = (display_name or "").strip()
    if not should_adopt_github_name(name, link, github_name):
        return name, greeting or name
    adopted = (github_name or "").strip()
    if len(adopted) > 200:
        adopted = adopted[:200].rstrip()
    if greeting == name or not greeting:
        return adopted, adopted
    return adopted, greeting


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def x_url(handle: str | None) -> str:
    text = (handle or "").strip().lstrip("@")
    if not text or "/" in text or " " in text:
        return ""
    return f"https://x.com/{text}"


def canonical_x_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    handle = path.split("/")[0] if path else ""
    built = x_url(handle)
    return built or url


def _matches_host(host: str, names: tuple[str, ...]) -> bool:
    for name in names:
        if host == name or host.endswith("." + name):
            return True
    return False


def classify_provider(provider: str | None, url: str) -> str:
    """A known site wins over a generic label. GitHub is named so callers can drop it."""
    raw = (provider or "").strip().lower()
    host = _host(url)
    if raw in {"twitter", "x"} or _matches_host(host, _X_HOSTS):
        return "x"
    named = ""
    for name, hosts in _HOST_PROVIDERS:
        if _matches_host(host, hosts):
            return name
        if raw == name and not named:
            named = name
    if named:
        return named
    if raw and raw != "generic":
        return raw
    return "generic"


SOURCE_PROVIDERS = frozenset({"devto", "github"})


def build_social_links(profile: dict | None, accounts: list | None) -> list[dict[str, str]]:
    """X from twitter_username, plus each social_accounts entry, one URL each."""
    links: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(provider: str, url: str) -> None:
        url = (url or "").strip()
        if not url.startswith(("http://", "https://")):
            return
        provider = classify_provider(provider, url)
        if provider == "x":
            url = canonical_x_url(url)
        if provider in SOURCE_PROVIDERS:
            return
        key = url.lower().rstrip("/")
        if key in seen:
            return
        seen.add(key)
        links.append({"provider": provider, "url": url, "status": "not_sent"})

    handle = ""
    if isinstance(profile, dict):
        handle = str(profile.get("twitter_username") or "")
    built = x_url(handle)
    if built:
        add("x", built)
    for item in accounts or []:
        if not isinstance(item, dict):
            continue
        add(str(item.get("provider") or ""), str(item.get("url") or ""))
    return links


def profile_bio(profile: dict | None) -> str:
    if not isinstance(profile, dict):
        return ""
    return str(profile.get("bio") or "").strip()


def profile_name(profile: dict | None) -> str:
    if not isinstance(profile, dict):
        return ""
    return str(profile.get("name") or "").strip()


def profile_location(profile: dict | None) -> str:
    if not isinstance(profile, dict):
        return ""
    return str(profile.get("location") or "").strip()


@dataclass(frozen=True)
class Place:
    location: str
    country: str
    skipped: bool = False


def place_from_text(location: str | None) -> Place:
    """GitHub location text kept only when it names a country we can store.

    Vague text stays noloc with an empty location, matching the Dev.to save rule.
    A blocked country is reported and not written over an existing noloc row.
    """
    from core.locations import detect_country, format_place, is_skipped_country

    text = (location or "").strip()
    if not text:
        return Place("", "noloc")
    country = detect_country(text)
    if not country or country == "noloc":
        return Place("", "noloc")
    if is_skipped_country(country):
        return Place(text, country, True)
    return Place(format_place(text, country), country)


def fetch_json(
    session: requests.Session,
    path: str,
    *,
    pause=None,
) -> tuple[str, object]:
    """Return (ok|missing|failed, payload). pause(seconds, note) runs before a retry sleep."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = github_get(session, path)
        except requests.RequestException as exc:
            wait = REQUEST_DELAY_SEC * attempt
            if pause:
                pause(wait, f"retry in {wait:.0f}s")
            time.sleep(wait)
            if attempt == MAX_ATTEMPTS:
                return "failed", str(exc)
            continue
        if response.status_code == 404:
            return "missing", None
        if response.status_code == 429 or response.status_code >= 500:
            wait = retry_after_sec(response) if response.status_code == 429 else REQUEST_DELAY_SEC * attempt
            if pause:
                pause(wait, f"retry in {wait:.0f}s")
            time.sleep(wait)
            if attempt == MAX_ATTEMPTS:
                return "failed", response.status_code
            continue
        if response.status_code != 200:
            return "failed", response.status_code
        try:
            return "ok", response.json()
        except ValueError:
            return "failed", "invalid json"
    return "failed", None


def collect_profile(
    session: requests.Session,
    username: str,
    *,
    pause=None,
    fetch_socials: bool = True,
) -> tuple[str, dict]:
    """Read bio, name, and social links for one GitHub username.

    status is ok, missing, or failed. On ok, socials is None when the second
    call failed and the row should stay unmarked.
    """
    status, payload = fetch_json(session, user_path(username), pause=pause)
    if status != "ok":
        return status, {}
    profile = payload if isinstance(payload, dict) else {}
    accounts = None
    if fetch_socials:
        time.sleep(REQUEST_DELAY_SEC)
        social_status, social_payload = fetch_json(
            session,
            social_accounts_path(username),
            pause=pause,
        )
        if social_status == "failed":
            accounts = None
        elif social_status == "missing" or not isinstance(social_payload, list):
            accounts = []
        else:
            accounts = social_payload
    result = {
        "name": profile_name(profile),
        "bio": profile_bio(profile),
        "location": profile_location(profile),
        "socials": None if accounts is None else build_social_links(profile, accounts),
        "profile": profile,
    }
    return "ok", result
