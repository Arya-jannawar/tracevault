/* Deletion-pipeline state badge.
   Terminal states are SOLID (COMPLETED lime + check, INCOMPLETE coral + minus,
   RETRY_PENDING amber), transitional states are outlined tints with a pulsing
   dot while running — INCOMPLETE can never be confused with COMPLETED. */
import { AlertTriangle, Check, CircleMinus, RotateCcw, X } from 'lucide-react';
import type { DeletionState } from '../api/types';

type BadgeVisual = {
  cls: string;
  icon: 'check' | 'minus' | 'x' | 'retry' | 'warn' | 'dot';
  pulse?: boolean;
  label?: string;
};

const MAP: Record<string, BadgeVisual> = {
  COMPLETED: { cls: 'st-completed', icon: 'check' },
  INCOMPLETE: { cls: 'st-incomplete', icon: 'minus' },
  FAILED: { cls: 'st-failed', icon: 'x' },
  RETRY_PENDING: { cls: 'st-retry_pending', icon: 'retry' },
  ACCEPTED: { cls: 'st-accepted', icon: 'dot' },
  FENCED: { cls: 'st-fenced', icon: 'warn' },
  DISCOVERING: { cls: 'st-discovering', icon: 'dot', pulse: true },
  INVALIDATING: { cls: 'st-invalidating', icon: 'dot', pulse: true },
  REMOVING: { cls: 'st-removing', icon: 'dot', pulse: true },
  VERIFYING: { cls: 'st-verifying', icon: 'dot', pulse: true },
  RUNNING: { cls: 'st-running', icon: 'dot', pulse: true },
  // document states
  active: { cls: 'st-active', icon: 'check' },
  pending_deletion: { cls: 'st-pending_deletion', icon: 'warn' },
  deleted: { cls: 'st-deleted', icon: 'x' },
};

const ICONS = {
  check: Check,
  minus: CircleMinus,
  x: X,
  retry: RotateCcw,
  warn: AlertTriangle,
  dot: null,
};

export function StateBadge({
  state,
  className,
}: {
  state: string | null | undefined;
  className?: string;
}) {
  const s = state ?? 'UNKNOWN';
  const visual = MAP[s] ?? { cls: 'st-neutral', icon: 'dot' as const };
  const Icon = ICONS[visual.icon];
  return (
    <span
      className={`state-badge ${visual.cls} ${visual.pulse ? 'pulse' : ''} ${
        className ?? ''
      }`}
      data-state={s}
    >
      {visual.pulse && <span className="dot" aria-hidden="true" />}
      {Icon ? <Icon aria-hidden="true" /> : null}
      {s.replace(/_/g, ' ')}
    </span>
  );
}

/** Tone for a deletion state, reused by tables/legend chips. */
export function stateTone(state: string): string {
  const visual = MAP[state];
  if (!visual) return 'neutral';
  switch (visual.cls) {
    case 'st-completed':
      return 'accent';
    case 'st-incomplete':
    case 'st-failed':
    case 'st-deleted':
      return 'danger';
    case 'st-retry_pending':
    case 'st-fenced':
    case 'st-pending_deletion':
      return 'warning';
    case 'st-discovering':
    case 'st-invalidating':
    case 'st-removing':
    case 'st-running':
      return 'info';
    case 'st-verifying':
      return 'violet';
    case 'st-active':
      return 'accent';
    default:
      return 'neutral';
  }
}

export type DeletionStateLike = DeletionState | string;
