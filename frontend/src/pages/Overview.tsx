/* Overview — hero, honest metric strip, mini provenance preview of the most
   recent document, recent operations, quick actions. No fabricated metrics. */
import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  Boxes,
  Database,
  FileText,
  HardDriveDownload,
  Layers,
  MessageSquareText,
  Network,
  Plus,
  ShieldAlert,
  Upload,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  AuditEventOut,
  DeletionRequestOut,
  DocumentOut,
  ProvenanceGraph,
} from '../api/types';
import { isTransitional } from '../api/types';
import { MetricCard } from '../components/MetricCard';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { ErrorState } from '../components/ErrorState';
import { EmptyState } from '../components/EmptyState';
import { GraphView } from '../components/GraphView';
import { StatusPill } from '../components/StatusPill';
import { useTopbarAction } from '../hooks/useTopbarAction';
import { timeAgo, shortId } from '../lib/format';

const PAGE_CAP = 100;

export function Overview() {
  const navigate = useNavigate();

  useTopbarAction(
    useMemo(
      () => ({
        label: 'Upload document',
        onClick: () => navigate('/documents?upload=1'),
      }),
      [navigate],
    ),
  );

  const documentsQuery = useQuery<DocumentOut[]>({
    queryKey: ['documents', 'overview'],
    queryFn: () => api.get<DocumentOut[]>('/documents', { page: 1, page_size: PAGE_CAP }),
  });
  const deletionsQuery = useQuery<DeletionRequestOut[]>({
    queryKey: ['deletion-requests', 'overview'],
    queryFn: () =>
      api.get<DeletionRequestOut[]>('/deletion-requests', { page: 1, page_size: PAGE_CAP }),
  });
  const auditQuery = useQuery<AuditEventOut[]>({
    queryKey: ['audit-events', 'overview'],
    queryFn: () => api.get<AuditEventOut[]>('/audit-events', { page: 1, page_size: 8 }),
  });

  const documents = documentsQuery.data ?? [];
  const deletions = deletionsQuery.data ?? [];
  const capped = documents.length >= PAGE_CAP;

  const newestDoc = documents[0] ?? null;

  const provenanceQuery = useQuery<ProvenanceGraph>({
    queryKey: ['provenance', 'overview', newestDoc?.id],
    queryFn: () =>
      api.get<ProvenanceGraph>('/provenance', {
        root: `document:${newestDoc!.id}`,
        direction: 'dependants',
        include_transitive: true,
        depth: 6,
      }),
    enabled: !!newestDoc,
  });

  const sums = useMemo(() => {
    const acc = { chunks: 0, summaries: 0, answers: 0, cache: 0, versions: 0 };
    for (const d of documents) {
      acc.chunks += d.chunk_count;
      acc.summaries += d.summary_count;
      acc.answers += d.answer_count;
      acc.cache += d.cache_count;
      acc.versions += d.version_count;
    }
    return acc;
  }, [documents]);

  const delStats = useMemo(() => {
    let inFlight = 0;
    let incomplete = 0;
    let failed = 0;
    let completed = 0;
    for (const r of deletions) {
      if (isTransitional(r.state)) inFlight += 1;
      else if (r.state === 'INCOMPLETE' || r.state === 'RETRY_PENDING') incomplete += 1;
      else if (r.state === 'FAILED') failed += 1;
      else if (r.state === 'COMPLETED') completed += 1;
    }
    return { inFlight, incomplete, failed, completed };
  }, [deletions]);

  const plusSuffix = capped ? '+' : '';
  const anyError =
    documentsQuery.isError || deletionsQuery.isError || auditQuery.isError;

  return (
    <div className="stack">
      <section className="hero">
        <h1>Control what your AI remembers.</h1>
        <p className="lede">
          TraceVault governs the <strong>stored artifacts</strong> of your RAG
          pipeline — documents, chunks, vectors, summaries, answers and cache
          entries — with provenance-aware deletion, a publication fence and
          recorded verification. It controls what remains retrievable, not the
          weights of any model.
        </p>
        <span className="scope-note">
          <ShieldAlert aria-hidden="true" />
          Research prototype · guarantees limited to registered components —
          see Settings &amp; About
        </span>
        <div className="row wrap" style={{ marginTop: 20, gap: 10 }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate('/documents?upload=1')}
          >
            <Upload aria-hidden="true" /> Upload a document
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => navigate('/playground')}
          >
            <MessageSquareText aria-hidden="true" /> Run a demo query
          </button>
        </div>
      </section>

      {anyError ? (
        <ErrorState
          error={documentsQuery.isError ? documentsQuery.error : deletionsQuery.isError ? deletionsQuery.error : auditQuery.error}
          onRetry={() => {
            void documentsQuery.refetch();
            void deletionsQuery.refetch();
            void auditQuery.refetch();
          }}
          title="Live counts are unavailable"
          hint="The API may be down or your session may have expired."
        />
      ) : documentsQuery.isLoading || deletionsQuery.isLoading ? (
        <LoadingSkeleton variant="stats" rows={5} label="Loading live counts" />
      ) : (
        <section aria-label="Live counts">
          <div className="metric-strip">
            <MetricCard
              label="Documents"
              value={`${documents.length}${plusSuffix}`}
              sub={`${sums.versions}${plusSuffix} versions registered`}
              icon={<FileText aria-hidden="true" />}
              tone="info"
            />
            <MetricCard
              label="Chunks"
              value={`${sums.chunks}${plusSuffix}`}
              sub="retrievable text segments"
              icon={<Layers aria-hidden="true" />}
              tone="violet"
            />
            <MetricCard
              label="Summaries"
              value={`${sums.summaries}${plusSuffix}`}
              sub="registered claim summaries"
              icon={<Boxes aria-hidden="true" />}
              tone="accent"
            />
            <MetricCard
              label="Answers + cache"
              value={`${sums.answers}${plusSuffix} / ${sums.cache}${plusSuffix}`}
              sub="published answers / cache entries"
              icon={<Database aria-hidden="true" />}
            />
            <MetricCard
              label="Deletions in flight"
              value={delStats.inFlight}
              sub={
                delStats.inFlight > 0
                  ? 'polling every 2s in Deletion Center'
                  : `${delStats.completed} completed · ${delStats.incomplete} incomplete · ${delStats.failed} failed`
              }
              icon={<ShieldAlert aria-hidden="true" />}
              tone={
                delStats.inFlight > 0
                  ? 'info'
                  : delStats.incomplete + delStats.failed > 0
                    ? 'warning'
                    : undefined
              }
            />
          </div>
          {capped && (
            <p className="tiny" style={{ marginTop: 8 }}>
              Counts include the first {PAGE_CAP} documents — refine with search
              in Documents for exact totals beyond that.
            </p>
          )}
        </section>
      )}

      <div className="grid-2">
        <section className="panel panel-flat" aria-label="Provenance preview">
          <div className="panel-head" style={{ padding: '18px 20px 0' }}>
            <h3>
              <Network aria-hidden="true" /> Provenance preview
            </h3>
            {newestDoc && (
              <Link
                to={`/provenance?root=document:${newestDoc.id}`}
                className="row tiny"
                style={{ gap: 4 }}
              >
                Explore full graph <ArrowRight size={12} aria-hidden="true" />
              </Link>
            )}
          </div>
          <div style={{ padding: '12px 14px 14px' }}>
            {!newestDoc && !documentsQuery.isLoading ? (
              <EmptyState
                icon={<Upload aria-hidden="true" />}
                title="No documents yet"
                actions={
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => navigate('/documents?upload=1')}
                  >
                    <Plus aria-hidden="true" /> Upload the first document
                  </button>
                }
              >
                Upload a document to ingest chunks, build summaries and grow the
                provenance graph.
              </EmptyState>
            ) : documentsQuery.isLoading || !newestDoc ? (
              <LoadingSkeleton variant="panel" label="Loading provenance preview" />
            ) : provenanceQuery.isError ? (
              <ErrorState
                error={provenanceQuery.error}
                onRetry={() => void provenanceQuery.refetch()}
                title="Provenance preview unavailable"
                hint={
                  newestDoc
                    ? `Could not load the graph for “${newestDoc.title}”.`
                    : undefined
                }
              />
            ) : provenanceQuery.isLoading ? (
              <LoadingSkeleton variant="panel" label="Loading graph" />
            ) : (
              <>
                <p className="tiny" style={{ marginBottom: 10 }}>
                  Most recent document:{' '}
                  <Link to={`/documents/${newestDoc.id}`}>{newestDoc.title}</Link>{' '}
                  — {provenanceQuery.data?.nodes.length ?? 0} artifacts,{' '}
                  {provenanceQuery.data?.edges.length ?? 0} recorded edges.
                </p>
                <GraphView
                  mini
                  withLegend={false}
                  height={240}
                  rootId={provenanceQuery.data?.nodes[0]?.id ?? null}
                  nodes={provenanceQuery.data?.nodes ?? []}
                  edges={provenanceQuery.data?.edges ?? []}
                />
              </>
            )}
          </div>
        </section>

        <section className="panel" aria-label="Recent operations">
          <div className="panel-head">
            <h3>
              <HardDriveDownload aria-hidden="true" /> Recent operations
            </h3>
            <Link to="/audit" className="row tiny" style={{ gap: 4 }}>
              Open audit log <ArrowRight size={12} aria-hidden="true" />
            </Link>
          </div>
          {auditQuery.isLoading ? (
            <LoadingSkeleton variant="table" rows={5} label="Loading audit events" />
          ) : auditQuery.isError ? (
            <ErrorState
              error={auditQuery.error}
              onRetry={() => void auditQuery.refetch()}
              title="Audit events unavailable"
            />
          ) : (auditQuery.data ?? []).length === 0 ? (
            <EmptyState
              icon={<HardDriveDownload aria-hidden="true" />}
              title="No operations recorded yet"
            >
              Ingestion, deletion and repair operations will appear here with
              redacted payload keys.
            </EmptyState>
          ) : (
            <div className="list-tight">
              {(auditQuery.data ?? []).map((e) => (
                <div className="list-item" key={e.id}>
                  <StatusPill
                    status={e.type.includes('deletion')
                      ? 'removed'
                      : e.type.includes('document')
                        ? 'active'
                        : e.type.includes('repair')
                          ? 'done'
                          : 'queued'}
                    label={e.type}
                  />
                  <span className="grow" style={{ minWidth: 0 }}>
                    <span className="tiny" style={{ display: 'block' }}>
                      by {e.actor}
                      {e.deletion_request_id
                        ? ` · request ${shortId(e.deletion_request_id, 8)}`
                        : ''}
                    </span>
                  </span>
                  <span className="tiny num">{timeAgo(e.created_at)}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
