import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../../components/Icon.tsx';
import { useToast } from '../../components/Toast.tsx';
import { api, errorMessage } from '../../api/client.ts';
import { useSession, type ThreadEntry } from '../../app/SessionContext.tsx';
import { uuid } from '../../lib/uuid.ts';
import { CanvasPanel } from '../canvas/CanvasPanel.tsx';
import { Composer } from './Composer.tsx';
import { RunMessage, UserMessage } from './Message.tsx';
import './ChatView.css';

interface ChatViewProps {
  canvasOpen: boolean;
  onOpenCanvas: () => void;
  onCloseCanvas: () => void;
}

const SUGGESTIONS = [
  {
    icon: 'user' as const,
    title: 'Reconcile a single user',
    body: 'Look up one identity across ServiceNow, Jamf, Intune, and Tenable.',
    fill: 'a.rivera',
  },
  {
    icon: 'users' as const,
    title: 'Compare a small cohort',
    body: 'Paste up to five usernames for the low-latency micro-query path.',
    fill: 'a.rivera\nj.chen\nm.okafor',
  },
  {
    icon: 'file' as const,
    title: 'Run a batch reconciliation',
    body: 'More than five identifiers routes to the deterministic batch pipeline.',
    fill: 'a.rivera\nj.chen\nm.okafor\ns.patel\nl.dubois\nk.tanaka',
  },
];

export function ChatView({ canvasOpen, onOpenCanvas, onCloseCanvas }: ChatViewProps) {
  const { workspaceId, entries, addEntry, updateEntry, clearThread, registerRows } = useSession();
  const [busy, setBusy] = useState(false);
  const [seed, setSeed] = useState({ value: '', nonce: 0 });
  const toast = useToast();
  const navigate = useNavigate();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [entries.length]);

  const submit = useCallback(
    async (entry: ThreadEntry, send: () => Promise<Awaited<ReturnType<typeof api.createRun>>>) => {
      addEntry(entry);
      setBusy(true);
      try {
        const run = await send();
        updateEntry(entry.id, { run });
        registerRows(run, entry.prompt.usernames);
        if (!canvasOpen && run.input_count > 0) onOpenCanvas();
      } catch (error) {
        const message = errorMessage(error);
        updateEntry(entry.id, { error: message });
        toast.error('Run could not be created', message);
      } finally {
        setBusy(false);
      }
    },
    [addEntry, canvasOpen, onOpenCanvas, registerRows, toast, updateEntry],
  );

  const handleText = useCallback(
    (text: string, kind: 'typed' | 'pasted', usernames: string[]) => {
      const entry: ThreadEntry = {
        id: uuid(),
        createdAt: new Date().toISOString(),
        prompt: { kind, text, usernames },
      };
      void submit(entry, () => api.createRun(workspaceId, { input_kind: kind, text }));
    },
    [submit, workspaceId],
  );

  const handleCsv = useCallback(
    (file: File) => {
      const entry: ThreadEntry = {
        id: uuid(),
        createdAt: new Date().toISOString(),
        prompt: { kind: 'csv', text: file.name, fileName: file.name, usernames: [] },
      };
      void submit(entry, () => api.uploadRun(workspaceId, file));
    },
    [submit, workspaceId],
  );

  const empty = entries.length === 0;

  return (
    <div className="chat-layout">
      <section className="chat" aria-label="Copilot chat">
        {!empty && (
          <div className="chat__toolbar">
            <span className="text-xs text-tertiary">
              {entries.length} {entries.length === 1 ? 'request' : 'requests'} in this session
            </span>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => {
                clearThread();
                toast.info('Session cleared', 'Local thread and canvas rows were reset.');
              }}
            >
              <Icon name="trash" size={14} /> Clear
            </button>
          </div>
        )}

        <div className="chat__scroll">
          {empty ? (
            <div className="chat__welcome">
              <span className="chat__welcome-mark">
                <Icon name="sparkle" size={22} />
              </span>
              <h2>What should we reconcile?</h2>
              <p>
                Paste usernames straight into the box below, or describe what you are investigating.
                Fleet Recon routes small lookups to the micro-query path and larger lists to batch
                automation.
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
            </div>
          ) : (
            <div className="chat__thread">
              {entries.map((entry) => (
                <div key={entry.id} className="chat__turn">
                  <UserMessage entry={entry} />
                  <RunMessage
                    entry={entry}
                    workspaceId={workspaceId}
                    onOpenCanvas={() => {
                      onOpenCanvas();
                      navigate(`/workspaces/${workspaceId}/canvas`);
                    }}
                    onStatusChange={(run) => updateEntry(entry.id, { run })}
                  />
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <Composer busy={busy} onSubmitText={handleText} onSubmitCsv={handleCsv} seed={seed} />
      </section>

      {canvasOpen && (
        <aside className="chat__canvas" aria-label="Live canvas">
          <CanvasPanel compact onClose={onCloseCanvas} />
        </aside>
      )}
    </div>
  );
}
