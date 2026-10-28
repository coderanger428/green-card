import { useState, useEffect, useRef } from 'react';
import toast from 'react-hot-toast';
import { POLL_INTERVAL_MS } from '../lib/constants';
import { maskEmail, formatCountryName, formatGroupMatchHint } from '../lib/format';
import { SCRAPERS } from '../lib/source';
import { SOCIAL_ACCOUNT_FILTERS, emptySocialFilters, socialProviderLabel } from '../lib/social';
import { renderTemplateText, senderDisplayName } from '../lib/templateText';

export function useDashboardState() {
  const [view, setView] = useState('pool');
  const [contactModal, setContactModal] = useState(null);
  const [countries, setCountries] = useState([]);
  const [selectedCountry, setSelectedCountry] = useState('');
  const [query, setQuery] = useState('');
  const [socialFilters, setSocialFilters] = useState(emptySocialFilters);
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const mailPreviewSeq = useRef(0);
  const [mailAccounts, setMailAccounts] = useState(null);
  const [mailEmail, setMailEmail] = useState('');
  const [mailSenderName, setMailSenderName] = useState('');
  const [mailSaveMode, setMailSaveMode] = useState('create');
  const [mailModalOpen, setMailModalOpen] = useState(false);
  const [scraperInfo, setScraperInfo] = useState(null);
  const [selectedScraper, setSelectedScraper] = useState(SCRAPERS[0].id);
  const [capMode, setCapMode] = useState('auto');
  const [capInput, setCapInput] = useState('');
  const [capDirty, setCapDirty] = useState(false);
  const [displayNameDrafts, setDisplayNameDrafts] = useState({});
  const [savingDisplayNameIds, setSavingDisplayNameIds] = useState(() => new Set());
  const [editingDisplayNameId, setEditingDisplayNameId] = useState(null);
  const [savingOutcomeIds, setSavingOutcomeIds] = useState(() => new Set());
  const [suppressingIds, setSuppressingIds] = useState(() => new Set());
  const [templates, setTemplates] = useState([]);
  const [templateCatalog, setTemplateCatalog] = useState({
    groups: [],
    countries: [],
    custom: [],
  });
  const [selectedTemplateRegion, setSelectedTemplateRegion] = useState('');
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [templateSaveMode, setTemplateSaveMode] = useState('create');
  const [templateFilename, setTemplateFilename] = useState('');
  const [templateRegion, setTemplateRegion] = useState('etc');
  const [templateSubject, setTemplateSubject] = useState('');
  const [templateBody, setTemplateBody] = useState('');

  const loadMailAccounts = () => {
    fetch('/api/mail-accounts')
      .then((res) => res.json())
      .then(setMailAccounts)
      .catch((err) => setError(`Unable to load mail accounts: ${err.message}`));
  };

  const applyScraperInfo = (data) => {
    setScraperInfo(data);
    if (!capDirty) {
      const mode = data?.cap_mode === 'manual' ? 'manual' : 'auto';
      setCapMode(mode);
      setCapInput(
        String(
          mode === 'manual'
            ? data?.daily_limit_override ?? data?.daily_limit ?? ''
            : data?.auto_daily_limit ?? data?.daily_limit ?? ''
        )
      );
    }
  };

  const loadScraperInfo = () => {
    fetch('/api/scraper')
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail || res.statusText;
          throw new Error(typeof detail === 'string' ? detail : 'Request failed');
        }
        return data;
      })
      .then(applyScraperInfo)
      .catch((err) => setError(`Unable to load scraper: ${err.message}`));
  };

  const loadTemplates = () => {
    Promise.all([
      fetch('/api/templates').then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail || res.statusText;
          throw new Error(typeof detail === 'string' ? detail : 'Request failed');
        }
        return data;
      }),
      fetch('/api/template-regions').then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail || res.statusText;
          throw new Error(typeof detail === 'string' ? detail : 'Request failed');
        }
        return data;
      }),
    ])
      .then(([templateData, catalog]) => {
        setTemplates(templateData.templates || []);
        setTemplateCatalog({
          groups: catalog.groups || [],
          countries: catalog.countries || [],
          custom: catalog.custom || [],
        });
      })
      .catch((err) => setError(`Unable to load templates: ${err.message}`));
  };

  const loadCountries = () => {
    fetch('/api/countries')
      .then((res) => res.json())
      .then(setCountries)
      .catch((err) => setError(`Unable to load countries: ${err.message}`));
  };

  useEffect(() => {
    loadCountries();
  }, []);

  const selectedSocials =
    view === 'pool'
      ? SOCIAL_ACCOUNT_FILTERS.map((item) => item.id).filter((id) => socialFilters[id])
      : [];

  const fetchUsers = ({ silent = false } = {}) => {
    const q = query.trim();
    const searchAll = !selectedCountry && q.length >= 2;
    if (!selectedCountry && !searchAll) {
      setUsers([]);
      setTotal(0);
      return Promise.resolve();
    }

    const params = new URLSearchParams();
    if (selectedCountry) {
      params.set('country', selectedCountry);
    }
    if (q) {
      params.set('q', q);
    }
    for (const provider of selectedSocials) {
      params.append('has_social', provider);
    }
    params.set('page', page);
    params.set('page_size', pageSize);

    if (!silent) {
      setLoading(true);
      setError('');
    }

    return fetch(`/api/users?${params.toString()}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        setUsers(data.users || []);
        setTotal(data.total || 0);
      })
      .catch((err) => {
        if (!silent) {
          setError(`Unable to load users: ${err.message}`);
        }
      })
      .finally(() => {
        if (!silent) {
          setLoading(false);
        }
      });
  };

  useEffect(() => {
    fetchUsers();
  }, [view, selectedCountry, query, page, pageSize, socialFilters]);

  useEffect(() => {
    if (view === 'senders') {
      loadMailAccounts();
    }
    if (view === 'scraper') {
      loadScraperInfo();
    }
    if (view === 'templates') {
      loadTemplates();
    }
  }, [view]);

  useEffect(() => {
    const poll = () => {
      if (typeof document !== 'undefined' && document.hidden) {
        return;
      }
      if (view === 'senders') {
        loadMailAccounts();
      }
      if (view === 'pool' || view === 'tracked') {
        loadCountries();
        if (selectedCountry || query.trim().length >= 2) {
          fetchUsers({ silent: true });
        }
      }
      if (view === 'scraper') {
        loadScraperInfo();
      }
      if (view === 'templates') {
        loadTemplates();
      }
    };

    const intervalId = window.setInterval(poll, POLL_INTERVAL_MS);
    const onVisibility = () => {
      if (!document.hidden) {
        poll();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [view, selectedCountry, query, page, pageSize, capDirty, socialFilters]);

  const searchQuery = query.trim();
  const isGlobalSearch = !selectedCountry && searchQuery.length >= 2;
  const showUserTable = Boolean(selectedCountry) || isGlobalSearch;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const mailAccountsData = mailAccounts || {};
  const accounts = mailAccountsData.accounts || [];
  const sortedCountries = [...countries].sort(
    (a, b) => (b.count || 0) - (a.count || 0) || String(a.country).localeCompare(String(b.country))
  );
  const sidebarCountries =
    view === 'tracked'
      ? sortedCountries
          .filter((item) => (Number(item.sent) || 0) > 0)
          .sort(
            (a, b) =>
              (Number(b.sent) || 0) - (Number(a.sent) || 0) ||
              String(a.country).localeCompare(String(b.country))
          )
      : sortedCountries;
  const sidebarTotal = sidebarCountries.reduce(
    (sum, item) =>
      sum + (view === 'tracked' ? Number(item.sent) || 0 : Number(item.count) || 0),
    0
  );
  const selectedCountryMeta = sortedCountries.find(
    (item) => item.country === selectedCountry
  );
  const trimmedMailEmail = mailEmail.trim().toLowerCase();
  const isEditMode = mailSaveMode === 'update';
  const canSaveMailAccount =
    !!trimmedMailEmail && !!mailSenderName.trim() && !loading;
  const templateGroups = templateCatalog.groups || [];
  const templateCountries = templateCatalog.countries || [];
  const templateCustom = templateCatalog.custom || [];
  const selectedGroupMeta = templateGroups.find(
    (item) => item.slug === selectedTemplateRegion
  );
  const selectedMatchHint = formatGroupMatchHint(selectedGroupMeta);
  const editingGroupMeta = templateGroups.find((item) => item.slug === templateRegion);
  const editingMatchHint = formatGroupMatchHint(editingGroupMeta);
  const visibleTemplates = selectedTemplateRegion
    ? templates.filter((item) => item.region === selectedTemplateRegion)
    : templates;
  const canSaveTemplate =
    !!templateRegion &&
    !!templateSubject.trim() &&
    !!templateBody.trim() &&
    !loading;
  const templateSidebarCountries = templateCountries.filter(
    (item) => (item.templates || 0) > 0
  );
  const templateSidebarCustom = templateCustom.filter(
    (item) => (item.templates || 0) > 0
  );

  const handleResetMailForm = () => {
    setMailEmail('');
    setMailSenderName('');
    setMailSaveMode('create');
  };

  const openCreateMailModal = () => {
    handleResetMailForm();
    setMailSaveMode('create');
    setMailModalOpen(true);
  };

  const openEditMailModal = (account) => {
    setMailEmail(account.email || '');
    setMailSenderName(account.sender_name || '');
    setMailSaveMode('update');
    setMailModalOpen(true);
  };

  const closeMailModal = () => {
    setMailModalOpen(false);
    handleResetMailForm();
  };

  const handleAddMailAccount = () => {
    setLoading(true);
    setError('');

    const url = isEditMode
      ? `/api/mail-accounts/${encodeURIComponent(trimmedMailEmail)}`
      : '/api/mail-accounts';
    const method = isEditMode ? 'PUT' : 'POST';
    const payload = { sender_name: mailSenderName.trim() };
    if (!isEditMode) {
      payload.email = mailEmail.trim();
    }

    fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then((res) => {
        if (!res.ok) {
          return res.json().then((body) => {
            throw new Error(body.detail || `HTTP ${res.status}`);
          });
        }
        return res.json();
      })
      .then(() => {
        toast.success(isEditMode ? 'Mail account updated.' : 'Mail account added.');
        closeMailModal();
        loadMailAccounts();
      })
      .catch((err) => {
        const message = `Unable to save mail account: ${err.message}`;
        setError(message);
        toast.error(message);
      })
      .finally(() => setLoading(false));
  };

  const handleDeleteMailAccount = () => {
    if (!isEditMode || !trimmedMailEmail) {
      toast.error('Select an existing account first.');
      return;
    }
    setLoading(true);
    setError('');

    fetch(`/api/mail-accounts/${encodeURIComponent(trimmedMailEmail)}`, {
      method: 'DELETE',
    })
      .then((res) => {
        if (!res.ok) {
          return res.json().then((body) => {
            throw new Error(body.detail || `HTTP ${res.status}`);
          });
        }
        return res.json();
      })
      .then(() => {
        toast.success(`Deleted ${maskEmail(trimmedMailEmail)}.`);
        closeMailModal();
        loadMailAccounts();
      })
      .catch((err) => {
        const message = `Unable to delete mail account: ${err.message}`;
        setError(message);
        toast.error(message);
      })
      .finally(() => setLoading(false));
  };

  const displayNameValue = (user) => {
    if (Object.prototype.hasOwnProperty.call(displayNameDrafts, user.id)) {
      return displayNameDrafts[user.id];
    }
    return user.display_name ?? user.name ?? '';
  };

  const handleDisplayNameChange = (userId, value) => {
    setDisplayNameDrafts((current) => ({ ...current, [userId]: value }));
  };

  const handleCancelDisplayName = (userId) => {
    setDisplayNameDrafts((current) => {
      const next = { ...current };
      delete next[userId];
      return next;
    });
  };

  const handleSaveDisplayName = (user) => {
    if (!Object.prototype.hasOwnProperty.call(displayNameDrafts, user.id)) {
      return;
    }
    if (savingDisplayNameIds.has(user.id)) {
      return;
    }
    const next = String(displayNameDrafts[user.id] ?? '').trim();
    const current = String(user.display_name ?? user.name ?? '').trim();
    if (next === current) {
      handleCancelDisplayName(user.id);
      return;
    }

    setSavingDisplayNameIds((currentIds) => {
      const nextIds = new Set(currentIds);
      nextIds.add(user.id);
      return nextIds;
    });
    setError('');
    fetch(`/api/users/${user.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: next }),
    })
      .then((res) => {
        if (!res.ok) {
          return res.json().then((body) => {
            throw new Error(body.detail || `HTTP ${res.status}`);
          });
        }
        return res.json();
      })
      .then((data) => {
        const saved = data.user || {};
        setUsers((list) =>
          list.map((row) => (row.id === user.id ? { ...row, ...saved } : row))
        );
        handleCancelDisplayName(user.id);
      })
      .catch((err) => {
        const message = `Unable to save display name: ${err.message}`;
        setError(message);
        toast.error(message);
      })
      .finally(() => {
        setSavingDisplayNameIds((currentIds) => {
          const nextIds = new Set(currentIds);
          nextIds.delete(user.id);
          return nextIds;
        });
      });
  };

  const handleSaveLocation = (user, next) => {
    const name = String(user.display_name || user.name || user.email || 'this user').trim();
    setError('');
    return fetch(`/api/users/${user.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ location: next }),
    })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = body.detail;
          const message = typeof detail === 'string' ? detail : `HTTP ${res.status}`;
          throw new Error(message);
        }
        return body;
      })
      .then((data) => {
        const action = data.action || 'save';
        const place = data.location || next || 'this place';
        if (action === 'delete') {
          toast.success(`Deleted ${name}. ${place} is excluded.`);
          loadCountries();
          fetchUsers({ silent: true });
          return;
        }
        if (action === 'suppress') {
          toast.success(`Suppressed ${name}. ${place} is a suppressed location.`);
          loadCountries();
          fetchUsers({ silent: true });
          return;
        }
        const saved = data.user || {};
        const leftCountry =
          selectedCountry && saved.country && saved.country !== selectedCountry;
        if (leftCountry) {
          loadCountries();
          fetchUsers({ silent: true });
          return;
        }
        setUsers((list) =>
          list.map((row) => (row.id === user.id ? { ...row, ...saved } : row))
        );
        if (saved.country && saved.country !== user.country) {
          loadCountries();
        }
      })
      .catch((err) => {
        const message = `Unable to save location: ${err.message}`;
        setError(message);
        toast.error(message);
        throw err;
      });
  };

  const openEmailContact = (user) => {
    const seq = mailPreviewSeq.current + 1;
    mailPreviewSeq.current = seq;
    setContactModal({
      channel: 'email',
      user,
      loading: true,
      subject: '',
      body: '',
      filename: '',
      templates: [],
      senders: [],
      sender: '',
    });
    Promise.all([
      fetch(`/api/users/${user.id}/mail-preview`).then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = body.detail;
          throw new Error(typeof detail === 'string' ? detail : `HTTP ${res.status}`);
        }
        return body;
      }),
      fetch('/api/templates').then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) return { templates: [] };
        return body;
      }),
      mailAccounts
        ? Promise.resolve(mailAccounts)
        : fetch('/api/mail-accounts')
            .then(async (res) => {
              const body = await res.json().catch(() => ({}));
              if (!res.ok) return null;
              return body;
            })
            .catch(() => null),
    ])
      .then(([data, templateData, accountsData]) => {
        if (seq !== mailPreviewSeq.current) return;
        const listed = templateData.templates || [];
        const previewTemplates = data.templates || [];
        const templates = listed.length ? listed : previewTemplates;
        const accounts = accountsData?.accounts || mailAccounts?.accounts || [];
        setContactModal((current) =>
          current && current.user.id === user.id
            ? {
                ...current,
                loading: false,
                subject: data.subject || '',
                body: data.body || '',
                filename: data.filename || templates[0]?.filename || '',
                templates,
                senders: data.senders || [],
                sender: data.sender || (data.senders || [])[0] || '',
                senderAccounts: accounts,
              }
            : current
        );
      })
      .catch((err) => {
        if (seq !== mailPreviewSeq.current) return;
        toast.error(`Unable to render the mail: ${err.message}`);
        setContactModal(null);
      });
  };

  const openSocialContact = (user, link) => {
    setContactModal({ channel: 'social', user, link, loading: false });
  };

  const reloadMailPreview = ({ sender, template } = {}) => {
    const currentModal = contactModal;
    if (!currentModal || currentModal.channel !== 'email' || !currentModal.user?.id) return;
    const nextSender = sender ?? currentModal.sender ?? '';
    const nextTemplate = template ?? currentModal.filename ?? '';
    const chosen = (currentModal.templates || []).find((item) => item.filename === nextTemplate);
    if (chosen && chosen.subject != null) {
      const person = currentModal.user.display_name || currentModal.user.name || '';
      const yourName = senderDisplayName(nextSender, currentModal.senderAccounts);
      const link = currentModal.user.link || '';
      setContactModal((current) => {
        if (!current || current.channel !== 'email') return current;
        return {
          ...current,
          sender: nextSender,
          filename: chosen.filename,
          subject: renderTemplateText(chosen.subject, person, yourName, link),
          body: renderTemplateText(chosen.body, person, yourName, link),
        };
      });
      return;
    }
    const seq = mailPreviewSeq.current + 1;
    mailPreviewSeq.current = seq;
    setContactModal((current) => {
      if (!current || current.channel !== 'email') return current;
      return { ...current, sender: nextSender, filename: nextTemplate };
    });
    const params = new URLSearchParams();
    if (nextSender) params.set('sender', nextSender);
    if (nextTemplate) params.set('template', nextTemplate);
    fetch(`/api/users/${currentModal.user.id}/mail-preview?${params.toString()}`)
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = body.detail;
          throw new Error(typeof detail === 'string' ? detail : `HTTP ${res.status}`);
        }
        return body;
      })
      .then((data) => {
        if (seq !== mailPreviewSeq.current) return;
        setContactModal((current) =>
          current && current.channel === 'email'
            ? {
                ...current,
                loading: false,
                subject: data.subject || '',
                body: data.body || '',
                filename: data.filename || nextTemplate,
                templates: data.templates || current.templates || [],
                sender: data.sender || nextSender,
              }
            : current
        );
      })
      .catch((err) => {
        if (seq !== mailPreviewSeq.current) return;
        toast.error(`Unable to render the mail: ${err.message}`);
        setContactModal((current) => (current ? { ...current, loading: false } : current));
      });
  };

  const saveContact = (status) => {
    if (!contactModal?.user) return;
    const { user, channel, sender } = contactModal;
    if (channel === 'email' && status === 'sent' && !String(sender || '').trim()) {
      toast.error('Choose a sender before marking the mail sent.');
      return;
    }
    setContactModal((current) => (current ? { ...current, saving: true } : current));
    fetch(`/api/users/${user.id}/contact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        channel,
        status,
        sender_email: channel === 'email' && status === 'sent' ? sender : '',
        template: channel === 'email' ? contactModal.filename || '' : '',
        url: channel === 'social' ? contactModal.link?.url || '' : '',
      }),
    })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = body.detail;
          throw new Error(typeof detail === 'string' ? detail : `HTTP ${res.status}`);
        }
        return body;
      })
      .then((data) => {
        const saved = { ...(data.user || {}) };
        if (channel === 'social' && contactModal.link?.url) {
          const target = String(contactModal.link.url).replace(/\/$/, '').toLowerCase();
          const links = Array.isArray(saved.socials) ? saved.socials : user.socials;
          saved.socials = (Array.isArray(links) ? links : []).map((link) => {
            const key = String(link?.url || '').replace(/\/$/, '').toLowerCase();
            if (key !== target) return link;
            return { ...link, status };
          });
        }
        setUsers((list) =>
          list.map((row) => (row.id === user.id ? { ...row, ...saved } : row))
        );
        if (channel === 'email') {
          loadCountries();
        }
        const name = String(user.display_name || user.name || user.email || 'User').trim();
        const label = status === 'sent' ? 'sent' : status === 'failed' ? 'failed' : 'cleared';
        const what = channel === 'social' ? socialProviderLabel(contactModal.link?.provider) : 'email';
        toast.success(`${name}: ${what} marked ${label}.`);
        setContactModal(null);
      })
      .catch((err) => {
        toast.error(`Unable to save contact: ${err.message}`);
        setContactModal((current) => (current ? { ...current, saving: false } : current));
      });
  };

  const handleOutcomeChange = (user, value) => {
    const previous = user.outcome || 'Waiting';
    if (value === previous || savingOutcomeIds.has(user.id)) {
      return;
    }
    setUsers((list) =>
      list.map((row) => (row.id === user.id ? { ...row, outcome: value } : row))
    );
    setSavingOutcomeIds((currentIds) => {
      const nextIds = new Set(currentIds);
      nextIds.add(user.id);
      return nextIds;
    });
    setError('');
    fetch(`/api/users/${user.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ outcome: value }),
    })
      .then((res) => {
        if (!res.ok) {
          return res.json().then((body) => {
            const detail = body.detail;
            const message = typeof detail === 'string' ? detail : `HTTP ${res.status}`;
            throw new Error(message);
          });
        }
        return res.json();
      })
      .then((data) => {
        const saved = data.user || {};
        setUsers((list) =>
          list.map((row) => (row.id === user.id ? { ...row, ...saved, outcome: value } : row))
        );
      })
      .catch((err) => {
        setUsers((list) =>
          list.map((row) =>
            row.id === user.id ? { ...row, outcome: previous } : row
          )
        );
        const message = `Unable to save outcome: ${err.message}`;
        setError(message);
        toast.error(message);
      })
      .finally(() => {
        setSavingOutcomeIds((currentIds) => {
          const nextIds = new Set(currentIds);
          nextIds.delete(user.id);
          return nextIds;
        });
      });
  };

  const handleSuppressUser = (user) => {
    if (suppressingIds.has(user.id)) {
      return;
    }
    const name = String(user.display_name || user.name || user.email || 'this user').trim();
    if (
      !window.confirm(
        `Suppress ${name}?\n\nThey will be hidden from the pool. The saved record stays so a later scrape cannot add them again.`
      )
    ) {
      return;
    }
    setSuppressingIds((currentIds) => {
      const nextIds = new Set(currentIds);
      nextIds.add(user.id);
      return nextIds;
    });
    setError('');
    fetch(`/api/users/${user.id}/suppress`, { method: 'POST' })
      .then((res) => {
        if (!res.ok) {
          return res.json().then((body) => {
            const detail = body.detail;
            const message = typeof detail === 'string' ? detail : `HTTP ${res.status}`;
            throw new Error(message);
          });
        }
        return res.json();
      })
      .then(() => {
        toast.success(`Suppressed ${name}.`);
        loadCountries();
        fetchUsers({ silent: true });
      })
      .catch((err) => {
        const message = `Unable to suppress ${name}: ${err.message}`;
        setError(message);
        toast.error(message);
      })
      .finally(() => {
        setSuppressingIds((currentIds) => {
          const nextIds = new Set(currentIds);
          nextIds.delete(user.id);
          return nextIds;
        });
      });
  };

  const handleScraperPause = (paused) => {
    setLoading(true);
    setError('');
    fetch('/api/scraper/pause', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paused }),
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail || res.statusText;
          throw new Error(typeof detail === 'string' ? detail : 'Request failed');
        }
        return data;
      })
      .then((data) => {
        toast.success(paused ? 'Scraper paused.' : 'Scraper resumed.');
        if (data.scraper) {
          applyScraperInfo(data.scraper);
        } else {
          loadScraperInfo();
        }
      })
      .catch((err) => {
        const message = `Unable to update scraper: ${err.message}`;
        setError(message);
        toast.error(message);
      })
      .finally(() => setLoading(false));
  };

  const handleSaveScrapeCap = () => {
    setLoading(true);
    setError('');
    const payload =
      capMode === 'manual'
        ? { cap_mode: 'manual', daily_cap: Number(capInput) }
        : { cap_mode: 'auto' };
    fetch('/api/scraper/cap', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail || res.statusText;
          throw new Error(typeof detail === 'string' ? detail : 'Request failed');
        }
        return data;
      })
      .then((data) => {
        toast.success(
          capMode === 'manual'
            ? `Daily scrape cap set to ${payload.daily_cap}.`
            : 'Daily scrape cap set to auto (mail-cap ratio).'
        );
        setCapDirty(false);
        if (data.scraper) {
          const next = data.scraper;
          setScraperInfo(next);
          const mode = next.cap_mode === 'manual' ? 'manual' : 'auto';
          setCapMode(mode);
          setCapInput(
            String(
              mode === 'manual'
                ? next.daily_limit_override ?? next.daily_limit ?? ''
                : next.auto_daily_limit ?? next.daily_limit ?? ''
            )
          );
        } else {
          loadScraperInfo();
        }
      })
      .catch((err) => {
        const message = `Unable to save scrape cap: ${err.message}`;
        setError(message);
        toast.error(message);
      })
      .finally(() => setLoading(false));
  };

  const openCreateTemplateModal = (region = '') => {
    setTemplateSaveMode('create');
    setTemplateFilename('');
    setTemplateRegion(region || selectedTemplateRegion || 'etc');
    setTemplateSubject('');
    setTemplateBody('');
    setTemplateModalOpen(true);
  };

  const openEditTemplateModal = (item) => {
    setTemplateSaveMode('update');
    setTemplateFilename(item.filename || '');
    setTemplateRegion(item.region || 'etc');
    setTemplateSubject(item.subject || '');
    setTemplateBody(item.body || '');
    setTemplateModalOpen(true);
  };

  const closeTemplateModal = () => {
    setTemplateModalOpen(false);
    setTemplateSaveMode('create');
    setTemplateFilename('');
    setTemplateSubject('');
    setTemplateBody('');
  };

  const handleSaveTemplate = () => {
    if (!canSaveTemplate) {
      return;
    }
    setLoading(true);
    setError('');
    const isUpdate = templateSaveMode === 'update' && templateFilename;
    const url = isUpdate
      ? `/api/templates/${encodeURIComponent(templateFilename)}`
      : '/api/templates';
    fetch(url, {
      method: isUpdate ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        region: templateRegion,
        subject: templateSubject.trim(),
        body: templateBody,
      }),
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail || res.statusText;
          throw new Error(typeof detail === 'string' ? detail : 'Request failed');
        }
        return data;
      })
      .then((data) => {
        const saved = data.template || {};
        toast.success(isUpdate ? 'Template updated.' : 'Template added.');
        closeTemplateModal();
        if (saved.region) {
          setSelectedTemplateRegion(saved.region);
        }
        loadTemplates();
      })
      .catch((err) => {
        const message = `Unable to save template: ${err.message}`;
        setError(message);
        toast.error(message);
      })
      .finally(() => setLoading(false));
  };

  const handleExcludeCountry = (country) => {
    const slug = String(country?.country || '').trim();
    if (!slug || slug === 'noloc') {
      return;
    }
    const name = formatCountryName(slug);
    const total = Number(country.count) || 0;
    const noun = total === 1 ? 'user' : 'users';
    if (
      !window.confirm(
        `Exclude ${name} permanently?\n\nThis deletes ${total} ${noun} from the database and stops scraping this country.`
      )
    ) {
      return;
    }
    setLoading(true);
    setError('');
    fetch(`/api/countries/${encodeURIComponent(slug)}/exclude`, {
      method: 'POST',
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail || res.statusText;
          throw new Error(typeof detail === 'string' ? detail : 'Request failed');
        }
        return data;
      })
      .then((data) => {
        const deleted = Number(data.deleted) || 0;
        toast.success(
          `Excluded ${name}. Deleted ${deleted} ${deleted === 1 ? 'user' : 'users'}.`
        );
        if (selectedCountry === slug) {
          setSelectedCountry('');
          setUsers([]);
          setTotal(0);
          setPage(1);
        }
        loadCountries();
        if (selectedCountry !== slug) {
          fetchUsers({ silent: true });
        }
      })
      .catch((err) => {
        const message = `Unable to exclude ${name}: ${err.message}`;
        setError(message);
        toast.error(message);
      })
      .finally(() => setLoading(false));
  };

  const handleDeleteTemplate = (item) => {
    if (!item?.filename) {
      return;
    }
    if (!window.confirm(`Delete ${item.filename}?`)) {
      return;
    }
    setLoading(true);
    setError('');
    fetch(`/api/templates/${encodeURIComponent(item.filename)}`, {
      method: 'DELETE',
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail || res.statusText;
          throw new Error(typeof detail === 'string' ? detail : 'Request failed');
        }
        return data;
      })
      .then(() => {
        toast.success(`Deleted ${item.filename}.`);
        if (templateFilename === item.filename) {
          closeTemplateModal();
        }
        loadTemplates();
      })
      .catch((err) => {
        const message = `Unable to delete template: ${err.message}`;
        setError(message);
        toast.error(message);
      })
      .finally(() => setLoading(false));
  };
  return {
    view,
    setView,
    contactModal,
    setContactModal,
    countries,
    setCountries,
    selectedCountry,
    setSelectedCountry,
    query,
    setQuery,
    socialFilters,
    setSocialFilters,
    users,
    setUsers,
    total,
    setTotal,
    page,
    setPage,
    pageSize,
    loading,
    setLoading,
    error,
    setError,
    mailAccounts,
    setMailAccounts,
    mailEmail,
    setMailEmail,
    mailSenderName,
    setMailSenderName,
    mailSaveMode,
    setMailSaveMode,
    mailModalOpen,
    setMailModalOpen,
    scraperInfo,
    setScraperInfo,
    selectedScraper,
    setSelectedScraper,
    capMode,
    setCapMode,
    capInput,
    setCapInput,
    capDirty,
    setCapDirty,
    displayNameDrafts,
    setDisplayNameDrafts,
    savingDisplayNameIds,
    setSavingDisplayNameIds,
    editingDisplayNameId,
    setEditingDisplayNameId,
    savingOutcomeIds,
    setSavingOutcomeIds,
    suppressingIds,
    setSuppressingIds,
    templates,
    setTemplates,
    templateCatalog,
    setTemplateCatalog,
    selectedTemplateRegion,
    setSelectedTemplateRegion,
    templateModalOpen,
    setTemplateModalOpen,
    templateSaveMode,
    setTemplateSaveMode,
    templateFilename,
    setTemplateFilename,
    templateRegion,
    setTemplateRegion,
    templateSubject,
    setTemplateSubject,
    templateBody,
    setTemplateBody,
    loadMailAccounts,
    applyScraperInfo,
    loadScraperInfo,
    loadTemplates,
    loadCountries,
    selectedSocials,
    fetchUsers,
    searchQuery,
    isGlobalSearch,
    showUserTable,
    pageCount,
    mailAccountsData,
    accounts,
    sortedCountries,
    sidebarCountries,
    sidebarTotal,
    selectedCountryMeta,
    trimmedMailEmail,
    isEditMode,
    canSaveMailAccount,
    templateGroups,
    templateCountries,
    templateCustom,
    selectedGroupMeta,
    selectedMatchHint,
    editingGroupMeta,
    editingMatchHint,
    visibleTemplates,
    canSaveTemplate,
    templateSidebarCountries,
    templateSidebarCustom,
    handleResetMailForm,
    openCreateMailModal,
    openEditMailModal,
    closeMailModal,
    handleAddMailAccount,
    handleDeleteMailAccount,
    displayNameValue,
    handleDisplayNameChange,
    handleCancelDisplayName,
    handleSaveDisplayName,
    handleSaveLocation,
    openEmailContact,
    openSocialContact,
    reloadMailPreview,
    saveContact,
    handleOutcomeChange,
    handleSuppressUser,
    handleScraperPause,
    handleSaveScrapeCap,
    openCreateTemplateModal,
    openEditTemplateModal,
    closeTemplateModal,
    handleSaveTemplate,
    handleExcludeCountry,
    handleDeleteTemplate,
  };
}
