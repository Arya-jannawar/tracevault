/* Metric card with tabular numerals and honest N/A handling. */
import type { ReactNode } from 'react';

export function MetricCard({
  label,
  value,
  sub,
  icon,
  tone,
  loading,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  tone?: 'accent' | 'info' | 'violet' | 'warning' | 'danger';
  loading?: boolean;
}) {
  return (
    <div className={`metric-card ${tone ? `tone-${tone}` : ''}`}>
      <div className="metric-label">
        {icon}
        {label}
      </div>
      {loading ? (
        <div className="skeleton skel-line w40" style={{ height: 26 }} />
      ) : (
        <div className="metric-value num">{value}</div>
      )}
      {sub ? <div className="metric-sub">{sub}</div> : null}
    </div>
  );
}
