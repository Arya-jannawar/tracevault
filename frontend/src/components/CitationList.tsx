/* Citation list for RAG answers. Click opens the authorized-excerpt drawer. */
import type { Citation } from '../api/types';
import { formatMetric } from '../lib/format';

export function CitationList({
  citations,
  onSelect,
  selectedId,
}: {
  citations: Citation[];
  onSelect: (citation: Citation) => void;
  selectedId?: string | null;
}) {
  if (citations.length === 0) {
    return (
      <p className="muted" style={{ fontSize: 13 }}>
        This answer has no citations — it was not grounded in retrieved chunks.
      </p>
    );
  }
  return (
    <div className="list-tight" role="list" aria-label="Citations">
      {citations.map((c, i) => (
        <button
          key={`${c.chunk_artifact_id}-${i}`}
          type="button"
          role="listitem"
          className="citation-item"
          onClick={() => onSelect(c)}
          aria-label={`Open citation ${c.label} excerpt`}
          data-selected={selectedId === c.chunk_artifact_id || undefined}
        >
          <span
            className={`chip chip-info citation-label`}
            aria-hidden="true"
          >
            {c.label}
          </span>
          <span className="grow" style={{ minWidth: 0 }}>
            <span className="cit-snippet">{c.snippet}</span>
            <span className="tiny" style={{ display: 'block', marginTop: 5 }}>
              score {formatMetric(c.score, 3)} · click for the authorized excerpt
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}
