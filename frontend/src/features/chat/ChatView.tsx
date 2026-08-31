import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon, type IconName } from '../../components/Icon.tsx';
import { useToast } from '../../components/Toast.tsx';
import { api, errorMessage } from '../../api/client.ts';
import { useAppState, type ChatEntry } from '../../app/AppState.tsx';
import { uuid } from '../../lib/uuid.ts';
import { Composer, type ComposerSubmission } from './Composer.tsx';
import { RunMessage, UserMessage } from './Message.tsx';
import './ChatView.css';

const SUGGESTIONS: { icon: IconName; title: string; body: string; fill: string }[] = [
  {
    icon: 'user',
    title: 'Look up a device',
    body: 'Paste a serial, hostname, or username for a full cross-system summary.',
    fill: 'look up MC5J392AKD',
  },
  {
    icon: 'file',
    title: 'Build an asset report',
    body: 'Paste several usernames (or upload a CSV) for one report across ServiceNow, Jamf, and Intune.',
    fill: 'build an asset report for: nina.patel, chris.okonkwo, sam.lee, jordan.nguyen',
  },
  {
    icon: 'search',
    title: 'Ask anything else',
    body: 'Tickets, Jira issues, Confluence pages, Slack — whatever tools the question needs.',
    fill: 'what can you help me with?',
  },
];

export function ChatView() {
  const { entries, addEntry, updateEntry, clearThread, threadId } = useAppState();
  const [busy, setBusy] = useState(false);
  const [seed, setSeed] = useState({ value: '', nonce: 0 });
  const toast = useToast();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [entries.length]);

  const handleSubmit = useCallback(
    async ({ text, file }: ComposerSubmission) => {
      const entry: ChatEntry = {
        id: uuid(),
        createdAt: new Date().toISOString(),
        prompt: { text, fileName: file?.name },
      };
      setBusy(true);
      try {
        const run = await api.createRun({ text, file, threadId });
        addEntry({ ...entry, run });
      } catch (error) {
        toast.error('Could not reach the session host', errorMessage(error));
      } finally {
        setBusy(false);
      }
    },
    [addEntry, threadId, toast],
  );

  const empty = entries.length === 0;

  return (
    <div className="chat-layout">
      <section className="chat" aria-label="Fleet Recon chat">
        {!empty && (
          <div className="chat__toolbar">
            <span className="text-xs text-tertiary">
              {entries.length} {entries.length === 1 ? 'message' : 'messages'} this session
            </span>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => {
                clearThread();
                toast.info('New conversation', 'The thread was reset.');
              }}
            >
              <Icon name="trash" size={14} /> New chat
            </button>
          </div>
        )}

        <div className="chat__scroll">
          {empty ? (
            <div className="chat__welcome">
              <span className="chat__welcome-mark">
                <Icon name="sparkle" size={22} />
              </span>
              <h2>What are you working on?</h2>
              <p>
                Ask like you would Claude — a device lookup, a batch asset report, a ticket search.
                Every MCP tool you have configured is already attached.
              </p>
              <div className="chat__suggestions">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion.title}
                    type="button"
                    className="suggestion"
                    onClick={() => setSeed((prev) => ({ value: suggestion.fill, nonce: prev.nonce + 1 }))}
                  >
                    <span className="suggestion__icon">
                      <Icon name={suggestion.icon} size={16} />
                    </span>
                    <span className="suggestion__title">{suggestion.title}</span>
                    <span className="suggestion__body">{suggestion.body}</span>
                  </button>
                ))}
              </div>
              <p className="chat__disclosure">
                This thread is kept only in your browser for this session — closing the tab clears
                it. There is no server-side audit log.
              </p>
            </div>
          ) : (
            <div className="chat__thread">
              {entries.map((entry) => (
                <div key={entry.id} className="chat__turn">
                  <UserMessage entry={entry} />
                  <RunMessage entry={entry} onRunUpdate={(run) => updateEntry(entry.id, { run })} />
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <Composer busy={busy} onSubmit={handleSubmit} seed={seed} />
      </section>
    </div>
  );
}
