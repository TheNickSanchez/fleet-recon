import { useCallback, useMemo, useState } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { CommandPalette, type Command } from '../components/CommandPalette.tsx';
import { usePersistentState, useHotkey, useMediaQuery } from '../hooks/usePersistentState.ts';
import { ActivityView } from '../features/activity/ActivityView.tsx';
import { ActionsView } from '../features/actions/ActionsView.tsx';
import { CanvasPanel } from '../features/canvas/CanvasPanel.tsx';
import { ChatView } from '../features/chat/ChatView.tsx';
import { CredentialsView } from '../features/settings/CredentialsView.tsx';
import { HealthView } from '../features/settings/HealthView.tsx';
import { ToolsView } from '../features/settings/ToolsView.tsx';
import { useSession } from './SessionContext.tsx';
import { Sidebar } from './Sidebar.tsx';
import { TopBar } from './TopBar.tsx';
import './AppShell.css';

export function App() {
  const { workspaceId } = useSession();
  return (
    <Routes>
      <Route path="/" element={<Navigate to={`/workspaces/${workspaceId}`} replace />} />
      <Route path="/workspaces/:wsId/*" element={<WorkspaceShell />} />
      <Route path="*" element={<Navigate to={`/workspaces/${workspaceId}`} replace />} />
    </Routes>
  );
}

function WorkspaceShell() {
  const { workspaceId, isAdmin, setRole, setTheme, resolvedTheme } = useSession();
  const navigate = useNavigate();
  const isNarrow = useMediaQuery('(max-width: 900px)');

  const [collapsed, setCollapsed] = usePersistentState('fr.sidebarCollapsed', false);
  const [canvasOpen, setCanvasOpen] = usePersistentState('fr.canvasOpen', false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const toggleSidebar = useCallback(() => {
    if (isNarrow) setDrawerOpen((v) => !v);
    else setCollapsed((v) => !v);
  }, [isNarrow, setCollapsed]);

  useHotkey({ key: 'b', meta: true }, toggleSidebar);
  useHotkey({ key: 'k', meta: true }, () => setPaletteOpen((v) => !v));
  useHotkey({ key: '\\', meta: true }, () => setCanvasOpen((v) => !v));

  const base = `/workspaces/${workspaceId}`;

  const commands = useMemo<Command[]>(() => {
    const go = (to: string) => () => navigate(to);
    const list: Command[] = [
      { id: 'chat', group: 'Go to', icon: 'chat', label: 'Copilot Chat', run: go(base) },
      { id: 'canvas', group: 'Go to', icon: 'canvas', label: 'Live Canvas', run: go(`${base}/canvas`) },
      { id: 'activity', group: 'Go to', icon: 'activity', label: 'Activity', run: go(`${base}/activity`) },
    ];

    if (isAdmin) {
      list.push(
        { id: 'tools', group: 'Administration', icon: 'tools', label: 'Tools', run: go(`${base}/settings/tools`) },
        { id: 'actions', group: 'Administration', icon: 'shield', label: 'Action Requests', run: go(`${base}/settings/actions`) },
        { id: 'credentials', group: 'Administration', icon: 'key', label: 'Credentials', run: go(`${base}/settings/credentials`) },
        { id: 'health', group: 'Administration', icon: 'pulse', label: 'Health', run: go(`${base}/settings/health`) },
      );
    }

    list.push(
      {
        id: 'toggle-canvas',
        group: 'Commands',
        icon: 'panelRight',
        label: canvasOpen ? 'Hide canvas panel' : 'Show canvas panel',
        hint: '⌘\\',
        run: () => setCanvasOpen((v) => !v),
      },
      {
        id: 'toggle-sidebar',
        group: 'Commands',
        icon: 'sidebar',
        label: collapsed ? 'Expand navigation' : 'Collapse navigation',
        hint: '⌘B',
        run: toggleSidebar,
      },
      {
        id: 'theme',
        group: 'Commands',
        icon: resolvedTheme === 'dark' ? 'sun' : 'moon',
        label: `Switch to ${resolvedTheme === 'dark' ? 'light' : 'dark'} theme`,
        run: () => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark'),
      },
      {
        id: 'role',
        group: 'Commands',
        icon: isAdmin ? 'user' : 'shield',
        label: `Switch role to ${isAdmin ? 'Workspace User' : 'Administrator'}`,
        run: () => setRole(isAdmin ? 'workspace_user' : 'administrator'),
      },
    );

    return list;
  }, [base, canvasOpen, collapsed, isAdmin, navigate, resolvedTheme, setCanvasOpen, setRole, setTheme, toggleSidebar]);

  return (
    <div
      className="shell"
      data-sidebar={collapsed ? 'collapsed' : 'expanded'}
      data-drawer={drawerOpen ? 'open' : 'closed'}
    >
      <Sidebar
        collapsed={collapsed}
        onToggleCollapsed={() => setCollapsed((v) => !v)}
        onNavigate={() => setDrawerOpen(false)}
      />

      {drawerOpen && (
        <div
          className="shell__scrim"
          role="presentation"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      <div className="shell__main">
        <TopBar
          onOpenDrawer={() => setDrawerOpen(true)}
          onOpenPalette={() => setPaletteOpen(true)}
          canvasOpen={canvasOpen}
          onToggleCanvas={() => setCanvasOpen((v) => !v)}
          showCanvasToggle={!isNarrow}
        />

        <div className="shell__body">
          <Routes>
            <Route
              index
              element={
                <ChatView
                  canvasOpen={canvasOpen && !isNarrow}
                  onOpenCanvas={() => setCanvasOpen(true)}
                  onCloseCanvas={() => setCanvasOpen(false)}
                />
              }
            />
            <Route
              path="canvas"
              element={
                <div className="view">
                  <CanvasPanel />
                </div>
              }
            />
            <Route path="activity" element={<ActivityView />} />
            <Route
              path="settings/tools"
              element={isAdmin ? <ToolsView /> : <Navigate to={base} replace />}
            />
            <Route
              path="settings/actions"
              element={isAdmin ? <ActionsView /> : <Navigate to={base} replace />}
            />
            <Route
              path="settings/credentials"
              element={isAdmin ? <CredentialsView /> : <Navigate to={base} replace />}
            />
            <Route
              path="settings/health"
              element={isAdmin ? <HealthView /> : <Navigate to={base} replace />}
            />
            <Route path="*" element={<Navigate to={base} replace />} />
          </Routes>
        </div>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        commands={commands}
      />
    </div>
  );
}
