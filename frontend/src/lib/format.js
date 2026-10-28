export const formatDate = (value) => {
  if (!value) return '-';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
};

export const MINUTE_MS = 60 * 1000;
export const HOUR_MS = 60 * MINUTE_MS;
export const DAY_MS = 24 * HOUR_MS;
export const WEEK_MS = 7 * DAY_MS;
export const MONTH_MS = 30 * DAY_MS;
export const TWO_MONTHS_MS = 60 * DAY_MS;

export const formatStep = (count, singular, plural) =>
  `${count} ${count === 1 ? singular : plural} ago`;

/** Coarse age: Just before, then min / hour / day / week, a month ago, Long ago after 2 months. */
export const formatUpdatedAgo = (value) => {
  if (!value) return '-';
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return '-';
  const elapsed = Date.now() - then;
  if (elapsed < MINUTE_MS) return 'Just before';
  if (elapsed < HOUR_MS) return formatStep(Math.floor(elapsed / MINUTE_MS), 'min', 'mins');
  if (elapsed < DAY_MS) return formatStep(Math.floor(elapsed / HOUR_MS), 'hour', 'hours');
  if (elapsed < WEEK_MS) return formatStep(Math.floor(elapsed / DAY_MS), 'day', 'days');
  if (elapsed < MONTH_MS) return formatStep(Math.floor(elapsed / WEEK_MS), 'week', 'weeks');
  if (elapsed < TWO_MONTHS_MS) return 'a month ago';
  return 'Long ago';
};

export const formatDateOnly = (value) => {
  if (!value) return '-';
  try {
    return new Date(value).toLocaleDateString();
  } catch {
    return value;
  }
};

/** e.g. alice04@gmail.com -> al....04@gmail.com */
export const maskEmail = (email) => {
  const text = String(email || '').trim();
  const at = text.lastIndexOf('@');
  if (at <= 0) {
    return text || '-';
  }
  const local = text.slice(0, at);
  const domain = text.slice(at);
  if (local.length <= 2) {
    return `${local.slice(0, 1)}....${domain}`;
  }
  if (local.length <= 4) {
    return `${local.slice(0, 2)}....${local.slice(-Math.min(2, local.length - 2))}${domain}`;
  }
  return `${local.slice(0, 2)}....${local.slice(-2)}${domain}`;
};

const GROUP_LABELS = {
  eu: 'EU',
  emea: 'EMEA',
  apac: 'APAC',
  latam: 'LATAM',
  etc: 'Other',
};

// Long and compound names use a short code. Single-word names stay as words.
const COMPOUND_COUNTRY_CODES = {
  usa: 'USA',
  uk: 'UK',
  uae: 'UAE',
  new_zealand: 'NZ',
  hong_kong: 'HK',
  south_africa: 'ZA',
  czech_republic: 'CZ',
  costa_rica: 'CR',
  saudi_arabia: 'SA',
  south_korea: 'KR',
  north_korea: 'KP',
  sri_lanka: 'LK',
  el_salvador: 'SV',
  dominican_republic: 'DO',
  puerto_rico: 'PR',
  trinidad_and_tobago: 'TT',
  ivory_coast: 'CI',
  sierra_leone: 'SL',
  cape_verde: 'CV',
  north_macedonia: 'MK',
  bosnia_and_herzegovina: 'BA',
  papua_new_guinea: 'PG',
  burkina_faso: 'BF',
  georgia_country: 'Georgia',
};

const SMALL_NAME_WORDS = new Set(['and', 'of', 'the']);

/** Short code for a long or compound country. A single word stays title case. */
export const formatCountryName = (slug) => {
  const key = String(slug || '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_');
  if (!key) return '';
  if (GROUP_LABELS[key]) return GROUP_LABELS[key];
  if (COMPOUND_COUNTRY_CODES[key]) return COMPOUND_COUNTRY_CODES[key];
  const words = key.split('_').filter(Boolean);
  const significant = words.filter((word) => !SMALL_NAME_WORDS.has(word));
  if (significant.length > 1) {
    return significant.map((word) => word.charAt(0).toUpperCase()).join('');
  }
  const word = significant[0] || words[0] || '';
  if (word.length <= 3) return word.toUpperCase();
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
};

export const formatGroupMatchHint = (group, preview = 5) => {
  const count = Number(group?.member_count) || 0;
  if (!group || count <= 0) {
    return '';
  }
  const names = (group.members || [])
    .slice(0, preview)
    .map((slug) => formatCountryName(slug));
  const extra = count - names.length;
  const list =
    extra > 0 ? `${names.join(', ')}, and ${extra} more` : names.join(', ');
  const noun = count === 1 ? 'country' : 'countries';
  return `${group.label} is used automatically for ${count} ${noun} (${list}).`;
};

export const SCRAPER_STATUS_LABELS = {
  running: 'Running',
  paused: 'Paused',
  idling: 'Waiting (daily cap)',
  stopped: 'Stopped',
};

export const formatWillSendAt = (item) => {
  if (item?.estimated_send_label) {
    return item.estimated_send_label;
  }
  if (!item?.estimated_send_at) {
    return '-';
  }
  const target = new Date(item.estimated_send_at).getTime();
  if (Number.isNaN(target)) {
    return '-';
  }
  const diffSec = Math.max(0, Math.round((target - Date.now()) / 1000));
  if (diffSec < 60) {
    return 'now';
  }
  const minutes = Math.round(diffSec / 60);
  if (minutes < 60) {
    return `${minutes} min later`;
  }
  const hours = Math.floor(minutes / 60);
  const remMin = minutes % 60;
  if (hours < 48) {
    return remMin > 0 ? `${hours}h ${remMin}m later` : `${hours}h later`;
  }
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? '' : 's'} later`;
};

export const dailyCapTone = (sent, limit) => {
  if (!limit || limit <= 0) {
    return 'green';
  }
  const pct = (sent / limit) * 100;
  if (pct < 60) return 'green';
  if (pct < 80) return 'orange';
  return 'red';
};
