/** dev.to and GitHub profile links shown in the Source column. */
export const SCRAPERS = [{ id: 'devto', label: 'dev.to' }];

export const sourceLabel = (source) => {
  const value = String(source || '').trim().toLowerCase();
  const match = SCRAPERS.find((scraper) => scraper.id === value);
  return match ? match.label : value || '-';
};

/** Public profile for a stored GitHub account. Blank when the account is missing or unsafe. */
export const githubProfileUrl = (account) => {
  const name = String(account || '').trim();
  if (!/^[A-Za-z0-9-]+$/.test(name)) return '';
  return `https://github.com/${name}`;
};

export const userSources = (user) => {
  const names = String(user.source || '')
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
  if (githubProfileUrl(user.github) && !names.includes('github')) {
    names.push('github');
  }
  if (!names.length && user.link) {
    names.push('devto');
  }
  return names.filter((name) => name !== 'github' || githubProfileUrl(user.github));
};
