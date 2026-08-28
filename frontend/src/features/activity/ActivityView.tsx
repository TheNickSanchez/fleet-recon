import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Icon, type IconName } from '../../components/Icon.tsx';
import { useSession } from '../../app/SessionContext.tsx';
import './ActivityView.css';

interface ActivityEvent {
  id: string;
  at: number;
  icon: IconName;
  tone: string;
  title: string;
  detail: string;
}

export function ActivityView() {
  const { entries, actions, workspaceId, actorId } = useSession();

  const events = useMemo<ActivityEvent[]>(() => {
    const list: ActivityEvent[] = [];

    entries.forEach((entry) => {
      if (entry.error) {
        list.push({
          id: `${entry.id}-error`,
          at: Date.parse(entry.createdAt),
          icon: 'alert',
          tone: 'danger',
          title: 'Run rejected',
          detail: entry.error,
        });
        return;
      }
      if (!entry.run) return;
      list.push({
        id: entry.run.id,
        at: Date.parse(entry.run.created_at),
        icon: entry.prompt.kind === 'csv' ? 'upload' : 'chat',
        tone: 'accent',
        title: `Run created · ${entry.run.mode === 'batch_automation' ? 'batch automation' : 'micro-query'}`,
        detail: `${entry.run.input_count} accepted, ${entry.run.rejected_count} rejected · correlation ${entry.run.correlation_id.slice(0, 8)}`,
      });
    });

    actions.forEach((action) => {
      list.push({
        id: action.id,
        at: Date.parse(action.expires_at) - 15 * 60 * 1000,
        icon: 'shield',
        tone:
          action.status === 'executed'
            ? 'success'
            : action.status === 'confirmed'
              ? 'accent'
              : 'warning',
        title: `Action ${action.status.replace(/_/g, ' ')} · ${action.connector}/${action.operation}`,
        detail: `${action.work_item_ids.length} targets · idempotency ${action.idempotency_key.slice(0, 8)}`,
      });
    });

    return list.sort((a, b) => b.at - a.at);
  }, [entries, actions]);

  return (
    <div className="view">
      <div className="view__scroll">
        <div className="view__inner">
          <div className="view__heading">
            <div>
              <h2>Activity</h2>
              <p>
                Safe state transitions recorded for this browser session — actor, time, and
                correlation metadata only, never secrets or raw connector responses.
              </p>
            </div>
          </div>

          {events.length === 0 ? (
            <div className="card empty">
              <span className="empty__icon">
                <Icon name="activity" size={20} />
              </span>
              <p className="empty__title">No activity yet</p>
              <p className="empty__desc">
                Runs and action requests appear here as they are created.
              </p>
              <Link className="btn btn--secondary btn--sm" to={`/workspaces/${workspaceId}`}>
                <Icon name="chat" size={14} /> Go to chat
              </Link>
            </div>
          ) : (
            <>
              <div className="notice">
                <Icon name="info" size={15} className="notice__icon" />
                <p className="notice__body">
                  The MVP API exposes no audit-query endpoint, so this timeline is reconstructed
                  from this browser session. It is not a substitute for the server-side audit log.
                </p>
              </div>

              <ol className="timeline">
                {events.map((event) => (
                  <li key={event.id} className="timeline__item">
                    <span className={`timeline__marker timeline__marker--${event.tone}`}>
                      <Icon name={event.icon} size={13} />
                    </span>
                    <div className="timeline__body">
                      <div className="timeline__head">
                        <span className="timeline__title">{event.title}</span>
                        <span className="timeline__time">
                          {new Date(event.at).toLocaleString([], {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>
                      <p className="timeline__detail">{event.detail}</p>
                      <p className="timeline__actor mono">{actorId}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
