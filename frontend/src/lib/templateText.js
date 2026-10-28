import { formatCountryName } from './format';

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

const IDENTIFIER_WIDTH = 8;
const SUBJECT_WIDTH = 28;

function padEnd(value, width) {
  const text = String(value || '');
  if (text.length >= width) return text;
  return text + ' '.repeat(width - text.length);
}

export function abbreviateSubject(subject, width = SUBJECT_WIDTH) {
  const text = String(subject || '').replace(/\s+/g, ' ').trim();
  if (text.length <= width) return text;
  const keep = Math.max(1, width - 3);
  return `${text.slice(0, keep).trimEnd()}...`;
}

export function templatePickerLabel(item) {
  const country = formatCountryName(item?.region || '') || 'Template';
  const match = String(item?.filename || '').match(/\((\d+)\)/);
  const head = padEnd(match ? `${country}(${match[1]})` : country, IDENTIFIER_WIDTH);
  const subject = abbreviateSubject(item?.subject);
  if (!subject) return head.trimEnd();
  return `${head}:${subject}`;
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
