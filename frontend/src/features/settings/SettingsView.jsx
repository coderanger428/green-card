import { useEffect, useState } from 'react';
import Modal from 'react-modal';
import toast from 'react-hot-toast';
import { useDashboard } from '../../app/DashboardContext';
import { IconRefresh } from '../../components/Icons';
import { formatDateOnly, maskEmail } from '../../lib/format';
import { cls } from '../../styles/cls';
import ui from '../../styles/ui.module.css';
import pool from '../../styles/pool.module.css';
import modal from '../../styles/modal.module.css';
import settings from '../../styles/settings.module.css';

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

function tokyoExpiration(iso) {
  if (!iso) {
    return '';
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Tokyo',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const pick = (type) => parts.find((part) => part.type === type)?.value || '';
  return `${pick('year')}-${pick('month')}-${pick('day')} ${pick('hour')}:${pick('minute')} JST`;
}

function expiresWithinWeek(iso) {
  if (!iso) {
    return false;
  }
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) {
    return false;
  }
  const remaining = time - Date.now();
  return remaining > 0 && remaining < WEEK_MS;
}

function TokenExpiry({ info }) {
  if (!info) {
    return null;
  }
  if (info.status === 'expired' || info.expired) {
    return <span className={cls(settings, 'token-expired')}>Expired</span>;
  }
  if (info.status === 'invalid') {
    return <span className={cls(settings, 'token-invalid')}>Invalid</span>;
  }
  if (info.status === 'no_expiration') {
    return <span>Does not expire</span>;
  }
  const when = tokyoExpiration(info.expires_at) || info.expires_label;
  const soon = Boolean(info.expires_soon) || (info.status === 'ok' && expiresWithinWeek(info.expires_at));
  if (!when && info.status === 'unreachable') {
    return <span>Could not check expiration</span>;
  }
  return (
    <>
      {when ? (
        <time dateTime={info.expires_at} title="Tokyo time (UTC+9)">
          {when}
        </time>
      ) : null}
      {soon ? <span className={cls(settings, 'token-soon')}>Expired soon</span> : null}
      {info.status === 'unreachable' ? <span>Could not check expiration</span> : null}
    </>
  );
}

export function SettingsView() {
  const {
    view,
    loading,
    error,
    mailAccounts,
    mailEmail,
    setMailEmail,
    mailSenderName,
    setMailSenderName,
    mailModalOpen,
    accounts,
    isEditMode,
    canSaveMailAccount,
    openCreateMailModal,
    openEditMailModal,
    closeMailModal,
    handleAddMailAccount,
    handleDeleteMailAccount,
  } = useDashboard();
  const [githubInfo, setGithubInfo] = useState(null);
  const [githubDraft, setGithubDraft] = useState('');
  const [githubSaving, setGithubSaving] = useState(false);
  const [githubReady, setGithubReady] = useState(null);
  const [renewOpen, setRenewOpen] = useState(false);
  const [renewError, setRenewError] = useState('');

  useEffect(() => {
    if (view !== 'senders') {
      return undefined;
    }
    let stop = false;
    const load = () => {
      fetch('/api/github-token')
        .then(async (res) => {
          if (res.status === 404) {
            return { missing: true };
          }
          if (!res.ok) {
            return null;
          }
          return res.json();
        })
        .then((data) => {
          if (stop || !data) {
            return;
          }
          if (data.missing) {
            setGithubReady(false);
            return;
          }
          setGithubReady(true);
          setGithubInfo(data);
        })
        .catch(() => {
          if (!stop) {
            setGithubReady(false);
          }
        });
    };
    load();
    const id = window.setInterval(load, 5000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, [view]);

  const closeRenewModal = () => {
    if (githubSaving) {
      return;
    }
    setRenewOpen(false);
    setGithubDraft('');
    setRenewError('');
  };

  const saveGithubToken = () => {
    const token = githubDraft.trim();
    if (!token || githubSaving) {
      return;
    }
    setGithubSaving(true);
    setRenewError('');
    fetch('/api/github-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = body.detail;
          const message = Array.isArray(detail)
            ? detail.map((item) => item.msg).filter(Boolean).join(' ')
            : detail || `HTTP ${res.status}`;
          throw new Error(message);
        }
        return body;
      })
      .then((data) => {
        setGithubInfo(data);
        setGithubDraft('');
        setGithubReady(true);
        setRenewOpen(false);
        setRenewError('');
        toast.success('GitHub token replaced.');
      })
      .catch((err) => {
        setRenewError(err.message);
      })
      .finally(() => setGithubSaving(false));
  };

  const checkGithubToken = () => {
    if (githubSaving) {
      return;
    }
    setGithubSaving(true);
    fetch('/api/github-token/check', { method: 'POST' })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        return body;
      })
      .then((data) => {
        setGithubInfo(data);
      })
      .catch((err) => {
        toast.error(`Unable to check GitHub token: ${err.message}`);
      })
      .finally(() => setGithubSaving(false));
  };

  return (
    <>
        {view === 'senders' && (
          <section className={`${cls(ui, "card")} ${"status-card"}`}>
            <h2>Settings</h2>
            {error && <div className={cls(ui, "alert")}>{error}</div>}
            {githubReady === false && (
              <div className={cls(ui, "alert")}>
                This dashboard process does not serve token or sender-name settings yet. They appear after the next restart. The scrape that is already running keeps the token it loaded at start.
              </div>
            )}
            <div className={cls(ui, "section-block")}>
              <div className={cls(ui, "section-header")}>
                <div>
                  <h3>GitHub token</h3>
                </div>
              </div>
              <div className={cls(settings, "token-line")}>
                <span>Current token:</span>
                {githubInfo?.configured ? (
                  <>
                    <span className={cls(settings, "token-mask")}>{githubInfo.masked}</span>
                    <TokenExpiry info={githubInfo} />
                    <button
                      type="button"
                      className={cls(settings, "token-refresh")}
                      aria-label="Refresh expiration"
                      title="Refresh expiration"
                      onClick={checkGithubToken}
                      disabled={githubReady === false || githubSaving}
                    >
                      <IconRefresh />
                    </button>
                  </>
                ) : (
                  <span>No token saved</span>
                )}
                <button
                  type="button"
                  className={cls(settings, "token-renew")}
                  onClick={() => {
                    setRenewError('');
                    setGithubDraft('');
                    setRenewOpen(true);
                  }}
                  disabled={githubReady === false || githubSaving}
                >
                  Renew token
                </button>
              </div>
            </div>
            {!mailAccounts ? (
              <div className={cls(ui, "empty-state")}>Loading mail account info...</div>
            ) : (
              <>
                <div className={cls(ui, "section-block")}>
                  <div className={cls(ui, "section-header mail-accounts-header")}>
                    <div>
                      <h3>Sender addresses</h3>
                    </div>
                    <button type="button" onClick={openCreateMailModal}>
                      Add sender
                    </button>
                  </div>
                  {accounts.length > 0 ? (
                    <div className={cls(pool, "table-scroll")}>
                      <table className={cls(settings, "accounts-table")}>
                        <thead>
                          <tr>
                            <th>Name</th>
                            <th>Email</th>
                            <th>Sent</th>
                            <th>Added</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {accounts.map((account) => (
                            <tr key={account.email}>
                              <td>{account.sender_name || ''}</td>
                              <td>
                                <span title={account.email}>{maskEmail(account.email)}</span>
                              </td>
                              <td>{Number(account.sent_total) || 0}</td>
                              <td>{formatDateOnly(account.created_at)}</td>
                              <td>
                                <button
                                  type="button"
                                  className={cls(ui, "secondary-button table-action-button")}
                                  onClick={() => openEditMailModal(account)}
                                >
                                  Edit
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className={cls(ui, "empty-state")}>No senders configured</div>
                  )}
                </div>

              </>
            )}

            <Modal
              isOpen={renewOpen}
              onRequestClose={closeRenewModal}
              contentLabel="Renew token"
              className={cls(modal, "mail-modal token-modal")}
              overlayClassName={cls(modal, "mail-modal-overlay")}
            >
              <div className={cls(modal, "mail-modal-header")}>
                <h3>Renew token</h3>
              </div>
              <label>
                New token
                <input
                  type="password"
                  autoComplete="off"
                  value={githubDraft}
                  onChange={(event) => setGithubDraft(event.target.value)}
                  placeholder="Paste a GitHub token"
                  disabled={githubSaving}
                />
              </label>
              {renewError && <div className={cls(ui, "alert")}>{renewError}</div>}
              <div className={cls(ui, "form-actions-row form-actions-end")}>
                <button
                  type="button"
                  onClick={saveGithubToken}
                  disabled={githubSaving || !githubDraft.trim()}
                >
                  Replace
                </button>
                <button
                  type="button"
                  className={cls(ui, "secondary-button")}
                  onClick={closeRenewModal}
                  disabled={githubSaving}
                >
                  Cancel
                </button>
              </div>
            </Modal>

            <Modal
              isOpen={mailModalOpen}
              onRequestClose={closeMailModal}
              contentLabel={isEditMode ? 'Edit sender' : 'Add sender'}
              className={cls(modal, "mail-modal")}
              overlayClassName={cls(modal, "mail-modal-overlay")}
            >
              <div className={cls(modal, "mail-modal-header")}>
                <h3>{isEditMode ? 'Edit sender' : 'Add sender'}</h3>
                <button
                  type="button"
                  className={cls(ui, "secondary-button")}
                  onClick={closeMailModal}
                >
                  Close
                </button>
              </div>
              <label>
                Sender name
                <input
                  type="text"
                  value={mailSenderName}
                  onChange={(event) => setMailSenderName(event.target.value)}
                  placeholder="Your name"
                />
              </label>
              <label>
                Gmail address
                <input
                  type="email"
                  value={mailEmail}
                  onChange={(event) => setMailEmail(event.target.value)}
                  placeholder="your-account@gmail.com"
                  disabled={isEditMode}
                />
              </label>
              <div className={cls(ui, "form-actions-row")}>
                <button
                  type="button"
                  onClick={handleAddMailAccount}
                  disabled={!canSaveMailAccount}
                >
                  {isEditMode ? 'Update account' : 'Add account'}
                </button>
                {isEditMode && (
                  <button
                    type="button"
                    className={cls(ui, "delete-button")}
                    onClick={handleDeleteMailAccount}
                    disabled={loading}
                  >
                    Delete account
                  </button>
                )}
              </div>
            </Modal>
          </section>
        )}
    </>
  );
}
