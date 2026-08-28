import { useCallback, useEffect, useState } from 'react';
import { Icon } from '../../components/Icon.tsx';
import { Modal } from '../../components/Modal.tsx';
import { useToast } from '../../components/Toast.tsx';
import { ApiError, api, errorMessage } from '../../api/client.ts';
import { useSession } from '../../app/SessionContext.tsx';
import type { ToolConfigView } from '../../types/api.ts';
import './Settings.css';

const KNOWN_AGENTS = ['orchestrator', 'analysis', 'dispatch'];

export function ToolsView() {
  const { workspaceId, role } = useSession();
  const toast = useToast();
  const [tools, setTools] = useState<ToolConfigView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; forbidden: boolean } | null>(null);
  const [editing, setEditing] = useState<ToolConfigView | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTools(await api.listTools(workspaceId));
    } catch (err) {
      setError({
        message: errorMessage(err),
        forbidden: err instanceof ApiError && err.isForbidden,
      });
      setTools([]);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  // `role` is a dependency so the view recovers on its own after a role switch.
  useEffect(() => {
    void load();
  }, [load, role]);

  const save = async (draft: ToolConfigView) => {
    try {
      const updated = await api.updateTool(workspaceId, draft.tool_id, {
        enabled: draft.enabled,
        assigned_agents: draft.assigned_agents,
        parameters: draft.parameters,
        expected_version: draft.configuration_version,
      });
      setTools((prev) => prev.map((t) => (t.tool_id === updated.tool_id ? updated : t)));
      setEditing(null);
      toast.success(
        `${updated.display_name} updated`,
        `Configuration version ${updated.configuration_version}.`,
      );
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) {
        toast.error(
          'Version conflict',
          'Another administrator changed this tool. Reloading the current server state.',
        );
        void load();
        setEditing(null);
        return;
      }
      toast.error('Update failed', errorMessage(err));
    }
  };

  return (
    <div className="view">
      <div className="view__scroll">
        <div className="view__inner">
          <div className="view__heading">
            <div>
              <h2>Tools</h2>
              <p>
                Enable or disable agent tools, adjust which agents may call them, and edit typed
                parameters. Saves use optimistic concurrency — a stale configuration version is
                rejected by the server.
              </p>
            </div>
            <button type="button" className="btn btn--secondary" onClick={() => void load()}>
              <Icon name={loading ? 'spinner' : 'refresh'} size={15} /> Refresh
            </button>
          </div>

          {error && <AuthorizationNotice message={error.message} forbidden={error.forbidden} />}

          {loading && !error && <TableSkeleton />}

          {!loading && !error && (
            <div className="card">
              <table className="table">
                <thead>
                  <tr>
                    <th>Tool</th>
                    <th>Integration</th>
                    <th>Agents</th>
                    <th>Parameters</th>
                    <th>State</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {tools.map((tool) => (
                    <tr key={tool.tool_id}>
                      <td>
                        <span className="cell-title">{tool.display_name}</span>
                        <span className="cell-sub mono">{tool.tool_id}</span>
                      </td>
                      <td>
                        <span className="badge badge--outline">{tool.integration}</span>
                        <span className="cell-sub">v{tool.version}</span>
                      </td>
                      <td>
                        <div className="chips">
                          {tool.assigned_agents.length === 0 ? (
                            <span className="text-xs text-tertiary">None</span>
                          ) : (
                            tool.assigned_agents.map((agent) => (
                              <span key={agent} className="badge">
                                {agent}
                              </span>
                            ))
                          )}
                        </div>
                      </td>
                      <td className="mono text-xs text-tertiary">
                        {summariseParameters(tool.parameters)}
                      </td>
                      <td>
                        <span className={`badge badge--${tool.enabled ? 'success' : 'danger'}`}>
                          <span className="dot" />
                          {tool.enabled ? 'Enabled' : 'Disabled'}
                        </span>
                        <span className="cell-sub">config v{tool.configuration_version}</span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={() => setEditing(tool)}
                        >
                          Configure
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <ToolEditor tool={editing} onClose={() => setEditing(null)} onSave={save} />
    </div>
  );
}

function ToolEditor({
  tool,
  onClose,
  onSave,
}: {
  tool: ToolConfigView | null;
  onClose: () => void;
  onSave: (draft: ToolConfigView) => Promise<void>;
}) {
  const [draft, setDraft] = useState<ToolConfigView | null>(tool);
  const [paramText, setParamText] = useState('{}');
  const [paramError, setParamError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(tool);
    setParamText(tool ? JSON.stringify(tool.parameters, null, 2) : '{}');
    setParamError(null);
    setSaving(false);
  }, [tool]);

  if (!tool || !draft) return null;

  const dirty =
    draft.enabled !== tool.enabled ||
    draft.assigned_agents.join() !== tool.assigned_agents.join() ||
    paramText.trim() !== JSON.stringify(tool.parameters, null, 2);

  const commit = async () => {
    let parameters: Record<string, unknown>;
    try {
      parameters = JSON.parse(paramText || '{}') as Record<string, unknown>;
    } catch {
      setParamError('Parameters must be valid JSON.');
      return;
    }
    setSaving(true);
    await onSave({ ...draft, parameters });
    setSaving(false);
  };

  const toggleAgent = (agent: string) =>
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            assigned_agents: prev.assigned_agents.includes(agent)
              ? prev.assigned_agents.filter((a) => a !== agent)
              : [...prev.assigned_agents, agent],
          }
        : prev,
    );

  return (
    <Modal
      open
      title={tool.display_name}
      description={`${tool.integration} · v${tool.version} · configuration version ${tool.configuration_version}`}
      onClose={onClose}
      width={560}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void commit()}
            disabled={!dirty || saving}
          >
            {saving && <Icon name="spinner" size={14} />} Save changes
          </button>
        </>
      }
    >
      <label className="switch tool-toggle">
        <input
          type="checkbox"
          checked={draft.enabled}
          onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })}
        />
        <span className="switch__track" />
        <span>
          <span className="cell-title">Enabled</span>
          <span className="cell-sub">Disabled tools are never offered to agents.</span>
        </span>
      </label>

      <div className="field">
        <span className="field__label">Assigned agents</span>
        <div className="chips">
          {KNOWN_AGENTS.map((agent) => {
            const active = draft.assigned_agents.includes(agent);
            return (
              <button
                key={agent}
                type="button"
                className={`chip${active ? ' is-active' : ''}`}
                onClick={() => toggleAgent(agent)}
                aria-pressed={active}
              >
                {active && <Icon name="check" size={12} />}
                {agent}
              </button>
            );
          })}
        </div>
        <span className="field__hint">
          Scope changes take effect on the next run that resolves this tool.
        </span>
      </div>

      <div className="field">
        <span className="field__label">Parameters (JSON)</span>
        <textarea
          className="textarea mono"
          rows={7}
          value={paramText}
          spellCheck={false}
          onChange={(event) => {
            setParamText(event.target.value);
            setParamError(null);
          }}
        />
        {paramError && <span className="field__hint" style={{ color: 'var(--danger)' }}>{paramError}</span>}
      </div>

      {dirty && (
        <div className="notice notice--warning">
          <Icon name="alert" size={15} className="notice__icon" />
          <p className="notice__body">
            Saving increments the configuration version to {tool.configuration_version + 1}. A
            concurrent edit will be rejected with a 409 conflict.
          </p>
        </div>
      )}
    </Modal>
  );
}

export function AuthorizationNotice({
  message,
  forbidden,
}: {
  message: string;
  forbidden: boolean;
}) {
  return (
    <div className={`notice notice--${forbidden ? 'warning' : 'danger'}`}>
      <Icon name={forbidden ? 'lock' : 'alert'} size={16} className="notice__icon" />
      <div>
        <p className="notice__title">{forbidden ? 'Not authorized' : 'Request failed'}</p>
        <p className="notice__body">
          {message}
          {forbidden &&
            ' Switch the simulated role to Administrator from the account menu to load this view.'}
        </p>
      </div>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="card" style={{ padding: 'var(--s-4)' }}>
      <div className="stack gap-3">
        {[0, 1, 2].map((row) => (
          <div key={row} className="row gap-4">
            <span className="skeleton" style={{ height: 12, flex: 2 }} />
            <span className="skeleton" style={{ height: 12, flex: 1 }} />
            <span className="skeleton" style={{ height: 12, flex: 1 }} />
          </div>
        ))}
      </div>
    </div>
  );
}

function summariseParameters(parameters: Record<string, unknown>): string {
  const keys = Object.keys(parameters);
  if (keys.length === 0) return '—';
  return keys.slice(0, 2).join(', ') + (keys.length > 2 ? ` +${keys.length - 2}` : '');
}
