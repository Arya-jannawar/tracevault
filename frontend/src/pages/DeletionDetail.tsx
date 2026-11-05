/* DeletionDetail — step timeline with per-step status/attempts/error codes,
   per-connector outcomes, affected artifact counts, coverage warnings, scope
   exclusions, verification checks, retry, and metadata-only report exports. */
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Check,
  CircleMinus,
  Clock,
  FileJson,
  FileSpreadsheet,
  Loader2,
  RotateCcw,
  ShieldAlert,
  Timer,
} from 'lucide-react';
import { api, exportUrl } from '../api/client';
import type {
  DeletionRequestDetail,
  DeletionStepOut,
  VerificationCheckOut,
} from '../api/types';
import { DELETION_STEP_ORDER, isTransitional } from '../api/types';
import { StateBadge } from '../components/StateBadge';
import { StatusPill } from '../components/StatusPill';
import { MetricCard } from '../components/MetricCard';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { useToast } from '../hooks/ToastProvider';
import { formatDateTime, formatElapsed, humanize, shortId } from '../lib/format';

const STEP_HELP: Record<string, string> = {
  FENCED: 'A tombstone was committed — application access is blocked before any removal.',
  DISCOVERING: 'The provenance graph is walked to enumerate every affected artifact.',
  INVALIDATING: 'Authoritative lifecycle states flip to invalidated (logical blocking).',
  REMOVING: 'Stored records are deleted through the supported connectors (qdrant, redis).',
  VERIFYING: 'Evidence checks confirm the declared scope actually settled.',
};

export function DeletionDetail() {
  const { id = '' } = useParams();
  const toast = useToast();
  const queryClient = useQueryClient();

  const query = useQuery<DeletionRequestDetail>({
    queryKey: ['deletion-request', id],
    queryFn: () => api.get<DeletionRequestDetail>(`/deletion-requests/${id}`),
    refetchInterval: (q) =>
      isTransitional(q.state.data?.state) ? 2000 : false,
  });

  const detail = query.data;
  const retryable = detail
    ? detail.state === 'RETRY_PENDING' || detail.state === 'INCOMPLETE' || detail.state === 'FAILED'
    : false;
  const [retryPending, setRetryPending] = useState(false);

  const doRetry = async () => {
    setRetryPending(true);
    try {
      await api.post(`/deletion-requests/${id}/retry`);
      toast.success('Retry queued', 'The request re-enters the pipeline shortly.');
      void queryClient.invalidateQueries({ queryKey: ['deletion-request', id] });
      void queryClient.invalidateQueries({ queryKey: ['deletion-requests'] });
    } catch (err) {
      toast.error('Retry failed', err instanceof Error ? err.message : undefined);
    } finally {
      setRetryPending(false);
    }
  };

  if (query.isLoading) {
    return (
      <div className="stack">
        <LoadingSkeleton variant="lines" rows={2} />
        <LoadingSkeleton variant="panel" />
      </div>
    );
  }
  if (query.isError || !detail) {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => void query.refetch()}
        title="Deletion request could not be loaded"
      />
    );
  }

  const report = detail.report ?? {};
  const byType = (report.affected_by_type ?? {}) as Record<string, string[]>;
  const stepsByStep = new Map<string, DeletionStepOut>(
    detail.steps.map((s) => [s.step, s]),
  );

  return (
    <div className="stack">
      <div>
        <Link to="/deletions" className="row tiny" style={{ gap: 5, marginBottom: 10 }}>
          <ArrowLeft size={13} aria-hidden="true" /> Deletion Center
        </Link>
        <div className="row wrap spread">
          <div>
            <h1 className="page-title row" style={{ gap: 12 }}>
              Deletion request
              <StateBadge state={detail.state} />
            </h1>
            <div className="row wrap tiny" style={{ gap: 12, marginTop: 4 }}>
              <span className="mono">{detail.id}</span>
              <span>
                target document:{' '}
                <Link to={`/documents/${detail.document_id}`} className="mono">
                  {shortId(detail.document_id, 8)}…
                </Link>
              </span>
              <span>fence epoch {detail.fence_epoch}</span>
              <span>accepted {formatDateTime(detail.accepted_at)}</span>
              <span className="row" style={{ gap: 4 }}>
                <Timer size={12} aria-hidden="true" />
                {formatElapsed(detail.started_at ?? detail.accepted_at, detail.finished_at)}
              </span>
            </div>
          </div>
          <div className="row" style={{ gap: 10 }}>
            <a
              className="btn"
              href={exportUrl(`/deletion-requests/${id}/report/export`, { format: 'json' })}
              download
            >
              <FileJson aria-hidden="true" size={15} /> Export JSON
            </a>
            <a
              className="btn"
              href={exportUrl(`/deletion-requests/${id}/report/export`, { format: 'csv' })}
              download
            >
              <FileSpreadsheet aria-hidden="true" size={15} /> Export CSV
            </a>
            {retryable && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void doRetry()}
                disabled={retryPending}
              >
                {retryPending ? (
                  <Loader2 className="spinner" aria-hidden="true" />
                ) : (
                  <RotateCcw aria-hidden="true" />
                )}
                Retry pipeline
              </button>
            )}
          </div>
        </div>

        {detail.failure_reason && (
          <div className="callout danger" role="alert" style={{ marginTop: 14 }}>
            <ShieldAlert aria-hidden="true" />
            <div className="callout-body">
              <div className="callout-title">Failure reason: {humanize(detail.failure_reason)}</div>
              The pipeline stopped early. Retry re-runs the remaining steps;
              steps already passed are not repeated blindly.
            </div>
          </div>
        )}
        {isTransitional(detail.state) && (
          <div className="callout info" style={{ marginTop: 14 }}>
            <Clock aria-hidden="true" />
            <div className="callout-body">
              <div className="callout-title">Running — this page polls every 2 seconds</div>
              Until verification settles, affected content is already fenced:
              application access is blocked even while removal is in progress.
            </div>
          </div>
        )}
      </div>

      {/* ---------- step timeline ---------- */}
      <section className="panel" aria-label="Pipeline steps">
        <div className="panel-head">
          <h3>
            <Timer aria-hidden="true" /> Step timeline
          </h3>
          <span className="tiny">FENCED → DISCOVERING → INVALIDATING → REMOVING → VERIFYING → COMPLETED</span>
        </div>
        <div className="timeline">
          {DELETION_STEP_ORDER.map((stepName) => {
            const step = stepsByStep.get(stepName);
            return (
              <TimelineStep
                key={stepName}
                name={stepName}
                step={step}
                nextSteps={DELETION_STEP_ORDER.slice(
                  DELETION_STEP_ORDER.indexOf(stepName) + 1,
                )}
                stepsByStep={stepsByStep}
              />
            );
          })}
          {/* terminal state marker */}
          <div className="tl-step">
            <div className="tl-rail">
              <span
                className={`tl-dot ${
                  detail.state === 'COMPLETED'
                    ? 'done'
                    : detail.state === 'INCOMPLETE' || detail.state === 'RETRY_PENDING'
                      ? 'fail'
                      : ''
                }`}
              >
                {detail.state === 'COMPLETED' ? <Check aria-hidden="true" /> : null}
              </span>
              <span className={`tl-line ${detail.state === 'COMPLETED' ? 'done' : ''}`} />
            </div>
            <div className="tl-body">
              <div className="tl-head">
                <span className="tl-title">COMPLETED</span>
                <StateBadge state={detail.state} />
              </div>
              {report.completed_at ? (
                <div className="tl-meta">finished {formatDateTime(String(report.completed_at))}</div>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      {/* ---------- affected counts ---------- */}
      <section aria-label="Affected artifacts">
        <div className="metric-strip">
          <MetricCard
            label="Affected artifacts"
            value={typeof report.affected_count === 'number' ? report.affected_count : '—'}
            tone="danger"
            sub="discovered through provenance"
          />
          {Object.entries(byType).map(([type, ids]) => (
            <MetricCard
              key={type}
              label={humanize(type)}
              value={Array.isArray(ids) ? ids.length : '—'}
              sub="invalidated + removed"
            />
          ))}
          <MetricCard
            label="Repair"
            value={detail.repair_enabled ? 'enabled' : 'off'}
            sub={
              detail.repair_enabled
                ? 'surviving summaries may be repaired'
                : 'summaries fully invalidated'
            }
            tone={detail.repair_enabled ? 'accent' : undefined}
          />
        </div>
      </section>

      <div className="grid-2">
        {/* ---------- coverage warnings ---------- */}
        <section className="panel" aria-label="Coverage warnings">
          <div className="panel-head">
            <h3>
              <ShieldAlert aria-hidden="true" /> Coverage warnings
            </h3>
          </div>
          {(report.coverage_warnings ?? []).length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>
              No warnings recorded — discovery covered the full registered
              dependency set.
            </p>
          ) : (
            <div className="list-tight">
              {(report.coverage_warnings ?? []).map((w, i) => (
                <div className="list-item warn-list-item" key={i}>
                  {typeof w === 'string' ? w : JSON.stringify(w)}
                </div>
              ))}
            </div>
          )}
          <hr className="divider" />
          <div className="section-title">Outside declared scope</div>
          <p className="tiny" style={{ marginBottom: 8 }}>
            Always shown — never touched by this deletion and not covered by its
            guarantees.
          </p>
          <div className="list-tight">
            {(report.scope_exclusions ?? []).map((s) => (
              <div className="list-item exclusion-item" key={s}>
                {s}
              </div>
            ))}
          </div>
        </section>

        {/* ---------- verification checks ---------- */}
        <section className="panel" aria-label="Verification checks">
          <div className="panel-head">
            <h3>
              <Check aria-hidden="true" /> Verification checks
            </h3>
            <span className="tiny">evidence from specified checks at a recorded time</span>
          </div>
          {detail.verification.length === 0 ? (
            <EmptyState
              icon={<Check aria-hidden="true" />}
              title="No checks recorded yet"
            >
              Checks appear once the pipeline reaches VERIFYING.
            </EmptyState>
          ) : (
            <div className="table-scroll">
              <table className="data">
                <caption className="visually-hidden">Verification checks and results</caption>
                <thead>
                  <tr>
                    <th scope="col">Check</th>
                    <th scope="col">Target</th>
                    <th scope="col">Result</th>
                    <th scope="col">Finished</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.verification.map((c, i) => (
                    <VerificationRow key={i} check={c} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function TimelineStep({
  name,
  step,
  stepsByStep,
  nextSteps,
}: {
  name: string;
  step: DeletionStepOut | undefined;
  stepsByStep: Map<string, DeletionStepOut>;
  nextSteps: readonly string[];
}) {
  const status = step?.status ?? 'pending';
  const dotCls =
    status === 'passed'
      ? 'done'
      : status === 'running'
        ? 'run'
        : status === 'failed'
          ? 'fail'
          : status === 'skipped'
            ? 'skip'
            : '';
  const nextStarted = nextSteps.some((s) => (stepsByStep.get(s)?.status ?? 'pending') !== 'pending');
  return (
    <div className="tl-step">
      <div className="tl-rail">
        <span className={`tl-dot ${dotCls}`}>
          {status === 'passed' && <Check aria-hidden="true" />}
          {status === 'failed' && <CircleMinus aria-hidden="true" />}
        </span>
        <span className={`tl-line ${nextStarted ? 'done' : ''}`} />
      </div>
      <div className="tl-body">
        <div className="tl-head">
          <span className="tl-title">{name}</span>
          <StatusPill status={status} />
          {step && step.attempts > 0 && (
            <span className="chip chip-neutral num">
              attempts: {step.attempts}
            </span>
          )}
          {step?.error_code && (
            <span className="chip chip-danger mono">{step.error_code}</span>
          )}
          {step?.finished_at && (
            <span className="tl-meta num">{formatDateTime(step.finished_at)}</span>
          )}
        </div>
        <div className="tl-meta">{STEP_HELP[name]}</div>
        {step?.detail && Object.keys(step.detail).length > 0 && (
          <div className="tl-detail">
            <ConnectorDetail detail={step.detail} />
          </div>
        )}
      </div>
    </div>
  );
}

/* Renders per-connector outcomes (qdrant/redis rows with ok/acknowledged) or a
   generic key/value listing for other step details. */
function ConnectorDetail({ detail }: { detail: Record<string, unknown> }) {
  const connectorLike = Object.entries(detail).filter(
    ([, v]) => v && typeof v === 'object' && ('ok' in (v as Record<string, unknown>) || 'acknowledged' in (v as Record<string, unknown>)),
  );
  if (connectorLike.length > 0) {
    return (
      <div>
        {connectorLike.map(([name, v]) => {
          const row = v as Record<string, unknown>;
          const ok = row['ok'] === true;
          const ack = row['acknowledged'] === true;
          return (
            <div className="connector-row" key={name}>
              <span className="chip chip-info">{name}</span>
              <span className={`chip ${ok ? 'chip-accent' : 'chip-danger'}`}>
                {ok ? 'ok' : 'failed'}
              </span>
              <span className={`chip ${ack ? 'chip-accent' : 'chip-warning'}`}>
                {ack ? 'acknowledged' : 'not acknowledged'}
              </span>
              {typeof row['error_code'] === 'string' && (
                <span className="chip chip-danger mono">{String(row['error_code'])}</span>
              )}
              {typeof row['detail'] === 'string' && (
                <span className="tiny">{String(row['detail'])}</span>
              )}
            </div>
          );
        })}
      </div>
    );
  }
  return (
    <div className="json-view">
      {Object.entries(detail)
        .map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
        .join('\n')}
    </div>
  );
}

function VerificationRow({ check }: { check: VerificationCheckOut }) {
  const tone =
    check.result === 'passed'
      ? 'chip-accent'
      : check.result === 'failed'
        ? 'chip-danger'
        : check.result === 'not_applicable'
          ? 'chip-neutral'
          : 'chip-warning';
  return (
    <tr>
      <td className="cell-title">{humanize(check.check_type)}</td>
      <td className="tiny mono">{check.target_label}</td>
      <td>
        <span className={`chip ${tone}`}>{check.result.replace(/_/g, ' ')}</span>
        {check.error_code && (
          <span className="chip chip-danger mono" style={{ marginLeft: 6 }}>
            {check.error_code}
          </span>
        )}
      </td>
      <td className="num">{check.finished_at ? formatDateTime(check.finished_at) : '—'}</td>
    </tr>
  );
}
