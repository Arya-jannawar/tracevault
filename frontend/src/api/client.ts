/* Fetch wrapper for the TraceVault API.
   - base `/api/v1` (dev proxy -> 127.0.0.1:8000, prod behind nginx)
   - `credentials: "include"` for the HttpOnly session cookie
   - every mutating request carries `X-TraceVault-Session: 1` (CSRF)
   - errors surface as ApiError with the contract's envelope {code,message,request_id}
   - 401 redirects to /login (unless already there or suppressed) */
import type { ErrorEnvelope } from './types';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;

  constructor(status: number, envelope: Partial<ErrorEnvelope>) {
    super(
      envelope.message ||
        `Request failed (${status || 'network'})${
          envelope.code ? ` · ${envelope.code}` : ''
        }`,
    );
    this.name = 'ApiError';
    this.status = status;
    this.code = envelope.code || (status === 0 ? 'network_error' : 'unknown');
    this.requestId = envelope.request_id ?? null;
  }

  /** Human-friendly gloss for the contract's known error codes. */
  get gloss(): string | null {
    const known: Record<string, string> = {
      content_blocked: 'This content was removed by a deletion request.',
      publication_blocked:
        'A deletion fence was committed before this answer could be published.',
      csrf_missing: 'Missing CSRF header — reload the page and retry.',
      auth_failed: 'Sign-in required.',
      forbidden: 'Your role is not allowed to perform this action.',
      not_found: 'Not found.',
      validation_failed: 'The request was rejected by validation.',
      unsupported_content: 'This file type cannot be ingested.',
      adapter_unavailable:
        'The AI adapter is unavailable. Try again or check backend settings.',
      connector_unavailable:
        'A storage connector is unavailable. Check service health.',
      idempotency_conflict: 'The same key was used with a different payload.',
    };
    return known[this.code] ?? null;
  }
}

export const API_BASE = '/api/v1';

type QueryValue = string | number | boolean | undefined | null;
export type Query = Record<string, QueryValue>;

export function buildQuery(params?: Query): string {
  if (!params) return '';
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      sp.set(key, String(value));
    }
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  formData?: FormData;
  query?: Query;
  /** Suppress the automatic 401 -> /login redirect (login itself, logout, /auth/me). */
  skipAuthRedirect?: boolean;
}

async function parseEnvelope(res: Response): Promise<Partial<ErrorEnvelope>> {
  try {
    const data = (await res.json()) as Partial<ErrorEnvelope>;
    if (data && typeof data === 'object') return data;
    return {};
  } catch {
    return {};
  }
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, formData, query, skipAuthRedirect } = opts;
  const headers: Record<string, string> = {};
  if (method !== 'GET') {
    headers['X-TraceVault-Session'] = '1';
  }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}${buildQuery(query)}`, {
      method,
      credentials: 'include',
      headers,
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch {
    throw new ApiError(0, {
      code: 'network_error',
      message:
        'Cannot reach the TraceVault API. Verify the backend is running on port 8000.',
    });
  }

  if (res.ok) {
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  const envelope = await parseEnvelope(res);

  if (res.status === 401 && !skipAuthRedirect) {
    const { pathname, search } = window.location;
    if (!pathname.startsWith('/login')) {
      const next = encodeURIComponent(pathname + search);
      window.location.assign(`/login?next=${next}`);
    }
  }

  throw new ApiError(res.status, envelope);
}

export const api = {
  get<T>(path: string, query?: Query, skipAuthRedirect?: boolean): Promise<T> {
    return request<T>(path, { query, skipAuthRedirect });
  },
  post<T>(
    path: string,
    body?: unknown,
    options?: { skipAuthRedirect?: boolean },
  ): Promise<T> {
    return request<T>(path, { method: 'POST', body, ...options });
  },
  postForm<T>(path: string, formData: FormData): Promise<T> {
    return request<T>(path, { method: 'POST', formData });
  },
  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, { method: 'PUT', body });
  },
  del<T>(path: string): Promise<T> {
    return request<T>(path, { method: 'DELETE' });
  },
};

/** Build a real browser download URL for metadata-only report exports. */
export function exportUrl(path: string, query?: Query): string {
  return `${API_BASE}${path}${buildQuery(query)}`;
}
