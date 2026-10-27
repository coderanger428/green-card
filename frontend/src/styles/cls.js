export function cls(map, value) {
  if (value == null || value === false || value === true) return '';
  return String(value)
    .split(/\s+/)
    .filter(Boolean)
    .map((token) => (map && map[token]) || token)
    .join(' ');
}
