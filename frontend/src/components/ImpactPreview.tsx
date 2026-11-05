/* Deletion-impact preview: affected artifact counts by type, coverage
   warnings, and the always-shown scope exclusions ("Outside declared scope").
   Shared by DocumentDetail and Overview; unit-tested. */
import { AlertTriangle, ShieldAlert } from 'lucide-react';
import type { DeletionImpact } from '../api/types';
import { humanize } from '../lib/format';

const TYPE_ORDER = [
  'document_version',
  'chunk',
  'vector',
  'summary',
  'answer',
  'cache_entry',
];

const TYPE_LABEL: Record<string, string> = {
  document_version: 'Document versions',
  chunk: 'Chunks',
  vector: 'Vectors',
  summary: 'Summaries',
  answer: 'Answers',
  cache_entry: 'Cache entries',
};

function warningText(w: DeletionImpact['coverage_warnings'][number]): string {
  if (typeof w === 'string') return w;
  if (w && typeof w === 'object') {
    const entries = Object.entries(w as Record<string, unknown>);
    const readable = entries
      .map(([k, v]) => `${humanize(k)}: ${String(v)}`)
      .join(' · ');
    return readable || JSON.stringify(w);
  }
  return String(w);
}

export function ImpactPreview({ impact }: { impact: DeletionImpact }) {
  const byType = impact.affected_by_type ?? {};
  const orderedTypes = [
    ...TYPE_ORDER.filter((t) => t in byType && byType[t] > 0),
    ...Object.keys(byType).filter(
      (t) => !TYPE_ORDER.includes(t) && byType[t] > 0,
    ),
  ];

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div>
        <div className="metric-value num" style={{ fontSize: 34 }}>
          {impact.affected_count}
        </div>
        <div className="tiny" style={{ marginTop: 4 }}>
          artifacts affected by deleting this document (provenance-discovered)
        </div>
      </div>

      {orderedTypes.length > 0 ? (
        <div className="metric-strip">
          {orderedTypes.map((t) => (
            <div className="metric-card" key={t} data-type={t}>
              <div className="metric-label">{TYPE_LABEL[t] ?? humanize(t)}</div>
              <div className="metric-value num" style={{ fontSize: 24 }}>
                {byType[t]}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="muted" style={{ fontSize: 13 }}>
          No downstream artifacts registered yet — nothing besides the document
          itself would be affected.
        </p>
      )}

      {impact.coverage_warnings?.length > 0 && (
        <div>
          <div className="section-title" style={{ color: 'var(--warning)' }}>
            <AlertTriangle aria-hidden="true" size={16} /> Coverage warnings
          </div>
          <div className="list-tight">
            {impact.coverage_warnings.map((w, i) => (
              <div className="list-item warn-list-item" key={i}>
                <span>{warningText(w)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="section-title">
          <ShieldAlert aria-hidden="true" size={16} /> Outside declared scope
        </div>
        <p className="tiny" style={{ marginBottom: 8 }}>
          Always shown: these are never touched by a TraceVault deletion and are
          not covered by its guarantees.
        </p>
        <div className="list-tight">
          {(impact.scope_exclusions ?? []).map((s) => (
            <div className="list-item exclusion-item" key={s}>
              <span>{s}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
