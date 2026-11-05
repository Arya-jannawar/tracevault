/* DocumentDetail — content (honest 410 state), chunks with redaction,
   versions, artifact summary, deletion-impact preview + fenced delete flow. */
import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Ban,
  Clock,
  FileText,
  Layers,
  Network,
  ScrollText,
  ShieldAlert,
  Trash2,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  Capabilities,
  ChunkOut,
  DeletionImpact,
  DeletionRequestOut,
  DocumentDetail as DocumentDetailData,
  DocumentVersionOut,
} from '../api/types';
import { StateBadge } from '../components/StateBadge';
import { StatusPill } from '../components/StatusPill';
import { MetricCard } from '../components/MetricCard';
import { Tabs } from '../components/Tabs';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ImpactPreview } from '../components/ImpactPreview';
import { useToast } from '../hooks/ToastProvider';
import { useTopbarAction } from '../hooks/useTopbarAction';
import { formatDateTime, shortId } from '../lib/format';

type TabId = 'content' | 'chunks' | 'versions' | 'artifacts' | 'impact';

export function DocumentDetail() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<TabId>('content');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deletePending, setDeletePending] = useState(false);

  const detailQuery = useQuery<DocumentDetailData>({
    queryKey: ['document', id],
    queryFn: () => api.get<DocumentDetailData>(`/documents/${id}`),
    // while ingestion is still pending, refresh so the UI comes alive
    refetchInterval: (q) => (q.state.data && q.state.data.chunk_count === 0 ? 3000 : false),
  });

  const impactQuery = useQuery<DeletionImpact>({
    queryKey: ['deletion-impact', id],
    queryFn: () => api.get<DeletionImpact>(`/documents/${id}/deletion-impact`),
    enabled: !!id,
  });

  const capsQuery = useQuery<Capabilities>({
    queryKey: ['capabilities'],
    queryFn: () => api.get<Capabilities>('/system/capabilities'),
    staleTime: 60_000,
  });
  const pendingJobs = capsQuery.data?.flags?.pending_jobs ?? 0;

  const detail = detailQuery.data;
  const impact = impactQuery.data;

  useTopbarAction(
    useMemo(
      () => ({
        label: 'Preview deletion impact',
        onClick: () => setTab('impact'),
      }),
      [],
    ),
  );

  const performDelete = async () => {
    setDeletePending(true);
    try {
      const req = await api.del<DeletionRequestOut>(`/documents/${id}`);
      toast.success(
        'Deletion request accepted',
        `Request ${shortId(req.id, 8)} fenced the document — follow it in the Deletion Center.`,
      );
      void queryClient.invalidateQueries({ queryKey: ['documents'] });
      void queryClient.invalidateQueries({ queryKey: ['deletion-requests'] });
      navigate(`/deletions/${req.id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Deletion failed.';
      toast.error('Could not start deletion', message);
      setConfirmOpen(false);
    } finally {
      setDeletePending(false);
    }
  };

  if (detailQuery.isLoading) {
    return (
      <div className="stack">
        <LoadingSkeleton variant="lines" rows={2} />
        <LoadingSkeleton variant="panel" />
      </div>
    );
  }

  if (detailQuery.isError || !detail) {
    return (
      <ErrorState
        error={detailQuery.error}
        onRetry={() => void detailQuery.refetch()}
        title="Document could not be loaded"
        hint="It may have been deleted, or the id may be malformed."
      />
    );
  }

  const ingestionPending = detail.chunk_count === 0;

  return (
    <div className="stack">
      <div>
        <Link to="/documents" className="row tiny" style={{ gap: 5, marginBottom: 10 }}>
          <ArrowLeft size={13} aria-hidden="true" /> All documents
        </Link>
        <div className="row wrap spread">
          <div className="grow" style={{ minWidth: 240 }}>
            <h1 className="page-title" style={{ marginBottom: 6 }}>
              {detail.title}
            </h1>
            <div className="row wrap" style={{ gap: 10 }}>
              <StateBadge state={detail.state} />
              <span className="tiny mono">{detail.id}</span>
              <span className="tiny">
                created {formatDateTime(detail.created_at)} · updated{' '}
                {formatDateTime(detail.updated_at)}
              </span>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => setConfirmOpen(true)}
            disabled={deletePending}
          >
            <Trash2 aria-hidden="true" /> Delete document
          </button>
        </div>
        {detail.coverage_notes.length > 0 && (
          <div className="callout warning" style={{ marginTop: 14 }}>
            <ShieldAlert aria-hidden="true" />
            <div className="callout-body">
              {detail.coverage_notes.map((n, i) => (
                <div key={i}>{n}</div>
              ))}
            </div>
          </div>
        )}
      </div>

      <Tabs<TabId>
        tabs={[
          { id: 'content', label: 'Content' },
          { id: 'chunks', label: 'Chunks', count: detail.chunk_count },
          { id: 'versions', label: 'Versions', count: detail.version_count },
          { id: 'artifacts', label: 'Artifacts' },
          { id: 'impact', label: 'Deletion impact' },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === 'content' && <ContentTab documentId={id} title={detail.title} />}
      {tab === 'chunks' && (
        <ChunksTab documentId={id} ingestionPending={ingestionPending} pendingJobs={pendingJobs} />
      )}
      {tab === 'versions' && <VersionsTab documentId={id} />}
      {tab === 'artifacts' && (
        <section className="stack" id="panel-artifacts" role="tabpanel" aria-label="Artifacts">
          <div className="metric-strip">
            <MetricCard label="Versions" value={detail.version_count} tone="info" />
            <MetricCard label="Chunks" value={detail.chunk_count} tone="violet" />
            <MetricCard label="Summaries" value={detail.summary_count} tone="accent" />
            <MetricCard label="Answers" value={detail.answer_count} />
            <MetricCard label="Cache entries" value={detail.cache_count} tone="danger" />
          </div>
          {ingestionPending && (
            <div className="callout info">
              <Clock aria-hidden="true" />
              <div className="callout-body">
                <div className="callout-title">Ingestion in progress</div>
                No chunks registered yet. The pipeline is still working
                {pendingJobs > 0 ? ` — ${pendingJobs} job(s) queued or running` : ''} —
                this view refreshes automatically until artifacts appear.
              </div>
            </div>
          )}
          <div className="panel">
            <div className="panel-head">
              <h3>
                <Network aria-hidden="true" /> Lineage
              </h3>
            </div>
            <p className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
              See every chunk, summary, answer and cache entry derived from this
              document, with per-node provenance status.
            </p>
            <Link className="btn" to={`/provenance?root=document:${detail.id}`}>
              Open in Provenance Explorer
            </Link>
          </div>
        </section>
      )}

      {tab === 'impact' && (
        <section
          className="panel"
          id="panel-impact"
          role="tabpanel"
          aria-label="Deletion impact preview"
        >
          <div className="panel-head">
            <h3>
              <ShieldAlert aria-hidden="true" /> Deletion impact preview
            </h3>
            <span className="tiny">GET /documents/{shortId(id, 8)}…/deletion-impact</span>
          </div>
          {impactQuery.isLoading ? (
            <LoadingSkeleton variant="lines" rows={4} label="Loading impact preview" />
          ) : impactQuery.isError || !impact ? (
            <ErrorState
              error={impactQuery.error}
              onRetry={() => void impactQuery.refetch()}
              title="Impact preview unavailable"
              hint="The document may already be fenced by an active deletion request."
            />
          ) : (
            <ImpactPreview impact={impact} />
          )}
        </section>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="Delete this document?"
        confirmLabel="Delete document"
        pending={deletePending}
        onConfirm={() => void performDelete()}
        onCancel={() => setConfirmOpen(false)}
      >
        <p style={{ marginBottom: 12 }}>
          You are about to delete{' '}
          <strong>“{detail.title}”</strong> ({shortId(detail.id, 8)}…). This
          fences the document and runs the five-step deletion protocol across
          every derived artifact.
        </p>
        {impact ? (
          <div className="list-tight" style={{ marginBottom: 12 }}>
            {Object.entries(impact.affected_by_type)
              .filter(([, n]) => n > 0)
              .map(([type, n]) => (
                <div className="list-item" key={type}>
                  <span className="chip chip-info">{type.replace(/_/g, ' ')}</span>
                  <span className="num">{n}</span>
                </div>
              ))}
            <div className="list-item">
              <span className="chip chip-danger">total affected</span>
              <span className="num">{impact.affected_count}</span>
            </div>
          </div>
        ) : (
          <p className="tiny" style={{ marginBottom: 12 }}>
            Affected-artifact counts are still loading — the deletion previews
            them again server-side before anything is removed.
          </p>
        )}
        <p className="tiny">
          Chunk text and derived artifacts will be invalidated; verification
          checks run afterwards. This action cannot be undone from the console.
        </p>
      </ConfirmDialog>
    </div>
  );
}

/* ---------------- tabs ---------------- */

function ContentTab({ documentId, title }: { documentId: string; title: string }) {
  const query = useQuery<{ document_id: string; title: string; content: string }>({
    queryKey: ['document-content', documentId],
    queryFn: () => api.get(`/documents/${documentId}/content`),
    retry: false, // 410 content_blocked is a *result*, not a failure to retry
  });

  if (query.isLoading) {
    return <LoadingSkeleton variant="lines" rows={8} label="Loading content" />;
  }

  if (query.isError) {
    const status = (query.error as { status?: number }).status;
    if (status === 410) {
      return (
        <EmptyState
          tone="danger"
          icon={<Ban aria-hidden="true" />}
          title="Blocked — removed by deletion request"
        >
          The stored content of “{title}” has been removed and its version
          tombstoned. TraceVault deliberately keeps no copy: only metadata,
          lineage and verification evidence remain.
        </EmptyState>
      );
    }
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        title="Content could not be loaded"
      />
    );
  }

  return (
    <section className="panel" role="tabpanel" aria-label="Document content">
      <div className="panel-head">
        <h3>
          <FileText aria-hidden="true" /> Stored content
        </h3>
        <span className="tiny">
          {(query.data?.content.length ?? 0).toLocaleString()} characters
        </span>
      </div>
      <div className="excerpt">{query.data?.content}</div>
    </section>
  );
}

function ChunksTab({
  documentId,
  ingestionPending,
  pendingJobs,
}: {
  documentId: string;
  ingestionPending: boolean;
  pendingJobs: number;
}) {
  const query = useQuery<ChunkOut[]>({
    queryKey: ['document-chunks', documentId],
    queryFn: () => api.get<ChunkOut[]>(`/documents/${documentId}/chunks`),
    refetchInterval: ingestionPending ? 3000 : false,
  });

  if (query.isLoading) {
    return <LoadingSkeleton variant="table" rows={6} label="Loading chunks" />;
  }
  if (query.isError) {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        title="Chunks could not be loaded"
      />
    );
  }
  const chunks = query.data ?? [];
  if (chunks.length === 0) {
    return (
      <EmptyState
        icon={<Layers aria-hidden="true" />}
        title="No chunks registered"
      >
        {ingestionPending
          ? `Ingestion is still running${pendingJobs > 0 ? ` (${pendingJobs} job(s) pending)` : ''} — this list fills in automatically.`
          : 'This document has no chunk artifacts. Re-upload it to build the index.'}
      </EmptyState>
    );
  }
  return (
    <section className="panel panel-flat" role="tabpanel" aria-label="Chunks">
      <div className="table-scroll">
        <table className="data">
          <caption className="visually-hidden">
            Chunks with index, lifecycle state and text (redacted when removed)
          </caption>
          <thead>
            <tr>
              <th scope="col" className="num">
                #
              </th>
              <th scope="col">Lifecycle</th>
              <th scope="col" className="num">
                Offsets
              </th>
              <th scope="col">Text</th>
              <th scope="col">Artifact</th>
            </tr>
          </thead>
          <tbody>
            {chunks.map((c) => (
              <tr key={c.artifact_id}>
                <td className="num">{c.index}</td>
                <td>
                  <StatusPill status={c.lifecycle_state} />
                </td>
                <td className="num">
                  {c.start}–{c.end}
                </td>
                <td style={{ maxWidth: 480 }}>
                  {c.text === null ? (
                    <span className="chip chip-danger">[removed]</span>
                  ) : (
                    <span style={{ fontSize: 13 }}>{c.text}</span>
                  )}
                </td>
                <td className="tiny mono">{shortId(c.artifact_id, 8)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function VersionsTab({ documentId }: { documentId: string }) {
  const query = useQuery<DocumentVersionOut[]>({
    queryKey: ['document-versions', documentId],
    queryFn: () => api.get<DocumentVersionOut[]>(`/documents/${documentId}/versions`),
  });
  if (query.isLoading) {
    return <LoadingSkeleton variant="table" rows={3} label="Loading versions" />;
  }
  if (query.isError) {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        title="Versions could not be loaded"
      />
    );
  }
  const versions = query.data ?? [];
  if (versions.length === 0) {
    return (
      <EmptyState icon={<ScrollText aria-hidden="true" />} title="No versions registered" />
    );
  }
  return (
    <section className="panel panel-flat" role="tabpanel" aria-label="Versions">
      <div className="table-scroll">
        <table className="data">
          <caption className="visually-hidden">Document versions</caption>
          <thead>
            <tr>
              <th scope="col" className="num">
                Version
              </th>
              <th scope="col">Source</th>
              <th scope="col">Filename</th>
              <th scope="col">Checksum</th>
              <th scope="col">Content state</th>
              <th scope="col">Created</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.id}>
                <td className="num">{v.version}</td>
                <td>
                  <span className="chip chip-info">{v.source_type}</span>
                </td>
                <td className="truncate">{v.filename}</td>
                <td className="tiny mono">{shortId(v.checksum, 12)}…</td>
                <td>
                  <StatusPill status={v.content_state} />
                </td>
                <td className="num">{formatDateTime(v.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* Exposed for tests: pending-ingestion banner decision. */
export function isIngestionPending(chunkCount: number): boolean {
  return chunkCount === 0;
}
