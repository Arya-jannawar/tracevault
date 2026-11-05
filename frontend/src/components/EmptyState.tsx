/* Guidance-first empty states. */
import type { ReactNode } from 'react';

export function EmptyState({
  icon,
  title,
  children,
  actions,
  tone = 'info',
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
  tone?: 'info' | 'accent' | 'danger';
}) {
  return (
    <div className={`state-block ${tone !== 'info' ? `tone-${tone}` : ''}`}>
      {icon ? (
        <div className="state-icon" aria-hidden="true">
          {icon}
        </div>
      ) : null}
      <h3>{title}</h3>
      {children ? <p>{children}</p> : null}
      {actions ? <div className="state-actions">{actions}</div> : null}
    </div>
  );
}
