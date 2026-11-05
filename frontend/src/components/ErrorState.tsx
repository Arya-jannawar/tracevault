/* Error state with retry. Shows the contract's error envelope fields
   (code, message, request_id) when available — a research tool should show
   its receipts. */
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { ApiError } from '../api/client';

export function ErrorState({
  error,
  onRetry,
  title = 'Something went wrong',
  hint,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  hint?: string;
}) {
  const isApi = error instanceof ApiError;
  const message = isApi
    ? error.message
    : error instanceof Error
      ? error.message
      : 'Unexpected error.';
  const code = isApi ? error.code : null;
  const requestId = isApi ? error.requestId : null;
  const gloss = isApi ? error.gloss : null;

  return (
    <div className="state-block tone-danger" role="alert">
      <div className="state-icon" aria-hidden="true">
        <AlertTriangle />
      </div>
      <h3>{title}</h3>
      <p>
        {message}
        {gloss && gloss !== message ? ` — ${gloss}` : ''}
      </p>
      {hint ? <p className="tiny">{hint}</p> : null}
      {(code || requestId) && (
        <p className="tiny mono">
          {code ? `code: ${code}` : ''}
          {requestId ? ` · request_id: ${requestId}` : ''}
        </p>
      )}
      {onRetry ? (
        <div className="state-actions">
          <button type="button" className="btn" onClick={onRetry}>
            <RefreshCw aria-hidden="true" /> Retry
          </button>
        </div>
      ) : null}
    </div>
  );
}
