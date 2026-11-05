/* Formatting helpers — honest, tabular, locale-stable. */

const dtFormat = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

const dtShort = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return dtFormat.format(d);
}

export function formatShortTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return dtShort.format(d);
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const seconds = Math.round((Date.now() - d.getTime()) / 1000);
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

/** Elapsed between two timestamps (or now when `end` is null — still running). */
export function formatElapsed(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  if (!start) return '—';
  const s = new Date(start).getTime();
  if (Number.isNaN(s)) return '—';
  const e = end ? new Date(end).getTime() : Date.now();
  if (Number.isNaN(e) || e < s) return '—';
  let sec = Math.max(0, Math.round((e - s) / 1000));
  const parts: string[] = [];
  const hours = Math.floor(sec / 3600);
  sec -= hours * 3600;
  const minutes = Math.floor(sec / 60);
  sec -= minutes * 60;
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);
  parts.push(`${sec}s`);
  return parts.slice(0, 2).join(' ');
}

/** Numbers with a bounded decimal count; null/undefined -> "N/A" (never 0). */
export function formatMetric(value: unknown, decimals = 3): string {
  if (value === null || value === undefined || value === 'N/A') return 'N/A';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 'N/A';
    return value.toFixed(decimals).replace(/\.?0+$/, (m) => (m.includes('.') ? '' : m));
  }
  return String(value);
}

export function formatInt(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value.toLocaleString();
  }
  return String(value ?? '—');
}

export function shortId(id: string | null | undefined, keep = 8): string {
  if (!id) return '—';
  return id.length <= keep + 2 ? id : `${id.slice(0, keep)}…`;
}

/** "scope_exclusions" -> "Scope exclusions"; "qdrant_unavailable" -> "Qdrant unavailable". */
export function humanize(raw: string | null | undefined): string {
  if (!raw) return '—';
  return raw
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

export function truncate(text: string, max = 160): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1).trimEnd()}…`;
}

export function percentLabel(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return `${(value * 100).toFixed(1)}%`;
  }
  return 'N/A';
}
