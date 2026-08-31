/**
 * Typed contracts mirroring the live session-host API
 * (`session-host/fleet_session_host/{api.py,runs.py,chat.py}`), documented in
 * `project-context/2.build/backend.md`.
 *
 * Product pivot 2026-08-31: there is no `mode`/`skill_id`/`intent_id` router
 * anymore — every run is one turn of a general chat thread. See backend.md
 * Audit for the full reasoning. There is no workspace, role, or
 * action-request model in this backend either — these types intentionally
 * do not have any of that shape.
 */

export type RunStatus = 'queued' | 'running' | 'completed' | 'failed';

export type InputKind = 'text' | 'csv';

export interface ChatTextResult {
  type: 'chat.text';
  text: string;
}

export type RunResult = ChatTextResult;

export interface RunErrorBody {
  code: string;
  message: string;
}

export interface RunSummary {
  id: string;
  correlation_id: string;
  thread_id: string;
  input_kind: InputKind;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  result: RunResult | null;
  error: RunErrorBody | null;
  diagnostic: string | null;
  /** Live "what is it doing right now" feed appended to while status is
   * `running` (e.g. "Calling jamf -> get_computer_by_username...") -- see
   * `chat.py`'s `on_progress` and `runs.py`'s `RunStore.append_activity`. */
  activity: string[];
}

const TERMINAL_STATUSES: readonly RunStatus[] = ['completed', 'failed'];

export function isRunTerminal(status: RunStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}
