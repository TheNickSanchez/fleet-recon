import { useEffect, useRef, useState, type ReactNode } from 'react';
import './Menu.css';

interface MenuProps {
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode;
  children: (props: { close: () => void }) => ReactNode;
  align?: 'start' | 'end';
  side?: 'top' | 'bottom';
  label?: string;
}

/** Lightweight popover menu with outside-click and Escape dismissal. */
export function Menu({ trigger, children, align = 'start', side = 'bottom', label }: MenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div className="menu" ref={rootRef}>
      {trigger({ open, toggle: () => setOpen((v) => !v) })}
      {open && (
        <div
          className={`menu__panel menu__panel--${align} menu__panel--${side}`}
          role="menu"
          aria-label={label}
        >
          {children({ close: () => setOpen(false) })}
        </div>
      )}
    </div>
  );
}

interface MenuItemProps {
  icon?: ReactNode;
  children: ReactNode;
  onSelect?: () => void;
  disabled?: boolean;
  hint?: string;
  danger?: boolean;
}

export function MenuItem({ icon, children, onSelect, disabled, hint, danger }: MenuItemProps) {
  return (
    <button
      type="button"
      role="menuitem"
      className={`menu__item${danger ? ' menu__item--danger' : ''}`}
      onClick={onSelect}
      disabled={disabled}
      title={disabled && hint ? hint : undefined}
    >
      {icon && <span className="menu__item-icon">{icon}</span>}
      <span className="menu__item-label">{children}</span>
      {hint && <span className="menu__item-hint">{hint}</span>}
    </button>
  );
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return <p className="menu__label">{children}</p>;
}

export function MenuSeparator() {
  return <div className="menu__separator" role="separator" />;
}
