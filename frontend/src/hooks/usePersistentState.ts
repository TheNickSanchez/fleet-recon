import { useEffect, useRef, useState } from 'react';

function useStorageState<T>(storage: Storage, key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = storage.getItem(key);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    try {
      storage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage unavailable — keep in-memory only */
    }
  }, [key, value]);

  return [value, setValue] as const;
}

/** UI preference backed by localStorage (persists across browser restarts),
 * resilient to unavailable storage (private mode). Use for durable
 * preferences like theme — never for chat/run history (see `useSessionState`). */
export function usePersistentState<T>(key: string, initial: T) {
  return useStorageState(window.localStorage, key, initial);
}

/** Thread/canvas history backed by sessionStorage, so it survives a reload
 * within the tab but is gone once the tab closes — matching the disclosed
 * "browser-session-only history" contract (no server audit log exists). */
export function useSessionState<T>(key: string, initial: T) {
  return useStorageState(window.sessionStorage, key, initial);
}

type Combo = { key: string; meta?: boolean; shift?: boolean };

/** Registers a global keyboard shortcut. Ignores keystrokes inside text fields unless `meta`. */
export function useHotkey(combo: Combo, handler: () => void) {
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== combo.key.toLowerCase()) return;
      const wantsMeta = combo.meta ?? false;
      const hasMeta = event.metaKey || event.ctrlKey;
      if (wantsMeta !== hasMeta) return;
      if ((combo.shift ?? false) !== event.shiftKey) return;

      const target = event.target as HTMLElement | null;
      const typing =
        target?.tagName === 'INPUT' ||
        target?.tagName === 'TEXTAREA' ||
        target?.isContentEditable === true;
      if (typing && !wantsMeta) return;

      event.preventDefault();
      handlerRef.current();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [combo.key, combo.meta, combo.shift]);
}

/** True when the viewport is below the given breakpoint. */
export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    setMatches(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}
