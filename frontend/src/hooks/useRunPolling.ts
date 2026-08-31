import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client.ts';
import { isRunTerminal, type RunSummary } from '../types/api.ts';

const FAST_POLL_MS = 2500;
const SLOW_POLL_MS = 8000;

/** The session host has no SSE/WebSocket (`backend.md` "Known Gaps"), so the
 * client polls `GET /runs/{id}` instead of subscribing to push updates.
 *
 * A single time budget was found to be too aggressive: a live `device_lookup`
 * run was observed completing in 45s (backend.md's own live testing raised
 * `max_turns` to 10 because a lookup routinely spends turns on tool-name
 * retries before fanning out to ServiceNow + Jamf/Intune), well past an
 * earlier flat 30s cutoff that stopped polling outright. So this uses two
 * thresholds: a SOFT one that surfaces a "this is taking a while" notice but
 * keeps checking in the background at a slower cadence, and a HARD one that
 * actually gives up and hands control back to a manual "Check again". */
export const SOFT_STALL_MS = 30_000;
export const HARD_STOP_MS = 120_000;

export interface RunPollingResult {
  run?: RunSummary;
  /** True while the client is actively polling for a transition (fast or slow cadence). */
  polling: boolean;
  /** True once the soft threshold elapsed without reaching a terminal state.
   * Polling continues in the background at a slower cadence while this is true. */
  stalled: boolean;
  /** True once the hard threshold elapsed and the client has stopped polling. */
  gaveUp: boolean;
  refresh: () => void;
}

export function useRunPolling(run?: RunSummary): RunPollingResult {
  const runId = run?.id;
  const createdAt = run?.created_at;
  const [phase, setPhase] = useState<'fast' | 'stalled' | 'stopped'>('fast');

  // Advance phases on timers rather than reading the clock during render.
  useEffect(() => {
    if (!createdAt) return;
    const startedAt = Date.parse(createdAt);
    const toStalled = startedAt + SOFT_STALL_MS - Date.now();
    const toStopped = startedAt + HARD_STOP_MS - Date.now();

    if (toStopped <= 0) {
      setPhase('stopped');
      return;
    }
    if (toStalled <= 0) {
      setPhase('stalled');
    } else {
      setPhase('fast');
    }

    const timers: number[] = [];
    if (toStalled > 0) timers.push(window.setTimeout(() => setPhase('stalled'), toStalled));
    timers.push(window.setTimeout(() => setPhase('stopped'), toStopped));
    return () => timers.forEach(window.clearTimeout);
  }, [createdAt]);

  const query = useQuery({
    queryKey: ['run', runId],
    queryFn: () => api.getRun(runId!),
    enabled: Boolean(runId),
    initialData: run,
    refetchInterval: ({ state }) => {
      const latest = state.data;
      if (!latest || isRunTerminal(latest.status)) return false;
      const elapsed = Date.now() - Date.parse(latest.created_at);
      if (elapsed > HARD_STOP_MS) return false;
      return elapsed > SOFT_STALL_MS ? SLOW_POLL_MS : FAST_POLL_MS;
    },
    refetchOnWindowFocus: false,
    retry: 1,
  });

  const current = query.data ?? run;
  const terminal = current ? isRunTerminal(current.status) : false;

  return {
    run: current,
    polling: Boolean(current) && !terminal && phase !== 'stopped',
    stalled: Boolean(current) && !terminal && phase === 'stalled',
    gaveUp: Boolean(current) && !terminal && phase === 'stopped',
    refresh: () => void query.refetch(),
  };
}
