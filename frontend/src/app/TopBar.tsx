import { Icon } from '../components/Icon.tsx';
import { useAppState } from './AppState.tsx';

const THEME_SEQUENCE = ['system', 'light', 'dark'] as const;
const THEME_ICON = { system: 'monitor', light: 'sun', dark: 'moon' } as const;
const THEME_LABEL = { system: 'System theme', light: 'Light theme', dark: 'Dark theme' } as const;

function ThemeToggle() {
  const { theme, setTheme } = useAppState();
  const next = THEME_SEQUENCE[(THEME_SEQUENCE.indexOf(theme) + 1) % THEME_SEQUENCE.length];
  return (
    <button
      type="button"
      className="btn btn--ghost btn--icon"
      onClick={() => setTheme(next)}
      aria-label={`${THEME_LABEL[theme]} — switch to ${THEME_LABEL[next].toLowerCase()}`}
      title={`${THEME_LABEL[theme]} (click for ${THEME_LABEL[next].toLowerCase()})`}
    >
      <Icon name={THEME_ICON[theme]} size={16} />
    </button>
  );
}

export function TopBar() {
  return (
    <header className="topbar">
      <span className="topbar__brand" aria-label="Fleet Recon">
        <span className="topbar__mark" aria-hidden="true">
          <Icon name="sparkle" size={14} />
        </span>
        <span className="topbar__wordmark">
          <span className="topbar__name">Fleet Recon</span>
          <span className="topbar__tagline">Session chat</span>
        </span>
      </span>

      <div className="topbar__spacer" />

      <ThemeToggle />
    </header>
  );
}
