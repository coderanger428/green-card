import Modal from 'react-modal';
import { SocialIcon } from '../../components/SocialIcon';
import { IconCopy, IconAt, IconChain, IconPhone } from '../../components/Icons';
import { useDashboard } from '../../app/DashboardContext';
import { socialProviderLabel, socialCopyValue } from '../../lib/social';
import { copyText } from '../../lib/clipboard';
import { cls } from '../../styles/cls';
import ui from '../../styles/ui.module.css';
import modal from '../../styles/modal.module.css';

const SocialKindMark = ({ kind }) => {
  const label = kind === 'username' ? 'Username' : kind === 'phone' ? 'Phone' : 'Link';
  return (
    <span className={cls(modal, "social-kind-mark")} title={label} aria-label={label}>
      {kind === 'username' ? <IconAt /> : kind === 'phone' ? <IconPhone /> : <IconChain />}
    </span>
  );
};

export function ContactModal() {
  const {
    contactModal,
    setContactModal,
    reloadMailPreview,
    saveContact,
  } = useDashboard();
  return (
    <>
        <Modal
          isOpen={Boolean(contactModal)}
          onRequestClose={() => setContactModal(null)}
          contentLabel={contactModal?.channel === 'social' ? 'Social contact' : 'Email contact'}
          className={cls(modal, "mail-modal contact-modal")}
          overlayClassName={cls(modal, "mail-modal-overlay")}
        >
          {contactModal ? (
            <>
              <div className={cls(modal, "mail-modal-header")}>
                <h3>
                  {contactModal.channel === 'social' ? (
                    <span className={cls(modal, "social-modal-platform")}>
                      <SocialIcon size="lg" provider={contactModal.link?.provider} />
                      {socialProviderLabel(contactModal.link?.provider)}
                    </span>
                  ) : (
                    'Email'
                  )}
                  <span aria-hidden="true">·</span>
                  <span>
                    {contactModal.user.display_name || contactModal.user.name || contactModal.user.email}
                  </span>
                </h3>
                <button type="button" className={cls(ui, "secondary-button")} onClick={() => setContactModal(null)}>
                  Cancel
                </button>
              </div>
              {contactModal.channel === 'email' ? (
                contactModal.loading ? (
                  <p>Rendering the template…</p>
                ) : (
                  <>
                    <div className={cls(modal, "mail-field-row")}>
                      <label>
                        Sender
                        <select
                          value={contactModal.sender || ''}
                          onChange={(event) => reloadMailPreview({ sender: event.target.value })}
                        >
                          {(contactModal.senders || []).length === 0 ? (
                            <option value="">Add a sender in Settings</option>
                          ) : (
                            contactModal.senders.map((email) => (
                              <option key={email} value={email}>
                                {email}
                              </option>
                            ))
                          )}
                        </select>
                      </label>
                      <label>
                        Template
                        <select
                          value={contactModal.filename || ''}
                          onChange={(event) => reloadMailPreview({ template: event.target.value })}
                        >
                          {(contactModal.templates || []).length === 0 ? (
                            <option value="">No templates</option>
                          ) : (
                            contactModal.templates.map((item) => (
                              <option key={item.filename} value={item.filename}>
                                {item.filename}
                              </option>
                            ))
                          )}
                        </select>
                      </label>
                    </div>
                    <label>
                      To
                      <span className={cls(modal, "copy-row")}>
                        <span className={cls(modal, "copy-value")}>{contactModal.user.email}</span>
                        <button type="button" className={`${cls(ui, "secondary-button")} ${cls(modal, "copy-button")}`} aria-label="Copy recipient" onClick={() => copyText(contactModal.user.email)}>
                          <IconCopy />
                        </button>
                      </span>
                    </label>
                    <label>
                      Subject
                      <span className={cls(modal, "copy-row")}>
                        <input
                          type="text"
                          value={contactModal.subject || ''}
                          onChange={(event) =>
                            setContactModal((current) =>
                              current ? { ...current, subject: event.target.value } : current
                            )
                          }
                        />
                        <button type="button" className={`${cls(ui, "secondary-button")} ${cls(modal, "copy-button")}`} aria-label="Copy subject" onClick={() => copyText(contactModal.subject)}>
                          <IconCopy />
                        </button>
                      </span>
                    </label>
                    <label>
                      Body
                      <span className={cls(modal, "copy-row copy-row-body")}>
                        <textarea
                          rows={10}
                          value={contactModal.body || ''}
                          onChange={(event) =>
                            setContactModal((current) =>
                              current ? { ...current, body: event.target.value } : current
                            )
                          }
                        />
                        <button type="button" className={`${cls(ui, "secondary-button")} ${cls(modal, "copy-button")}`} aria-label="Copy body" onClick={() => copyText(contactModal.body)}>
                          <IconCopy />
                        </button>
                      </span>
                    </label>
                  </>
                )
              ) : (
                <div className={cls(modal, "social-copy-list")}>
                  {contactModal.link ? (
                    (() => {
                      const copy = socialCopyValue(contactModal.link.provider, contactModal.link.url);
                      return (
                        <div className={cls(modal, "social-copy-item")}>
                          <span className={cls(modal, "social-copy-provider")}>
                            <SocialIcon size="lg" provider={contactModal.link.provider} />
                            {socialProviderLabel(contactModal.link.provider)}
                          </span>
                          <SocialKindMark kind={copy.kind} />
                          <code>{copy.value}</code>
                          <button type="button" className={`${cls(ui, "secondary-button")} ${cls(modal, "copy-button")}`} aria-label={`Copy ${copy.label}`} onClick={() => copyText(copy.value)}>
                            <IconCopy />
                          </button>
                        </div>
                      );
                    })()
                  ) : (
                    <p>No social link selected.</p>
                  )}
                </div>
              )}
              <div className={cls(ui, "form-actions-row form-actions-end")}>
                <button
                  type="button"
                  className={`${"contact-action"} ${cls(modal, "contact-action-sent")}`}
                  disabled={contactModal.loading || contactModal.saving}
                  onClick={() => saveContact('sent')}
                >
                  Sent
                </button>
                <button
                  type="button"
                  className={`${"contact-action"} ${cls(modal, "contact-action-failed")}`}
                  disabled={contactModal.loading || contactModal.saving}
                  onClick={() => saveContact('failed')}
                >
                  Failed
                </button>
                <button
                  type="button"
                  className={cls(ui, "secondary-button")}
                  disabled={contactModal.loading || contactModal.saving}
                  onClick={() => saveContact('not_sent')}
                >
                  Clear
                </button>
              </div>
            </>
          ) : null}
        </Modal>
    </>
  );
}
