"""
Template regions vs send-window regions.

Send windows stay us / eu / ja / etc (Tokyo clock). Template files use
`{slug} (n).txt`: a multi-country group (eu, emea, apac, latam, etc) or a
country name (japan, usa, india). Abbreviations like ja / us / jp are aliases
of those country names, not file prefixes.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from core.locations import is_skipped_country, known_country_slugs

# Most specific named group first after an exact country slug.
GROUP_PRIORITY = ("eu", "latam", "emea", "apac")
FALLBACK_REGION = "etc"

REGION_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
INVALID_REGION_SLUG = (
    "Region must start with a letter and use only letters, numbers, or underscores."
)

GROUP_META: tuple[dict[str, str], ...] = (
    {"slug": "eu", "label": "EU", "description": "Europe (EU, EEA, UK, Switzerland)"},
    {"slug": "emea", "label": "EMEA", "description": "Europe, Middle East, and Africa"},
    {"slug": "apac", "label": "APAC", "description": "Asia-Pacific"},
    {"slug": "latam", "label": "LATAM", "description": "Latin America"},
    {"slug": "etc", "label": "Other", "description": "Fallback when no other region matches"},
)

# Aliases that show up in tests / free text → DB country slugs.
SLUG_ALIASES: dict[str, str] = {
    "us": "usa",
    "usa": "usa",
    "united states": "usa",
    "united states of america": "usa",
    "america": "usa",
    "ja": "japan",
    "jp": "japan",
    "jpn": "japan",
    "japan": "japan",
    "gb": "uk",
    "gbr": "uk",
    "great britain": "uk",
    "united kingdom": "uk",
    "uk": "uk",
    "de": "germany",
    "deutschland": "germany",
    "cz": "czech_republic",
    "czechia": "czech_republic",
    "kr": "south_korea",
    "korea": "south_korea",
}

US_COUNTRIES = frozenset({"usa"})

JA_COUNTRIES = frozenset({"japan"})

EU_COUNTRIES = frozenset(
    {
        "austria",
        "belgium",
        "bulgaria",
        "croatia",
        "cyprus",
        "czech_republic",
        "denmark",
        "estonia",
        "finland",
        "france",
        "germany",
        "greece",
        "hungary",
        "iceland",
        "ireland",
        "italy",
        "latvia",
        "liechtenstein",
        "lithuania",
        "luxembourg",
        "malta",
        "netherlands",
        "norway",
        "poland",
        "portugal",
        "romania",
        "slovakia",
        "slovenia",
        "spain",
        "sweden",
        "switzerland",
        "uk",
    }
)

LATAM_COUNTRIES = frozenset(
    {
        "argentina",
        "bolivia",
        "brazil",
        "chile",
        "colombia",
        "costa_rica",
        "cuba",
        "dominican_republic",
        "ecuador",
        "el_salvador",
        "guatemala",
        "honduras",
        "jamaica",
        "mexico",
        "nicaragua",
        "panama",
        "paraguay",
        "peru",
        "puerto_rico",
        "trinidad_and_tobago",
        "uruguay",
        "venezuela",
    }
)

EMEA_EXTRA = frozenset(
    {
        "albania",
        "algeria",
        "andorra",
        "angola",
        "armenia",
        "azerbaijan",
        "bahrain",
        "belarus",
        "benin",
        "bosnia",
        "botswana",
        "burundi",
        "cameroon",
        "cape_verde",
        "congo",
        "egypt",
        "eswatini",
        "ethiopia",
        "gabon",
        "georgia_country",
        "ghana",
        "guernsey",
        "iran",
        "iraq",
        "israel",
        "ivory_coast",
        "jordan",
        "kenya",
        "kosovo",
        "kuwait",
        "lebanon",
        "libya",
        "madagascar",
        "malawi",
        "mauritania",
        "mauritius",
        "moldova",
        "monaco",
        "montenegro",
        "morocco",
        "mozambique",
        "namibia",
        "nigeria",
        "north_macedonia",
        "oman",
        "palestine",
        "qatar",
        "russia",
        "rwanda",
        "saudi_arabia",
        "senegal",
        "serbia",
        "sierra_leone",
        "south_africa",
        "sudan",
        "syria",
        "tanzania",
        "tunisia",
        "turkey",
        "uae",
        "uganda",
        "ukraine",
        "zambia",
        "zimbabwe",
    }
)

EMEA_COUNTRIES = EU_COUNTRIES | EMEA_EXTRA

APAC_COUNTRIES = frozenset(
    {
        "afghanistan",
        "australia",
        "bangladesh",
        "bhutan",
        "cambodia",
        "china",
        "hong_kong",
        "india",
        "indonesia",
        "japan",
        "kazakhstan",
        "kyrgyzstan",
        "laos",
        "macau",
        "malaysia",
        "maldives",
        "mongolia",
        "myanmar",
        "nepal",
        "new_zealand",
        "north_korea",
        "pakistan",
        "philippines",
        "singapore",
        "south_korea",
        "sri_lanka",
        "taiwan",
        "thailand",
        "turkmenistan",
        "uzbekistan",
        "vietnam",
    }
)

GROUP_COUNTRIES: dict[str, frozenset[str]] = {
    "eu": EU_COUNTRIES,
    "latam": LATAM_COUNTRIES,
    "emea": EMEA_COUNTRIES,
    "apac": APAC_COUNTRIES,
}

NAMED_GROUP_SLUGS = frozenset(GROUP_COUNTRIES) | {FALLBACK_REGION}


def normalize_region_slug(value: str | None) -> str:
    """Lowercase slug: letters, digits, underscore. Spaces/hyphens become _."""
    text = (value or "").strip().lower()
    text = text.replace("-", " ").replace("/", " ")
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"[\s]+", "_", text).strip("_")
    return text


def canonical_country_slug(country: str | None) -> str:
    slug = normalize_region_slug(country)
    if not slug or slug in {"noloc", "unknown"}:
        return ""
    spaced = slug.replace("_", " ")
    if spaced in SLUG_ALIASES:
        return SLUG_ALIASES[spaced]
    if slug in SLUG_ALIASES:
        return SLUG_ALIASES[slug]
    return slug


def is_valid_region_slug(slug: str) -> bool:
    return bool(REGION_SLUG_RE.fullmatch(slug or ""))


def require_region_slug(value: str | None) -> str:
    slug = normalize_region_slug(value)
    if not is_valid_region_slug(slug):
        raise ValueError(INVALID_REGION_SLUG)
    return slug


def canonical_template_region(value: str | None) -> str:
    """Named group as-is; otherwise the country name (`ja`/`jp` → japan, `us` → usa)."""
    slug = require_region_slug(value)
    if slug in NAMED_GROUP_SLUGS:
        return slug
    return canonical_country_slug(slug) or slug


def decorate_template(item: dict[str, Any]) -> dict[str, Any]:
    """Attach display fields used by the dashboard API."""
    row = dict(item)
    row["region_label"] = region_label(str(row.get("region") or ""))
    return row


def schedule_region_for_country(country: str | None) -> str:
    """Send-window bucket: us / eu / ja / etc. Unchanged from the original mapping."""
    slug = canonical_country_slug(country)
    if not slug:
        return FALLBACK_REGION
    if slug in US_COUNTRIES:
        return "us"
    if slug in EU_COUNTRIES:
        return "eu"
    if slug in JA_COUNTRIES:
        return "ja"
    return FALLBACK_REGION


def template_region_candidates(country: str | None) -> list[str]:
    """
    Regions to try for a recipient, most specific first.

    Example: germany → germany, eu, emea, etc
             india   → india, apac, etc
             japan   → japan, apac, etc
             usa     → usa, etc
    """
    slug = canonical_country_slug(country)
    ordered: list[str] = []

    def add(item: str) -> None:
        if item and item not in ordered:
            ordered.append(item)

    if slug and slug not in NAMED_GROUP_SLUGS:
        add(slug)
    elif slug in NAMED_GROUP_SLUGS and slug != FALLBACK_REGION:
        add(slug)

    for group in GROUP_PRIORITY:
        members = GROUP_COUNTRIES.get(group, frozenset())
        if slug in members or slug == group:
            add(group)

    add(FALLBACK_REGION)
    return ordered


def group_members(slug: str) -> tuple[str, ...]:
    members = GROUP_COUNTRIES.get(normalize_region_slug(slug), frozenset())
    return tuple(sorted(members))


def select_template_region(country: str | None, available: Iterable[str]) -> str:
    """
    Template region used for a recipient given the files on disk.

    Adding `apac (n).txt` selects APAC for India, China, Japan, and other
    APAC members. A country file (`japan (n).txt`, or legacy `ja (n).txt`)
    still wins for that country.
    """
    have: set[str] = set()
    for region in available:
        raw = normalize_region_slug(region)
        if not raw:
            continue
        if is_valid_region_slug(raw):
            have.add(canonical_template_region(raw))
        else:
            have.add(raw)
    for region in template_region_candidates(country):
        if region in have:
            return region
    if FALLBACK_REGION in have:
        return FALLBACK_REGION
    return next(iter(sorted(have)), FALLBACK_REGION)


# Long and compound country names. Single-word names stay as words.
_COMPOUND_COUNTRY_CODES = {
    "usa": "USA",
    "uk": "UK",
    "uae": "UAE",
    "new_zealand": "NZ",
    "hong_kong": "HK",
    "south_africa": "ZA",
    "czech_republic": "CZ",
    "costa_rica": "CR",
    "saudi_arabia": "SA",
    "south_korea": "KR",
    "north_korea": "KP",
    "sri_lanka": "LK",
    "el_salvador": "SV",
    "dominican_republic": "DO",
    "puerto_rico": "PR",
    "trinidad_and_tobago": "TT",
    "ivory_coast": "CI",
    "sierra_leone": "SL",
    "cape_verde": "CV",
    "north_macedonia": "MK",
    "bosnia_and_herzegovina": "BA",
    "papua_new_guinea": "PG",
    "burkina_faso": "BF",
    "georgia_country": "Georgia",
}
_SMALL_NAME_WORDS = frozenset({"and", "of", "the"})


def region_label(slug: str) -> str:
    key = (slug or "").strip().lower().replace(" ", "_").replace("-", "_")
    for item in GROUP_META:
        if item["slug"] == key:
            return item["label"]
    if key in _COMPOUND_COUNTRY_CODES:
        return _COMPOUND_COUNTRY_CODES[key]
    words = [part for part in key.split("_") if part and part not in _SMALL_NAME_WORDS]
    if len(words) > 1:
        return "".join(part[0].upper() for part in words)
    word = words[0] if words else ""
    if not word:
        return "Unknown"
    if len(word) <= 3:
        return word.upper()
    return word.capitalize()


def suggestion_catalog(
    *,
    user_counts: dict[str, int] | None = None,
    template_regions: list[str] | None = None,
    templates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Groups + countries for the template region suggestion box."""
    counts = user_counts or {}
    by_region: dict[str, int] = {}
    for item in templates or []:
        raw = str(item.get("region") or "").strip()
        if not raw:
            continue
        try:
            region = canonical_template_region(raw)
        except ValueError:
            region = normalize_region_slug(raw)
        if region:
            by_region[region] = by_region.get(region, 0) + 1
    used = set(by_region)
    used.update((r or "").strip().lower() for r in (template_regions or []) if r)

    groups = []
    for item in GROUP_META:
        members = list(group_members(item["slug"]))
        groups.append(
            {
                "slug": item["slug"],
                "label": item["label"],
                "description": item["description"],
                "kind": "fallback" if item["slug"] == FALLBACK_REGION else "group",
                "templates": by_region.get(item["slug"], 0),
                "member_count": len(members),
                "members": members,
            }
        )

    seen: set[str] = set()
    countries: list[dict[str, Any]] = []
    for slug in known_country_slugs():
        if is_skipped_country(slug):
            continue
        seen.add(slug)
        countries.append(
            {
                "slug": slug,
                "label": region_label(slug),
                "kind": "country",
                "users": int(counts.get(slug, 0)),
                "templates": by_region.get(slug, 0),
            }
        )

    extra_slugs = set(counts) | used
    for slug in extra_slugs:
        key = canonical_country_slug(slug) or normalize_region_slug(slug)
        if (
            not key
            or key in seen
            or key in NAMED_GROUP_SLUGS
            or is_skipped_country(key)
            or key == "noloc"
        ):
            continue
        seen.add(key)
        countries.append(
            {
                "slug": key,
                "label": region_label(key),
                "kind": "country",
                "users": int(counts.get(key, 0) or counts.get(slug, 0)),
                "templates": by_region.get(key, 0),
            }
        )

    countries.sort(key=lambda row: (-int(row["users"]), str(row["label"])))
    grouped_slugs = {item["slug"] for item in groups} | {item["slug"] for item in countries}
    custom = [
        {
            "slug": slug,
            "label": region_label(slug),
            "kind": "custom",
            "templates": count,
        }
        for slug, count in sorted(by_region.items())
        if slug not in grouped_slugs
    ]
    return {
        "groups": groups,
        "countries": countries,
        "custom": custom,
        "template_counts": by_region,
    }
