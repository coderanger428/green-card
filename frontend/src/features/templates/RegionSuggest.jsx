import { useState } from 'react';
import { formatCountryName } from '../../lib/format';
import { cls } from '../../styles/cls';
import templates from '../../styles/templates.module.css';

const slugifyRegionQuery = (value) =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s-/]+/g, '_')
    .replace(/[^a-z0-9_]/g, '')
    .replace(/^_+|_+$/g, '')
    .slice(0, 40);

export const RegionSuggest = ({
  groups = [],
  countries = [],
  custom = [],
  value,
  onChange,
  disabled = false,
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState(false);

  const options = [
    ...groups.map((item) => ({ ...item, section: 'Regions' })),
    ...custom.map((item) => ({ ...item, section: 'Custom' })),
    ...countries.map((item) => ({ ...item, section: 'Countries' })),
  ];
  const selected = options.find((item) => item.slug === value);
  const matchText = editing ? query : selected?.label || value || '';
  const needle = slugifyRegionQuery(editing ? query : matchText);
  const labelNeedle = (editing ? query : matchText).trim().toLowerCase();

  const matches = (item) => {
    if (!labelNeedle) {
      return true;
    }
    if (
      String(item.slug || '').includes(needle) ||
      String(item.label || '').toLowerCase().includes(labelNeedle) ||
      String(item.description || '').toLowerCase().includes(labelNeedle)
    ) {
      return true;
    }
    return (item.members || []).some(
      (slug) =>
        String(slug).includes(needle) ||
        formatCountryName(slug).toLowerCase().includes(labelNeedle)
    );
  };

  const groupHits = groups.filter(matches);
  const customHits = custom.filter(matches);
  const countryHits = countries.filter(matches).slice(0, 12);
  const known = new Set(options.map((item) => item.slug));
  const addSlug = slugifyRegionQuery(query);
  const showAdd =
    Boolean(addSlug) &&
    /^[a-z][a-z0-9_]*$/.test(addSlug) &&
    !known.has(addSlug);

  const pick = (slug) => {
    onChange(slug);
    setEditing(false);
    setQuery('');
    setOpen(false);
  };

  return (
    <div className={cls(templates, "region-suggest")}>
      <input
        type="text"
        value={editing ? query : selected?.label || value || ''}
        disabled={disabled}
        placeholder="Search EU, APAC, LATAM, or a country"
        autoComplete="off"
        aria-label="Template region"
        aria-expanded={open}
        onFocus={() => {
          setEditing(true);
          setQuery(selected?.label || value || '');
          setOpen(true);
        }}
        onChange={(event) => {
          setEditing(true);
          setQuery(event.target.value);
          setOpen(true);
        }}
        onBlur={() => {
          window.setTimeout(() => {
            setOpen(false);
            setEditing(false);
            setQuery('');
          }, 120);
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            if (showAdd) {
              pick(addSlug);
            } else if (groupHits[0]) {
              pick(groupHits[0].slug);
            } else if (customHits[0]) {
              pick(customHits[0].slug);
            } else if (countryHits[0]) {
              pick(countryHits[0].slug);
            }
          }
          if (event.key === 'Escape') {
            setOpen(false);
            setEditing(false);
            setQuery('');
            event.currentTarget.blur();
          }
        }}
      />
      {open ? (
        <div className={cls(templates, "region-suggest-menu")} role="listbox">
          {groupHits.length > 0 ? (
            <div className={cls(templates, "region-suggest-section")}>
              <div className={cls(templates, "region-suggest-heading")}>Regions</div>
              {groupHits.map((item) => (
                <button
                  key={`g-${item.slug}`}
                  type="button"
                  role="option"
                  className={cls(templates, item.slug === value
                      ? 'region-suggest-option active'
                      : 'region-suggest-option')}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => pick(item.slug)}
                >
                  <span>{item.label}</span>
                  <span className={cls(templates, "region-suggest-meta")}>
                    {item.member_count
                      ? `${item.member_count} ${
                          item.member_count === 1 ? 'country' : 'countries'
                        }`
                      : item.description}
                  </span>
                </button>
              ))}
            </div>
          ) : null}
          {customHits.length > 0 ? (
            <div className={cls(templates, "region-suggest-section")}>
              <div className={cls(templates, "region-suggest-heading")}>Custom</div>
              {customHits.map((item) => (
                <button
                  key={`x-${item.slug}`}
                  type="button"
                  role="option"
                  className={cls(templates, "region-suggest-option")}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => pick(item.slug)}
                >
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
          ) : null}
          {countryHits.length > 0 ? (
            <div className={cls(templates, "region-suggest-section")}>
              <div className={cls(templates, "region-suggest-heading")}>Countries</div>
              {countryHits.map((item) => (
                <button
                  key={`c-${item.slug}`}
                  type="button"
                  role="option"
                  className={cls(templates, item.slug === value
                      ? 'region-suggest-option active'
                      : 'region-suggest-option')}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => pick(item.slug)}
                >
                  <span>{item.label}</span>
                  {item.users ? (
                    <span className={cls(templates, "region-suggest-meta")}>{item.users} users</span>
                  ) : null}
                </button>
              ))}
            </div>
          ) : null}
          {showAdd ? (
            <button
              type="button"
              className={cls(templates, "region-suggest-option region-suggest-add")}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => pick(addSlug)}
            >
              Add country “{addSlug.replace(/_/g, ' ')}”
            </button>
          ) : null}
          {groupHits.length === 0 &&
          customHits.length === 0 &&
          countryHits.length === 0 &&
          !showAdd ? (
            <div className={cls(templates, "region-suggest-empty")}>No matching regions</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};
