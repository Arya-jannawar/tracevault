/* Repair Lab — experimental selective summary repair. Conservative
   invalidation is the default; repair only appears when the backend flag is on.
   Includes the claim-survival semantics explainer. */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  FlaskConical,
  GitBranch,
  Info,
  Loader2,
  Network,
  ShieldCheck,
  Wrench,
} from 'lucide-react';
import { api } from '../api/client';
import type {
  Capabilities,
  DeletionRequestOut,
  RepairCandidateOut,
  RepairJob,
} from '../api/types';
import { StateBadge } from '../components/StateBadge';
import { StatusPill } from '../components/StatusPill';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { useToast } from '../hooks/ToastProvider';
import { formatShortTime, shortId } from '../lib/format';

export function RepairLab() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [repairJob, setRepairJob] = useState<RepairJob | null>(null);
  const [repairPending, setRepairPending] = useState(false);

  const capsQuery = useQuery<Capabilities>({
    queryKey: ['capabilities'],
    queryFn: () => api.get<Capabilities>('/system/capabilities'),
  });
  const selectiveRepair = capsQuery.data?.flags?.selective_repair === true;

  const requestsQuery = useQuery<DeletionRequestOut[]>({
    queryKey: ['deletion-requests', 'repair-lab'],
    queryFn: () =>
      api.get<DeletionRequestOut[]>('/deletion-requests', { page: 1, page_size: 50 }),
    enabled: selectiveRepair,
  });

  const eligible = (requestsQuery.data ?? []).filter(
    (r) => r.repair_enabled || r.state === 'INCOMPLETE',
  );
  const activeRequest = selectedRequestId ?? eligible[0]?.id ?? null;

  const candidatesQuery = useQuery<RepairCandidateOut[]>({
    queryKey: ['repair-candidates', activeRequest],
    queryFn: () =>
      api.get<RepairCandidateOut[]>(`/deletion-requests/${activeRequest}/repair-candidates`),
    enabled: selectiveRepair && !!activeRequest,
  });

  const doRepair = async (candidate: RepairCandidateOut) => {
    setRepairPending(true);
    try {
      const job = await api.post<RepairJob>(`/summaries/${candidate.summary_artifact_id}/repair`, {
        deletion_request_id: activeRequest,
      });
      setRepairJob(job);
      toast.info('Repair job queued', `Job ${shortId(job.job_id, 8)} — polling status…`);
      // poll to completion
      const terminal = new Set(['done', 'failed', 'retry_pending']);
      let current = job;
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        current = await api.get<RepairJob>(`/repair-jobs/${job.job_id}`);
        setRepairJob(current);
        if (terminal.has(current.status)) break;
      }
      if (current.status === 'done') {
        toast.success(
          'Repair complete',
          'The summary was re-derived; surviving claims kept their supports.',
        );
      } else {
        toast.error(
          'Repair did not finish',
          current.last_error ?? `Final status: ${current.status}`,
        );
      }
      void queryClient.invalidateQueries({ queryKey: ['repair-candidates'] });
    } catch (err) {
      toast.error(
        'Repair failed to start',
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setRepairPending(false);
    }
  };

  return (
    <div className="stack">
      <header>
        <h1 className="page-title">Repair Lab</h1>
        <p className="page-sub" style={{ marginBottom: 0 }}>
          <strong>Conservative invalidation is the default:</strong> anything
          downstream of a deleted document is invalidated, even if it might
          survive. Selective repair is an <strong>experimental</strong> second
          pass that rebuilds summaries whose claims are still supported by
          surviving sources.
        </p>
      </header>

      <div className="callout accent">
        <GitBranch aria-hidden="true" />
        <div className="callout-body">
          <div className="callout-title">Claim survival semantics</div>
          Facts <strong>independently supported</strong> by surviving sources may
          remain (the claim is re-registered with its surviving supports). Facts
          supported <strong>only by the deleted source</strong> are removed — the
          repaired summary never paraphrases the removed evidence back into
          existence.
        </div>
      </div>

      {capsQuery.isLoading ? (
        <LoadingSkeleton variant="lines" rows={2} label="Checking capabilities" />
      ) : capsQuery.isError ? (
        <ErrorState
          error={capsQuery.error}
          onRetry={() => void capsQuery.refetch()}
          title="Capabilities unavailable"
          hint="Repair Lab needs GET /system/capabilities to decide whether repair is enabled."
        />
      ) : !selectiveRepair ? (
        <EmptyState
          tone="info"
          icon={<FlaskConical aria-hidden="true" />}
          title="Selective repair is disabled on this deployment"
        >
          The backend flag{' '}
          <code className="mono">flags.selective_repair</code> is currently{' '}
          <strong>false</strong>. Conservative invalidation runs alone: summaries
          downstream of a deletion are invalidated and not rebuilt. To enable the
          experimental repair path, start the backend with{' '}
          <code className="mono">ENABLE_SELECTIVE_REPAIR=true</code>, then reload
          this page.
        </EmptyState>
      ) : (
        <>
          <section className="panel" aria-label="Deletion requests eligible for repair">
            <div className="panel-head">
              <h3>
                <Wrench aria-hidden="true" /> Eligible deletion requests
              </h3>
              <span className="tiny">repair_enabled or INCOMPLETE</span>
            </div>
            {requestsQuery.isLoading ? (
              <LoadingSkeleton variant="table" rows={3} label="Loading requests" />
            ) : requestsQuery.isError ? (
              <ErrorState
                error={requestsQuery.error}
                onRetry={() => void requestsQuery.refetch()}
                title="Deletion requests unavailable"
              />
            ) : eligible.length === 0 ? (
              <EmptyState icon={<Wrench aria-hidden="true" />} title="No repair-eligible requests">
                Requests appear here when they were created with “repair
                enabled” or when they finished INCOMPLETE. Start one from a
                document in the Documents view.
              </EmptyState>
            ) : (
              <div className="row wrap" style={{ gap: 8 }}>
                {eligible.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    className={`btn btn-sm ${activeRequest === r.id ? 'btn-primary' : ''}`}
                    onClick={() => setSelectedRequestId(r.id)}
                  >
                    <StateBadge state={r.state} /> {shortId(r.id, 8)}… ·{' '}
                    {formatShortTime(r.accepted_at)}
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="panel" aria-label="Repair candidates">
            <div className="panel-head">
              <h3>
                <ShieldCheck aria-hidden="true" /> Repair candidates
              </h3>
              {activeRequest && (
                <Link to={`/deletions/${activeRequest}`} className="tiny">
                  view deletion request
                </Link>
              )}
            </div>
            {!activeRequest ? null : candidatesQuery.isLoading ? (
              <LoadingSkeleton variant="table" rows={3} label="Loading candidates" />
            ) : candidatesQuery.isError ? (
              <ErrorState
                error={candidatesQuery.error}
                onRetry={() => void candidatesQuery.refetch()}
                title="Repair candidates unavailable"
              />
            ) : (candidatesQuery.data ?? []).length === 0 ? (
              <EmptyState icon={<GitBranch aria-hidden="true" />} title="No summaries to repair">
                This request either had no registered summaries or they were all
                fully removed with their source.
              </EmptyState>
            ) : (
              <div className="table-scroll">
                <table className="data">
                  <caption className="visually-hidden">
                    Repair candidates with claim survival statistics
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Summary</th>
                      <th scope="col" className="num">
                        Total claims
                      </th>
                      <th scope="col" className="num">
                        Surviving supports
                      </th>
                      <th scope="col" className="num">
                        Surviving source docs
                      </th>
                      <th scope="col">Repairable</th>
                      <th scope="col">
                        <span className="visually-hidden">Action</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(candidatesQuery.data ?? []).map((c) => (
                      <tr key={c.summary_artifact_id}>
                        <td>
                          <div className="cell-title mono">
                            {shortId(c.summary_artifact_id, 8)}…
                          </div>
                          <div className="cell-sub">summary v{c.summary_version}</div>
                        </td>
                        <td className="num">{c.total_claims}</td>
                        <td className="num">{c.surviving_supports}</td>
                        <td className="num">{c.surviving_source_docs.length}</td>
                        <td>
                          <StatusPill
                            status={c.repairable ? 'done' : 'not_applicable'}
                            label={c.repairable ? 'repairable' : 'not repairable'}
                          />
                        </td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-sm btn-primary"
                            disabled={!c.repairable || repairPending}
                            onClick={() => void doRepair(c)}
                          >
                            {repairPending ? (
                              <Loader2 className="spinner" aria-hidden="true" />
                            ) : (
                              <Wrench aria-hidden="true" size={13} />
                            )}
                            Repair
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {repairJob && (
              <div className="callout info" style={{ marginTop: 14 }}>
                <Info aria-hidden="true" />
                <div className="callout-body">
                  <div className="callout-title">
                    Repair job {shortId(repairJob.job_id, 8)}… — <StatusPill status={repairJob.status} />
                  </div>
                  {repairJob.last_error ? (
                    <p className="tiny">{repairJob.last_error}</p>
                  ) : (
                    <p className="tiny">
                      status: {repairJob.status}
                      {typeof repairJob.attempts === 'number'
                        ? ` · attempts: ${repairJob.attempts}`
                        : ''}
                    </p>
                  )}
                  {repairJob.status === 'done' && (
                    <Link
                      className="btn btn-sm"
                      style={{ marginTop: 8 }}
                      to={`/provenance?root=${candidatesQuery.data?.[0]?.summary_artifact_id ?? ''}`}
                    >
                      <Network aria-hidden="true" size={13} /> Inspect the repaired summary lineage
                    </Link>
                  )}
                </div>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
