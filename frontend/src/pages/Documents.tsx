/* Documents — searchable, filterable, paginated table + upload dialog
   (file drag-drop or pasted text; honest 415/422 validation messages). */
import { useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  Loader2,
  Search,
  Upload,
  X,
} from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { DocumentOut } from '../api/types';
import { StateBadge } from '../components/StateBadge';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { ConfirmUploadDialog } from '../components/UploadDialog';
import { useTopbarAction } from '../hooks/useTopbarAction';
import { formatShortTime } from '../lib/format';

const PAGE_SIZE = 20;
const DOC_STATES = ['active', 'pending_deletion', 'deleted'];

export function Documents() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const q = params.get('q') ?? '';
  const state = params.get('state') ?? '';
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1);
  const uploadOpen = params.get('upload') === '1';

  const [searchDraft, setSearchDraft] = useState(q);
  useEffect(() => setSearchDraft(q), [q]);

  const query = useQuery<DocumentOut[]>({
    queryKey: ['documents', { q, state, page }],
    queryFn: () =>
      api.get<DocumentOut[]>('/documents', {
        q: q || undefined,
        state: state || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  const setParam = (key: string, value: string) => {
    const nextParams = new URLSearchParams(params);
    if (value) nextParams.set(key, value);
    else nextParams.delete(key);
    if (key !== 'page') nextParams.delete('page');
    setParams(nextParams, { replace: true });
  };

  const rows = query.data ?? [];
  const hasPrev = page > 1;
  const hasNext = rows.length === PAGE_SIZE;

  useTopbarAction(
    useMemo(
      () => ({
        label: 'Upload document',
        onClick: () => setParam('upload', '1'),
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }),
      [params],
    ),
  );

  const closeUpload = () => setParam('upload', '');

  return (
    <div className="stack">
      <header>
        <h1 className="page-title">Documents</h1>
        <p className="page-sub" style={{ marginBottom: 0 }}>
          Every document registered in this workspace, with its artifact counts
          and lifecycle state. Upload accepts .txt, .md and text-based .pdf.
        </p>
      </header>

      <div className="filter-bar" role="search">
        <form
          className="field"
          style={{ maxWidth: 360 }}
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            setParam('q', searchDraft.trim());
          }}
        >
          <label htmlFor="doc-search">Search by title</label>
          <div className="row" style={{ gap: 8 }}>
            <input
              id="doc-search"
              className="input"
              placeholder="e.g. Nightingale"
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.target.value)}
              style={{ flex: 1 }}
            />
            <button type="submit" className="btn" aria-label="Search documents">
              <Search aria-hidden="true" size={16} />
            </button>
          </div>
        </form>
        <div className="field" style={{ maxWidth: 220 }}>
          <label htmlFor="doc-state">Lifecycle state</label>
          <select
            id="doc-state"
            className="select"
            value={state}
            onChange={(e) => setParam('state', e.target.value)}
          >
            <option value="">All states</option>
            {DOC_STATES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
        </div>
        {(q || state) && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => setParams(new URLSearchParams(), { replace: true })}
          >
            <X aria-hidden="true" size={15} /> Clear filters
          </button>
        )}
      </div>

      <section className="panel panel-flat" aria-label="Documents table">
        {query.isLoading ? (
          <div style={{ padding: 20 }}>
            <LoadingSkeleton variant="table" rows={6} label="Loading documents" />
          </div>
        ) : query.isError ? (
          <div style={{ padding: 20 }}>
            <ErrorState
              error={query.error}
              onRetry={() => void query.refetch()}
              title="Documents could not be loaded"
            />
          </div>
        ) : rows.length === 0 ? (
          <div style={{ padding: 20 }}>
            <EmptyState
              icon={<FileText aria-hidden="true" />}
              title={q || state ? 'No documents match these filters' : 'No documents yet'}
              actions={
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => setParam('upload', '1')}
                >
                  <Upload aria-hidden="true" /> Upload a document
                </button>
              }
            >
              {q || state
                ? 'Try a different search term or clear the filters.'
                : 'Upload a .txt, .md or text-based .pdf file to start building provenance-tracked artifacts.'}
            </EmptyState>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data">
              <caption className="visually-hidden">
                Documents with lifecycle state, artifact counts and last update
              </caption>
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">State</th>
                  <th scope="col" className="num">
                    Chunks
                  </th>
                  <th scope="col" className="num">
                    Summaries
                  </th>
                  <th scope="col" className="num">
                    Answers
                  </th>
                  <th scope="col" className="num">
                    Cache
                  </th>
                  <th scope="col">Updated</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((d) => (
                  <tr
                    key={d.id}
                    className="clickable"
                    tabIndex={0}
                    onClick={() => navigate(`/documents/${d.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') navigate(`/documents/${d.id}`);
                    }}
                    aria-label={`Open document ${d.title}`}
                  >
                    <td>
                      <div className="cell-title truncate">{d.title}</div>
                      <div className="cell-sub mono">{d.id.slice(0, 8)}…</div>
                    </td>
                    <td>
                      <StateBadge state={d.state} />
                    </td>
                    <td className="num">{d.chunk_count}</td>
                    <td className="num">{d.summary_count}</td>
                    <td className="num">{d.answer_count}</td>
                    <td className="num">{d.cache_count}</td>
                    <td className="num">{formatShortTime(d.updated_at)}</td>
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
              {rows.length === PAGE_SIZE ? ` (≥ ${(page - 1) * PAGE_SIZE + 1})` : ''}
            </span>
            <button
              type="button"
              className="btn btn-sm"
              disabled={!hasPrev}
              onClick={() => setParam('page', String(page - 1))}
            >
              <ChevronLeft aria-hidden="true" size={15} /> Prev
            </button>
            <button
              type="button"
              className="btn btn-sm"
              disabled={!hasNext}
              onClick={() => setParam('page', String(page + 1))}
            >
              Next <ChevronRight aria-hidden="true" size={15} />
            </button>
          </div>
        )}
      </section>

      <ConfirmUploadDialog open={uploadOpen} onClose={closeUpload} />
    </div>
  );
}

/* Exposed for tests and reuse: derive next-page availability. */
export function canGoNext(rows: number, pageSize: number): boolean {
  return rows === pageSize;
}

/* Thin wrapper kept for the toolbar button used by Overview quick actions. */
export function UploadButton({ onClick }: { onClick?: () => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  return (
    <button ref={ref} type="button" className="btn btn-primary" onClick={onClick}>
      <Loader2 aria-hidden="true" style={{ display: 'none' }} />
      <Upload aria-hidden="true" /> Upload document
    </button>
  );
}

/* re-export for tests */
export { DOC_STATES };

/* helper used by UploadDialog to surface 415/422 messages */
export function uploadErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 415) return err.message;
    if (err.status === 422) return `Validation failed: ${err.message}`;
    return err.message;
  }
  return 'Upload failed unexpectedly.';
}

export type { ChangeEvent, DragEvent };
