import { useEffect } from 'react';
import { Icon, type IconName } from '../../components/Icon.tsx';
import type { RunStatus, RunSummary } from '../../types/api.ts';
import type { ThreadEntry } from '../../app/SessionContext.tsx';
import { useRunStatus } from '../../hooks/useRunStatus.ts';
import { MODE_LABEL } from './parseInput.ts';
import './Message.css';

const STATUS_META: Record<RunStatus, { label: string; tone: string; icon: IconName }> = {
  queued: { label: 'Queued', tone: 'info', icon: 'clock' },
  running: { label: 'Running', tone: 'accent', icon: 'spinner' },
  completed: { label: 'Completed', tone: 'success', icon: 'checkCircle' },
  partial: { label: 'Partial', tone: 'warning', icon: 'alert' },
  failed: { label: 'Failed', tone: 'danger', icon: 'alert' },
};

function timeOf(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function UserMessage({ entry }: { entry: ThreadEntry }) {
  const { prompt } = entry;
  return (
    <div className="msg msg--user">
      <div className="msg__bubble">
        {prompt.kind === 'csv' ? (
          <span className="msg__file">
            <Icon name="file" size={15} />
            <span className="truncate">{prompt.fileName}</span>
          </span>
        ) : (
          <p className="msg__text">{prompt.text}</p>
        )}
      </div>
      <span className="msg__time">{timeOf(entry.createdAt)}</span>
    </div>
  );
}

interface RunMessageProps {
  entry: ThreadEntry;
  workspaceId: string;
  onOpenCanvas: () => void;
  onStatusChange: (run: RunSummary) => void;
}

export function RunMessage({ entry, workspaceId, onOpenCanvas, onStatusChange }: RunMessageProps) {
  const { run, polling, stalled, refresh } = useRunStatus({ workspaceId, run: entry.run });

  const observedStatus = run?.status;
  const knownStatus = entry.run?.status;
  useEffect(() => {
    if (run && observedStatus !== knownStatus) onStatusChange(run);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [observedStatus, knownStatus]);

  if (entry.error) {
    return (
      <div className="msg msg--agent">
        <AgentAvatar tone="danger" />
        <div className="msg__card msg__card--danger">
          <div className="msg__card-head">
            <Icon name="alert" size={15} />
            <span className="msg__card-title">Request rejected</span>
          </div>
          <p className="msg__error">{entry.error}</p>
        </div>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="msg msg--agent">
        <AgentAvatar tone="accent" />
        <div className="msg__card">
          <div className="msg__skeleton">
            <span className="skeleton" style={{ width: '38%', height: 12 }} />
            <span className="skeleton" style={{ width: '62%', height: 12 }} />
          </div>
        </div>
      </div>
    );
  }

  const meta = STATUS_META[run.status];

  return (
    <div className="msg msg--agent">
      <AgentAvatar tone={meta.tone} />
      <div className="msg__card">
        <div className="msg__card-head">
          <span className={`badge badge--${meta.tone}`}>
            <Icon name={polling ? 'spinner' : meta.icon} size={12} />
            {meta.label}
          </span>
          <span className="badge badge--outline">{MODE_LABEL[run.mode]}</span>
          <span className="msg__card-time">{timeOf(run.created_at)}</span>
        </div>

        <p className="msg__summary">
          Accepted <strong>{run.input_count}</strong>{' '}
          {run.input_count === 1 ? 'identifier' : 'identifiers'}
          {run.rejected_count > 0 && (
            <>
              {' '}
              and rejected <strong>{run.rejected_count}</strong> malformed{' '}
              {run.rejected_count === 1 ? 'token' : 'tokens'}
            </>
          )}
          .{' '}
          {run.mode === 'batch_automation'
            ? 'Routed to the deterministic batch pipeline.'
            : 'Routed to the low-latency micro-query path.'}
        </p>

        {polling && (
          <div className="msg__progress" role="status" aria-live="polite">
            <span className="msg__progress-bar" />
            <span className="msg__progress-label">Waiting for connector results…</span>
          </div>
        )}

        {stalled && (
          <div className="notice notice--warning msg__notice">
            <Icon name="info" size={15} className="notice__icon" />
            <div>
              <p className="notice__title">Run accepted, results pending</p>
              <p className="notice__body">
                The MVP backend persists and routes the run but has no connector worker yet, so the
                status stays <code>queued</code>. Evidence tables appear here once the orchestration
                service is wired up.
              </p>
            </div>
          </div>
        )}

        <dl className="msg__facts">
          <div>
            <dt>Run</dt>
            <dd className="mono">{run.id.slice(0, 8)}</dd>
          </div>
          <div>
            <dt>Correlation</dt>
            <dd className="mono">{run.correlation_id.slice(0, 8)}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{run.input_kind}</dd>
          </div>
        </dl>

        <div className="msg__actions">
          <button type="button" className="btn btn--secondary btn--sm" onClick={onOpenCanvas}>
            <Icon name="canvas" size={14} /> View on canvas
          </button>
          <button type="button" className="btn btn--ghost btn--sm" onClick={refresh}>
            <Icon name="refresh" size={14} /> Refresh
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => void navigator.clipboard?.writeText(run.correlation_id)}
            title="Copy correlation ID for support"
          >
            <Icon name="copy" size={14} /> Correlation ID
          </button>
        </div>
      </div>
    </div>
  );
}

function AgentAvatar({ tone }: { tone: string }) {
  return (
    <span className={`msg__avatar msg__avatar--${tone}`} aria-hidden="true">
      <Icon name="sparkle" size={14} />
    </span>
  );
}
