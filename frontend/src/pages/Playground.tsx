/* RAG Playground — ask questions, filter scope by document, see mode/cache/
   latency labels, citations with authorized-excerpt drawer, honest empty
   result and publication-fence states, plus the seeded before/after demo. */
import { useMemo, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Ban,
  BookOpenCheck,
  CircleHelp,
  Clock3,
  FlaskConical,
  MessageSquareText,
  Search,
  Send,
  X,
} from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { Citation, DocumentOut, RagQueryResponse } from '../api/types';
import { CacheBadge } from '../components/CacheBadge';
import { CitationList } from '../components/CitationList';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { useToast } from '../hooks/ToastProvider';
import { useTopbarAction } from '../hooks/useTopbarAction';
import { truncate } from '../lib/format';

const DEMO_QUESTION = 'When is the Nightingale phase 2 rollout scheduled?';

function modeLabel(mode: string): string {
  switch (mode) {
    case 'llm':
      return 'LLM — generative model configured';
    case 'extractive':
      return 'EXTRACTIVE — no generative model configured';
    case 'deterministic':
      return 'DETERMINISTIC — fixed rules, no model';
    default:
      return `${mode.toUpperCase()} — labeled mode`;
  }
}

function isInsufficient(answer: string, note: string | null): boolean {
  const hay = `${answer} ${note ?? ''}`.toUpperCase();
  return hay.includes('INSUFFICIENT_AUTHORIZED_EVIDENCE');
}

export function Playground() {
  const toast = useToast();
  const [question, setQuestion] = useState('');
  const [topK, setTopK] = useState(6);
  const [filterOpen, setFilterOpen] = useState(false);
  const [selectedDocs, setSelectedDocs] = useState<Map<string, string>>(new Map());
  const [result, setResult] = useState<RagQueryResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [askError, setAskError] = useState<ApiError | null>(null);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);

  const docsQuery = useQuery<DocumentOut[]>({
    queryKey: ['documents', 'playground-picker'],
    queryFn: () => api.get<DocumentOut[]>('/documents', { page: 1, page_size: 100 }),
  });
  const docs = docsQuery.data ?? [];

  useTopbarAction(
    useMemo(
      () => ({
        label: 'Ask a question',
        onClick: () => {
          document.getElementById('rag-question')?.focus();
        },
      }),
      [],
    ),
  );

  const ask = async (e?: FormEvent) => {
    e?.preventDefault();
    const q = question.trim();
    if (!q || pending) return;
    setPending(true);
    setAskError(null);
    setResult(null);
    try {
      const documentIds = selectedDocs.size > 0 ? [...selectedDocs.keys()] : undefined;
      const res = await api.post<RagQueryResponse>('/rag/query', {
        question: q,
        document_ids: documentIds,
        top_k: topK,
      });
      setResult(res);
    } catch (err) {
      if (err instanceof ApiError) {
        setAskError(err);
        if (err.status === 409) {
          toast.error('Publication blocked by the deletion fence', err.message);
        } else if (err.status !== 401) {
          toast.error('Query failed', err.message);
        }
      } else {
        setAskError(new ApiError(0, { code: 'network_error', message: 'Query failed.' }));
      }
    } finally {
      setPending(false);
    }
  };

  const insufficient = result ? isInsufficient(result.answer, result.answer_note) : false;
  const fenced = askError?.status === 409;

  return (
    <div className="stack">
      <header>
        <h1 className="page-title">RAG Playground</h1>
        <p className="page-sub" style={{ marginBottom: 0 }}>
          Ask against the registered corpus. Every answer is labeled with its
          mode and model, cites its retrieved chunks, and respects the deletion
          fence — removed evidence can never be republished.
        </p>
      </header>

      <div className="grid-2" style={{ gridTemplateColumns: 'minmax(0, 5fr) minmax(0, 7fr)' }}>
        {/* -------- ask panel -------- */}
        <section className="panel" aria-label="Ask a question">
          <div className="panel-head">
            <h3>
              <MessageSquareText aria-hidden="true" /> Question
            </h3>
          </div>
          <form onSubmit={(e) => void ask(e)}>
            <div className="field">
              <label htmlFor="rag-question">Your question</label>
              <textarea
                id="rag-question"
                className="input"
                rows={3}
                maxLength={2000}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={DEMO_QUESTION}
                disabled={pending}
              />
            </div>

            <div className="field">
              <label htmlFor="rag-topk">Top K retrieved chunks: {topK}</label>
              <input
                id="rag-topk"
                type="range"
                min={1}
                max={12}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                disabled={pending}
              />
            </div>

            <div className="field">
              <div className="row spread">
                <label id="doc-filter-label">Scope: {selectedDocs.size === 0 ? 'all documents' : `${selectedDocs.size} selected`}</label>
                <button
                  type="button"
                  className="btn btn-sm"
                  aria-expanded={filterOpen}
                  aria-controls="doc-filter-list"
                  onClick={() => setFilterOpen((v) => !v)}
                >
                  {filterOpen ? 'Hide' : 'Choose documents'}
                </button>
              </div>
              {filterOpen && (
                <div
                  id="doc-filter-list"
                  role="group"
                  aria-labelledby="doc-filter-label"
                  style={{
                    maxHeight: 240,
                    overflowY: 'auto',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: 6,
                    background: 'var(--inset)',
                  }}
                >
                  {docsQuery.isLoading ? (
                    <LoadingSkeleton variant="lines" rows={3} label="Loading documents" />
                  ) : docs.length === 0 ? (
                    <p className="tiny" style={{ padding: 8 }}>
                      No documents registered yet — queries will run over an
                      empty index.
                    </p>
                  ) : (
                    docs.map((d) => (
                      <label className="checkbox-row" key={d.id}>
                        <input
                          type="checkbox"
                          checked={selectedDocs.has(d.id)}
                          onChange={(e) => {
                            setSelectedDocs((prev) => {
                              const next = new Map(prev);
                              if (e.target.checked) next.set(d.id, d.title);
                              else next.delete(d.id);
                              return next;
                            });
                          }}
                        />
                        <span className="grow" style={{ minWidth: 0 }}>
                          <span className="truncate" style={{ display: 'block' }}>
                            {d.title}
                          </span>
                          <span className="tiny">{d.chunk_count} chunks</span>
                        </span>
                      </label>
                    ))
                  )}
                </div>
              )}
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-lg"
              style={{ width: '100%' }}
              disabled={pending || !question.trim()}
            >
              {pending ? (
                <>
                  <span className="spinner" aria-hidden="true" /> Retrieving & answering…
                </>
              ) : (
                <>
                  <Send aria-hidden="true" /> Ask
                </>
              )}
            </button>
          </form>

          {/* synthetic demo card */}
          <aside className="callout accent" style={{ marginTop: 18 }}>
            <FlaskConical aria-hidden="true" />
            <div className="callout-body grow">
              <div className="callout-title">Synthetic before/after deletion demo</div>
              <p style={{ marginBottom: 8 }}>
                With the seeded corpus: 1) ask the Nightingale question and note
                the cited answer; 2) delete{' '}
                <strong>“Project Nightingale Phase 2 Brief”</strong> in the
                Deletion Center; 3) re-ask — the fence blocks republication and
                the unique fact is gone, while shared facts survive via docB.
              </p>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => {
                  setQuestion(DEMO_QUESTION);
                  void ask();
                }}
                disabled={pending}
              >
                <Search aria-hidden="true" size={13} /> Ask “{truncate(DEMO_QUESTION, 34)}”
              </button>
            </div>
          </aside>
        </section>

        {/* -------- answer panel -------- */}
        <section aria-label="Answer" className="stack" style={{ gap: 14 }}>
          {pending && (
            <div className="panel">
              <LoadingSkeleton variant="lines" rows={3} label="Waiting for the answer" />
              <p className="tiny" style={{ marginTop: 10 }}>
                Retrieving authorized chunks, assembling the answer, registering
                the answer artifact…
              </p>
            </div>
          )}

          {!pending && fenced && askError && (
            <div className="callout danger" role="alert">
              <Ban aria-hidden="true" />
              <div className="callout-body">
                <div className="callout-title">Publication blocked (409 · publication_blocked)</div>
                <p>
                  {askError.message}
                </p>
                <p className="tiny" style={{ marginTop: 6 }}>
                  A deletion fence was committed before this answer could be
                  published — the question touches removed evidence.
                </p>
              </div>
            </div>
          )}

          {!pending && askError && !fenced && (
            <ErrorState
              error={askError}
              onRetry={() => void ask()}
              title="The query failed"
              hint="If the AI adapter or a connector is down, this usually clears once the backend recovers."
            />
          )}

          {!pending && !askError && !result && (
            <EmptyState
              icon={<CircleHelp aria-hidden="true" />}
              title="No question asked yet"
            >
              Ask anything about the stored corpus. Answers are assembled only
              from chunks you are authorized to see, in the scope you choose.
            </EmptyState>
          )}

          {result && insufficient && (
            <EmptyState
              tone="info"
              icon={<BookOpenCheck aria-hidden="true" />}
              title="No authorized evidence found"
            >
              {result.answer_note ??
                'Nothing in the declared scope answers this question. TraceVault refuses to invent content — try a broader question or a different scope.'}
            </EmptyState>
          )}

          {result && !insufficient && (
            <>
              <div className="answer-panel">
                <div className="meta-chip-row" style={{ marginBottom: 14 }}>
                  <span className="mode-chip">{modeLabel(result.mode)}</span>
                  <CacheBadge cacheHit={result.cache_hit} cacheType={result.cache_type} />
                  <span className="chip chip-neutral">
                    <Clock3 aria-hidden="true" /> {Math.round(result.latency_ms)} ms
                  </span>
                  <span className="chip chip-neutral">model: {result.model}</span>
                </div>
                <div className="answer-text">{result.answer}</div>
                {result.answer_note && !insufficient && (
                  <p className="tiny" style={{ marginTop: 12 }}>
                    Note: {result.answer_note}
                  </p>
                )}
              </div>

              <div className="panel">
                <div className="panel-head">
                  <h3>
                    <BookOpenCheck aria-hidden="true" /> Citations ({result.citations.length})
                  </h3>
                  <span className="tiny">click a citation for the authorized excerpt</span>
                </div>
                <CitationList
                  citations={result.citations}
                  onSelect={(c) => setActiveCitation(c)}
                />
              </div>
            </>
          )}
        </section>
      </div>

      {/* -------- citation excerpt drawer -------- */}
      {activeCitation && (
        <>
          <button
            type="button"
            className="drawer-backdrop"
            aria-label="Close excerpt"
            onClick={() => setActiveCitation(null)}
          />
          <aside
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label={`Authorized excerpt ${activeCitation.label}`}
          >
            <div className="drawer-head">
              <h3 className="row">
                <span className="chip chip-info">{activeCitation.label}</span>
                <span className="tiny">score {activeCitation.score.toFixed(3)}</span>
              </h3>
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={() => setActiveCitation(null)}
                aria-label="Close excerpt drawer"
              >
                <X aria-hidden="true" />
              </button>
            </div>
            <div className="drawer-body stack">
              <div className="excerpt">{activeCitation.snippet}</div>
              <p className="tiny">
                Authorized excerpt of chunk{' '}
                <span className="mono">{shortChunkId(activeCitation.chunk_artifact_id)}</span>{' '}
                — this is the full text the retrieval layer was allowed to use.
              </p>
            </div>
          </aside>
        </>
      )}
    </div>
  );
}

function shortChunkId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}
