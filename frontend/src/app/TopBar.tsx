import { useLocation } from 'react-router-dom';
import { Icon } from '../components/Icon.tsx';
import { Menu, MenuItem, MenuLabel, MenuSeparator } from '../components/Menu.tsx';
import { useSession, type ThemePreference } from './SessionContext.tsx';
import { apiOrigin } from '../api/client.ts';

interface TopBarProps {
  onOpenDrawer: () => void;
  onOpenPalette: () => void;
  canvasOpen: boolean;
  onToggleCanvas: () => void;
  showCanvasToggle: boolean;
}

const TITLES: { match: (path: string) => boolean; title: string; subtitle?: string }[] = [
  {
    match: (p) => p.endsWith('/canvas'),
    title: 'Live Canvas',
    subtitle: 'Shared reconciliation state',
  },
  { match: (p) => p.endsWith('/activity'), title: 'Activity', subtitle: 'Run and audit timeline' },
  {
    match: (p) => p.endsWith('/settings/tools'),
    title: 'Tools',
    subtitle: 'Agent tool configuration',
  },
  {
    match: (p) => p.endsWith('/settings/actions'),
    title: 'Action Requests',
    subtitle: 'Confirm and execute scoped remediation',
  },
  { match: (p) => p.endsWith('/settings/credentials'), title: 'Credentials', subtitle: 'Integration secrets' },
  { match: (p) => p.endsWith('/settings/health'), title: 'Health', subtitle: 'Live API and connector probes' },
];

export function TopBar({
  onOpenDrawer,
  onOpenPalette,
  canvasOpen,
  onToggleCanvas,
  showCanvasToggle,
}: TopBarProps) {
  const { pathname } = useLocation();
  const { role, setRole, actorId, theme, setTheme } = useSession();

  const matched = TITLES.find((entry) => entry.match(pathname));
  const title = matched?.title ?? 'Copilot Chat';
  const subtitle = matched?.subtitle ?? 'Ask about users, devices, and compliance';

  const themeOptions: { value: ThemePreference; label: string; icon: 'sun' | 'moon' | 'monitor' }[] =
    [
      { value: 'system', label: 'System', icon: 'monitor' },
      { value: 'light', label: 'Light', icon: 'sun' },
      { value: 'dark', label: 'Dark', icon: 'moon' },
    ];

  return (
    <header className="topbar">
      <button
        type="button"
        className="btn btn--ghost btn--icon topbar__menu-btn"
        onClick={onOpenDrawer}
        aria-label="Open navigation"
      >
        <Icon name="sidebar" size={17} />
      </button>

      <div className="row gap-3" style={{ minWidth: 0 }}>
        <h1 className="topbar__title">{title}</h1>
        <span className="topbar__subtitle">{subtitle}</span>
      </div>

      <div className="topbar__spacer" />

      <button type="button" className="topbar__search" onClick={onOpenPalette}>
        <Icon name="search" size={14} />
        <span>Search or jump to…</span>
        <span className="topbar__search-hint">
          <kbd>⌘</kbd>
          <kbd>K</kbd>
        </span>
      </button>

      {showCanvasToggle && (
        <button
          type="button"
          className={`btn ${canvasOpen ? 'btn--secondary' : 'btn--ghost'} btn--icon`}
          onClick={onToggleCanvas}
          aria-pressed={canvasOpen}
          aria-label={canvasOpen ? 'Hide canvas panel' : 'Show canvas panel'}
          title={`${canvasOpen ? 'Hide' : 'Show'} canvas (⌘\\)`}
        >
          <Icon name="panelRight" size={17} />
        </button>
      )}

      <Menu
        align="end"
        label="Appearance"
        trigger={({ toggle }) => (
          <button
            type="button"
            className="btn btn--ghost btn--icon"
            onClick={toggle}
            aria-label="Appearance"
          >
            <Icon name={theme === 'dark' ? 'moon' : theme === 'light' ? 'sun' : 'monitor'} size={17} />
          </button>
        )}
      >
        {({ close }) => (
          <>
            <MenuLabel>Appearance</MenuLabel>
            {themeOptions.map((option) => (
              <MenuItem
                key={option.value}
                icon={<Icon name={option.icon} size={15} />}
                hint={theme === option.value ? '✓' : undefined}
                onSelect={() => {
                  setTheme(option.value);
                  close();
                }}
              >
                {option.label}
              </MenuItem>
            ))}
          </>
        )}
      </Menu>

      <Menu
        align="end"
        label="Session"
        trigger={({ toggle }) => (
          <button type="button" className="topbar__identity" onClick={toggle}>
            <span className="topbar__avatar" aria-hidden="true">
              {role === 'administrator' ? 'A' : 'U'}
            </span>
            <span className="topbar__role">
              {role === 'administrator' ? 'Administrator' : 'Workspace User'}
            </span>
            <Icon name="chevronDown" size={13} />
          </button>
        )}
      >
        {({ close }) => (
          <>
            <MenuLabel>Signed in as</MenuLabel>
            <div className="menu__item" style={{ cursor: 'default' }}>
              <span className="menu__item-icon">
                <Icon name="user" size={15} />
              </span>
              <span className="menu__item-label mono text-xs">{actorId}</span>
            </div>
            <MenuSeparator />
            <MenuLabel>Simulated role</MenuLabel>
            <MenuItem
              icon={<Icon name="user" size={15} />}
              hint={role === 'workspace_user' ? '✓' : undefined}
              onSelect={() => {
                setRole('workspace_user');
                close();
              }}
            >
              Workspace User
            </MenuItem>
            <MenuItem
              icon={<Icon name="shield" size={15} />}
              hint={role === 'administrator' ? '✓' : undefined}
              onSelect={() => {
                setRole('administrator');
                close();
              }}
            >
              Administrator
            </MenuItem>
            <MenuSeparator />
            <div className="menu__meta">
              <span className="dev-pill">
                <Icon name="alert" size={11} /> DEV IDENTITY
              </span>
              <p>
                Role is sent as an <code>X-Role</code> header for local development only. The server
                still enforces authorization.
              </p>
              <p className="mono">{apiOrigin}</p>
            </div>
          </>
        )}
      </Menu>
    </header>
  );
}
