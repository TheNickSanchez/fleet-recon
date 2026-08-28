import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { getDevIdentity, setDevIdentity } from '../api/client.ts';
import { usePersistentState } from '../hooks/usePersistentState.ts';
import { uuid } from '../lib/uuid.ts';
import type { ActionRequestView, InputKind, Role, RunSummary } from '../types/api.ts';

export type ThemePreference = 'system' | 'light' | 'dark';

export interface ThreadPrompt {
  kind: InputKind;
  text: string;
  fileName?: string;
  usernames: string[];
}

export interface ThreadEntry {
  id: string;
  createdAt: string;
  prompt: ThreadPrompt;
  run?: RunSummary;
  error?: string;
}

/**
 * A canvas row derived from a submitted run.
 *
 * The MVP backend does not yet persist CanvasWorkItem records, so rows are
 * reconstructed from the input the client submitted. `id` is a provisional
 * client-side identifier used for action-request targeting.
 */
export interface CanvasRow {
  id: string;
  username: string;
  runId: string;
  correlationId: string;
  mode: RunSummary['mode'];
  status: RunSummary['status'];
  submittedAt: string;
  checked: boolean;
  note: string;
}

interface SessionValue {
  workspaceId: string;
  actorId: string;
  role: Role;
  setRole: (role: Role) => void;
  isAdmin: boolean;

  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
  resolvedTheme: 'light' | 'dark';

  entries: ThreadEntry[];
  addEntry: (entry: ThreadEntry) => void;
  updateEntry: (id: string, patch: Partial<ThreadEntry>) => void;
  clearThread: () => void;

  rows: CanvasRow[];
  toggleRow: (id: string) => void;
  setRowChecked: (ids: string[], checked: boolean) => void;
  setRowNote: (id: string, note: string) => void;
  registerRows: (run: RunSummary, usernames: string[]) => void;

  actions: ActionRequestView[];
  upsertAction: (action: ActionRequestView) => void;
}

const SessionContext = createContext<SessionValue | null>(null);

const DEFAULT_WORKSPACE = '550e8400-e29b-41d4-a716-446655440000';

export function SessionProvider({ children }: { children: ReactNode }) {
  const workspaceId = (import.meta.env.VITE_WORKSPACE_ID as string | undefined) ?? DEFAULT_WORKSPACE;
  const actorId = (import.meta.env.VITE_DEV_ACTOR_ID as string | undefined) ?? 'local-dev-user';
  const envRole = ((import.meta.env.VITE_DEV_ROLE as Role | undefined) ?? 'workspace_user') as Role;

  const [role, setRole] = usePersistentState<Role>('fr.role', envRole);
  const [theme, setTheme] = usePersistentState<ThemePreference>('fr.theme', 'system');
  const [entries, setEntries] = usePersistentState<ThreadEntry[]>('fr.thread', []);
  const [rows, setRows] = usePersistentState<CanvasRow[]>('fr.rows', []);
  const [actions, setActions] = usePersistentState<ActionRequestView[]>('fr.actions', []);

  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia('(prefers-color-scheme: dark)').matches,
  );

  useEffect(() => {
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  const resolvedTheme: 'light' | 'dark' =
    theme === 'system' ? (systemDark ? 'dark' : 'light') : theme;

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolvedTheme);
  }, [resolvedTheme]);

  // Applied during render (not in an effect) so child effects that fire first
  // still issue requests with the current role.
  const current = getDevIdentity();
  if (current.role !== role || current.actorId !== actorId) {
    setDevIdentity({ actorId, role });
  }

  const addEntry = useCallback(
    (entry: ThreadEntry) => setEntries((prev) => [...prev, entry]),
    [setEntries],
  );

  const updateEntry = useCallback(
    (id: string, patch: Partial<ThreadEntry>) => {
      setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)));
      if (patch.run) {
        const run = patch.run;
        setRows((prev) => {
          const existing = prev.filter((r) => r.runId === run.id);
          if (existing.length === 0) return prev;
          return prev.map((r) => (r.runId === run.id ? { ...r, status: run.status } : r));
        });
      }
    },
    [setEntries, setRows],
  );

  const clearThread = useCallback(() => {
    setEntries([]);
    setRows([]);
  }, [setEntries, setRows]);

  const toggleRow = useCallback(
    (id: string) => setRows((prev) => prev.map((r) => (r.id === id ? { ...r, checked: !r.checked } : r))),
    [setRows],
  );

  const setRowChecked = useCallback(
    (ids: string[], checked: boolean) =>
      setRows((prev) => prev.map((r) => (ids.includes(r.id) ? { ...r, checked } : r))),
    [setRows],
  );

  const setRowNote = useCallback(
    (id: string, note: string) => setRows((prev) => prev.map((r) => (r.id === id ? { ...r, note } : r))),
    [setRows],
  );

  const upsertAction = useCallback(
    (action: ActionRequestView) =>
      setActions((prev) => {
        const index = prev.findIndex((a) => a.id === action.id);
        if (index === -1) return [action, ...prev];
        const next = [...prev];
        next[index] = action;
        return next;
      }),
    [setActions],
  );

  // Exposed so the chat feature can register derived rows when a run is created.
  const registerRows = useCallback(
    (run: RunSummary, usernames: string[]) => {
      const created: CanvasRow[] = usernames.map((username) => ({
        id: uuid(),
        username,
        runId: run.id,
        correlationId: run.correlation_id,
        mode: run.mode,
        status: run.status,
        submittedAt: run.created_at,
        checked: false,
        note: '',
      }));
      setRows((prev) => [...created, ...prev].slice(0, 2000));
    },
    [setRows],
  );

  const value = useMemo<SessionValue>(
    () => ({
      workspaceId,
      actorId,
      role,
      setRole,
      isAdmin: role === 'administrator',
      theme,
      setTheme,
      resolvedTheme,
      entries,
      addEntry,
      updateEntry,
      clearThread,
      rows,
      toggleRow,
      setRowChecked,
      setRowNote,
      actions,
      upsertAction,
      registerRows,
    }),
    [
      workspaceId,
      actorId,
      role,
      setRole,
      theme,
      setTheme,
      resolvedTheme,
      entries,
      addEntry,
      updateEntry,
      clearThread,
      rows,
      toggleRow,
      setRowChecked,
      setRowNote,
      actions,
      upsertAction,
      registerRows,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within SessionProvider');
  return ctx;
}
