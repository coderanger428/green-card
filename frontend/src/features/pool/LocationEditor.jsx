import { useState, useEffect, useLayoutEffect, useRef } from 'react';
import { cls } from '../../styles/cls';
import pool from '../../styles/pool.module.css';

const locationEffectLabel = (action) => {
  if (action === 'delete') return 'Excluded';
  if (action === 'suppress') return 'Suppressed';
  return '';
};

export const LocationEditor = ({ user, disabled = false, onCommit }) => {
  const inputRef = useRef(null);
  const draftRef = useRef('');
  const committingRef = useRef(false);
  const requestRef = useRef(0);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [active, setActive] = useState(0);
  const [saving, setSaving] = useState(false);
  const [menuPos, setMenuPos] = useState(null);
  const currentLocation = String(user.location || '');

  const setDraftValue = (value) => {
    draftRef.current = value;
    setDraft(value);
  };

  useEffect(() => {
    if (!open) return undefined;
    const queryText = draft.trim();
    if (queryText.length < 2) {
      setSuggestions([]);
      setActive(0);
      return undefined;
    }
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    const handle = window.setTimeout(() => {
      fetch(`/api/locations/suggest?q=${encodeURIComponent(queryText)}`)
        .then((res) => (res.ok ? res.json() : { suggestions: [] }))
        .then((data) => {
          if (requestId !== requestRef.current) return;
          const next = Array.isArray(data.suggestions) ? data.suggestions : [];
          setSuggestions(next);
          setActive(0);
        })
        .catch(() => {
          if (requestId !== requestRef.current) return;
          setSuggestions([]);
        });
    }, 120);
    return () => window.clearTimeout(handle);
  }, [draft, open]);

  useLayoutEffect(() => {
    if (!open || !inputRef.current) return undefined;
    const place = () => {
      const rect = inputRef.current.getBoundingClientRect();
      setMenuPos({
        left: rect.left,
        top: rect.bottom + 4,
        width: Math.max(rect.width, 240),
      });
    };
    place();
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    return () => {
      window.removeEventListener('scroll', place, true);
      window.removeEventListener('resize', place);
    };
  }, [open, draft, suggestions]);

  const commit = (value) => {
    if (committingRef.current || saving) return;
    const next = String(value ?? '').trim();
    if (next === currentLocation.trim()) {
      setEditing(false);
      setOpen(false);
      setDraftValue(currentLocation);
      return;
    }
    committingRef.current = true;
    setSaving(true);
    setOpen(false);
    onCommit(user, next)
      .then(() => {
        setEditing(false);
        setDraftValue(next);
      })
      .catch(() => {
        setDraftValue(next);
        setEditing(true);
      })
      .finally(() => {
        committingRef.current = false;
        setSaving(false);
      });
  };

  const pickSuggestion = (index) => {
    const item = suggestions[index];
    if (!item) {
      commit(draftRef.current);
    } else {
      commit(item.location);
    }
    inputRef.current?.blur();
  };

  return (
    <div className={cls(pool, "location-editor")} title={String(user.github_bio || '').trim() || undefined}>
      <input
        ref={inputRef}
        type="text"
        className={cls(pool, editing ? 'display-name-input is-editing' : 'display-name-input')}
        value={editing ? draft : currentLocation}
        disabled={disabled || saving}
        maxLength={300}
        autoComplete="off"
        spellCheck={false}
        aria-label={`Location for user ${user.id}`}
        aria-autocomplete="list"
        aria-expanded={open}
        placeholder="City, country"
        onFocus={() => {
          setEditing(true);
          setDraftValue(currentLocation);
          setOpen(true);
        }}
        onChange={(event) => {
          setEditing(true);
          setDraftValue(event.target.value);
          setOpen(true);
        }}
        onBlur={() => {
          if (committingRef.current) return;
          commit(draftRef.current);
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' && suggestions.length) {
            event.preventDefault();
            setOpen(true);
            setActive((index) => (index + 1) % suggestions.length);
          } else if (event.key === 'ArrowUp' && suggestions.length) {
            event.preventDefault();
            setOpen(true);
            setActive((index) => (index - 1 + suggestions.length) % suggestions.length);
          } else if (event.key === 'Enter') {
            event.preventDefault();
            if (open && suggestions.length) {
              pickSuggestion(active);
            } else {
              commit(draftRef.current);
            }
            event.currentTarget.blur();
          } else if (event.key === 'Escape') {
            event.preventDefault();
            committingRef.current = true;
            setEditing(false);
            setOpen(false);
            setDraftValue(currentLocation);
            event.currentTarget.blur();
            committingRef.current = false;
          }
        }}
        onClick={(event) => event.stopPropagation()}
      />
      {open && menuPos && suggestions.length ? (
        <div
          className={cls(pool, "location-suggest-menu")}
          role="listbox"
          style={{ left: menuPos.left, top: menuPos.top, width: menuPos.width }}
        >
          {suggestions.map((item, index) => {
            const effect = locationEffectLabel(item.action);
            return (
              <button
                key={`${item.location}-${item.country}`}
                type="button"
                role="option"
                aria-selected={index === active}
                className={cls(pool, index === active
                    ? 'location-suggest-option active'
                    : 'location-suggest-option')}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActive(index)}
                onClick={() => pickSuggestion(index)}
              >
                <span>{item.location}</span>
                {effect ? (
                  <span
                    className={cls(pool, item.action === 'delete'
                        ? 'location-suggest-meta is-delete'
                        : 'location-suggest-meta is-suppress')}
                  >
                    {effect}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};
