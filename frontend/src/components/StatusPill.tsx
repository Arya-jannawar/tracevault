/* Generic status chip for lifecycle states, claim statuses, verification
   results, job/run statuses — any lower_snake_case status string. */
import { stateTone } from './StateBadge';

const EXTRA_TONES: Record<string, string> = {
  // lifecycle
  active: 'accent',
  pending_deletion: 'warning',
  invalidated: 'warning',
  removed: 'danger',
  registered: 'accent',
  unknown: 'warning',
  // claims
  pending: 'neutral',
  supported: 'accent',
  uncertain: 'warning',
  // verification results
  passed: 'accent',
  failed: 'danger',
  not_applicable: 'neutral',
  // jobs / runs
  queued: 'info',
  running: 'info',
  done: 'accent',
  completed: 'accent',
  // content states
  blocked: 'danger',
  ok: 'accent',
  degraded: 'warning',
  unavailable: 'danger',
  true: 'accent',
  false: 'neutral',
};

const CHIP_CLASS: Record<string, string> = {
  accent: 'chip-accent',
  info: 'chip-info',
  violet: 'chip-violet',
  warning: 'chip-warning',
  danger: 'chip-danger',
  neutral: 'chip-neutral',
};

/** True when the status should show a pulsing dot (work in progress). */
export function isPulsing(status: string): boolean {
  return ['running', 'queued', 'discovering', 'invalidating', 'removing'].includes(
    status,
  );
}

export function statusTone(status: string): string {
  const key = status.toLowerCase();
  return EXTRA_TONES[key] ?? stateTone(status) ?? 'neutral';
}

export function StatusPill({
  status,
  label,
}: {
  status: string | null | undefined;
  label?: string;
}) {
  const s = status ?? 'unknown';
  const tone = statusTone(s);
  return (
    <span
      className={`chip ${CHIP_CLASS[tone] ?? 'chip-neutral'} ${
        isPulsing(s.toLowerCase()) ? 'pulse' : ''
      }`}
    >
      {isPulsing(s.toLowerCase()) && <span className="dot" aria-hidden="true" />}
      {label ?? s.replace(/_/g, ' ')}
    </span>
  );
}
