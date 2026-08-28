import { useEffect, useState } from 'react';
import { Icon } from '../../components/Icon.tsx';
import { Modal } from '../../components/Modal.tsx';
import type { CanvasRow } from '../../app/SessionContext.tsx';
import {
  ALLOWED_OPERATIONS,
  type ActionRequestCreate,
  type ActionRequestView,
} from '../../types/api.ts';
import './Actions.css';

interface ActionRequestDialogProps {
  open: boolean;
  rows: CanvasRow[];
  onClose: () => void;
  onCreated: (action: ActionRequestView) => void;
  onError: (error: unknown) => void;
  createAction: (payload: ActionRequestCreate) => Promise<ActionRequestView>;
}

export function ActionRequestDialog({
  open,
  rows,
  onClose,
  onCreated,
  onError,
  createAction,
}: ActionRequestDialogProps) {
  const [choice, setChoice] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setChoice(0);
      setSubmitting(false);
    }
  }, [open]);

  const operation = ALLOWED_OPERATIONS[choice];

  const submit = async () => {
    setSubmitting(true);
    try {
      const action = await createAction({
        work_item_ids: rows.map((row) => row.id),
        connector: operation.connector,
        operation: operation.operation,
        parameters: {},
      });
      onCreated(action);
    } catch (error) {
      onError(error);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title="Request a scoped action"
      description="Fleet Recon never mutates a connector directly. This creates a previewable request that must be confirmed before execution."
      onClose={onClose}
      width={520}
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void submit()}
            disabled={submitting || rows.length === 0}
          >
            {submitting && <Icon name="spinner" size={14} />}
            Create request
          </button>
        </>
      }
    >
      <div className="field">
        <span className="field__label">Operation</span>
        <div className="choice-group">
          {ALLOWED_OPERATIONS.map((option, index) => (
            <button
              key={option.operation}
              type="button"
              className={`choice${index === choice ? ' is-active' : ''}`}
              onClick={() => setChoice(index)}
              aria-pressed={index === choice}
            >
              <span className="choice__radio" />
              <span className="choice__body">
                <span className="choice__title">{option.label}</span>
                <span className="choice__meta mono">
                  {option.connector} · {option.operation}
                </span>
              </span>
            </button>
          ))}
        </div>
        <span className="field__hint">
          Only allowlisted connector/operation pairs are accepted by the server.
        </span>
      </div>

      <div className="preview">
        <div className="preview__row">
          <span>Targets</span>
          <strong>{rows.length}</strong>
        </div>
        <div className="preview__row">
          <span>Confirmation</span>
          <strong>Required before execution</strong>
        </div>
        <div className="preview__row">
          <span>Expires</span>
          <strong>15 minutes after creation</strong>
        </div>
        {rows.length > 0 && (
          <ul className="preview__targets">
            {rows.slice(0, 8).map((row) => (
              <li key={row.id}>{row.username}</li>
            ))}
            {rows.length > 8 && <li className="text-tertiary">+{rows.length - 8} more</li>}
          </ul>
        )}
      </div>

      <div className="notice notice--info">
        <Icon name="info" size={15} className="notice__icon" />
        <p className="notice__body">
          Work-item identifiers are provisional client-side IDs until the backend persists{' '}
          <code>CanvasWorkItem</code> records. Execution is an audit-only transition in the MVP.
        </p>
      </div>
    </Modal>
  );
}
