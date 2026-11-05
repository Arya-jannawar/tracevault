/* Verification & Audit — filterable event log. Payload keys only (the server
   already redacts payload values). Exports live in DeletionDetail. */
import { useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Filter, ListChecks } from 'lucide-react';
import { api } from '../api/client';
import type { AuditEventOut } from '../api/types';
import { StatusPill } from '../components/StatusPill';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { formatDateTime, shortId } from '../lib/format';

const PAGE_SIZE = 50;

export function Audit() {
  const [params, setParams] = useSearchParams();
  const [draft, setDraft] = useState({
    operation: params.get('operation') ?? '',
    target_id: params.get('target_id') ?? '',
    from_date: params.get('from_date') ?? '',
    to_date: params.get('to_date') ?? '',
  });
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1);

  const get = (k: string) => params.get(k) ?? '';
  const hasFilters =
    get('operation') || get('target_id') || get('from_date') || get('to_date');

  const query = useQuery<AuditEventOut[]>({
    queryKey: [
      'audit-events',
      {
        operation: get('operation'),
        target_id: get('target_id'),
        from_date: get('from_date'),
        to_date: get('to_date'),
        page,
      },
    ],
    queryFn: () =>
      api.get<AuditEventOut[]>('/audit-events', {
        operation: get('operation') || undefined,
        target_id: get('target_id') || undefined,
        from_date: get('from_date')
          ? new Date(`${get('from_date')}T00:00:00Z`).toISOString()
          : undefined,
        to_date: get('to_date')
          ? new Date(`${get('to_date')}T23:59:59Z`).toISOString()
          : undefined,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  const apply = (e: FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams();
    if (draft.operation.trim()) next.set('operation', draft.operation.trim());
    if (draft.target_id.trim()) next.set('target_id', draft.target_id.trim());
    if (draft.from_date) next.set('from_date', draft.from_date);
    if (draft.to_date) next.set('to_date', draft.to_date);
    setParams(next, { replace: true });
  };

  const rows = query.data ?? [];

  return (
    <div className="stack">
      <header>
        <h1 className="page-title">Verification &amp; Audit</h1>
        <p className="page-sub" style={{ marginBottom: 0 }}>
          Append-only operational history. Payloads are redacted server-side —
          the console shows which keys were recorded, never their values.
        </p>
      </header>

      <form className="filter-bar" role="search" onSubmit={apply}>
        <div className="field">
          <label htmlFor="audit-operation">Operation prefix</label>
          <input
            id="audit-operation"
            className="input"
            placeholder="e.g. deletion"
            value={draft.operation}
            onChange={(e) => setDraft({ ...draft, operation: e.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="audit-target">Target id (deletion request)</label>
          <input
            id="audit-target"
            className="input mono"
            placeholder="uuid…"
            value={draft.target_id}
            onChange={(e) => setDraft({ ...draft, target_id: e.target.value })}
          />
        </div>
        <div className="field" style={{ maxWidth: 180 }}>
          <label htmlFor="audit-from">From date</label>
          <input
            id="audit-from"
            type="date"
            className="input"
            value={draft.from_date}
            onChange={(e) => setDraft({ ...draft, from_date: e.target.value })}
          />
        </div>
        <div className="field" style={{ maxWidth: 180 }}>
          <label htmlFor="audit-to">To date</label>
          <input
            id="audit-to"
            type="date"
            className="input"
            value={draft.to_date}
            onChange={(e) => setDraft({ ...draft, to_date: e.target.value })}
          />
        </div>
        <button type="submit" className="btn">
          <Filter aria-hidden="true" size={15} /> Apply
        </button>
        {hasFilters ? (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              setDraft({ operation: '', target_id: '', from_date: '', to_date: '' });
              setParams(new URLSearchParams(), { replace: true });
            }}
          >
            Clear
          </button>
        ) : null}
      </form>

      <section className="panel panel-flat" aria-label="Audit events">
        {query.isLoading ? (
          <div style={{ padding: 20 }}>
            <LoadingSkeleton variant="table" rows={6} label="Loading audit events" />
          </div>
        ) : query.isError ? (
          <div style={{ padding: 20 }}>
            <ErrorState
              error={query.error}
              onRetry={() => void query.refetch()}
              title="Audit events could not be loaded"
            />
          </div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 20 }}>
            <EmptyState
              icon={<ListChecks aria-hidden="true" />}
              title={hasFilters ? 'No events match these filters' : 'No audit events yet'}
            >
              {hasFilters
                ? 'Loosen the operation prefix or widen the date range.'
                : 'Operations (ingest, deletion, repair, evaluation) will be recorded here as they happen.'}
            </EmptyState>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data">
              <caption className="visually-hidden">Audit events</caption>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Type</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Deletion request</th>
                  <th scope="col">Payload keys</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id}>
                    <td className="num" style={{ whiteSpace: 'nowrap' }}>
                      {formatDateTime(e.created_at)}
                    </td>
                    <td>
                      <StatusPill status={eventTone(e.type)} label={e.type} />
                    </td>
                    <td>{e.actor}</td>
                    <td className="mono tiny">
                      {e.deletion_request_id ? (
                        <a href={`/deletions/${e.deletion_request_id}`}>
                          {shortId(e.deletion_request_id, 8)}…
                        </a>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      {Object.keys(e.payload ?? {}).length > 0 ? (
                        <span className="tiny mono">
                          {Object.keys(e.payload).join(', ')}
                        </span>
                      ) : (
                        <span className="tiny">—</span>
                      )}
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
              onClick={() => {
                const next = new URLSearchParams(params);
                next.set('page', String(page - 1));
                setParams(next, { replace: true });
              }}
            >
              <ChevronLeft aria-hidden="true" size={15} /> Prev
            </button>
            <button
              type="button"
              className="btn btn-sm"
              disabled={rows.length < PAGE_SIZE}
              onClick={() => {
                const next = new URLSearchParams(params);
                next.set('page', String(page + 1));
                setParams(next, { replace: true });
              }}
            >
              Next <ChevronRight aria-hidden="true" size={15} />
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

function eventTone(type: string): string {
  if (type.includes('deletion.completed')) return 'done';
  if (type.includes('deletion.failed') || type.includes('deletion.incomplete')) return 'removed';
  if (type.startsWith('deletion')) return 'pending_deletion';
  if (type.includes('repair')) return 'done';
  if (type.includes('document')) return 'active';
  return 'queued';
}
