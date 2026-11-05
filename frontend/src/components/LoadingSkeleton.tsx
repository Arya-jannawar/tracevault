/* Loading skeletons (shimmer). Variants map to the shapes we actually render. */
export function LoadingSkeleton({
  variant = 'lines',
  rows = 3,
  label = 'Loading',
}: {
  variant?: 'lines' | 'stats' | 'table' | 'panel';
  rows?: number;
  label?: string;
}) {
  return (
    <div role="status" aria-label={label}>
      <span className="visually-hidden">{label}…</span>
      {variant === 'lines' && (
        <div>
          {Array.from({ length: rows }, (_, i) => (
            <div
              key={i}
              className={`skeleton skel-line w${((i * 20 + 40) % 60) + 20}`}
            />
          ))}
        </div>
      )}
      {variant === 'stats' && (
        <div className="metric-strip" aria-hidden="true">
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} className="skeleton skel-stat" />
          ))}
        </div>
      )}
      {variant === 'table' && (
        <div aria-hidden="true">
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} className="skeleton skel-row" />
          ))}
        </div>
      )}
      {variant === 'panel' && <div className="skeleton skel-panel" aria-hidden="true" />}
    </div>
  );
}
