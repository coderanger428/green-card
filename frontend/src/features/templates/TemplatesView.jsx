import Modal from 'react-modal';
import { RegionSuggest } from './RegionSuggest';
import { useDashboard } from '../../app/DashboardContext';
import { formatCountryName, formatDateOnly } from '../../lib/format';
import { cls } from '../../styles/cls';
import layout from '../../styles/layout.module.css';
import ui from '../../styles/ui.module.css';
import pool from '../../styles/pool.module.css';
import modal from '../../styles/modal.module.css';
import templates from '../../styles/templates.module.css';

function templateUpdatedOn(value) {
  const parsed = value ? new Date(value) : null;
  if (parsed && !Number.isNaN(parsed.getTime())) {
    return formatDateOnly(value);
  }
  return formatDateOnly(new Date().toISOString());
}

export function TemplatesView() {
  const {
    view,
    countries,
    users,
    loading,
    error,
    templates,
    selectedTemplateRegion,
    setSelectedTemplateRegion,
    templateModalOpen,
    templateSaveMode,
    templateFilename,
    templateRegion,
    setTemplateRegion,
    templateSubject,
    setTemplateSubject,
    templateBody,
    setTemplateBody,
    accounts,
    templateGroups,
    templateCountries,
    templateCustom,
    selectedGroupMeta,
    selectedMatchHint,
    visibleTemplates,
    canSaveTemplate,
    templateSidebarCountries,
    templateSidebarCustom,
    openCreateTemplateModal,
    openEditTemplateModal,
    closeTemplateModal,
    handleSaveTemplate,
    handleDeleteTemplate,
  } = useDashboard();
  return (
    <>
        {view === 'templates' && (
          <section className={cls(layout, "users-layout")}>
            <aside className={`${cls(ui, "card")} ${cls(layout, "countries-sidebar")}`}>
              <div className={cls(layout, "countries-sidebar-header")}>Regions</div>
              <div className={cls(layout, "countries-list")} role="listbox" aria-label="Template regions">
                <button
                  type="button"
                  role="option"
                  aria-selected={!selectedTemplateRegion}
                  className={cls(layout, !selectedTemplateRegion
                      ? 'country-list-item active'
                      : 'country-list-item')}
                  onClick={() => setSelectedTemplateRegion('')}
                >
                  <div className={cls(layout, "country-list-top")}>
                    <span className={cls(layout, "country-list-name")}>All templates</span>
                    <span className={cls(layout, "country-list-count")}>{templates.length}</span>
                  </div>
                </button>
                {templateGroups.map((item) => (
                  <button
                    key={item.slug}
                    type="button"
                    role="option"
                    aria-selected={selectedTemplateRegion === item.slug}
                    className={cls(layout, selectedTemplateRegion === item.slug
                        ? 'country-list-item active'
                        : 'country-list-item')}
                    onClick={() => setSelectedTemplateRegion(item.slug)}
                  >
                    <div className={cls(layout, "country-list-top")}>
                      <span className={cls(layout, "country-list-name")}>{item.label}</span>
                      <span className={cls(layout, "country-list-count")}>{item.templates || 0}</span>
                    </div>
                  </button>
                ))}
                {templateSidebarCountries.length > 0 ? (
                  <>
                    <div className={cls(templates, "region-sidebar-label")}>Countries</div>
                    {templateSidebarCountries.map((item) => (
                      <button
                        key={item.slug}
                        type="button"
                        role="option"
                        aria-selected={selectedTemplateRegion === item.slug}
                        className={cls(layout, selectedTemplateRegion === item.slug
                            ? 'country-list-item active'
                            : 'country-list-item')}
                        onClick={() => setSelectedTemplateRegion(item.slug)}
                      >
                        <div className={cls(layout, "country-list-top")}>
                          <span className={cls(layout, "country-list-name")}>{formatCountryName(item.slug)}</span>
                          <span className={cls(layout, "country-list-count")}>{item.templates || 0}</span>
                        </div>
                      </button>
                    ))}
                  </>
                ) : null}
                {templateSidebarCustom.length > 0 ? (
                  <>
                    <div className={cls(templates, "region-sidebar-label")}>Custom</div>
                    {templateSidebarCustom.map((item) => (
                      <button
                        key={item.slug}
                        type="button"
                        role="option"
                        aria-selected={selectedTemplateRegion === item.slug}
                        className={cls(layout, selectedTemplateRegion === item.slug
                            ? 'country-list-item active'
                            : 'country-list-item')}
                        onClick={() => setSelectedTemplateRegion(item.slug)}
                      >
                        <div className={cls(layout, "country-list-top")}>
                          <span className={cls(layout, "country-list-name")}>{formatCountryName(item.slug)}</span>
                          <span className={cls(layout, "country-list-count")}>{item.templates || 0}</span>
                        </div>
                      </button>
                    ))}
                  </>
                ) : null}
              </div>
            </aside>

            <div className={cls(layout, "users-main")}>
              <section className={`${cls(ui, "card")} ${"status-card"}`}>
                <div className={cls(ui, "section-header mail-accounts-header")}>
                  <div>
                    <h2>Templates</h2>
                    {selectedMatchHint ? (
                      <p className={cls(ui, "help-text")}>{selectedMatchHint}</p>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => openCreateTemplateModal()}
                  >
                    Add template
                  </button>
                </div>
                {error && <div className={cls(ui, "alert")}>{error}</div>}
                {visibleTemplates.length === 0 ? (
                  <div className={cls(ui, "empty-state")}>
                    {selectedMatchHint
                      ? `No ${selectedGroupMeta.label} templates yet. Add one and it is used for those countries automatically.`
                      : selectedTemplateRegion
                        ? 'No templates in this region yet.'
                        : 'No templates found.'}
                  </div>
                ) : (
                  <div className={cls(pool, "table-scroll")}>
                    <table className={cls(pool, "users-table")}>
                      <thead>
                        <tr>
                          <th>Region</th>
                          <th>Subject</th>
                          <th>Updated</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {visibleTemplates.map((item) => (
                          <tr key={item.filename}>
                            <td>{formatCountryName(item.region)}</td>
                            <td>{item.subject || '-'}</td>
                            <td>{templateUpdatedOn(item.updated_at)}</td>
                            <td>
                              <div className={cls(ui, "form-actions-row")}>
                                <button
                                  type="button"
                                  className={cls(ui, "secondary-button table-action-button")}
                                  onClick={() => openEditTemplateModal(item)}
                                >
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  className={cls(ui, "delete-button table-action-button")}
                                  onClick={() => handleDeleteTemplate(item)}
                                  disabled={loading}
                                >
                                  Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </div>

            <Modal
              isOpen={templateModalOpen}
              onRequestClose={closeTemplateModal}
              contentLabel={
                templateSaveMode === 'update' ? 'Edit template' : 'Add template'
              }
              className={cls(modal, "mail-modal template-modal")}
              overlayClassName={cls(modal, "mail-modal-overlay")}
            >
              <div className={cls(modal, "mail-modal-header")}>
                <h3>{templateSaveMode === 'update' ? 'Edit template' : 'Add template'}</h3>
                <button
                  type="button"
                  className={cls(ui, "secondary-button")}
                  onClick={closeTemplateModal}
                >
                  Close
                </button>
              </div>
              <label>
                Region
                <RegionSuggest
                  groups={templateGroups}
                  countries={templateCountries}
                  custom={templateCustom}
                  value={templateRegion}
                  onChange={setTemplateRegion}
                  disabled={loading}
                />
              </label>
              <label>
                Subject
                <input
                  type="text"
                  value={templateSubject}
                  onChange={(event) => setTemplateSubject(event.target.value)}
                  placeholder="Subject line"
                  maxLength={200}
                />
              </label>
              <label>
                Body
                <textarea
                  value={templateBody}
                  onChange={(event) => setTemplateBody(event.target.value)}
                  placeholder="Plain-text email body"
                  rows={12}
                />
              </label>
              <div className={cls(ui, "form-actions-row")}>
                <button
                  type="button"
                  onClick={handleSaveTemplate}
                  disabled={!canSaveTemplate}
                >
                  {templateSaveMode === 'update' ? 'Save template' : 'Add template'}
                </button>
                {templateSaveMode === 'update' && templateFilename ? (
                  <button
                    type="button"
                    className={cls(ui, "delete-button")}
                    onClick={() =>
                      handleDeleteTemplate({ filename: templateFilename })
                    }
                    disabled={loading}
                  >
                    Delete template
                  </button>
                ) : null}
              </div>
            </Modal>
          </section>
        )}
    </>
  );
}
