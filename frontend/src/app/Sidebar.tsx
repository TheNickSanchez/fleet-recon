import { NavLink } from 'react-router-dom';
import { Icon, type IconName } from '../components/Icon.tsx';
import { useSession } from './SessionContext.tsx';

export interface NavEntry {
  to: string;
  label: string;
  icon: IconName;
  end?: boolean;
  badge?: number;
}

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onNavigate: () => void;
}

export function Sidebar({ collapsed, onToggleCollapsed, onNavigate }: SidebarProps) {
  const { workspaceId, isAdmin, rows, actions, entries } = useSession();
  const base = `/workspaces/${workspaceId}`;

  const workspaceNav: NavEntry[] = [
    { to: base, label: 'Copilot Chat', icon: 'chat', end: true, badge: entries.length || undefined },
    { to: `${base}/canvas`, label: 'Live Canvas', icon: 'canvas', badge: rows.length || undefined },
    { to: `${base}/activity`, label: 'Activity', icon: 'activity' },
  ];

  const adminNav: NavEntry[] = [
    { to: `${base}/settings/tools`, label: 'Tools', icon: 'tools' },
    {
      to: `${base}/settings/actions`,
      label: 'Action Requests',
      icon: 'shield',
      badge: actions.length || undefined,
    },
    { to: `${base}/settings/credentials`, label: 'Credentials', icon: 'key' },
    { to: `${base}/settings/health`, label: 'Health', icon: 'pulse' },
  ];

  return (
    <aside className="sidebar" aria-label="Primary">
      <div className="sidebar__brand">
        <span className="sidebar__logo" aria-hidden="true">
          <Icon name="sparkle" size={16} />
        </span>
        <span className="sidebar__wordmark">
          <span className="sidebar__name">Fleet Recon</span>
          <span className="sidebar__env">Reconciliation workspace</span>
        </span>
      </div>

      <nav className="sidebar__nav">
        <p className="sidebar__section-label">Workspace</p>
        {workspaceNav.map((item) => (
          <NavItem key={item.to} item={item} onNavigate={onNavigate} />
        ))}

        {isAdmin && (
          <>
            <p className="sidebar__section-label">Administration</p>
            {adminNav.map((item) => (
              <NavItem key={item.to} item={item} onNavigate={onNavigate} />
            ))}
          </>
        )}
      </nav>

      <div className="sidebar__footer">
        <button
          type="button"
          className="btn btn--ghost sidebar__collapse"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          title={`${collapsed ? 'Expand' : 'Collapse'} navigation (⌘B)`}
        >
          <Icon name={collapsed ? 'chevronRight' : 'chevronLeft'} size={16} />
          {!collapsed && <span>Collapse</span>}
        </button>
        <p className="sidebar__footer-text">MVP build · in-memory backend</p>
      </div>
    </aside>
  );
}

function NavItem({ item, onNavigate }: { item: NavEntry; onNavigate: () => void }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      data-tooltip={item.label}
      className={({ isActive }) => `navitem${isActive ? ' is-active' : ''}`}
    >
      <span className="navitem__icon">
        <Icon name={item.icon} size={17} />
      </span>
      <span className="navitem__label">{item.label}</span>
      {item.badge !== undefined && <span className="navitem__badge">{item.badge}</span>}
    </NavLink>
  );
}
