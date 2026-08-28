/**
 * Typed contracts mirroring backend/schemas.py.
 * Python `set[str]` serialises to a JSON array, so it is modelled as `string[]`.
 */

export type Role = 'workspace_user' | 'administrator';

export type RunStatus = 'queued' | 'running' | 'completed' | 'partial' | 'failed';

export type InputKind = 'typed' | 'pasted' | 'csv';

export type RunMode = 'micro_query' | 'batch_automation';

/** Backend action lifecycle: services.py creates `pending_confirmation`. */
export type ActionStatus =
  | 'pending_confirmation'
  | 'confirmed'
  | 'executed'
  | 'expired'
  | 'cancelled';

export interface RunRequest {
  input_kind: InputKind;
  text: string;
  intent?: string;
}

export interface RunSummary {
  id: string;
  workspace_id: string;
  input_kind: InputKind;
  input_count: number;
  rejected_count: number;
  mode: RunMode;
  status: RunStatus;
  correlation_id: string;
  created_at: string;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: { field: string; reason: string }[];
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody;
  correlation_id: string;
}

export interface ToolConfigView {
  tool_id: string;
  display_name: string;
  integration: string;
  version: string;
  enabled: boolean;
  assigned_agents: string[];
  parameters: Record<string, unknown>;
  configuration_version: number;
}

export interface ToolConfigPatch {
  enabled: boolean;
  assigned_agents: string[];
  parameters: Record<string, unknown>;
  expected_version: number;
}

export interface ActionRequestCreate {
  work_item_ids: string[];
  connector: string;
  operation: string;
  parameters?: Record<string, unknown>;
}

export interface ActionRequestView {
  id: string;
  workspace_id: string;
  work_item_ids: string[];
  connector: string;
  operation: string;
  status: ActionStatus;
  expires_at: string;
  idempotency_key: string;
}

export interface HealthResponse {
  status: string;
}

export interface ReadyResponse {
  status: string;
  persistence: string;
}

/** Connector/operation pairs allowlisted by services.ALLOWED_ACTIONS. */
export const ALLOWED_OPERATIONS = [
  { connector: 'servicenow', operation: 'create_ticket', label: 'ServiceNow — Create ticket' },
  { connector: 'jamf', operation: 'trigger_policy', label: 'Jamf Pro — Trigger policy' },
] as const;

export const RUN_TERMINAL_STATUSES: RunStatus[] = ['completed', 'partial', 'failed'];

export function isRunTerminal(status: RunStatus): boolean {
  return RUN_TERMINAL_STATUSES.includes(status);
}
