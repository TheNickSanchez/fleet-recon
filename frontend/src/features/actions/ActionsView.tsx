import { Fragment, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '../../components/Icon.tsx';
import { useToast } from '../../components/Toast.tsx';
import { api, errorMessage } from '../../api/client.ts';
import { useSession } from '../../app/SessionContext.tsx';
import type { ActionRequestView } from '../../types/api.ts';
import './Actions.css';

const STEPS: { key: string; label: string }[] = [
  { key: 'pending_confirmation', label: 'Created' },
  { key: 'confirmed', label: 'Confirmed' },
  { key: 'executed', label: 'Executed' },
];

export function ActionsView() {
  const { actions, upsertAction, workspaceId, rows } = useSession();
  const toast = useToast();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const run = async (
    action: ActionRequestView,
    fn: () => Promise<ActionRequestView>,
    successTitle: string,
  ) => {
    setBusyId(action.id);
    try {
      const updated = await fn();
      upsertAction(updated);
      toast.success(successTitle);
    } catch (error) {
      toast.error('Request rejected', errorMessage(error));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="view">
      <div className="view__scroll">
        <div className="view__inner">
          <div className="view__heading">
            <div>
              <h2>Action Requests</h2>
              <p>
                Every remediation is a two-phase request: create a scoped preview, confirm it, then
                execute. Requests expire 15 minutes after creation and cannot be executed without a
                matching unexpired confirmation.
              </p>
            </div>
          </div>

          {actions.length === 0 ? (
            <div className="card empty">
              <span className="empty__icon">
                <Icon name="shield" size={20} />
              </span>
              <p className="empty__title">No action requests</p>
              <p className="empty__desc">
                Select rows on the Live Canvas and choose <strong>Request action</strong> to create
                one. {rows.length === 0 && 'Submit usernames in chat first to populate the canvas.'}
              </p>
              <Link className="btn btn--secondary btn--sm" to={`/workspaces/${workspaceId}/canvas`}>
                <Icon name="canvas" size={14} /> Open Live Canvas
              </Link>
            </div>
          ) : (
            <div className="stack gap-3">
              {actions.map((action) => {
                const expiresIn = Date.parse(action.expires_at) - now;
                const expired = expiresIn <= 0 && action.status !== 'executed';
                const state = expired && action.status !== 'executed' ? 'expired' : action.status;
                const busy = busyId === action.id;

                return (
                  <article key={action.id} className={`action-card action-card--${state}`}>
                    <div className="action-card__head">
                      <span className="action-card__connector">{action.connector}</span>
                      <span className="action-card__op">{action.operation}</span>
                      <StatusBadge state={state} />
                      <span className="grow" />
                      {!expired && action.status !== 'executed' && (
                        <span className="badge badge--outline">
                          <Icon name="clock" size={11} /> {formatCountdown(expiresIn)}
                        </span>
                      )}
                    </div>

                    <div className="action-card__steps">
                      {STEPS.map((step, index) => {
                        const currentIndex = STEPS.findIndex((s) => s.key === action.status);
                        const done = index < currentIndex || action.status === 'executed';
                        const current = index === currentIndex && action.status !== 'executed';
                        return (
                          <Fragment key={step.key}>
                            <span
                              className={`step${done ? ' is-done' : ''}${current ? ' is-current' : ''}`}
                            >
                              <span className="step__dot">{done ? '✓' : index + 1}</span>
                              {step.label}
                            </span>
                            {index < STEPS.length - 1 && <span className="step__line" />}
                          </Fragment>
                        );
                      })}
                    </div>

                    <dl className="action-card__facts">
                      <div>
                        <dt>Targets</dt>
                        <dd>{action.work_item_ids.length}</dd>
                      </div>
                      <div>
                        <dt>Expires</dt>
                        <dd>{new Date(action.expires_at).toLocaleTimeString()}</dd>
                      </div>
                      <div>
                        <dt>Idempotency key</dt>
                        <dd className="mono">{action.idempotency_key.slice(0, 13)}…</dd>
                      </div>
                    </dl>

                    <div className="action-card__actions">
                      <button
                        type="button"
                        className="btn btn--secondary btn--sm"
                        disabled={busy || expired || action.status !== 'pending_confirmation'}
                        onClick={() =>
                          void run(
                            action,
                            () => api.confirmAction(workspaceId, action.id),
                            'Action confirmed',
                          )
                        }
                      >
                        <Icon name={busy ? 'spinner' : 'check'} size={14} /> Confirm
                      </button>
                      <button
                        type="button"
                        className="btn btn--primary btn--sm"
                        disabled={busy || expired || action.status !== 'confirmed'}
                        onClick={() =>
                          void run(
                            action,
                            () => api.executeAction(workspaceId, action.id),
                            'Action executed',
                          )
                        }
                      >
                        <Icon name={busy ? 'spinner' : 'play'} size={14} /> Execute
                      </button>
                      {expired && (
                        <span className="text-xs text-tertiary row gap-1">
                          <Icon name="clock" size={13} /> Confirmation window closed — create a new
                          request.
                        </span>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ state }: { state: string }) {
  const tone =
    state === 'executed'
      ? 'success'
      : state === 'confirmed'
        ? 'accent'
        : state === 'expired'
          ? 'danger'
          : 'warning';
  const label =
    state === 'pending_confirmation' ? 'Awaiting confirmation' : state.replace(/_/g, ' ');
  return <span className={`badge badge--${tone}`}>{label}</span>;
}

function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')} left`;
}
