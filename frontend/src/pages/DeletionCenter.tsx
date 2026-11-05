/* Deletion Center — every request with state badge, attempts, elapsed time.
   Active (transitional) rows poll every 2s; the list refreshes slowly otherwise. */
import { useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ShieldAlert } from 'lucide-react';
import { api } from '../api/client';
import type { DeletionRequestOut } from '../api/types';
import { isTransitional } from '../api/types';
import { StateBadge } from '../components/StateBadge';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { useTopbarAction } from '../hooks/useTopbarAction';
import { formatElapsed, formatShortTime, shortId } from '../lib/format';

const PAGE_SIZE = 20;
const STATUS_FILTERS = [
  '',
  'ACCEPTED',
  'COMPLETED',
  'INCOMPLETE',
  'RETRY_PENDING',
  'FAILED',
] as const;

export function DeletionCenter() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = params.get('status') ?? '';
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1);

  useTopbarAction(
    useMemo(
      () => ({
        label: 'How deletions work',
        onClick: () => navigate('/settings'),
      }),
      [navigate],
    ),
  );

  const query = useQuery<DeletionRequestOut[]>({
    queryKey: ['deletion-requests', { status, page }],
    queryFn: () =>
      api.get<DeletionRequestOut[]>('/deletion-requests', {
        status: status || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    // Transitional rows poll every 2s (react-query cleans up on unmount);
    // a settled list is fine at 15s.
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => isTransitional(r.state)) ? 2000 : 15000,
  });

  const rows = query.data ?? [];
  const anyActive = rows.some((r) => isTransitional(r.state));

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== 'page') next.delete('page');
    setParams(next, { replace: true });
  };

  return (
    <div className="stack">
      <header>
        <h1 className="page-title">Deletion Center</h1>
        <p className="page-sub" style={{ marginBottom: 0 }}>
          Each deletion is a fenced, five-step protocol: fence → discover →
          invalidate → remove → verify. INCOMPLETE requests kept guarantees
          partially applied and can be retried.
        </p>
      </header>

      <div className="filter-bar">
        <div className="field" style={{ maxWidth: 240 }}>
          <label htmlFor="del-status">State filter</label>
          <select
            id="del-status"
            className="select"
            value={status}
            onChange={(e) => setParam('status', e.target.value)}
          >
            {STATUS_FILTERS.map((s) => (
              <option key={s} value={s}>
                {s === '' ? 'All states' : s.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
        </div>
        {anyActive && (
          <span className="chip chip-info pulse" style={{ alignSelf: 'center' }}>
            <span className="dot" aria-hidden="true" /> live — polling every 2s
          </span>
        )}
      </div>

      <section className="panel panel-flat" aria-label="Deletion requests">
        {query.isLoading ? (
          <div style={{ padding: 20 }}>
            <LoadingSkeleton variant="table" rows={5} label="Loading deletion requests" />
          </div>
        ) : query.isError ? (
          <div style={{ padding: 20 }}>
            <ErrorState
              error={query.error}
              onRetry={() => void query.refetch()}
              title="Deletion requests could not be loaded"
            />
          </div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 20 }}>
            <EmptyState
              icon={<ShieldAlert aria-hidden="true" />}
              title={status ? `No requests in state ${status}` : 'No deletion requests yet'}
            >
              Start one from any document: open it and press “Delete document”.
              Deletion is the product — this center tracks every step and every
              connector acknowledgement.
            </EmptyState>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data">
              <caption className="visually-hidden">
                Deletion requests with state, attempts and elapsed time
              </caption>
              <thead>
                <tr>
                  <th scope="col">Request</th>
                  <th scope="col">Target document</th>
                  <th scope="col">State</th>
                  <th scope="col" className="num">
                    Attempts
                  </th>
                  <th scope="col">Accepted</th>
                  <th scope="col" className="num">
                    Elapsed
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    className="clickable"
                    tabIndex={0}
                    onClick={() => navigate(`/deletions/${r.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') navigate(`/deletions/${r.id}`);
                    }}
                    aria-label={`Open deletion request ${shortId(r.id, 8)}`}
                  >
                    <td>
                      <div className="cell-title mono">{shortId(r.id, 8)}…</div>
                      <div className="cell-sub">
                        fence epoch {r.fence_epoch}
                        {r.repair_enabled ? ' · repair enabled' : ''}
                      </div>
                    </td>
                    <td className="mono tiny">{shortId(r.document_id, 10)}…</td>
                    <td>
                      <StateBadge state={r.state} />
                      {r.failure_reason && (
                        <div className="cell-sub" style={{ maxWidth: 240 }}>
                          {r.failure_reason}
                        </div>
                      )}
                    </td>
                    <td className="num">{r.report ? countAttempts(r) : '—'}</td>
                    <td className="num">{formatShortTime(r.accepted_at)}</td>
                    <td className="num">
                      {formatElapsed(r.started_at ?? r.accepted_at, r.finished_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {rows.length > 0 && (
          <div className="pagination" style={{ padding: '12px 16px' }}>
            <span className="page-ind num">
              Page {page} · {rows.length} shown
            </span>
            <button
              type="button"
              className="btn btn-sm"
              disabled={page <= 1}
              onClick={() => setParam('page', String(page - 1))}
            >
              <ChevronLeft aria-hidden="true" size={15} /> Prev
            </button>
            <button
              type="button"
              className="btn btn-sm"
              disabled={rows.length < PAGE_SIZE}
              onClick={() => setParam('page', String(page + 1))}
            >
              Next <ChevronRight aria-hidden="true" size={15} />
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

function countAttempts(r: DeletionRequestOut): string {
  return String((r.report as { attempts?: number } | null)?.attempts ?? '—');
}
