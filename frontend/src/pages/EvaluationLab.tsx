/* Evaluation Lab — launch runs over the synthetic corpus, poll to completion,
   read metrics with honest N/A handling, compare completed runs in a bar chart.
   Empty state until a run exists: never decorative fake results. */
import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BarChart3,
  FlaskConical,
  Info,
  Play,
  RefreshCw,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../api/client';
import type {
  EvaluationRunOut,
  ScenarioOut,
} from '../api/types';
import { StatusPill } from '../components/StatusPill';
import { MetricCard } from '../components/MetricCard';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { useToast } from '../hooks/ToastProvider';
import { useTopbarAction } from '../hooks/useTopbarAction';
import { formatDateTime, formatMetric, humanize, shortId } from '../lib/format';

/* The four baselines with their operational definitions (from the backend's
   evaluation module — quoted honestly, not invented). */
const BASELINES: { id: string; name: string; description: string }[] = [
  {
    id: 'vector_only',
    name: 'vector_only',
    description:
      'Deletes only the source document’s vector points; derived artifacts stay. Intentionally demonstrates the weakness.',
  },
  {
    id: 'broad_conservative',
    name: 'broad_conservative',
    description:
      'Invalidates EVERY artifact in the bounded evaluation workspace after deleting the source. Safe, wasteful.',
  },
  {
    id: 'provenance_conservative',
    name: 'provenance_conservative',
    description:
      'The production path: the full provenance-aware deletion protocol.',
  },
  {
    id: 'provenance_repair',
    name: 'provenance_repair',
    description:
      'The same safe invalidation, plus selective summary repair for surviving claims.',
  },
];

const METRIC_LABELS: Record<string, string> = {
  deletion_effectiveness: 'Deletion effectiveness',
  residual_information_rate: 'Residual information rate',
  dependency_precision: 'Dependency precision',
  dependency_recall: 'Dependency recall',
  false_invalidation_rate: 'False invalidation rate',
  information_preservation: 'Information preservation',
  cache_hit_before_deletion: 'Cache hits before deletion',
};

const CHART_COLORS = ['#C7FF5E', '#45D9F5', '#A99BFF', '#FFBE55', '#FF6B75'];

export function EvaluationLab() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [scenario, setScenario] = useState('');
  const [baseline, setBaseline] = useState(BASELINES[0].id);
  const [seed, setSeed] = useState(42);
  const [launching, setLaunching] = useState(false);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);

  const scenariosQuery = useQuery<ScenarioOut[]>({
    queryKey: ['evaluation-scenarios'],
    queryFn: () => api.get<ScenarioOut[]>('/evaluation/scenarios'),
  });

  const runsQuery = useQuery<EvaluationRunOut[]>({
    queryKey: ['evaluation-runs'],
    queryFn: () => api.get<EvaluationRunOut[]>('/evaluation-runs'),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => r.status === 'queued' || r.status === 'running')
        ? 2000
        : false,
  });

  const runs = runsQuery.data ?? [];
  const activeScenario = scenario || scenariosQuery.data?.[0]?.name || '';
  const currentRunId = selectedRun ?? runs[0]?.id ?? null;

  const runDetailQuery = useQuery<EvaluationRunOut>({
    queryKey: ['evaluation-run', currentRunId],
    queryFn: () => api.get<EvaluationRunOut>(`/evaluation-runs/${currentRunId}`),
    enabled: !!currentRunId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === 'queued' || s === 'running' ? 2000 : false;
    },
  });

  useTopbarAction(
    useMemo(
      () => ({
        label: 'Launch run',
        onClick: () => document.getElementById('eval-launch')?.scrollIntoView({ behavior: 'smooth' }),
      }),
      [],
    ),
  );

  const launch = async () => {
    if (!activeScenario) return;
    setLaunching(true);
    try {
      const run = await api.post<EvaluationRunOut>('/evaluation-runs', {
        scenario: activeScenario,
        baseline,
        seed,
      });
      toast.success(
        'Run queued',
        `${baseline} on ${activeScenario} (seed ${seed}) — polling until it settles.`,
      );
      setSelectedRun(run.id);
      void queryClient.invalidateQueries({ queryKey: ['evaluation-runs'] });
    } catch (err) {
      toast.error(
        'Could not launch the run',
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setLaunching(false);
    }
  };

  const completedRuns = runs.filter((r) => r.status === 'completed');
  const run = runDetailQuery.data;

  const chartData = useMemo(() => {
    if (completedRuns.length === 0) return [];
    const metricKeys = Object.keys(METRIC_LABELS);
    return metricKeys
      .map((metric) => {
        const row: Record<string, string | number | null> = { metric: METRIC_LABELS[metric] };
        let any = false;
        for (const [i, r] of completedRuns.entries()) {
          const v = r.metrics?.[metric];
          row[r.id] = typeof v === 'number' && Number.isFinite(v) ? v : null;
          if (row[r.id] !== null) any = true;
          void i;
        }
        return any ? row : null;
      })
      .filter((x): x is Record<string, string | number | null> => x !== null);
  }, [completedRuns]);

  return (
    <div className="stack">
      <header>
        <h1 className="page-title">Evaluation Lab</h1>
        <p className="page-sub" style={{ marginBottom: 0 }}>
          Measures deletion behaviour on the seeded synthetic corpus in an
          isolated workspace. Zero-denominator metrics are reported as N/A —
          never as 0%. Deterministic demo embeddings unless stated otherwise;
          these are not general real-world privacy evidence.
        </p>
      </header>

      {/* launch form */}
      <section className="panel" id="eval-launch" aria-label="Launch an evaluation run">
        <div className="panel-head">
          <h3>
            <Play aria-hidden="true" /> Launch a run
          </h3>
        </div>
        <div className="filter-bar" style={{ marginBottom: 0 }}>
          <div className="field" style={{ maxWidth: 340 }}>
            <label htmlFor="eval-scenario">Scenario</label>
            <select
              id="eval-scenario"
              className="select"
              value={activeScenario}
              onChange={(e) => setScenario(e.target.value)}
              disabled={scenariosQuery.isLoading}
            >
              {scenariosQuery.isLoading ? (
                <option value="">Loading scenarios…</option>
              ) : (
                (scenariosQuery.data ?? []).map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name}
                  </option>
                ))
              )}
            </select>
            {scenariosQuery.data
              ?.filter((s) => s.name === activeScenario)
              .map((s) => (
                <span className="field-hint" key={s.name}>
                  {s.description}
                </span>
              ))}
          </div>
          <div className="field" style={{ maxWidth: 340 }}>
            <label htmlFor="eval-baseline">Baseline</label>
            <select
              id="eval-baseline"
              className="select"
              value={baseline}
              onChange={(e) => setBaseline(e.target.value)}
            >
              {BASELINES.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
            <span className="field-hint">
              {BASELINES.find((b) => b.id === baseline)?.description}
            </span>
          </div>
          <div className="field" style={{ maxWidth: 140 }}>
            <label htmlFor="eval-seed">Seed</label>
            <input
              id="eval-seed"
              type="number"
              className="input num"
              value={seed}
              min={0}
              onChange={(e) => setSeed(Number(e.target.value))}
            />
          </div>
          <button
            type="button"
            className="btn btn-primary"
            style={{ alignSelf: 'flex-end' }}
            onClick={() => void launch()}
            disabled={launching || !activeScenario}
          >
            {launching ? (
              <span className="spinner" aria-hidden="true" />
            ) : (
              <FlaskConical aria-hidden="true" size={15} />
            )}
            {launching ? 'Queuing…' : 'Launch run'}
          </button>
        </div>
      </section>

      {/* runs list */}
      <section className="panel panel-flat" aria-label="Evaluation runs">
        <div className="panel-head" style={{ padding: '16px 20px 0' }}>
          <h3>
            <BarChart3 aria-hidden="true" /> Runs
          </h3>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => void runsQuery.refetch()}
          >
            <RefreshCw aria-hidden="true" size={13} /> Refresh
          </button>
        </div>
        <div style={{ padding: 20 }}>
          {runsQuery.isLoading ? (
            <LoadingSkeleton variant="table" rows={3} label="Loading runs" />
          ) : runsQuery.isError ? (
            <ErrorState
              error={runsQuery.error}
              onRetry={() => void runsQuery.refetch()}
              title="Runs could not be loaded"
            />
          ) : runs.length === 0 ? (
            <EmptyState
              icon={<FlaskConical aria-hidden="true" />}
              title="No evaluation runs yet"
              actions={
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void launch()}
                  disabled={launching || !activeScenario}
                >
                  <Play aria-hidden="true" size={15} /> Launch the first run
                </button>
              }
            >
              Choose a scenario and a baseline above, then press “Launch run”.
              The backend replays the seeded deletion scenario in an isolated
              workspace and reports measured metrics here — nothing is shown
              until a real run completes.
            </EmptyState>
          ) : (
            <div className="table-scroll">
              <table className="data">
                <caption className="visually-hidden">Evaluation runs</caption>
                <thead>
                  <tr>
                    <th scope="col">Run</th>
                    <th scope="col">Scenario</th>
                    <th scope="col">Baseline</th>
                    <th scope="col" className="num">
                      Seed
                    </th>
                    <th scope="col">Status</th>
                    <th scope="col">Started</th>
                    <th scope="col">Finished</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr
                      key={r.id}
                      className={`clickable ${currentRunId === r.id ? 'selected' : ''}`}
                      tabIndex={0}
                      onClick={() => setSelectedRun(r.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') setSelectedRun(r.id);
                      }}
                      style={currentRunId === r.id ? { background: 'var(--accent-dim)' } : undefined}
                      aria-label={`Select run ${shortId(r.id, 8)}`}
                    >
                      <td className="mono tiny">{shortId(r.id, 8)}…</td>
                      <td className="tiny">{r.scenario}</td>
                      <td>
                        <span className="chip chip-violet">{r.baseline}</span>
                      </td>
                      <td className="num">{r.seed}</td>
                      <td>
                        <StatusPill status={r.status} />
                        {r.error && (
                          <div className="cell-sub" style={{ maxWidth: 220 }}>
                            {r.error}
                          </div>
                        )}
                      </td>
                      <td className="num">{formatDateTime(r.started_at)}</td>
                      <td className="num">{formatDateTime(r.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* results */}
      {run && (
        <section className="panel" aria-label="Run results">
          <div className="panel-head">
            <h3>
              <Info aria-hidden="true" /> Results — {run.baseline} on {run.scenario}
            </h3>
            <StatusPill status={run.status} />
          </div>

          {run.status === 'queued' || run.status === 'running' ? (
            <div>
              <LoadingSkeleton variant="stats" rows={4} label="Waiting for run completion" />
              <p className="tiny" style={{ marginTop: 10 }}>
                The run re-executes the deletion protocol against the seeded
                corpus — this view polls every 2 seconds until it completes.
              </p>
            </div>
          ) : run.status === 'failed' ? (
            <ErrorState
              error={new Error(run.error ?? 'The run failed.')}
              onRetry={() => void runDetailQuery.refetch()}
              title="Run failed"
            />
          ) : (
            <>
              <div className="metric-strip" style={{ marginBottom: 18 }}>
                {Object.entries(METRIC_LABELS).map(([key, label]) => {
                  const v = run.metrics?.[key];
                  return (
                    <MetricCard
                      key={key}
                      label={label}
                      value={
                        typeof v === 'number' && v >= 0 && v <= 1
                          ? `${(v * 100).toFixed(1)}%`
                          : formatMetric(v)
                      }
                      sub={formatMetric(v) === 'N/A' ? 'zero denominator — N/A by design' : undefined}
                      tone={
                        typeof v === 'number'
                          ? key.includes('rate') && key.includes('false')
                            ? v > 0.02
                              ? 'warning'
                              : 'accent'
                            : undefined
                          : undefined
                      }
                    />
                  );
                })}
              </div>

              {run.counts && (
                <div className="row wrap" style={{ gap: 8, marginBottom: 16 }}>
                  {Object.entries(run.counts).map(([k, v]) => (
                    <span className="chip chip-neutral num" key={k}>
                      {humanize(k)}: {String(v)}
                    </span>
                  ))}
                </div>
              )}

              {run.config && (
                <div>
                  <div className="section-title">Run configuration</div>
                  <div className="json-view">
                    {Object.entries(run.config)
                      .map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
                      .join('\n')}
                  </div>
                </div>
              )}

              {completedRuns.length > 1 && chartData.length > 0 && (
                <div style={{ marginTop: 20 }}>
                  <div className="section-title">
                    Metric comparison across completed runs
                  </div>
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 4, left: -12 }}>
                      <CartesianGrid stroke="rgba(168,181,202,0.12)" vertical={false} />
                      <XAxis
                        dataKey="metric"
                        tick={{ fill: '#A8B5CA', fontSize: 10.5 }}
                        interval={0}
                        angle={-22}
                        textAnchor="end"
                        height={74}
                      />
                      <YAxis tick={{ fill: '#A8B5CA', fontSize: 11 }} domain={[0, 1]} />
                      <Tooltip
                        cursor={{ fill: 'rgba(168,181,202,0.06)' }}
                        contentStyle={{
                          background: '#16233A',
                          border: '1px solid rgba(168,181,202,0.28)',
                          borderRadius: 10,
                          color: '#F4F7FC',
                          fontSize: 12.5,
                        }}
                      />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      {completedRuns.map((r, i) => (
                        <Bar
                          key={r.id}
                          dataKey={r.id}
                          name={`${r.baseline} · ${shortId(r.id, 6)}`}
                          fill={CHART_COLORS[i % CHART_COLORS.length]}
                          radius={[4, 4, 0, 0]}
                        />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                  <p className="tiny" style={{ marginTop: 8 }}>
                    Bars omit N/A entries rather than plotting them as zero — a
                    missing bar means “not measurable for that run”.
                  </p>
                </div>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
