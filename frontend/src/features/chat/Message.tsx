import { useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Icon, type IconName } from '../../components/Icon.tsx';
import { useToast } from '../../components/Toast.tsx';
import { useRunPolling } from '../../hooks/useRunPolling.ts';
import type { RunStatus, RunSummary } from '../../types/api.ts';
import type { ChatEntry } from '../../app/AppState.tsx';
import './Message.css';

const STATUS_META: Record<RunStatus, { label: string; tone: string; icon: IconName }> = {
  queued: { label: 'Queued', tone: 'info', icon: 'clock' },
  running: { label: 'Running', tone: 'accent', icon: 'spinner' },
  completed: { label: 'Completed', tone: 'success', icon: 'checkCircle' },
  failed: { label: 'Failed', tone: 'danger', icon: 'alert' },
};

function timeOf(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function UserMessage({ entry }: { entry: ChatEntry }) {
  const { prompt } = entry;
  return (
    <div className="msg msg--user">
      <div className="msg__bubble">
        {prompt.fileName && (
          <span className="msg__file">
            <Icon name="file" size={15} />
            <span className="truncate">{prompt.fileName}</span>
          </span>
        )}
        {prompt.text && <p className="msg__text">{prompt.text}</p>}
      </div>
      <span className="msg__time">{timeOf(entry.createdAt)}</span>
    </div>
  );
}

interface RunMessageProps {
  entry: ChatEntry;
  onRunUpdate: (run: RunSummary) => void;
}

export function RunMessage({ entry, onRunUpdate }: RunMessageProps) {
  const { run, polling, stalled, gaveUp, refresh } = useRunPolling(entry.run);
  const toast = useToast();

  const observedUpdatedAt = run?.updated_at;
  const knownUpdatedAt = entry.run?.updated_at;
  useEffect(() => {
    if (run && observedUpdatedAt !== knownUpdatedAt) onRunUpdate(run);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [observedUpdatedAt, knownUpdatedAt]);

  if (!run) return null;

  const meta = STATUS_META[run.status];
  // `?? []` guards a run object persisted to sessionStorage before `activity` existed on the
  // contract (this field shipped after threadId did) -- an old tab's stale entry must not crash
  // the whole message on the next poll.
  const activity = run.activity ?? [];
  const recentActivity = activity.length > 0 ? activity.slice(-5) : ['Connecting to the session...'];
  const activityOffset = activity.length - recentActivity.length;

  const copyText = () => {
    if (run.result?.type !== 'chat.text') return;
    void navigator.clipboard?.writeText(run.result.text);
    toast.success('Copied', 'Response copied to clipboard.');
  };

  return (
    <div className="msg msg--agent">
      <AgentAvatar tone={meta.tone} />
      <div className="msg__card">
        <div className="msg__card-head">
          <span className={`badge badge--${meta.tone}`}>
            <Icon name={polling ? 'spinner' : meta.icon} size={12} />
            {meta.label}
          </span>
          <span className="msg__card-time">{timeOf(run.created_at)}</span>
        </div>

        {polling && (
          <div className="msg__activity" role="status" aria-live="polite">
            {recentActivity.map((line, i) => {
              const isCurrent = i === recentActivity.length - 1;
              return (
                <div key={activityOffset + i} className={`msg__activity-line${isCurrent ? ' is-current' : ''}`}>
                  <Icon name={isCurrent ? 'spinner' : 'checkCircle'} size={13} />
                  <span>{line}</span>
                </div>
              );
            })}
          </div>
        )}

        {stalled && (
          <div className="notice notice--info msg__notice" role="status">
            <Icon name="info" size={15} className="notice__icon" />
            <div>
              <p className="notice__title">Taking longer than usual</p>
              <p className="notice__body">
                A general chat turn can call several tools in sequence, which can take under a
                minute. This will update on its own when it finishes; no need to click anything.
              </p>
            </div>
          </div>
        )}

        {gaveUp && (
          <div className="notice notice--warning msg__notice" role="status">
            <Icon name="info" size={15} className="notice__icon" />
            <div>
              <p className="notice__title">Still {run.status} after 2 minutes</p>
              <p className="notice__body">
                The session host has no push transport, so this client stopped polling rather
                than spinning forever. The run may still be working in the background — check
                again below.
              </p>
            </div>
          </div>
        )}

        {run.status === 'failed' && (
          <div className="notice notice--danger msg__notice" role="alert">
            <Icon name="alert" size={15} className="notice__icon" />
            <div>
              <p className="notice__title">Failed</p>
              <p className="notice__body">
                {run.diagnostic ?? run.error?.message ?? 'No further detail was returned.'}
              </p>
            </div>
          </div>
        )}

        {run.status === 'completed' && run.result?.type === 'chat.text' && (
          <div className="msg__result markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{run.result.text}</ReactMarkdown>
          </div>
        )}

        <div className="msg__actions">
          <button type="button" className="btn btn--ghost btn--sm" onClick={refresh}>
            <Icon name="refresh" size={14} /> Check again
          </button>
          {run.status === 'completed' && run.result?.type === 'chat.text' && (
            <button type="button" className="btn btn--ghost btn--sm" onClick={copyText}>
              <Icon name="copy" size={14} /> Copy
            </button>
          )}
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
