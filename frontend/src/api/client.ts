import type {
  ActionRequestCreate,
  ActionRequestView,
  HealthResponse,
  ReadyResponse,
  Role,
  RunRequest,
  RunSummary,
  ToolConfigPatch,
  ToolConfigView,
} from '../types/api.ts';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '')
  ?? '/api/v1';

/**
 * Development identity. The backend reads `X-Actor-Id` / `X-Role`.
 * This is a local-development stand-in for verified OIDC claims and must be
 * replaced by a real token exchange before any non-local deployment.
 */
export interface DevIdentity {
  actorId: string;
  role: Role;
}

/** localStorage key shared with SessionProvider's persisted role. */
const ROLE_STORAGE_KEY = 'fr.role';

function persistedRole(): Role | null {
  try {
    const raw = window.localStorage.getItem(ROLE_STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as unknown;
    return value === 'administrator' || value === 'workspace_user' ? value : null;
  } catch {
    return null;
  }
}

// Initialised synchronously at module load so the first request issued by any
// component already carries the persisted role, not just the env default.
let identity: DevIdentity = {
  actorId: (import.meta.env.VITE_DEV_ACTOR_ID as string | undefined) ?? 'local-dev-user',
  role:
    persistedRole() ??
    (((import.meta.env.VITE_DEV_ROLE as Role | undefined) ?? 'workspace_user') as Role),
};

export function setDevIdentity(next: DevIdentity) {
  identity = next;
}

export function getDevIdentity(): DevIdentity {
  return identity;
}

export class ApiError extends Error {
  readonly status: number;
  readonly correlationId?: string;

  constructor(message: string, status: number, correlationId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.correlationId = correlationId;
  }

  /** True when the failure is an authorization denial rather than a transport fault. */
  get isForbidden() {
    return this.status === 403 || this.status === 401;
  }

  get isConflict() {
    return this.status === 409;
  }
}

function authHeaders(): Record<string, string> {
  return { 'X-Actor-Id': identity.actorId, 'X-Role': identity.role };
}

async function readError(response: Response): Promise<ApiError> {
  let message = response.statusText || `Request failed (${response.status})`;
  let correlationId: string | undefined;

  try {
    const body = (await response.json()) as Record<string, unknown>;
    // FastAPI HTTPException -> { detail }, project envelope -> { error: { message }, correlation_id }
    if (typeof body.detail === 'string') {
      message = body.detail;
    } else if (Array.isArray(body.detail)) {
      message = body.detail
        .map((item) => {
          const entry = item as { loc?: unknown[]; msg?: string };
          return `${entry.loc?.slice(1).join('.') ?? 'request'}: ${entry.msg ?? 'invalid'}`;
        })
        .join('; ');
    } else if (body.error && typeof body.error === 'object') {
      message = (body.error as { message?: string }).message ?? message;
    }
    if (typeof body.correlation_id === 'string') correlationId = body.correlation_id;
  } catch {
    /* non-JSON error body — keep the status text */
  }

  if (response.status === 403) {
    message = message || 'Your role does not permit this operation.';
  }
  return new ApiError(message, response.status, correlationId);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      `Cannot reach the Fleet Recon API at ${API_BASE_URL}. Is the backend running?`,
      0,
    );
  }
  if (!response.ok) throw await readError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function jsonRequest<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

const ws = (workspaceId: string) => `/workspaces/${encodeURIComponent(workspaceId)}`;

export const api = {
  health: () => request<HealthResponse>('/health'),

  ready: () => request<ReadyResponse>('/ready'),

  createRun: (workspaceId: string, body: RunRequest) =>
    jsonRequest<RunSummary>(`${ws(workspaceId)}/runs`, 'POST', body),

  uploadRun: (workspaceId: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<RunSummary>(`${ws(workspaceId)}/runs/upload`, {
      method: 'POST',
      headers: authHeaders(),
      body: form,
    });
  },

  getRun: (workspaceId: string, runId: string) =>
    request<RunSummary>(`${ws(workspaceId)}/runs/${runId}`, { headers: authHeaders() }),

  listTools: (workspaceId: string) =>
    request<ToolConfigView[]>(`${ws(workspaceId)}/admin/tools`, { headers: authHeaders() }),

  updateTool: (workspaceId: string, toolId: string, patch: ToolConfigPatch) =>
    jsonRequest<ToolConfigView>(`${ws(workspaceId)}/admin/tools/${toolId}`, 'PATCH', patch),

  createAction: (workspaceId: string, body: ActionRequestCreate) =>
    jsonRequest<ActionRequestView>(`${ws(workspaceId)}/action-requests`, 'POST', body),

  confirmAction: (workspaceId: string, actionId: string) =>
    jsonRequest<ActionRequestView>(`${ws(workspaceId)}/action-requests/${actionId}/confirm`, 'POST'),

  executeAction: (workspaceId: string, actionId: string) =>
    jsonRequest<ActionRequestView>(`${ws(workspaceId)}/action-requests/${actionId}/execute`, 'POST'),
};


/** Absolute form of the API base, useful for diagnostics display. */
export const apiOrigin = API_BASE_URL.startsWith('http')
  ? API_BASE_URL
  : `${window.location.origin}${API_BASE_URL}`;

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Unexpected error.';
}
