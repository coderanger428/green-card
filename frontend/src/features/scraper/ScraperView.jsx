import { DailyCapProgress } from '../../components/DailyCapProgress';
import { useDashboard } from '../../app/DashboardContext';
import { SCRAPER_STATUS_LABELS } from '../../lib/format';
import { SCRAPERS } from '../../lib/source';
import { cls } from '../../styles/cls';
import layout from '../../styles/layout.module.css';
import ui from '../../styles/ui.module.css';
import scraper from '../../styles/scraper.module.css';

export function ScraperView() {
  const {
    view,
    countries,
    users,
    loading,
    error,
    scraperInfo,
    selectedScraper,
    setSelectedScraper,
    capMode,
    setCapMode,
    capInput,
    setCapInput,
    setCapDirty,
    accounts,
    handleScraperPause,
    handleSaveScrapeCap,
  } = useDashboard();
  return (
    <>
        {view === 'scraper' && (
          <section className={cls(layout, "users-layout")}>
            <aside className={`${cls(ui, "card")} ${cls(layout, "countries-sidebar")}`}>
              <div className={cls(layout, "countries-sidebar-header")}>Scrapers</div>
              <div className={cls(layout, "countries-list")} role="listbox" aria-label="Scrapers">
                {SCRAPERS.map((scraper) => (
                  <button
                    key={scraper.id}
                    type="button"
                    role="option"
                    aria-selected={selectedScraper === scraper.id}
                    className={cls(layout, selectedScraper === scraper.id
                        ? 'country-list-item active'
                        : 'country-list-item')}
                    onClick={() => setSelectedScraper(scraper.id)}
                  >
                    <span className={cls(layout, "country-list-name")}>{scraper.label}</span>
                  </button>
                ))}
              </div>
            </aside>
            <div className={cls(layout, "users-main")}>
          <section className={`${cls(ui, "card")} ${"status-card"}`}>
            <h2>
              {SCRAPERS.find((scraper) => scraper.id === selectedScraper)?.label ||
                'Scraper'}
            </h2>
            {error && <div className={cls(ui, "alert")}>{error}</div>}
            {!scraperInfo ? (
              <div className={cls(ui, "empty-state")}>Loading scraper status...</div>
            ) : (
              <>
                <div className={cls(ui, "section-block")}>
                  <div className={cls(ui, "section-header mail-accounts-header")}>
                    <h3>Stats</h3>
                    <button
                      type="button"
                      className={cls(scraper, scraperInfo.paused
                          ? 'scrape-control-button is-resume'
                          : 'scrape-control-button is-pause')}
                      onClick={() => handleScraperPause(!scraperInfo.paused)}
                      disabled={loading || scraperInfo.status === 'stopped'}
                      title={
                        scraperInfo.status === 'stopped'
                          ? 'The scraper process is not running'
                          : undefined
                      }
                    >
                      {scraperInfo.paused ? (
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          width="14"
                          height="14"
                          viewBox="0 0 24 24"
                          aria-hidden="true"
                        >
                          <polygon points="7,4 20,12 7,20" fill="currentColor" />
                        </svg>
                      ) : (
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          width="14"
                          height="14"
                          viewBox="0 0 24 24"
                          aria-hidden="true"
                        >
                          <rect x="5" y="4" width="5" height="16" rx="1" fill="currentColor" />
                          <rect x="14" y="4" width="5" height="16" rx="1" fill="currentColor" />
                        </svg>
                      )}
                      {scraperInfo.paused ? 'Resume scraping' : 'Pause scraping'}
                    </button>
                  </div>
                  <div className={cls(ui, "status-grid")}>
                    <div className={cls(ui, "status-stat")}>
                      <strong>Process</strong>
                      <div className={cls(ui, "status-stat-value")}>
                        <span
                          className={cls(ui, `badge badge-scrape-${scraperInfo.status || 'stopped'}`)}
                        >
                          {SCRAPER_STATUS_LABELS[scraperInfo.status] || scraperInfo.status}
                        </span>
                      </div>
                    </div>
                    <div className={cls(ui, "status-stat")}>
                      <strong>Last Dev.to ID</strong>
                      <div className={cls(ui, "status-stat-value")}>{scraperInfo.last_id ?? 0}</div>
                    </div>
                    <div className={cls(ui, "status-stat")}>
                      <strong>Users saved</strong>
                      <div className={cls(ui, "status-stat-value")}>{scraperInfo.total_users ?? 0}</div>
                    </div>
                  </div>
                </div>

                <div className={cls(ui, "section-block")}>
                  <div className={cls(ui, "section-header")}>
                    <h3>Daily scrape cap</h3>
                  </div>
                  <div className={cls(ui, "status-grid")}>
                    <div className={cls(ui, "status-stat")}>
                      <strong>Located saved today</strong>
                      <DailyCapProgress
                        sent={scraperInfo.saved_today}
                        limit={scraperInfo.daily_limit}
                      />
                    </div>
                    <div className={cls(ui, "status-stat")}>
                      <strong>Cap mode</strong>
                      <div className={cls(ui, "status-stat-value")}>
                        {scraperInfo.cap_mode === 'manual' ? 'Manual' : 'Auto'}
                      </div>
                    </div>
                  </div>
                  <div className={cls(scraper, "scraper-cap-form")}>
                    <label className={cls(scraper, "checkbox-label")}>
                      <input
                        type="radio"
                        name="scrape-cap-mode"
                        checked={capMode === 'auto'}
                        onChange={() => {
                          setCapMode('auto');
                          setCapInput(String(scraperInfo.auto_daily_limit ?? ''));
                          setCapDirty(true);
                        }}
                      />
                      Auto ({Number(scraperInfo.ratio) || 1.5}× mail caps ={' '}
                      {scraperInfo.auto_daily_limit})
                    </label>
                    <label className={cls(scraper, "checkbox-label")}>
                      <input
                        type="radio"
                        name="scrape-cap-mode"
                        checked={capMode === 'manual'}
                        onChange={() => {
                          setCapMode('manual');
                          setCapInput(
                            String(
                              scraperInfo.daily_limit_override ??
                                scraperInfo.daily_limit ??
                                ''
                            )
                          );
                          setCapDirty(true);
                        }}
                      />
                      Manual
                    </label>
                    <label className={cls(scraper, "scraper-cap-input")}>
                      Located users per Tokyo day
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={capInput}
                        disabled={capMode !== 'manual'}
                        onChange={(event) => {
                          setCapInput(event.target.value);
                          setCapDirty(true);
                        }}
                      />
                    </label>
                    <div className={cls(ui, "form-actions-row")}>
                      <button
                        type="button"
                        onClick={handleSaveScrapeCap}
                        disabled={
                          loading ||
                          (capMode === 'manual' &&
                            (!Number.isInteger(Number(capInput)) ||
                              Number(capInput) < 1))
                        }
                      >
                        Save cap
                      </button>
                    </div>
                  </div>
                </div>
              </>
            )}
          </section>
            </div>
          </section>
        )}
    </>
  );
}
