import { Toaster } from 'react-hot-toast';
import { IconUsers, IconSettings, IconScraper, IconTemplates } from '../../components/Icons';
import { PoolView } from '../pool/PoolView';
import { ScraperView } from '../scraper/ScraperView';
import { SettingsView } from '../settings/SettingsView';
import { TemplatesView } from '../templates/TemplatesView';
import { ContactModal } from '../pool/ContactModal';
import { useDashboard } from '../../app/DashboardContext';
import { cls } from '../../styles/cls';
import shell from '../../styles/shell.module.css';

const NAV_ITEMS = [
  { id: 'scraper', label: 'Scraper', Icon: IconScraper },
  { id: 'pool', label: 'Pool', Icon: IconUsers },
  { id: 'templates', label: 'Templates', Icon: IconTemplates },
  { id: 'senders', label: 'Settings', Icon: IconSettings },
];

export function Shell() {
  const {
    view,
    setView,
    setPage,
  } = useDashboard();
  return (
    <div className={cls(shell, 'app-shell')}>
      <Toaster
        position="top-right"
        gutter={10}
        containerStyle={{ top: 76, right: 16 }}
        toastOptions={{
          duration: 4000,
          className: 'app-toast',
          style: {
            background: '#ffffff',
            color: '#1c2733',
            border: '1px solid #dde3eb',
            boxShadow: '0 10px 24px rgba(36, 62, 88, 0.12)',
            maxWidth: 420,
          },
          success: {
            iconTheme: { primary: '#16a34a', secondary: '#ffffff' },
          },
          error: {
            iconTheme: { primary: '#dc2626', secondary: '#ffffff' },
          },
        }}
      />
      <header className={cls(shell, "topbar")}>
        <div className={cls(shell, "topbar-inner")}>
          <button
            type="button"
            className={cls(shell, "topbar-brand")}
            onClick={() => setView('pool')}
          >
            <span className={cls(shell, "topbar-brand-mark")} aria-hidden="true">
              M
            </span>
            <span className="topbar-brand-text">
              <span className={cls(shell, "topbar-title")}>Mail Dashboard</span>
            </span>
          </button>
          <nav className={cls(shell, "nav-bar")} aria-label="Main">
            {NAV_ITEMS.map(({ id, label, Icon }) => (
              <button
                key={id}
                type="button"
                className={cls(shell, view === id ? 'nav-button active' : 'nav-button')}
                onClick={() => {
                  if (id !== view && id === 'pool') {
                    setPage(1);
                  }
                  setView(id);
                }}
                aria-current={view === id ? 'page' : undefined}
              >
                <Icon />
                <span>{label}</span>
              </button>
            ))}
          </nav>
        </div>
      </header>
      <main className={cls(shell, 'content')}>
        <PoolView />
        <ScraperView />
        <TemplatesView />
        <SettingsView />
        <ContactModal />
        <button
          type="button"
          className={cls(shell, 'go-top-bubble')}
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          aria-label="Go to top"
        >
          ^
        </button>
      </main>
    </div>
  );
}
