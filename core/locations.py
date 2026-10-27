"""
Location → country slug mapping.

Country data shared by the server and scrapers.
detect_country() returns:
  - a country slug (e.g. "usa", "greece")
  - "noloc" if empty, joke/vague, or unmatched (location string cleared on save)
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

# Used if exclude-regions.txt is missing.
DEFAULT_EXCLUDED_COUNTRIES = frozenset({"south_korea"})
EXCLUDE_REGIONS_FILE = Path(__file__).resolve().parent.parent / "exclude-regions.txt"
_NEVER_EXCLUDE = frozenset({"", "noloc", "unknown"})

_exclude_cache_key: tuple[str, float] | None = None
_exclude_cache: frozenset[str] = DEFAULT_EXCLUDED_COUNTRIES


def _normalize_exclude_token(value: str) -> str:
    text = (value or "").strip().lower().replace("-", " ").replace("/", " ")
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"[\s]+", "_", text).strip("_")


def _expand_exclude_token(token: str) -> set[str]:
    """Country slug, or all members if the token is a named region (eu, apac, …)."""
    slug = _normalize_exclude_token(token)
    if not slug or slug in _NEVER_EXCLUDE:
        return set()
    try:
        from mail.regions import (
            FALLBACK_REGION,
            GROUP_COUNTRIES,
            canonical_country_slug,
        )
    except ImportError:
        return {slug}
    country = canonical_country_slug(slug) or slug
    if country in _NEVER_EXCLUDE or country == FALLBACK_REGION:
        return set()
    members = GROUP_COUNTRIES.get(slug) or GROUP_COUNTRIES.get(country)
    if members:
        return set(members)
    return {country}


def excluded_country_slugs(path: Path | None = None) -> frozenset[str]:
    """Country slugs listed in exclude-regions.txt (mtime-cached)."""
    global _exclude_cache_key, _exclude_cache
    file_path = path or EXCLUDE_REGIONS_FILE
    try:
        mtime = file_path.stat().st_mtime
        key = (str(file_path.resolve()), mtime)
    except OSError:
        return DEFAULT_EXCLUDED_COUNTRIES
    if _exclude_cache_key == key:
        return _exclude_cache
    found: set[str] = set()
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_EXCLUDED_COUNTRIES
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        found.update(_expand_exclude_token(raw))
    _exclude_cache_key = key
    _exclude_cache = frozenset(found) if found else DEFAULT_EXCLUDED_COUNTRIES
    return _exclude_cache


def is_skipped_country(country: str | None) -> bool:
    slug = (country or "").strip().lower()
    if not slug or slug in _NEVER_EXCLUDE:
        return False
    return slug in excluded_country_slugs()


def add_excluded_country(country: str | None, path: Path | None = None) -> str:
    """Append a country slug to exclude-regions.txt. Returns the canonical slug."""
    global _exclude_cache_key
    slug = _normalize_exclude_token(country)
    try:
        from mail.regions import canonical_country_slug

        slug = canonical_country_slug(slug) or slug
    except ImportError:
        pass
    if not slug or slug in _NEVER_EXCLUDE:
        raise ValueError("Cannot exclude this region")

    file_path = Path(path) if path else EXCLUDE_REGIONS_FILE
    if slug in excluded_country_slugs(file_path):
        _exclude_cache_key = None
        return slug

    file_path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if file_path.is_file():
        existing = file_path.read_text(encoding="utf-8")
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with file_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{prefix}{slug}\n")
    _exclude_cache_key = None
    return slug


def known_country_slugs() -> list[str]:
    """Canonical country slugs from the location catalog (excludes skipped)."""
    return sorted(
        slug
        for slug in COUNTRY_ALIAS_GROUPS
        if slug and slug != "noloc" and not is_skipped_country(slug)
    )


# ---------------------------------------------------------------------------
# Administrative abbreviations (matched as bare tokens or trailing ", XX")
# ---------------------------------------------------------------------------

US_STATE_ABBREVS = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
    "dc",
}

CA_PROVINCE_ABBREVS = {
    "ab", "bc", "mb", "nb", "nl", "ns", "nt", "nu", "on", "pe", "qc", "sk", "yt",
}

# Brazilian state codes (after comma), e.g. "Piracicaba, SP"
BR_STATE_ABBREVS = {
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma",
    "mt", "ms", "mg", "pa", "pb", "pr", "pe", "pi", "rj", "rn",
    "rs", "ro", "rr", "sc", "sp", "se", "to",
}

# Empty / joke / vague / unusable free-text → noloc (location string cleared on save)
NULL_LOCATION_TOKENS = {
    "null", "none", "nil", "n/a", "na", "n.a.", "undefined", "unknown",
    "not set", "no location", "-", "--", ".", "?", "b", "www", "e23e", "1,-1",
    "kf", "rnd", "nig", "zh", "bj", "sl",  # too short / ambiguous to trust
    # regions / multi-country without a country
    "eu", "europe", "european union", "asia", "africa", "scandinavia",
    "undefined, africa", "west africa",
    # world / remote jokes
    "world", "the world", "everywhere", "somewhere", "anywhere", "here",
    "planet", "earth", "planet earth", "on the earth", "somewhere, earth",
    "moon", "milky way", "milky way galaxy", "virgo supercluster", "galaxy",
    "metaverse", "offworld", "ice kingdom", "stairway to heaven",
    "in the fabric of reality.", "in the fabric of reality",
    "across the wire", "digitalnomad on two wheels", "nomad", "moving around",
    "wherever i am that day", "my home", "in my house", "fancore",
    "remote", "worldwide", "worldwide remote", "work from home", "wfh",
    "somewhere on earth", "internet", "the internet", "terminal",
    "cyberspace", "online", "global", "rivendell, middle earth",
    # localhost / urls / junk
    "127.0.0.1", "127.0.0.1:3000", "public_html/_views/groups/register",
    # emoji-only / multi-flag / bare globe
    "🌐",
    "🇸🇪 🇮🇸 🏳️‍🌈",
}

# ---------------------------------------------------------------------------
# Alias lists per country slug. Add new places here when unknowns appear.
# Longer phrases are preferred automatically (sorted by length at load time).
# ---------------------------------------------------------------------------

COUNTRY_ALIAS_GROUPS: dict[str, list[str]] = {
    "usa": [
        "united states of america", "united states", "u.s.a.", "u.s.a", "u.s.", "usa",
        "america",
        "new york", "los angeles", "san francisco", "san diego", "san jose",
        "seattle", "chicago", "boston", "austin", "dallas", "houston", "denver",
        "atlanta", "miami", "portland", "phoenix", "philadelphia",
        "california", "texas", "florida", "el dorado hills", "sacramento", "oakland",
        "washington dc", "washington d.c.", "new jersey", "massachusetts", "colorado",
        "illinois", "pennsylvania", "arizona", "georgia", "ohio", "michigan", "oregon",
        "nevada", "virginia", "north carolina", "south carolina", "minnesota",
        "wisconsin", "maryland", "utah", "tennessee", "missouri", "indiana",
        "connecticut",         "brooklyn", "manhattan", "silicon valley", "bay area",
        "pittsburgh", "new orleans", "sunnyvale", "columbus", "philadelphia",
        "philladelphia", "philly", "nola", "minneapolis", "st paul", "saint paul",
        "san mateo", "twin cities", "st louis", "st. louis", "saint louis",
        "honolulu", "salt lake city", "high point", "palo alto", "nyc",
        "new york city", "greater nyc", "greater nyc area", "los angels",
        "alabama", "alaska", "arkansas", "delaware", "hawaii", "idaho", "iowa",
        "kansas", "kentucky", "louisiana", "maine", "mississippi", "montana",
        "nebraska", "new hampshire", "new mexico", "north dakota", "oklahoma",
        "rhode island", "south dakota", "vermont", "west virginia", "wyoming",
    ],
    "uk": [
        "united kingdom", "great britain", "england", "scotland", "wales",
        "northern ireland", "london", "manchester", "birmingham", "edinburgh",
        "glasgow", "bristol", "leeds", "liverpool", "sheffield", "cardiff",
        "belfast", "u.k.", "uk", "britain",
    ],
    "canada": [
        "canada", "toronto", "vancouver", "vancover", "montreal", "ottawa", "calgary",
        "edmonton", "winnipeg", "ontario", "british columbia", "quebec",
        "alberta", "manitoba", "saskatchewan", "nova scotia",
    ],
    "australia": [
        "australia", "sydney", "melbourne", "brisbane", "perth", "adelaide",
        "canberra", "hobart", "gold coast",
    ],
    "new_zealand": [
        "new zealand", "auckland", "wellington", "christchurch",
    ],
    "germany": [
        "germany", "deutschland", "berlin", "munich", "münchen", "hamburg",
        "frankfurt", "cologne", "köln", "stuttgart", "düsseldorf", "dortmund",
        "leipzig", "dresden", "karlsruhe",
    ],
    "france": [
        "france", "paris", "lyon", "marseille", "toulouse", "nice", "bordeaux",
        "nantes", "strasbourg", "villeurbanne", "clamart",
    ],
    "netherlands": [
        "netherlands", "holland", "amsterdam", "rotterdam", "utrecht", "hague",
        "the hague", "eindhoven",
    ],
    "belgium": [
        "belgium", "brussels", "antwerp", "ghent", "bruges", "belgië", "belgique",
    ],
    "switzerland": [
        "switzerland", "swiss", "zurich", "geneva", "bern", "basel", "lausanne",
        "schweiz", "suisse",
    ],
    "austria": [
        "austria", "vienna", "wien", "salzburg", "graz", "österreich",
    ],
    "ireland": [
        "ireland", "dublin", "cork", "galway", "limerick", "éire",
    ],
    "spain": [
        "spain", "españa", "madrid", "barcelona", "valencia", "seville", "sevilla",
        "malaga", "málaga", "bilbao", "vigo", "galicia", "palma de mallorca",
        "palma", "mallorca",
    ],
    "portugal": [
        "portugal", "lisbon", "lisboa", "porto", "braga",
    ],
    "italy": [
        "italy", "italia", "rome", "roma", "milan", "milano", "naples", "napoli",
        "turin", "torino", "florence", "firenze", "bologna",
    ],
    "greece": [
        "greece", "hellas", "ελλάδα", "athens", "athina", "thessaloniki",
        "patras", "heraklion", "larissa", "volos", "kilkis", "crete", "krete",
    ],
    "poland": [
        "poland", "polska", "warsaw", "warszawa", "krakow", "kraków", "wroclaw",
        "wrocław", "gdansk", "gdańsk", "poznan", "poznań", "lodz", "łódź", "rybnik",
    ],
    "sweden": [
        "sweden", "sverige", "stockholm", "gothenburg", "göteborg", "malmo", "malmö",
    ],
    "norway": [
        "norway", "norge", "oslo", "bergen", "trondheim", "hamar",
    ],
    "denmark": [
        "denmark", "danmark", "copenhagen", "københavn", "aarhus",
    ],
    "finland": [
        "finland", "suomi", "helsinki", "tampere", "turku", "espoo",
    ],
    "czech_republic": [
        "czech republic", "czechia", "czech", "prague", "praha", "brno",
        "pardubice", "ostrava", "plzen", "pilsen",
    ],
    "romania": [
        "romania", "românia", "bucharest", "bucurești", "cluj", "timisoara",
    ],
    "hungary": [
        "hungary", "magyarország", "budapest", "szeged", "debrecen", "pecs", "pécs",
        "szekesfehervar", "székesfehérvár",
    ],
    "bulgaria": [
        "bulgaria", "sofia", "plovdiv", "varna",
    ],
    "serbia": [
        "serbia", "belgrade", "beograd", "novi sad",
    ],
    "croatia": [
        "croatia", "hrvatska", "zagreb", "split", "dubrovnik", "osijek",
    ],
    "slovakia": [
        "slovakia", "bratislava",
    ],
    "slovenia": [
        "slovenia", "ljubljana",
    ],
    "ukraine": [
        "ukraine", "ukraina", "kyiv", "kiev", "kharkiv", "odesa", "odessa", "lviv",
        "dnipro", "dnipropetrovsk", "vinnytsia", "vinnitsa",
    ],
    "russia": [
        "russia", "russian federation", "moscow", "saint petersburg",
        "st petersburg", "st. petersburg", "санкт-петербург", "vladivostok",
        "kaliningrad", "novosibirsk", "yekaterinburg", "kazan", "nizhny novgorod",
        "samara", "ufa", "komsomolsk-on-amur", "komsomolsk",
    ],
    "turkey": [
        "turkey", "türkiye", "turkiye", "istanbul", "ankara", "izmir", "bursa",
        "antalya",
    ],
    "israel": [
        "israel", "tel aviv", "tel-aviv", "jerusalem", "haifa",
    ],
    "palestine": [
        "palestine", "gaza", "ramallah",
    ],
    "uae": [
        "uae", "united arab emirates", "dubai", "abu dhabi", "sharjah",
    ],
    "saudi_arabia": [
        "saudi arabia", "riyadh", "jeddah", "mecca", "medina", "dammam",
    ],
    "qatar": [
        "qatar", "doha",
    ],
    "kuwait": [
        "kuwait", "kuwait city",
    ],
    "bahrain": [
        "bahrain", "manama",
    ],
    "oman": [
        "oman", "muscat",
    ],
    "jordan": [
        "jordan", "amman",
    ],
    "lebanon": [
        "lebanon", "beirut",
    ],
    "syria": [
        "syria", "damascus", "aleppo",
    ],
    "iraq": [
        "iraq", "baghdad", "basra", "erbil", "mosul",
    ],
    "iran": [
        "iran", "tehran", "isfahan", "shiraz", "mashhad", "qom", "tabriz",
    ],
    "afghanistan": [
        "afghanistan", "kabul",
    ],
    "pakistan": [
        "pakistan", "karachi", "lahore", "islamabad", "rawalpindi", "peshawar",
        "faisalabad",
    ],
    "india": [
        "india", "bharat", "bangalore", "bengaluru", "mumbai", "delhi", "new delhi",
        "hyderabad", "chennai", "kolkata", "pune", "ahmedabad", "surat", "jaipur",
        "lucknow", "kanpur", "nagpur", "indore", "thane", "bhopal", "patna", "noida",
        "gurgaon", "gurugram", "coimbatore", "kochi", "chandigarh", "vadodara",
        "ghaziabad", "ludhiana", "agra", "nashik", "faridabad", "meerut", "rajkot",
        "varanasi", "srinagar", "aurangabad", "amritsar", "navi mumbai", "allahabad",
        "prayagraj", "raipur", "gwalior", "jabalpur", "madurai", "guwahati", "jodhpur",
        "bhubaneswar", "salem", "warangal", "guntur", "gorakhpur", "bikaner",
        "amravati", "jamshedpur", "bhilai", "cuttack", "kota", "mangalore",
        "mangaluru", "dehradun", "durgapur", "asansol", "nanded", "kolhapur", "ajmer",
        "gulbarga", "jalandhar", "udaipur", "thiruvananthapuram", "trivandrum",
        "gandhinagar", "tiruppur", "visakhapatnam", "kerala", "kannur", "kozhikode",
        "calicut", "thrissur", "trivandrum", "banglore", "bengalooru",
        "andhra pradesh", "andhra", "nandyal", "behaluru", "vijayawada",
        "visakhapatnam", "vizag", "tirupati", "warangal", "guntur",
        "alwar", "hajipur", "nellore", "kottayam", "mathura", "karnataka",
        "cochin", "kochi", "rourkela", "purnia", "uttar pradesh",
    ],
    "bangladesh": [
        "bangladesh", "dhaka", "chittagong", "chattogram", "khulna",
    ],
    "sri_lanka": [
        "sri lanka", "colombo", "kandy",
    ],
    "nepal": [
        "nepal", "kathmandu", "pokhara",
    ],
    "bhutan": [
        "bhutan", "thimphu",
    ],
    "myanmar": [
        "myanmar", "burma", "yangon", "rangoon", "mandalay", "naypyidaw",
    ],
    "thailand": [
        "thailand", "bangkok", "chiang mai", "phuket",
    ],
    "vietnam": [
        "vietnam", "viet nam", "hanoi", "ha noi", "ho chi minh", "ho chi minh city",
        "hcmc", "tp ho chi minh", "tp.hcm", "tphcm", "saigon", "sai gon",
        "da nang", "danang", "da nang city",
    ],
    "cambodia": [
        "cambodia", "phnom penh", "siem reap",
    ],
    "laos": [
        "laos", "vientiane",
    ],
    "malaysia": [
        "malaysia", "kuala lumpur", "penang", "johor bahru", "malacca", "melaka",
    ],
    "singapore": [
        "singapore",
    ],
    "indonesia": [
        "indonesia", "jakarta", "jakarata", "bali", "surabaya", "bandung", "medan",
        "bekasi", "idn", "ina", "yogya", "yogyakarta", "jogja", "depok", "tangerang",
        "makassar", "semarang", "palembang", "penajam", "north penajam paser",
        "penajam paser",
    ],
    "philippines": [
        "philippines", "manila", "cebu", "davao", "quezon city", "makati",
        "pasig", "taguig",
    ],
    "taiwan": [
        "taiwan", "taipei", "kaohsiung", "taichung",
    ],
    "hong_kong": [
        "hong kong", "hongkong",
    ],
    "macau": [
        "macau", "macao",
    ],
    "china": [
        "china", "prc", "beijing", "shanghai", "shenzhen", "guangzhou", "hangzhou",
        "chengdu", "wuhan", "nanjing", "xi'an", "xian", "suzhou", "tianjin",
    ],
    "mongolia": [
        "mongolia", "ulaanbaatar",
    ],
    "japan": [
        "japan", "tokyo", "osaka", "kyoto", "yokohama", "nagoya", "sapporo", "fukuoka",
        "kobe", "kanazawa", "san mateo, kanazawa",
    ],
    "south_korea": [
        "south korea", "korea", "republic of korea", "seoul", "busan", "incheon",
        "daegu", "daejeon",
    ],
    "north_korea": [
        "north korea", "dprk", "pyongyang",
    ],
    "egypt": [
        "egypt", "cairo", "alexandria", "giza",
    ],
    "morocco": [
        "morocco", "casablanca", "rabat", "marrakech", "marrakesh", "fez",
        "ouarzazate",
    ],
    "algeria": [
        "algeria", "algiers",
    ],
    "tunisia": [
        "tunisia", "tunis",
    ],
    "libya": [
        "libya", "tripoli",
    ],
    "sudan": [
        "sudan", "khartoum",
    ],
    "ethiopia": [
        "ethiopia", "addis ababa", "addis abeba",
    ],
    "kenya": [
        "kenya", "nairobi", "mombasa",
    ],
    "uganda": [
        "uganda", "kampala",
    ],
    "tanzania": [
        "tanzania", "dar es salaam", "dodoma",
    ],
    "rwanda": [
        "rwanda", "kigali",
    ],
    "nigeria": [
        "nigeria", "nigerian", "lagos", "abuja", "port harcourt", "ibadan", "kano",
        "ebonyi", "ebonyi state", "kaduna", "kwara", "umuahia", "ile-ife",
        "benin city", "edo state", "gombe", "yenagoa", "bayelsa", "bayelsa state",
    ],
    "ghana": [
        "ghana", "accra", "kumasi", "🇬🇭",
    ],
    "ivory_coast": [
        "ivory coast", "côte d'ivoire", "cote d'ivoire", "abidjan",
    ],
    "senegal": [
        "senegal", "dakar",
    ],
    "cameroon": [
        "cameroon", "yaounde", "yaoundé", "douala", "buea",
    ],
    "south_africa": [
        "south africa", "cape town", "johannesburg", "pretoria", "durban",
    ],
    "zimbabwe": [
        "zimbabwe", "harare",
    ],
    "mozambique": [
        "mozambique", "maputo",
    ],
    "angola": [
        "angola", "luanda",
    ],
    "mauritius": [
        "mauritius", "port louis",
    ],
    "mauritania": [
        "mauritania", "nouakchott", "nouadhibou",
    ],
    "madagascar": [
        "madagascar", "antananarivo",
    ],
    "maldives": [
        "maldives", "malé", "republic of maldives",
    ],
    "brazil": [
        "brazil", "brasil", "são paulo", "sao paulo", "rio de janeiro", "rio",
        "brasília", "brasilia", "salvador", "fortaleza", "belo horizonte",
        "manaus", "curitiba", "recife", "porto alegre", "belém", "belem",
        "goiânia", "goiania", "guarulhos", "campinas", "são luís", "sao luis",
        "maceió", "maceio", "macio", "mació", "natal", "cuiaba", "cuiabá",
        "campo grande", "florianópolis", "florianopolis", "joão pessoa",
        "joao pessoa", "alagoas", "vista serrana", "taboao da serra",
        "taboão da serra", "sao bernardo", "osasco", "sorocaba",
        "piracicaba", "contagem", "quintana", "bazil",  # common typo for brasil
        "colinas do tocantins", "tocantins", "joinville", "santa catarina",
        "anapolis", "anápolis",
    ],
    "argentina": [
        "argentina", "buenos aires", "córdoba", "cordoba", "rosario", "mendoza",
        "neuquen", "neuquén", "neuquen capital",
    ],
    "chile": [
        "chile", "santiago", "valparaíso", "valparaiso",
    ],
    "colombia": [
        "colombia", "bogota", "bogotá", "medellin", "medellín", "cali", "barranquilla",
    ],
    "peru": [
        "peru", "perú", "lima", "cusco", "arequipa",
    ],
    "venezuela": [
        "venezuela", "caracas", "maracaibo",
    ],
    "ecuador": [
        "ecuador", "quito", "guayaquil",
    ],
    "bolivia": [
        "bolivia", "la paz", "santa cruz", "sucre",
    ],
    "paraguay": [
        "paraguay", "asuncion", "asunción",
    ],
    "uruguay": [
        "uruguay", "montevideo",
    ],
    "mexico": [
        "mexico", "méxico", "mexico city", "ciudad de mexico", "ciudad de méxico",
        "cdmx", "guadalajara", "monterrey", "mty", "puebla", "tijuana", "cancun",
        "cancún", "merida", "mérida", "yucatan", "yucatán", "yucatan peninsula",
    ],
    "guatemala": [
        "guatemala", "guatemala city",
    ],
    "costa_rica": [
        "costa rica", "san jose costa rica", "san josé",
    ],
    "nicaragua": [
        "nicaragua", "managua", "leon", "león", "granada", "masaya",
        "matagalpa", "chinandega", "esteli", "estelí",
    ],
    "honduras": [
        "honduras", "tegucigalpa", "san pedro sula",
    ],
    "el_salvador": [
        "el salvador", "san salvador",
    ],
    "panama": [
        "panama", "panamá", "panama city",
    ],
    "cuba": [
        "cuba", "havana", "la habana",
    ],
    "dominican_republic": [
        "dominican republic", "republica dominicana", "república dominicana",
        "santo domingo",
    ],
    "puerto_rico": [
        "puerto rico", "san juan",
    ],
    "jamaica": [
        "jamaica", "kingston",
    ],
    "trinidad_and_tobago": [
        "trinidad and tobago", "trinidad", "port of spain",
    ],
    "iceland": [
        "iceland", "reykjavik", "reykjavík",
    ],
    "estonia": [
        "estonia", "tallinn",
    ],
    "latvia": [
        "latvia", "riga",
    ],
    "lithuania": [
        "lithuania", "vilnius",
    ],
    "belarus": [
        "belarus", "minsk",
    ],
    "moldova": [
        "moldova", "chisinau", "chișinău",
    ],
    "georgia_country": [
        # slug avoids clash with US state "georgia" (US aliases are longer / checked via states)
        "tbilisi", "batumi", "sakartvelo",
    ],
    "armenia": [
        "armenia", "yerevan",
    ],
    "azerbaijan": [
        "azerbaijan", "baku",
    ],
    "kazakhstan": [
        "kazakhstan", "almaty", "astana", "nur-sultan",
    ],
    "kyrgyzstan": [
        "kyrgyzstan", "kyrgyz", "bishkek", "osh", "kirgizstan", "kirghizstan",
    ],
    "uzbekistan": [
        "uzbekistan", "tashkent",
    ],
    "cyprus": [
        "cyprus", "nicosia", "limassol",
    ],
    "malta": [
        "malta", "valletta",
    ],
    "luxembourg": [
        "luxembourg",
    ],
    "monaco": [
        "monaco",
    ],
    "andorra": [
        "andorra",
    ],
    "liechtenstein": [
        "liechtenstein",
    ],
    "albania": [
        "albania", "tirana",
    ],
    "north_macedonia": [
        "north macedonia", "macedonia", "skopje",
    ],
    "bosnia": [
        "bosnia", "bosnia and herzegovina", "sarajevo",
    ],
    "montenegro": [
        "montenegro", "podgorica",
    ],
    "kosovo": [
        "kosovo", "pristina", "prishtina", "prishtine", "kosove",
    ],
}

# Extra aliases from unknown backlog (merged before alias list is built).
_EXTRA_ALIASES: dict[str, list[str]] = {
    "usa": [
        "washington, d.c.", "washington, dc", "washington dc", "washington",
        "atl", "milwaukee", "raleigh", "richmond", "las vegas", "indianapolis",
        "cincinnati", "san antonio", "bakersfield", "fort wayne", "boca raton",
        "corona", "ellensburg", "brookyln", "brooklyn", "sfo",
    ],
    "uk": [
        "croydon", "guildford", "cambridge", "milton keynes", "bracknell",
    ],
    "france": [
        "lille", "annecy", "clermont-ferrand", "rouen",
        "montpellier", "guyancourt", "limoges", "sophia antipolis", "french alps",
    ],
    "spain": [
        "alcorcon", "alcorcón", "badajoz", "menorca", "las palmas de gran canaria",
        "las palmas",
    ],
    "germany": [
        "leverkusen", "saarland", "lower saxony", "nds",
    ],
    "netherlands": [
        "nederland", "neitherland", "netherland", "amstelveen", "breda", "breda(nl)",
    ],
    "belgium": [
        "bruxelles", "tienen",
    ],
    "sweden": [
        "lund",
    ],
    "hungary": [
        "pomaz", "gyor", "győr", "nyireyhaza", "nyíreyháza",
    ],
    "poland": [
        "bialystok", "białystok", "radom", "czestochowa", "częstochowa",
        "bydgoszcz", "cracow", "katowice",
    ],
    "slovakia": [
        "komarno", "komárno",
    ],
    "serbia": [
        "nis", "niš",
    ],
    "romania": [
        "craiova",
    ],
    "italy": [
        "cagliari", "frosinone", "brescia", "nicotera",
    ],
    "slovenia": [
        "maribor",
    ],
    "croatia": [
        "pula",
    ],
    "ukraine": [
        "sumy", "crimea", "sevastopol",
    ],
    "russia": [
        "bryansk", "saint-petersburg", "fryazino", "tver", "krasnodar",
        "stavropol", "yakutsk",
    ],
    "turkey": [
        "balikesir", "balıkesir",
    ],
    "israel": [
        "ashdod", "isarel",
    ],
    "uae": [
        "uaeu",
    ],
    "bahrain": [
        "diraz",
    ],
    "china": [
        "bei jing", "beijing", "qingdao", "dongguan", "dongtan", "guiyang", "贵阳",
        "kunming", "昆明",
    ],
    "hong_kong": [
        "hon kong",
    ],
    "japan": [
        "kawasaki",
    ],
    "india": [
        "ranchi", "bareilly", "indian", "bihar", "rajasthan", "sringeri",
        "kurukshetra", "haryana", "sivaganga", "tamil nadu", "tamilnadu",
        "goa", "khagaria", "chakradharpur", "karnal", "sundernagar",
        "himachal pradesh", "silchar", "virar", "gautambudh nagar",
        "vizianagaram", "theni", "kharagpur", "mandapeta", "assam",
        "junagadh", "gaya", "mysore", "rajamundry", "bhadreswar",
    ],
    "pakistan": [
        "abbottabad", "sahiwal",
    ],
    "nepal": [
        "lalitpur", "ktm",
    ],
    "sri_lanka": [
        "matara", "srilanka",
    ],
    "indonesia": [
        "malang", "jawa timur", "west java", "probolinggo", "sidoarjo",
        "tuban", "tulungagung",
    ],
    "malaysia": [
        "kl",
    ],
    "thailand": [
        "bkk", "chonburi", "bangkon", "bangkok",
    ],
    "vietnam": [
        "hochiminh city", "ho chi minh city",
    ],
    "philippines": [
        "philipppines",
    ],
    "taiwan": [
        "formosa",
    ],
    "australia": [
        "vic", "victoria",
    ],
    "namibia": [
        "namibia", "windhoek",
    ],
    "zambia": [
        "zambia", "lusaka",
    ],
    "malawi": [
        "malawi",
    ],
    "botswana": [
        "botswana", "gaborone",
    ],
    "eswatini": [
        "eswatini", "swaziland",
    ],
    "congo": [
        "congo", "drc", "drcongo", "democratic republic of congo",
        "democratic republic of the congo", "goma", "bukavu", "nord-kivu",
        "nord kivu",
    ],
    "burundi": [
        "burundi", "bujumbura",
    ],
    "sierra_leone": [
        "sierra leone", "freetown",
    ],
    "cape_verde": [
        "cape verde", "cabo verde",
    ],
    "gabon": [
        "gabon", "libreville",
    ],
    "benin": [
        "bénin", "cotonou",
        # bare "benin" omitted — "Benin City" is Nigeria (longer alias wins there)
    ],
    "brazil": [
        "mogi das cruzes", "sao jose dos campos", "são josé dos campos",
        "salto-sp", "salto", "vila velha", "itapipoca", "franca", "franca/sp",
        "tabuleiro do norte", "antonio carlos", "antônio carlos",
        "campina grande", "paraiba", "paraíba", "sinop", "brazi", "beazil",
        "londrina", "cascavel", "jundiai", "jundiaí", "seropedica", "seropédica",
        "cianorte", "campo mourao", "campo mourão", "cotegipe", "bahia",
    ],
    "mexico": [
        "zapopan", "jalisco", "hermosillo", "son", "veracruz", "sinaloa",
        "culiacan", "culiacán",
    ],
    "argentina": [
        "argentine", "san miguel de tucuman", "san miguel de tucumán",
    ],
    "colombia": [
        "manizales", "bog",
    ],
    "chile": [
        "valdivia",
    ],
    "peru": [
        "barranca",
    ],
    "cyprus": [
        "kyrenia",
    ],
    "guernsey": [
        "guernsey",
    ],
    "uzbekistan": [
        "andizkhan", "andijan",
    ],
    "turkmenistan": [
        "turkmenistan", "ashgabat",
    ],
}

for _country, _aliases in _EXTRA_ALIASES.items():
    COUNTRY_ALIAS_GROUPS.setdefault(_country, []).extend(_aliases)

# ISO 3166-1 alpha-3 (and a few safe alpha-2) when the whole location is just the code.
# Intentionally excludes codes that clash with US states / CA provinces (e.g. ID, IN, OR, ON, CA).
ISO_CODE_TO_COUNTRY: dict[str, str] = {
    "usa": "usa", "us": "usa", "um": "usa",
    "gbr": "uk", "gb": "uk", "uk": "uk",
    "can": "canada",
    "aus": "australia", "au": "australia",
    "nzl": "new_zealand", "nz": "new_zealand",
    "deu": "germany", "de": "germany",
    "fra": "france", "fr": "france",
    "nld": "netherlands", "nl": "netherlands",
    "bel": "belgium", "be": "belgium",
    "che": "switzerland", "ch": "switzerland",
    "aut": "austria", "at": "austria",
    "irl": "ireland", "ie": "ireland",
    "esp": "spain", "es": "spain",
    "prt": "portugal", "pt": "portugal",
    "ita": "italy", "it": "italy",
    "grc": "greece", "gr": "greece",
    "pol": "poland", "pl": "poland",
    "swe": "sweden", "se": "sweden",
    "nor": "norway", "no": "norway",
    "dnk": "denmark", "dk": "denmark",
    "fin": "finland", "fi": "finland",
    "cze": "czech_republic", "cz": "czech_republic",
    "rou": "romania", "ro": "romania",
    "hun": "hungary", "hu": "hungary",
    "bgr": "bulgaria", "bg": "bulgaria",
    "srb": "serbia", "rs": "serbia",
    "hrv": "croatia", "hr": "croatia",
    "svk": "slovakia", "sk": "slovakia",  # sk also Saskatchewan — bare SK handled as CA province first
    "svn": "slovenia", "si": "slovenia",
    "ukr": "ukraine", "ua": "ukraine",
    "rus": "russia", "ru": "russia",
    "tur": "turkey", "tr": "turkey",
    "isr": "israel", "il": "israel",  # il also Illinois — bare IL is US state first
    "are": "uae", "ae": "uae",
    "sau": "saudi_arabia", "sa": "saudi_arabia",
    "qat": "qatar", "qa": "qatar",
    "kwt": "kuwait", "kw": "kuwait",
    "bhr": "bahrain", "bh": "bahrain",
    "omn": "oman", "om": "oman",
    "jor": "jordan", "jo": "jordan",
    "lbn": "lebanon", "lb": "lebanon",
    "syr": "syria", "sy": "syria",
    "irq": "iraq", "iq": "iraq",
    "irn": "iran", "ir": "iran",
    "afg": "afghanistan", "af": "afghanistan",
    "pak": "pakistan", "pk": "pakistan",
    "ind": "india",  # not "in" — Indiana
    "bgd": "bangladesh", "bd": "bangladesh",
    "lka": "sri_lanka", "lk": "sri_lanka",
    "npl": "nepal", "np": "nepal",
    "mmr": "myanmar", "mm": "myanmar",
    "tha": "thailand", "th": "thailand",
    "vnm": "vietnam", "vn": "vietnam",
    "khm": "cambodia", "kh": "cambodia",
    "lao": "laos", "la": "laos",
    "mys": "malaysia", "my": "malaysia",
    "sgp": "singapore", "sg": "singapore",
    "idn": "indonesia",  # not "id" — Idaho
    "phl": "philippines", "ph": "philippines",
    "twn": "taiwan", "tw": "taiwan",
    "hkg": "hong_kong", "hk": "hong_kong",
    "mac": "macau", "mo": "macau",
    "chn": "china", "cn": "china",
    "mng": "mongolia", "mn": "mongolia",  # mn also Minnesota — bare MN is US first
    "jpn": "japan", "jp": "japan",
    "kor": "south_korea", "kr": "south_korea",
    "prk": "north_korea", "kp": "north_korea",
    "egy": "egypt", "eg": "egypt",
    "mar": "morocco", "ma": "morocco",  # ma also Massachusetts
    "dza": "algeria", "dz": "algeria",
    "tun": "tunisia", "tn": "tunisia",  # tn also Tennessee
    "lby": "libya", "ly": "libya",
    "sdn": "sudan", "sd": "sudan",  # sd also South Dakota
    "eth": "ethiopia", "et": "ethiopia",
    "ken": "kenya", "ke": "kenya",
    "uga": "uganda", "ug": "uganda",
    "tza": "tanzania", "tz": "tanzania",
    "rwa": "rwanda", "rw": "rwanda",
    "nga": "nigeria", "ng": "nigeria",
    "gha": "ghana", "gh": "ghana",
    "civ": "ivory_coast", "ci": "ivory_coast",
    "sen": "senegal", "sn": "senegal",
    "cmr": "cameroon", "cm": "cameroon",
    "zaf": "south_africa", "za": "south_africa",
    "zwe": "zimbabwe", "zw": "zimbabwe",
    "moz": "mozambique", "mz": "mozambique",
    "ago": "angola", "ao": "angola",
    "mrt": "mauritania", "mr": "mauritania",
    "mdv": "maldives", "mv": "maldives",
    "mus": "mauritius", "mu": "mauritius",
    "mdg": "madagascar", "mg": "madagascar",
    "bra": "brazil", "br": "brazil",
    "arg": "argentina", "ar": "argentina",  # ar also Arkansas — bare AR is US first
    "chl": "chile", "cl": "chile",
    "col": "colombia", "co": "colombia",  # co also Colorado
    "per": "peru", "pe": "peru",  # pe also Prince Edward Island
    "ven": "venezuela", "ve": "venezuela",
    "ecu": "ecuador", "ec": "ecuador",
    "bol": "bolivia", "bo": "bolivia",
    "pry": "paraguay", "py": "paraguay",
    "ury": "uruguay", "uy": "uruguay",
    "mex": "mexico", "mx": "mexico",
    "gtm": "guatemala", "gt": "guatemala",
    "cri": "costa_rica", "cr": "costa_rica",
    "nic": "nicaragua", "ni": "nicaragua",
    "hnd": "honduras", "hn": "honduras",
    "slv": "el_salvador", "sv": "el_salvador",
    "pan": "panama", "pa": "panama",  # pa also Pennsylvania
    "cub": "cuba", "cu": "cuba",
    "dom": "dominican_republic", "do": "dominican_republic",
    "pri": "puerto_rico", "pr": "puerto_rico",
    "jam": "jamaica", "jm": "jamaica",
    "tto": "trinidad_and_tobago", "tt": "trinidad_and_tobago",
    "isl": "iceland", "is": "iceland",
    "est": "estonia", "ee": "estonia",
    "lva": "latvia", "lv": "latvia",
    "ltu": "lithuania", "lt": "lithuania",
    "blr": "belarus", "by": "belarus",
    "mda": "moldova", "md": "moldova",  # md also Maryland
    "geo": "georgia_country", "ge": "georgia_country",  # ge also Georgia US — bare GE is US first via state list? ge is not a US state abbrev. GA is.
    "arm": "armenia", "am": "armenia",
    "aze": "azerbaijan", "az": "azerbaijan",  # az also Arizona
    "kaz": "kazakhstan", "kz": "kazakhstan",
    "kgz": "kyrgyzstan", "kg": "kyrgyzstan",
    "uzb": "uzbekistan", "uz": "uzbekistan",
    "cyp": "cyprus", "cy": "cyprus",
    "mlt": "malta", "mt": "malta",  # mt also Montana
    "lux": "luxembourg", "lu": "luxembourg",
    "mco": "monaco", "mc": "monaco",
    "and": "andorra", "ad": "andorra",
    "lie": "liechtenstein", "li": "liechtenstein",
    "alb": "albania", "al": "albania",  # al also Alabama
    "mkd": "north_macedonia", "mk": "north_macedonia",
    "bih": "bosnia", "ba": "bosnia",
    "mne": "montenegro", "me": "montenegro",  # me also Maine
    "xkx": "kosovo", "xk": "kosovo",
    "nam": "namibia", "na": "namibia",  # na also null-token when alone
    "zmb": "zambia", "zm": "zambia",
    "mwi": "malawi", "mw": "malawi",
    "bwa": "botswana", "bw": "botswana",
    "swz": "eswatini", "sz": "eswatini",
    "cod": "congo", "cd": "congo",
    "bdi": "burundi", "bi": "burundi",
    "sle": "sierra_leone",  # not bare "sl" — ambiguous
    "cpv": "cape_verde", "cv": "cape_verde",
    "btn": "bhutan",
    "pse": "palestine",
    "gab": "gabon", "ga": "gabon",  # ga also Georgia US — bare GA is US state first
    "ben": "benin", "bj": "benin",  # bj also null-token / Beijing abbrev — null wins when alone
    "tkm": "turkmenistan", "tm": "turkmenistan",
    "ggy": "guernsey", "gg": "guernsey",
}


def _fold(text: str) -> str:
    """Lowercase, strip diacritics, trim trailing punctuation: 'CN.' → 'cn'."""
    text = text.strip().lower()
    decomposed = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[.\u3002]+$", "", text)  # trailing dots
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_alias_list() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for country, aliases in COUNTRY_ALIAS_GROUPS.items():
        for alias in aliases:
            folded = _fold(alias)
            if folded:
                pairs.append((folded, country))
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return pairs


COUNTRY_ALIASES: list[tuple[str, str]] = _build_alias_list()

_US_STATE_ALT = "|".join(sorted(US_STATE_ABBREVS))
_CA_PROV_ALT = "|".join(sorted(CA_PROVINCE_ABBREVS))
_BR_STATE_ALT = "|".join(sorted(BR_STATE_ABBREVS))
# Prefer longer ISO codes first (e.g. "usa" before "us")
_ISO_ALT = "|".join(sorted(ISO_CODE_TO_COUNTRY.keys(), key=len, reverse=True))

US_STATE_ABBREV_RE = re.compile(
    # "Palo Alto, CA" or "Palo Alto, CA 94306"
    rf",\s*({_US_STATE_ALT})(?:\s+\d{{5}}(?:-\d{{4}})?)?\.?\s*$",
    re.IGNORECASE,
)
# "Sunnyvale CA" / "Columbus OH" (space, no comma)
US_STATE_SPACE_RE = re.compile(
    rf"[a-z0-9]\s+({_US_STATE_ALT})\.?\s*$",
    re.IGNORECASE,
)
CA_PROVINCE_ABBREV_RE = re.compile(
    rf",\s*({_CA_PROV_ALT})\.?\s*$",
    re.IGNORECASE,
)
BR_STATE_ABBREV_RE = re.compile(
    rf",\s*({_BR_STATE_ALT})\b",
    re.IGNORECASE,
)
# "Szeged, HU" / "taboao..., SP - BR" / "Mty, Mx"
TRAILING_ISO_RE = re.compile(
    rf"(?:,|\s[-–/]\s|\s)({_ISO_ALT})\.?\s*$",
    re.IGNORECASE,
)


def normalize_location(location: str | None) -> str:
    try:
        return _fold(location or "")
    except Exception:
        return ""


def detect_country(location: str | None) -> str:
    """
    Map free-text location → country slug or 'noloc'.

    Unmatched / joke / vague strings return 'noloc' (no more 'unknown' bucket).
    """
    normalized = normalize_location(location)
    if not normalized or normalized in NULL_LOCATION_TOKENS:
        return "noloc"
    # Bare URLs / paths are not places
    if normalized.startswith(("http://", "https://", "www.")):
        return "noloc"

    # Bare admin abbreviations win over ISO when they clash (IL, IN, ID, ...).
    if normalized in US_STATE_ABBREVS:
        return "usa"
    if normalized in CA_PROVINCE_ABBREVS:
        return "canada"

    if normalized in ISO_CODE_TO_COUNTRY:
        return ISO_CODE_TO_COUNTRY[normalized]

    for alias, country in COUNTRY_ALIASES:
        pattern = r"(?:^|[^a-z0-9])" + re.escape(alias) + r"(?:[^a-z0-9]|$)"
        if re.search(pattern, normalized):
            return country

    # Comma/slash-separated codes: "IR,HMD,NVD" → iran via IR
    for part in re.split(r"[,;/|]+", normalized):
        part = part.strip()
        if not part:
            continue
        if part in US_STATE_ABBREVS:
            return "usa"
        if part in CA_PROVINCE_ABBREVS:
            return "canada"
        if part in ISO_CODE_TO_COUNTRY:
            return ISO_CODE_TO_COUNTRY[part]

    if US_STATE_ABBREV_RE.search(normalized) or US_STATE_SPACE_RE.search(normalized):
        return "usa"
    if CA_PROVINCE_ABBREV_RE.search(normalized):
        return "canada"
    if BR_STATE_ABBREV_RE.search(normalized):
        return "brazil"

    m = TRAILING_ISO_RE.search(normalized)
    if m:
        code = m.group(1).lower()
        if code in US_STATE_ABBREVS:
            return "usa"
        if code in CA_PROVINCE_ABBREVS:
            return "canada"
        if code in ISO_CODE_TO_COUNTRY:
            return ISO_CODE_TO_COUNTRY[code]

    return "noloc"


# Stored location text: "City, XXX" or "XXX".
# US / UK / UAE keep their short names. Every other country uses its
# ISO alpha-3 code. A US place with a state stays "City, ST".

_MANUAL_COUNTRY_CODES = {
    "usa": "US",
    "uk": "UK",
    "uae": "UAE",
}

_COUNTRY_NAME_EXTRAS: dict[str, set[str]] = {
    "usa": {"united states", "united states of america", "america", "usa", "us", "u s a", "u s"},
    "uk": {
        "united kingdom", "great britain", "britain", "england", "scotland",
        "wales", "northern ireland", "uk", "u k",
    },
    "brazil": {"brazil", "brasil"},
    "germany": {"germany", "deutschland"},
    "spain": {"spain", "espana", "españa"},
    "netherlands": {"netherlands", "the netherlands", "holland"},
    "czech_republic": {"czech republic", "czechia"},
    "south_korea": {"south korea", "korea", "republic of korea"},
    "uae": {"uae", "united arab emirates"},
    "russia": {"russia", "russian federation"},
    "vietnam": {"vietnam", "viet nam"},
    "ivory_coast": {"ivory coast", "cote divoire", "cote d ivoire"},
}

_ADMIN_REGIONS: dict[str, set[str]] = {
    "canada": {
        "ontario", "british columbia", "quebec", "alberta", "manitoba",
        "saskatchewan", "nova scotia", "new brunswick", "newfoundland",
        "prince edward island", "northwest territories", "nunavut", "yukon",
    },
    "australia": {
        "victoria", "new south wales", "queensland", "tasmania",
        "western australia", "south australia", "australian capital territory",
    },
    "brazil": {
        "bahia", "paraiba", "parana", "minas gerais",
        "rio grande do sul", "santa catarina",
    },
}

_SMALL_WORDS = {"de", "da", "do", "das", "dos", "del", "la", "le", "van", "von", "of"}

US_STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "north carolina": "NC", "north dakota": "ND",
    "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}

# City spellings we already treat as US places, with the state they imply
# when the text itself does not name one. An explicit "Portland, ME" still wins.
_US_CITY_STATE: dict[str, tuple[str, str]] = {
    "new york": ("New York", "NY"),
    "new york city": ("New York", "NY"),
    "nyc": ("New York", "NY"),
    "greater nyc": ("New York", "NY"),
    "brooklyn": ("Brooklyn", "NY"),
    "brookyln": ("Brooklyn", "NY"),
    "manhattan": ("Manhattan", "NY"),
    "los angeles": ("Los Angeles", "CA"),
    "los angels": ("Los Angeles", "CA"),
    "san francisco": ("San Francisco", "CA"),
    "san diego": ("San Diego", "CA"),
    "san jose": ("San Jose", "CA"),
    "sacramento": ("Sacramento", "CA"),
    "oakland": ("Oakland", "CA"),
    "sunnyvale": ("Sunnyvale", "CA"),
    "san mateo": ("San Mateo", "CA"),
    "palo alto": ("Palo Alto", "CA"),
    "el dorado hills": ("El Dorado Hills", "CA"),
    "bakersfield": ("Bakersfield", "CA"),
    "corona": ("Corona", "CA"),
    "sfo": ("San Francisco", "CA"),
    "seattle": ("Seattle", "WA"),
    "ellensburg": ("Ellensburg", "WA"),
    "chicago": ("Chicago", "IL"),
    "boston": ("Boston", "MA"),
    "austin": ("Austin", "TX"),
    "dallas": ("Dallas", "TX"),
    "houston": ("Houston", "TX"),
    "san antonio": ("San Antonio", "TX"),
    "denver": ("Denver", "CO"),
    "atlanta": ("Atlanta", "GA"),
    "atl": ("Atlanta", "GA"),
    "miami": ("Miami", "FL"),
    "boca raton": ("Boca Raton", "FL"),
    "portland": ("Portland", "OR"),
    "phoenix": ("Phoenix", "AZ"),
    "philadelphia": ("Philadelphia", "PA"),
    "philladelphia": ("Philadelphia", "PA"),
    "philly": ("Philadelphia", "PA"),
    "pittsburgh": ("Pittsburgh", "PA"),
    "columbus": ("Columbus", "OH"),
    "cincinnati": ("Cincinnati", "OH"),
    "minneapolis": ("Minneapolis", "MN"),
    "st paul": ("St Paul", "MN"),
    "saint paul": ("St Paul", "MN"),
    "st louis": ("St Louis", "MO"),
    "st. louis": ("St Louis", "MO"),
    "saint louis": ("St Louis", "MO"),
    "honolulu": ("Honolulu", "HI"),
    "salt lake city": ("Salt Lake City", "UT"),
    "high point": ("High Point", "NC"),
    "raleigh": ("Raleigh", "NC"),
    "charlotte": ("Charlotte", "NC"),
    "richmond": ("Richmond", "VA"),
    "las vegas": ("Las Vegas", "NV"),
    "indianapolis": ("Indianapolis", "IN"),
    "fort wayne": ("Fort Wayne", "IN"),
    "milwaukee": ("Milwaukee", "WI"),
    "new orleans": ("New Orleans", "LA"),
    "nola": ("New Orleans", "LA"),
    "washington dc": ("Washington", "DC"),
    "washington d.c": ("Washington", "DC"),
    "washington d.c.": ("Washington", "DC"),
}

_US_REGION_CODE = {
    "silicon valley": "CA",
    "bay area": "CA",
    "sf bay area": "CA",
    "san francisco bay area": "CA",
    "southern california": "CA",
    "northern california": "CA",
    "socal": "CA",
    "norcal": "CA",
    "twin cities": "MN",
}


def _alpha3_by_slug() -> dict[str, str]:
    codes: dict[str, str] = {}
    for code, slug in ISO_CODE_TO_COUNTRY.items():
        if len(code) == 3 and slug not in codes:
            codes[slug] = code.upper()
    return codes


_ALPHA3_BY_SLUG = _alpha3_by_slug()


def country_code(country: str | None) -> str:
    """Short code stored in a location: US, UK, UAE, otherwise ISO alpha-3."""
    slug = (country or "").strip().lower()
    if not slug or slug == "noloc":
        return ""
    if slug in _MANUAL_COUNTRY_CODES:
        return _MANUAL_COUNTRY_CODES[slug]
    return _ALPHA3_BY_SLUG.get(slug, "")


def _plain(text: str) -> str:
    return _fold(text).replace(".", "").strip()


def _location_parts(location: str) -> list[str]:
    text = location.replace(" / ", ", ").replace(" - ", ", ")
    return [part.strip(" .") for part in text.split(",") if part.strip(" .")]


def _title_place(text: str) -> str:
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    titled: list[str] = []
    for index, word in enumerate(words):
        if index > 0 and word.lower() in _SMALL_WORDS:
            titled.append(word.lower())
        elif word:
            titled.append(word[:1].upper() + word[1:])
    return " ".join(titled)


def _display_city(part: str) -> str:
    text = re.sub(r"\s+", " ", (part or "").strip())
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return text
    if any(ch.islower() for ch in letters) and any(ch.isupper() for ch in letters):
        return text
    return _title_place(text)


def _peel_region(folded: str) -> str:
    text = folded
    changed = True
    while changed and text:
        changed = False
        for prefix in ("greater ", "downtown "):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                changed = True
        for suffix in (" metropolitan area", " metro area", " bay area", " metro", " area"):
            if text.endswith(suffix) and len(text) > len(suffix) + 2:
                text = text[: -len(suffix)].strip()
                changed = True
    return text


def _country_tokens(country: str) -> set[str]:
    tokens = {_plain(country.replace("_", " ")), _plain(country_code(country))}
    tokens.update(_plain(name) for name in _COUNTRY_NAME_EXTRAS.get(country, set()))
    for code, slug in ISO_CODE_TO_COUNTRY.items():
        if slug == country:
            tokens.add(_plain(code))
    return {token for token in tokens if token}


def _is_admin_token(part: str, country: str) -> bool:
    folded = _plain(part)
    if not folded:
        return True
    if folded in _country_tokens(country):
        return True
    if folded in _ADMIN_REGIONS.get(country, set()):
        return True
    if country == "canada" and folded in CA_PROVINCE_ABBREVS:
        return True
    if country == "brazil" and folded in BR_STATE_ABBREVS:
        return True
    if country != "usa" and folded in ISO_CODE_TO_COUNTRY and ISO_CODE_TO_COUNTRY[folded] == country:
        return True
    return False


def _us_state_code(part: str) -> str:
    folded = _plain(part)
    folded = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", folded).strip()
    if folded in US_STATE_ABBREVS:
        return folded.upper()
    if folded in US_STATE_NAME_TO_CODE:
        return US_STATE_NAME_TO_CODE[folded]
    return ""


def _format_usa(location: str) -> str:
    folded = _plain(location)
    folded = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", folded).strip()
    if folded in {"washington dc", "washington d c"}:
        return "Washington, DC"
    # "Charlotte NC" names the state in the text, ahead of the city table.
    if "," not in folded:
        bits = folded.split()
        if len(bits) >= 2 and bits[-1] in US_STATE_ABBREVS:
            state = bits[-1].upper()
            city_fold = " ".join(bits[:-1])
            known = _US_CITY_STATE.get(city_fold)
            city = known[0] if known else _display_city(city_fold)
            return f"{city}, {state}" if city else state
    peeled = _peel_region(folded)
    if peeled in _US_CITY_STATE and "," not in folded:
        city, code = _US_CITY_STATE[peeled]
        return f"{city}, {code}"
    if folded in _US_REGION_CODE and "," not in folded:
        return _US_REGION_CODE[folded]

    parts = _location_parts(location)
    abbrev_state = ""
    name_state = ""
    for part in parts:
        folded_part = re.sub(
            r"\s+\d{5}(?:-\d{4})?$", "", _plain(part)
        ).strip()
        if folded_part in US_STATE_ABBREVS:
            abbrev_state = folded_part.upper()
        elif folded_part in US_STATE_NAME_TO_CODE:
            name_state = US_STATE_NAME_TO_CODE[folded_part]
    # "Washington, DC": the abbreviation is the state, the name is the city.
    state = abbrev_state or name_state
    city = ""
    for part in parts:
        folded_part = re.sub(
            r"\s+\d{5}(?:-\d{4})?$", "", _plain(part)
        ).strip()
        part_code = US_STATE_NAME_TO_CODE.get(folded_part, "")
        if folded_part in US_STATE_ABBREVS or part_code == state:
            continue
        if _is_admin_token(part, "usa"):
            continue
        if city:
            continue
        part_fold = _peel_region(folded_part)
        known = _US_CITY_STATE.get(part_fold)
        if known:
            city = known[0]
            state = state or known[1]
        else:
            city = _display_city(part)
    if city and state:
        return f"{city}, {state}"
    if state:
        return state
    if folded in US_STATE_NAME_TO_CODE:
        return US_STATE_NAME_TO_CODE[folded]
    if city:
        return f"{city}, US"
    return "US"


def format_place(location: str | None, country: str | None) -> str:
    """Normalize a free-text place into the stored location form.

    Countries are codes: US, UK, UAE, and ISO alpha-3 for the rest
    (``Berlin, DEU``). A US place with a state stays ``City, ST``.
    """
    slug = (country or "").strip().lower()
    text = (location or "").strip()
    if not text or not slug or slug == "noloc":
        return ""
    if slug == "usa":
        return _format_usa(text)
    label = country_code(slug)
    if not label:
        return ""
    city = ""
    for part in _location_parts(text):
        if _is_admin_token(part, slug):
            continue
        if not city:
            city = _display_city(part)
    if not city or _plain(city) in _country_tokens(slug):
        return label
    return f"{city}, {label}"


class UnknownLocation(ValueError):
    """Non-empty text that does not name a country."""


def place_decision(
    location: str | None,
    *,
    suppressed_locations: set[str] | None = None,
) -> dict[str, str]:
    """Turn free text into the stored place and what saving it should do.

    ``action`` is ``save``, ``delete`` (country is on the exclusion list),
    or ``suppress`` (this formatted place was marked by a suppressed user).
    Blank text clears the place and keeps the user. Unrecognized text raises
    UnknownLocation.
    """
    text = (location or "").strip()
    if not text:
        return {"location": "", "country": "noloc", "action": "save"}
    country = detect_country(text)
    if not country or country == "noloc":
        raise UnknownLocation("Unknown location")
    formatted = format_place(text, country) or country_code(country)
    if not formatted:
        raise UnknownLocation("Unknown location")
    if is_skipped_country(country):
        return {"location": formatted, "country": country, "action": "delete"}
    marks = {
        item.casefold()
        for item in (suppressed_locations or set())
        if (item or "").strip()
    }
    if formatted.casefold() in marks:
        return {"location": formatted, "country": country, "action": "suppress"}
    return {"location": formatted, "country": country, "action": "save"}


def _suggestion_catalog() -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for country, aliases in COUNTRY_ALIAS_GROUPS.items():
        for alias in aliases:
            label = format_place(alias, country)
            if not label:
                continue
            bucket = grouped.setdefault(
                label.casefold(),
                {"location": label, "country": country, "keys": set()},
            )
            bucket["keys"].add(alias)
            bucket["keys"].add(label)
        code = country_code(country)
        if not code:
            continue
        bucket = grouped.setdefault(
            code.casefold(),
            {"location": code, "country": country, "keys": set()},
        )
        bucket["keys"].add(code)
        bucket["keys"].add(country.replace("_", " "))
        for extra in _COUNTRY_NAME_EXTRAS.get(country, set()):
            bucket["keys"].add(extra)
    return [
        {
            "location": item["location"],
            "country": item["country"],
            "keys": tuple(item["keys"]),
        }
        for item in grouped.values()
    ]


_SUGGESTION_CATALOG: list[dict[str, Any]] | None = None


def _catalog() -> list[dict[str, Any]]:
    global _SUGGESTION_CATALOG
    if _SUGGESTION_CATALOG is None:
        _SUGGESTION_CATALOG = _suggestion_catalog()
    return _SUGGESTION_CATALOG


def _match_score(needle: str, location: str, keys: tuple[str, ...] | list[str]) -> int | None:
    folded_location = _plain(location)
    folded_keys = [_plain(key) for key in keys if key]
    if needle == folded_location or needle in folded_keys:
        return 0
    if folded_location.startswith(needle) or any(key.startswith(needle) for key in folded_keys):
        return 1
    if needle in folded_location or any(needle in key for key in folded_keys):
        return 2
    return None


def suggest_places(
    query: str | None,
    *,
    suppressed_locations: set[str] | None = None,
    stored: list[dict[str, str]] | None = None,
    limit: int = 12,
) -> list[dict[str, str]]:
    """Places matching typed or pasted text, best match first.

    Each item is the formatted location plus ``save``, ``delete``, or ``suppress``.
    """
    needle = _plain(query or "")
    if len(needle) < 2:
        return []
    marks = {
        item.casefold()
        for item in (suppressed_locations or set())
        if (item or "").strip()
    }
    hits: dict[str, dict[str, Any]] = {}

    def consider(location: str, country: str, score: int) -> None:
        label = (location or "").strip()
        slug = (country or "").strip().lower()
        if not label or not slug:
            return
        key = label.casefold()
        current = hits.get(key)
        if current is not None and current["score"] <= score:
            return
        if is_skipped_country(slug):
            action = "delete"
        elif key in marks:
            action = "suppress"
        else:
            action = "save"
        hits[key] = {
            "location": label,
            "country": slug,
            "action": action,
            "score": score,
        }

    try:
        typed = place_decision(query, suppressed_locations=suppressed_locations)
    except UnknownLocation:
        typed = None
    if typed and typed["location"]:
        consider(typed["location"], typed["country"], 0)

    for item in _catalog():
        score = _match_score(needle, item["location"], item["keys"])
        if score is not None:
            consider(item["location"], item["country"], score)
    for item in stored or []:
        label = str(item.get("location") or "")
        score = _match_score(needle, label, (label, str(item.get("country") or "")))
        if score is not None:
            consider(label, str(item.get("country") or ""), score)

    ranked = sorted(hits.values(), key=lambda item: (item["score"], len(item["location"]), item["location"]))
    return [
        {"location": item["location"], "country": item["country"], "action": item["action"]}
        for item in ranked[: max(1, int(limit))]
    ]
