import os
import random
import re
import smtplib
import unicodedata
from email.message import EmailMessage
from pathlib import Path

from mail.regions import (
    FALLBACK_REGION,
    canonical_template_region,
    require_region_slug,
    schedule_region_for_country,
    select_template_region,
)

TEMPLATES_DIR = Path("templates")


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

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

_sender_emails = [
    email.strip()
    for email in os.environ.get("SENDER_EMAILS", "").split(",")
    if email.strip()
]
SENDER_EMAILS = _sender_emails or ([GMAIL_ADDRESS] if GMAIL_ADDRESS else [])


def choose_sender() -> str:
    if not SENDER_EMAILS:
        raise ValueError(
            "No sender address is configured. Set SENDER_EMAILS or GMAIL_ADDRESS."
        )
    return random.choice(SENDER_EMAILS)


def region_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    return require_region_slug(stem.split(" ", 1)[0]) if stem else FALLBACK_REGION


def parse_template_text(filename: str, body_text: str) -> dict[str, str]:
    lines = body_text.splitlines()
    if not lines:
        raise ValueError(f"Template {filename} is empty")

    subject_line = lines[0].strip()
    if subject_line.lower().startswith("subject:"):
        subject = subject_line.split(":", 1)[1].strip()
    else:
        subject = subject_line

    body = "\n".join(lines[1:]).lstrip("\r\n")
    if not body.strip():
        raise ValueError(
            f"Template {filename} must contain body content after the subject line"
        )

    try:
        region = canonical_template_region(region_from_filename(filename))
    except ValueError:
        region = FALLBACK_REGION

    return {
        "filename": filename,
        "region": region,
        "subject": subject,
        "body": body,
    }


def serialize_template_text(subject: str, body: str) -> str:
    subject_line = (subject or "").strip()
    if not subject_line:
        raise ValueError("Subject is required")
    body_text = (body or "").replace("\r\n", "\n").strip("\n")
    if not body_text.strip():
        raise ValueError("Body is required")
    return f"Subject: {subject_line}\n{body_text}\n"


def load_template_pool(templates_dir: Path = TEMPLATES_DIR) -> list[dict[str, str]]:
    """Return templates; raise if the directory is missing or empty."""
    if not templates_dir.is_dir():
        raise FileNotFoundError(f"Templates directory not found: {templates_dir}")
    pool = list_templates(templates_dir)
    if not pool:
        raise FileNotFoundError(f"No templates found in {templates_dir}")
    return pool


def list_templates(templates_dir: Path = TEMPLATES_DIR) -> list[dict[str, str]]:
    """Read every .txt template; empty dir → []."""
    if not templates_dir.is_dir():
        return []
    return [
        parse_template_text(path.name, path.read_text(encoding="utf-8"))
        for path in sorted(templates_dir.glob("*.txt"))
    ]


def templates_dir_mtime(templates_dir: Path = TEMPLATES_DIR) -> float:
    if not templates_dir.is_dir():
        return 0.0
    mtimes = [path.stat().st_mtime for path in templates_dir.glob("*.txt")]
    return max(mtimes) if mtimes else templates_dir.stat().st_mtime


def _safe_template_path(filename: str, templates_dir: Path) -> Path:
    name = Path(filename).name
    if name != filename or not name.endswith(".txt") or ".." in name:
        raise ValueError("Invalid template filename")
    region_from_filename(name)
    directory = templates_dir.resolve()
    path = (directory / name).resolve()
    if path.parent != directory:
        raise ValueError("Invalid template filename")
    return path


def next_template_filename(region: str, templates_dir: Path = TEMPLATES_DIR) -> str:
    slug = canonical_template_region(region)
    highest = 0
    prefix = f"{slug} ("
    for path in templates_dir.glob(f"{slug} (*).txt"):
        stem = path.stem
        if not stem.startswith(prefix) or not stem.endswith(")"):
            continue
        num_text = stem[len(prefix) : -1]
        if num_text.isdigit():
            highest = max(highest, int(num_text))
    return f"{slug} ({highest + 1}).txt"


def create_template(
    region: str,
    subject: str,
    body: str,
    templates_dir: Path = TEMPLATES_DIR,
) -> dict[str, str]:
    slug = canonical_template_region(region)
    templates_dir.mkdir(parents=True, exist_ok=True)
    filename = next_template_filename(slug, templates_dir)
    path = _safe_template_path(filename, templates_dir)
    text = serialize_template_text(subject, body)
    path.write_text(text, encoding="utf-8")
    return parse_template_text(filename, text)


def update_template(
    filename: str,
    *,
    region: str,
    subject: str,
    body: str,
    templates_dir: Path = TEMPLATES_DIR,
) -> dict[str, str]:
    old_path = _safe_template_path(filename, templates_dir)
    if not old_path.is_file():
        raise FileNotFoundError(filename)
    slug = canonical_template_region(region)
    text = serialize_template_text(subject, body)
    old_region = region_from_filename(old_path.name)
    if slug == old_region:
        old_path.write_text(text, encoding="utf-8")
        return parse_template_text(old_path.name, text)

    new_name = next_template_filename(slug, templates_dir)
    new_path = _safe_template_path(new_name, templates_dir)
    new_path.write_text(text, encoding="utf-8")
    old_path.unlink()
    return parse_template_text(new_name, text)


def delete_template(filename: str, templates_dir: Path = TEMPLATES_DIR) -> None:
    path = _safe_template_path(filename, templates_dir)
    if not path.is_file():
        raise FileNotFoundError(filename)
    remaining = [p for p in templates_dir.glob("*.txt") if p.resolve() != path.resolve()]
    if not remaining:
        raise ValueError("Cannot delete the last template")
    path.unlink()


_BRACE_CONTENT_RE = re.compile(
    r"\([^()]*\)|\[[^\[\]]*\]|\{[^{}]*\}|（[^（）]*）|【[^【】]*】"
)


def normalize_display_name(name: str) -> str:
    if not name:
        return ""

    text = str(name).strip()
    if not text:
        return ""

    # Drop parentheticals like "(He/Him)" before the letter filter, or
    # "Jason Watt (He/Him)" would become "Jason Watt Hehim".
    text = _BRACE_CONTENT_RE.sub(" ", text)

    cleaned = "".join(
        ch
        for ch in text
        if unicodedata.category(ch).startswith("L")
        or unicodedata.category(ch).startswith("M")
        or ch in {" ", "-", "'", "’", "."}
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""

    def cap_word(word: str) -> str:
        if "-" in word:
            return "-".join(part.capitalize() for part in word.split("-"))
        return word.capitalize()

    return " ".join(cap_word(part) for part in cleaned.split(" "))


def render_template_text(text: str, name: str, your_name: str, link: str) -> str:
    # Canonical placeholders: [Name], [Your Name], [Link]
    # Normalize legacy markdown escapes like \[Name] → [Name].
    rendered = text.replace("\\[", "[")

    name_value = normalize_display_name(name) if name else ""
    # Missing/invalid name → "there" so "Hi [Name]," becomes "Hi there,"
    if not name_value:
        name_value = "there"

    rendered = re.sub(r"\[(?:name)\]", name_value, rendered, flags=re.IGNORECASE)
    if your_name:
        rendered = re.sub(
            r"\[(?:your name)\]", your_name.strip(), rendered, flags=re.IGNORECASE
        )
    else:
        rendered = re.sub(r"\[(?:your name)\]", "", rendered, flags=re.IGNORECASE)
    rendered = re.sub(r"\[(?:link)\]", link or "", rendered, flags=re.IGNORECASE)
    return rendered


def region_for_country(country: str) -> str:
    """Send-window region (us / eu / ja / etc). Template matching is separate."""
    return schedule_region_for_country(country)


def pick_message(
    template_pool: list[dict[str, str]],
    country: str,
    name: str,
    your_name: str,
    link: str,
) -> tuple[str, str, str]:
    """Select a template by country, then named region (EU/APAC/…), then Other."""
    def item_region(item: dict[str, str]) -> str:
        raw = item.get("region") or ""
        try:
            return canonical_template_region(raw)
        except ValueError:
            return raw

    region = select_template_region(country, (item_region(item) for item in template_pool))
    choices = [item for item in template_pool if item_region(item) == region]
    if not choices:
        fallback = [item for item in template_pool if item.get("region") == FALLBACK_REGION]
        template = random.choice(fallback or template_pool)
    else:
        template = random.choice(choices)

    subject = render_template_text(template["subject"], name, your_name, link)
    body = render_template_text(template["body"], name, your_name, link)
    return template["filename"], subject, body




def build_message(
    from_email: str, to_email: str, subject: str, body: str
) -> EmailMessage:
    """Build a plain-text email (templates are .txt; no HTML/Markdown)."""
    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send_email(
    smtp: smtplib.SMTP_SSL, from_email: str, to_email: str, subject: str, body: str
) -> None:
    smtp.send_message(build_message(from_email, to_email, subject, body))


def main() -> None:
    raise RuntimeError(
        "Direct CSV batch sending is deprecated. "
        "Use the dashboard queue to enqueue users and send mail from SQLite."
    )


if __name__ == "__main__":
    main()