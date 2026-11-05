/* A single toast notification (rendered inside the aria-live region). */
import { CheckCircle2, Info, X, XCircle } from 'lucide-react';
import type { Toast } from '../hooks/ToastProvider';

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
};

export function Notification({
  toast,
  onClose,
}: {
  toast: Toast;
  onClose: () => void;
}) {
  const Icon = ICONS[toast.kind];
  return (
    <div className={`toast ${toast.kind}`} data-kind={toast.kind}>
      <Icon aria-hidden="true" />
      <div className="grow">
        <div className="toast-title">{toast.title}</div>
        {toast.message ? <div className="toast-msg">{toast.message}</div> : null}
      </div>
      <button
        type="button"
        className="toast-close"
        onClick={onClose}
        aria-label={`Dismiss: ${toast.title}`}
      >
        <X aria-hidden="true" />
      </button>
    </div>
  );
}
