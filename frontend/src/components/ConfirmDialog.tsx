/* Accessible confirmation dialog for destructive operations:
   portal, Escape to cancel, focus moved into the dialog, Tab cycled inside,
   explicit pending state on the confirm button (no optimistic success). */
import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, X } from 'lucide-react';

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = true,
  pending = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        if (!pending) onCancel();
        return;
      }
      if (e.key === 'Tab') {
        const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (!focusables || focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement;
        if (e.shiftKey && (active === first || !dialogRef.current?.contains(active))) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', keyHandler, true);
    // move focus in on open
    const t = window.setTimeout(() => {
      dialogRef.current?.querySelector<HTMLElement>('[data-autofocus]')?.focus();
    }, 0);
    return () => {
      document.removeEventListener('keydown', keyHandler, true);
      window.clearTimeout(t);
      previouslyFocused?.focus?.();
    };
  }, [open, onCancel, pending]);

  if (!open) return null;

  return createPortal(
    <div
      className="dialog-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !pending) onCancel();
      }}
    >
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        ref={dialogRef}
      >
        <div className="dialog-head">
          <h3 id="confirm-dialog-title" className="row">
            {danger && (
              <AlertTriangle
                aria-hidden="true"
                style={{ color: 'var(--danger)', width: 18, height: 18 }}
              />
            )}
            {title}
          </h3>
          <button
            type="button"
            className="btn-ghost btn btn-sm"
            onClick={onCancel}
            disabled={pending}
            aria-label="Close dialog"
          >
            <X aria-hidden="true" />
          </button>
        </div>
        <div className="dialog-body">{children}</div>
        <div className="dialog-foot">
          <button
            type="button"
            className="btn"
            onClick={onCancel}
            disabled={pending}
            data-autofocus
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
            onClick={onConfirm}
            disabled={pending}
          >
            {pending && <span className="spinner" aria-hidden="true" />}
            {pending ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
