import type { RunSummary } from '../types/api.ts';

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1';

/**
 * The session host is a private, unauthenticated bind (`backend.md` "Known
 * Gaps": no per-actor auth, no CORS). There is no dev-identity header to
 * simulate here — that concept belonged to the superseded enterprise
 * backend and has no equivalent on this API.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly correlationId?: string;

  constructor(message: string, status: number, code?: string, correlationId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
  }

  /** True for the zero-identity submit rejection (`VALIDATION_ERROR`, HTTP 400). */
  get isValidationError() {
    return this.code === 'VALIDATION_ERROR';
  }
}

async function readError(response: Response): Promise<ApiError> {
  let message = response.statusText || `Request failed (${response.status})`;
  let code: string | undefined;
  let correlationId: string | undefined;

  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string };
      correlation_id?: string;
    };
    if (body.error?.message) message = body.error.message;
    code = body.error?.code;
    correlationId = body.correlation_id;
  } catch {
    /* non-JSON error body — keep the status text */
  }

  return new ApiError(message, response.status, code, correlationId);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      `Cannot reach the Fleet Recon session host at ${API_BASE_URL}. Is it running ` +
        '(`uv run python -m fleet_session_host` from `session-host/`)?',
      0,
    );
  }
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

export interface CreateRunInput {
  text?: string;
  file?: File;
  /** Groups this turn into an existing conversation (`runs.py`'s
   * `RunStore.get_thread_history`). Omit to start a new thread. */
  threadId?: string;
}

export const api = {
  createRun: ({ text, file, threadId }: CreateRunInput) => {
    if (file) {
      const form = new FormData();
      form.append('file', file);
      if (text) form.append('text', text);
      if (threadId) form.append('thread_id', threadId);
      return request<RunSummary>('/runs', { method: 'POST', body: form });
    }
    return request<RunSummary>('/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text ?? '', thread_id: threadId }),
    });
  },

  getRun: (runId: string) => request<RunSummary>(`/runs/${encodeURIComponent(runId)}`),
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Unexpected error.';
}
