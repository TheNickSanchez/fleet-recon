import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '../../components/Icon.tsx';
import { Menu, MenuItem, MenuLabel } from '../../components/Menu.tsx';
import { useToast } from '../../components/Toast.tsx';
import { CSV_ACCEPT, MODE_LABEL, parseInput, validateCsv } from './parseInput.ts';
import './Composer.css';

interface ComposerProps {
  busy: boolean;
  onSubmitText: (text: string, kind: 'typed' | 'pasted', usernames: string[]) => void;
  onSubmitCsv: (file: File) => void;
  /** Increment `nonce` to load `value` into the composer from outside. */
  seed?: { value: string; nonce: number };
}

export function Composer({ busy, onSubmitText, onSubmitCsv, seed }: ComposerProps) {
  const [text, setText] = useState('');
  const [dragging, setDragging] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const parsed = parseInput(text);
  const canSubmit = !busy && parsed.accepted.length > 0;

  const seedNonce = seed?.nonce ?? 0;
  const seedValue = seed?.value ?? '';
  useEffect(() => {
    if (seedNonce === 0) return;
    setText(seedValue);
    textareaRef.current?.focus();
  }, [seedNonce, seedValue]);

  // Auto-grow the textarea up to a capped height.
  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = 'auto';
    node.style.height = `${Math.min(node.scrollHeight, 220)}px`;
  }, [text]);

  const submit = useCallback(() => {
    if (!canSubmit) return;
    onSubmitText(text.trim(), parsed.kind, parsed.accepted);
    setText('');
  }, [canSubmit, onSubmitText, parsed.accepted, parsed.kind, text]);

  const handleFile = useCallback(
    (file: File) => {
      const problem = validateCsv(file);
      if (problem) {
        toast.error('CSV rejected', problem);
        return;
      }
      onSubmitCsv(file);
    },
    [onSubmitCsv, toast],
  );

  return (
    <div className="composer-dock">
      <div
        className={`composer${dragging ? ' is-dragging' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files?.[0];
          if (file) handleFile(file);
        }}
      >
        <textarea
          ref={textareaRef}
          className="composer__input"
          value={text}
          rows={1}
          disabled={busy}
          placeholder="Paste usernames or ask about a user, device, or compliance gap…"
          aria-label="Message Fleet Recon"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />

        <div className="composer__bar">
          <Menu
            side="top"
            label="Attachments and actions"
            trigger={({ toggle, open }) => (
              <button
                type="button"
                className={`btn btn--ghost btn--icon composer__plus${open ? ' is-open' : ''}`}
                onClick={toggle}
                disabled={busy}
                aria-label="Add attachment"
                title="Attach CSV"
              >
                <Icon name="plus" size={17} />
              </button>
            )}
          >
            {({ close }) => (
              <>
                <MenuLabel>Attach</MenuLabel>
                <MenuItem
                  icon={<Icon name="upload" size={15} />}
                  onSelect={() => {
                    close();
                    fileRef.current?.click();
                  }}
                >
                  Upload CSV…
                </MenuItem>
                <MenuLabel>Integration actions</MenuLabel>
                <MenuItem icon={<Icon name="lock" size={15} />} disabled hint="Select canvas rows">
                  ServiceNow ticket
                </MenuItem>
                <MenuItem icon={<Icon name="lock" size={15} />} disabled hint="Select canvas rows">
                  Jamf policy
                </MenuItem>
              </>
            )}
          </Menu>

          <input
            ref={fileRef}
            type="file"
            accept={CSV_ACCEPT}
            className="sr-only"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) handleFile(file);
              event.target.value = '';
            }}
          />

          <ComposerFeedback
            count={parsed.accepted.length}
            rejected={parsed.rejected.length}
            mode={parsed.mode}
            prose={parsed.looksLikeProse}
            empty={text.trim().length === 0}
          />

          <button
            type="button"
            className="btn btn--primary btn--icon composer__send"
            onClick={submit}
            disabled={!canSubmit}
            aria-label="Send"
            title="Send (Enter)"
          >
            <Icon name={busy ? 'spinner' : 'send'} size={16} />
          </button>
        </div>

        {dragging && (
          <div className="composer__dropzone">
            <Icon name="upload" size={18} />
            <span>Drop a CSV with a <code>username</code> column</span>
          </div>
        )}
      </div>

      <p className="composer__legal">
        <kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line · usernames are
        de-duplicated and validated server-side.
      </p>
    </div>
  );
}

function ComposerFeedback({
  count,
  rejected,
  mode,
  prose,
  empty,
}: {
  count: number;
  rejected: number;
  mode: 'micro_query' | 'batch_automation';
  prose: boolean;
  empty: boolean;
}) {
  if (empty) {
    return (
      <p className="composer__feedback composer__feedback--muted">
        Detected identifiers appear here as you type.
      </p>
    );
  }

  if (count === 0) {
    return (
      <p className="composer__feedback composer__feedback--warn">
        <Icon name="alert" size={13} /> No valid usernames detected yet.
      </p>
    );
  }

  return (
    <p className="composer__feedback" aria-live="polite">
      <span className="badge badge--accent">
        {count} {count === 1 ? 'username' : 'usernames'}
      </span>
      <span className="badge badge--outline">{MODE_LABEL[mode]}</span>
      {rejected > 0 && (
        <span className="badge badge--warning" title="These tokens fail the server username pattern">
          {rejected} ignored
        </span>
      )}
      {prose && <span className="composer__feedback-note">Free-text intent is preserved.</span>}
    </p>
  );
}
