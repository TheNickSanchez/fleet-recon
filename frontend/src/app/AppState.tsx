import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { usePersistentState, useSessionState } from '../hooks/usePersistentState.ts';
import type { RunSummary } from '../types/api.ts';
import { uuid } from '../lib/uuid.ts';

export type ThemePreference = 'system' | 'light' | 'dark';

export interface ChatPrompt {
  text: string;
  fileName?: string;
}

export interface ChatEntry {
  id: string;
  createdAt: string;
  prompt: ChatPrompt;
  run?: RunSummary;
}

interface AppStateValue {
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
  resolvedTheme: 'light' | 'dark';

  /** Groups every entry in this browser session into one backend
   * conversation (`RunStore.get_thread_history`) so follow-up turns keep
   * context. Product pivot 2026-08-31 — see backend.md Audit. */
  threadId: string;
  entries: ChatEntry[];
  addEntry: (entry: ChatEntry) => void;
  updateEntry: (id: string, patch: Partial<ChatEntry>) => void;
  clearThread: () => void;
}

const AppStateContext = createContext<AppStateValue | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = usePersistentState<ThemePreference>('fr.theme', 'system');
  const [entries, setEntries] = useSessionState<ChatEntry[]>('fr.thread', []);
  const [threadId, setThreadId] = useSessionState<string>('fr.threadId', uuid());

  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia('(prefers-color-scheme: dark)').matches,
  );

  useEffect(() => {
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  const resolvedTheme: 'light' | 'dark' = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme;

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolvedTheme);
  }, [resolvedTheme]);

  const addEntry = useCallback((entry: ChatEntry) => setEntries((prev) => [...prev, entry]), [setEntries]);

  const updateEntry = useCallback(
    (id: string, patch: Partial<ChatEntry>) =>
      setEntries((prev) => prev.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry))),
    [setEntries],
  );

  const clearThread = useCallback(() => {
    setEntries([]);
    setThreadId(uuid());
  }, [setEntries, setThreadId]);

  const value = useMemo<AppStateValue>(
    () => ({
      theme,
      setTheme,
      resolvedTheme,
      threadId,
      entries,
      addEntry,
      updateEntry,
      clearThread,
    }),
    [theme, setTheme, resolvedTheme, threadId, entries, addEntry, updateEntry, clearThread],
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppStateValue {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error('useAppState must be used within AppStateProvider');
  return ctx;
}
