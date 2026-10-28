const BRACE_CONTENT = /\([^()]*\)|\[[^\[\]]*\]|\{[^{}]*\}|（[^（）]*）|【[^【】]*】/g;

function capWord(word) {
  return word
    .split('-')
    .map((part) => (part ? part.charAt(0).toUpperCase() + part.slice(1).toLowerCase() : part))
    .join('-');
}

export function normalizeDisplayName(name) {
  let text = String(name || '').trim();
  if (!text) return '';
  text = text.replace(BRACE_CONTENT, ' ');
  text = Array.from(text)
    .filter((ch) => /\p{L}|\p{M}/u.test(ch) || ch === ' ' || ch === '-' || ch === "'" || ch === '’' || ch === '.')
    .join('');
  text = text.replace(/\s+/g, ' ').trim();
  if (!text) return '';
  return text.split(' ').map(capWord).join(' ');
}

export function renderTemplateText(text, name, yourName, link) {
  let rendered = String(text || '').replace(/\\\[/g, '[');
  const nameValue = normalizeDisplayName(name) || 'there';
  rendered = rendered.replace(/\[name\]/gi, nameValue);
  rendered = rendered.replace(/\[your name\]/gi, String(yourName || '').trim());
  rendered = rendered.replace(/\[link\]/gi, link || '');
  return rendered;
}

export function senderDisplayName(email, accounts) {
  const key = String(email || '').trim().toLowerCase();
  const match = (accounts || []).find(
    (account) => String(account?.email || '').trim().toLowerCase() === key
  );
  const stored = String(match?.sender_name || '').trim();
  if (stored) return stored;
  const local = key.split('@')[0].replace(/[._]/g, ' ').trim();
  return local
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}
