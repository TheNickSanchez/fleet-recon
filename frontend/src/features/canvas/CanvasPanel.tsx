import { useMemo, useState } from 'react';
import { Icon } from '../../components/Icon.tsx';
import { useToast } from '../../components/Toast.tsx';
import { api, errorMessage } from '../../api/client.ts';
import { useSession, type CanvasRow } from '../../app/SessionContext.tsx';
import { ActionRequestDialog } from '../actions/ActionRequestDialog.tsx';
import './CanvasPanel.css';

interface CanvasPanelProps {
  compact?: boolean;
  onClose?: () => void;
}

type StatusFilter = 'all' | 'queued' | 'running' | 'completed' | 'partial' | 'failed';

export function CanvasPanel({ compact = false, onClose }: CanvasPanelProps) {
  const { rows, toggleRow, setRowChecked, upsertAction, workspaceId } = useSession();
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [runFilter, setRunFilter] = useState('all');
  const [dialogOpen, setDialogOpen] = useState(false);
  const toast = useToast();

  const runOptions = useMemo(() => {
    const seen = new Map<string, string>();
    rows.forEach((row) => {
      if (!seen.has(row.runId)) seen.set(row.runId, row.submittedAt);
    });
    return [...seen.entries()].map(([id, at]) => ({ id, at }));
  }, [rows]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (needle && !row.username.toLowerCase().includes(needle)) return false;
      if (statusFilter !== 'all' && row.status !== statusFilter) return false;
      if (runFilter !== 'all' && row.runId !== runFilter) return false;
      return true;
    });
  }, [rows, query, statusFilter, runFilter]);

  const selected = filtered.filter((row) => row.checked);
  const allVisibleChecked = filtered.length > 0 && selected.length === filtered.length;

  const exportCsv = () => {
    const header = 'username,run_id,correlation_id,mode,status,submitted_at,note';
    const body = filtered
      .map((row) =>
        [row.username, row.runId, row.correlationId, row.mode, row.status, row.submittedAt, row.note]
          .map((value) => `"${String(value).replace(/"/g, '""')}"`)
          .join(','),
      )
      .join('\n');
    const blob = new Blob([`${header}\n${body}\n`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `fleet-recon-canvas-${new Date().toISOString().slice(0, 19)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    toast.success('Export generated', `${filtered.length} rows written from the current filter.`);
  };

  return (
    <div className={`canvas${compact ? ' canvas--compact' : ''}`}>
      <header className="canvas__head">
        <div className="canvas__head-main">
          <h2 className="canvas__title">Live Canvas</h2>
          <p className="canvas__subtitle">
            {rows.length === 0
              ? 'No reconciliation rows yet'
              : `${filtered.length} of ${rows.length} rows`}
          </p>
        </div>
        <div className="row gap-1">
          <button
            type="button"
            className="btn btn--ghost btn--icon btn--sm"
            onClick={exportCsv}
            disabled={filtered.length === 0}
            title="Export current view as CSV"
            aria-label="Export CSV"
          >
            <Icon name="download" size={15} />
          </button>
          {onClose && (
            <button
              type="button"
              className="btn btn--ghost btn--icon btn--sm"
              onClick={onClose}
              aria-label="Hide canvas"
              title="Hide canvas (⌘\)"
            >
              <Icon name="x" size={15} />
            </button>
          )}
        </div>
      </header>

      {rows.length > 0 && (
        <div className="canvas__filters">
          <div className="canvas__search">
            <Icon name="search" size={14} />
            <input
              className="canvas__search-input"
              placeholder="Filter usernames…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Filter usernames"
            />
          </div>
          <select
            className="select canvas__select"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
            aria-label="Filter by status"
          >
            <option value="all">All statuses</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="partial">Partial</option>
            <option value="failed">Failed</option>
          </select>
          {!compact && runOptions.length > 1 && (
            <select
              className="select canvas__select"
              value={runFilter}
              onChange={(event) => setRunFilter(event.target.value)}
              aria-label="Filter by run"
            >
              <option value="all">All runs</option>
              {runOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  Run {option.id.slice(0, 8)} · {new Date(option.at).toLocaleTimeString()}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      <div className="canvas__body">
        {rows.length === 0 ? (
          <div className="empty">
            <span className="empty__icon">
              <Icon name="canvas" size={20} />
            </span>
            <p className="empty__title">Nothing on the canvas yet</p>
            <p className="empty__desc">
              Submit usernames in chat and every accepted identifier lands here as a shared row you
              can filter, annotate, and target with an action request.
            </p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="empty">
            <span className="empty__icon">
              <Icon name="filter" size={20} />
            </span>
            <p className="empty__title">No rows match these filters</p>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              onClick={() => {
                setQuery('');
                setStatusFilter('all');
                setRunFilter('all');
              }}
            >
              Reset filters
            </button>
          </div>
        ) : (
          <table className="table canvas__table">
            <thead>
              <tr>
                <th className="canvas__check-col">
                  <input
                    type="checkbox"
                    checked={allVisibleChecked}
                    aria-label="Select all visible rows"
                    onChange={(event) =>
                      setRowChecked(
                        filtered.map((row) => row.id),
                        event.target.checked,
                      )
                    }
                  />
                </th>
                <th>Identity</th>
                {!compact && <th>Run</th>}
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.id} className={row.checked ? 'is-selected' : undefined}>
                  <td className="canvas__check-col">
                    <input
                      type="checkbox"
                      checked={row.checked}
                      onChange={() => toggleRow(row.id)}
                      aria-label={`Select ${row.username}`}
                    />
                  </td>
                  <td>
                    <span className="canvas__user">{row.username}</span>
                    <span className="canvas__meta">
                      {row.mode === 'batch_automation' ? 'Batch' : 'Micro-query'} ·{' '}
                      {new Date(row.submittedAt).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </td>
                  {!compact && (
                    <td className="mono text-xs text-tertiary">{row.runId.slice(0, 8)}</td>
                  )}
                  <td>
                    <RowState row={row} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected.length > 0 && (
        <div className="canvas__selection" role="region" aria-label="Selection actions">
          <span className="canvas__selection-count">{selected.length} selected</span>
          <button
            type="button"
            className="btn btn--primary btn--sm"
            onClick={() => setDialogOpen(true)}
          >
            <Icon name="shield" size={14} /> Request action
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setRowChecked(selected.map((row) => row.id), false)}
          >
            Clear
          </button>
        </div>
      )}

      <ActionRequestDialog
        open={dialogOpen}
        rows={selected}
        onClose={() => setDialogOpen(false)}
        onCreated={(action) => {
          upsertAction(action);
          setDialogOpen(false);
          toast.success(
            'Action request created',
            'Confirm it before execution — the request expires in 15 minutes.',
          );
        }}
        onError={(error) => toast.error('Action request failed', errorMessage(error))}
        createAction={(payload) => api.createAction(workspaceId, payload)}
      />
    </div>
  );
}

function RowState({ row }: { row: CanvasRow }) {
  const tone =
    row.status === 'completed'
      ? 'success'
      : row.status === 'failed'
        ? 'danger'
        : row.status === 'partial'
          ? 'warning'
          : 'info';
  return (
    <span className={`badge badge--${tone}`}>
      <span className={`dot${row.status === 'running' ? ' dot--pulse' : ''}`} />
      {row.status === 'queued' ? 'Awaiting evidence' : row.status}
    </span>
  );
}
