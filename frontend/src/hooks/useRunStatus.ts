import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client.ts';
import { isRunTerminal, type RunSummary } from '../types/api.ts';

const POLL_INTERVAL_MS = 2500;
/** The MVP backend has no orchestration worker, so bound the poll window. */
export const MAX_POLL_MS = 30_000;

interface Options {
  workspaceId: string;
  run?: RunSummary;
  enabled?: boolean;
}

export interface RunStatusResult {
  run?: RunSummary;
  /** True while the client is actively polling for a transition. */
  polling: boolean;
  /** True once the poll window elapsed without reaching a terminal state. */
  stalled: boolean;
  refresh: () => void;
  error: unknown;
}

export function useRunStatus({ workspaceId, run, enabled = true }: Options): RunStatusResult {
  const runId = run?.id;
  const createdAt = run?.created_at;
  const [windowClosed, setWindowClosed] = useState(false);

  // Close the poll window on a timer rather than reading the clock during render.
  useEffect(() => {
    if (!createdAt) return;
    const remaining = Date.parse(createdAt) + MAX_POLL_MS - Date.now();
    if (remaining <= 0) {
      setWindowClosed(true);
      return;
    }
    const timer = window.setTimeout(() => setWindowClosed(true), remaining);
    return () => window.clearTimeout(timer);
  }, [createdAt, runId]);

  const query = useQuery({
    queryKey: ['run', workspaceId, runId],
    queryFn: () => api.getRun(workspaceId, runId!),
    enabled: Boolean(runId) && enabled,
    initialData: run,
    refetchInterval: ({ state }) => {
      const latest = state.data;
      if (!latest || isRunTerminal(latest.status)) return false;
      if (Date.now() - Date.parse(latest.created_at) > MAX_POLL_MS) return false;
      return POLL_INTERVAL_MS;
    },
    refetchOnWindowFocus: false,
    retry: 1,
  });

  const current = query.data ?? run;
  const terminal = current ? isRunTerminal(current.status) : false;

  return {
    run: current,
    polling: Boolean(current) && !terminal && !windowClosed && enabled,
    stalled: Boolean(current) && !terminal && windowClosed,
    refresh: () => void query.refetch(),
    error: query.error,
  };
}
