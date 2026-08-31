import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '../../components/Icon.tsx';
import { Menu, MenuItem, MenuLabel } from '../../components/Menu.tsx';
import { useToast } from '../../components/Toast.tsx';
import { CSV_ACCEPT, validateCsv } from './parseInput.ts';
import './Composer.css';

export interface ComposerSubmission {
  text: string;
  file?: File;
}

interface ComposerProps {
  busy: boolean;
  onSubmit: (submission: ComposerSubmission) => void;
  /** Increment `nonce` to load `value` into the composer from outside. */
  seed?: { value: string; nonce: number };
}

export function Composer({ busy, onSubmit, seed }: ComposerProps) {
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const canSubmit = !busy && (text.trim().length > 0 || file !== null);

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
    onSubmit({ text: text.trim(), file: file ?? undefined });
    setText('');
    setFile(null);
  }, [canSubmit, onSubmit, text, file]);

  const stageFile = useCallback(
    (candidate: File) => {
      const problem = validateCsv(candidate);
      if (problem) {
        toast.error('CSV rejected', problem);
        return;
      }
      setFile(candidate);
    },
    [toast],
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
          const dropped = event.dataTransfer.files?.[0];
          if (dropped) stageFile(dropped);
        }}
      >
        {file && (
          <div className="composer__staged">
            <Icon name="file" size={14} />
            <span className="truncate">{file.name}</span>
            <button
              type="button"
              className="btn btn--ghost btn--icon composer__staged-remove"
              onClick={() => setFile(null)}
              aria-label="Remove attachment"
              disabled={busy}
            >
              <Icon name="x" size={13} />
            </button>
          </div>
        )}

        <textarea
          ref={textareaRef}
          className="composer__input"
          value={text}
          rows={1}
          disabled={busy}
          placeholder="Ask anything — a device lookup, a batch report, a ticket search…"
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
            label="Attachments"
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
              </>
            )}
          </Menu>

          <input
            ref={fileRef}
            type="file"
            accept={CSV_ACCEPT}
            className="sr-only"
            onChange={(event) => {
              const picked = event.target.files?.[0];
              if (picked) stageFile(picked);
              event.target.value = '';
            }}
          />

          <p className="composer__feedback composer__feedback--muted">
            {file ? 'CSV attached — add a note or just send.' : 'Type a message, or attach a CSV.'}
          </p>

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
            <span>Drop a CSV (username column, under 5 MiB)</span>
          </div>
        )}
      </div>

      <p className="composer__legal">
        <kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line
      </p>
    </div>
  );
}
