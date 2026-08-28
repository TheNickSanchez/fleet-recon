import { useEffect, useRef, type ReactNode } from 'react';
import { Icon } from './Icon.tsx';
import './Modal.css';

interface ModalProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}

export function Modal({ open, title, description, onClose, children, footer, width = 480 }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    panelRef.current?.focus();
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="modal-overlay" role="presentation" onMouseDown={onClose}>
      <div
        ref={panelRef}
        className="modal"
        style={{ width: `min(${width}px, calc(100vw - 2rem))` }}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="modal__head">
          <div>
            <h2 className="modal__title">{title}</h2>
            {description && <p className="modal__desc">{description}</p>}
          </div>
          <button
            type="button"
            className="btn btn--ghost btn--icon btn--sm"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <Icon name="x" size={15} />
          </button>
        </header>
        <div className="modal__body">{children}</div>
        {footer && <footer className="modal__foot">{footer}</footer>}
      </div>
    </div>
  );
}
