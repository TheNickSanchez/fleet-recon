import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon, type IconName } from './Icon.tsx';
import './CommandPalette.css';

export interface Command {
  id: string;
  label: string;
  group: string;
  icon: IconName;
  hint?: string;
  run: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  commands: Command[];
}

export function CommandPalette({ open, onClose, commands }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (open) {
      setQuery('');
      setCursor(0);
      window.requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matches = needle
      ? commands.filter(
          (command) =>
            command.label.toLowerCase().includes(needle) ||
            command.group.toLowerCase().includes(needle),
        )
      : commands;
    // Precompute group headers so rendering stays free of mutable state.
    return matches.map((command, index) => ({
      command,
      showGroup: index === 0 || matches[index - 1].group !== command.group,
    }));
  }, [commands, query]);

  useEffect(() => {
    setCursor((current) => Math.min(current, Math.max(results.length - 1, 0)));
  }, [results.length]);

  if (!open) return null;

  const runAt = (index: number) => {
    const entry = results[index];
    if (!entry) return;
    onClose();
    entry.command.run();
  };

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      setCursor((c) => (c + 1) % Math.max(results.length, 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setCursor((c) => (c - 1 + results.length) % Math.max(results.length, 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      runAt(cursor);
    }
  };


  return (
    <div className="palette-overlay" role="presentation" onMouseDown={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="palette__search">
          <Icon name="search" size={16} />
          <input
            ref={inputRef}
            className="palette__input"
            placeholder="Search views and commands…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Search commands"
          />
          <kbd>esc</kbd>
        </div>

        <div className="palette__results" role="listbox">
          {results.length === 0 && <p className="palette__empty">No matching commands.</p>}
          {results.map(({ command, showGroup }, index) => (
            <div key={command.id}>
              {showGroup && <p className="palette__group">{command.group}</p>}
              <button
                type="button"
                role="option"
                aria-selected={index === cursor}
                className={`palette__item${index === cursor ? ' is-active' : ''}`}
                onMouseEnter={() => setCursor(index)}
                onClick={() => runAt(index)}
              >
                <Icon name={command.icon} size={16} />
                <span className="palette__item-label">{command.label}</span>
                {command.hint && <kbd>{command.hint}</kbd>}
                <Icon name="arrowRight" size={14} className="palette__item-arrow" />
              </button>
            </div>
          ))}
        </div>

        <div className="palette__footer">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> navigate
          </span>
          <span>
            <kbd>↵</kbd> select
          </span>
          <button
            type="button"
            className="palette__link"
            onClick={() => {
              onClose();
              navigate(-1);
            }}
          >
            Go back
          </button>
        </div>
      </div>
    </div>
  );
}
