/* API client unit tests: CSRF header on mutations, JSON envelope parsing into
   ApiError, 401 suppression, network-failure normalisation. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, authRedirect } from '../api/client';

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api client', () => {
  it('sends credentials and the CSRF header on mutations only', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { ok: true }));

    await api.get('/documents');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, getInit] = fetchMock.mock.calls[0];
    expect(getInit.credentials).toBe('include');
    expect(getInit.headers['X-TraceVault-Session']).toBeUndefined();

    await api.post('/rag/query', { question: 'q' });
    const [, postInit] = fetchMock.mock.calls[1];
    expect(postInit.credentials).toBe('include');
    expect(postInit.headers['X-TraceVault-Session']).toBe('1');
    expect(postInit.headers['Content-Type']).toBe('application/json');
    expect(postInit.body).toBe(JSON.stringify({ question: 'q' }));

    await api.del('/documents/abc');
    const [, delInit] = fetchMock.mock.calls[2];
    expect(delInit.method).toBe('DELETE');
    expect(delInit.headers['X-TraceVault-Session']).toBe('1');
  });

  it('serialises query params and skips empty ones', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, []));
    await api.get('/documents', { q: 'nightingale', page: 2, page_size: 20, state: '' });
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/documents?q=nightingale&page=2&page_size=20');
  });

  it('parses the error envelope {code,message,request_id} into ApiError', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(409, {
        code: 'publication_blocked',
        message: 'Fence committed before publication.',
        request_id: 'req-123',
      }),
    );
    const err = (await api
      .post('/rag/query', { question: 'x' })
      .catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.code).toBe('publication_blocked');
    expect(err.message).toBe('Fence committed before publication.');
    expect(err.requestId).toBe('req-123');
  });

  it('falls back to a generic envelope when the error body is not JSON', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('not json')),
    } as unknown as Response);
    const err = (await api.get('/documents').catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(500);
    expect(err.code).toBe('unknown');
    expect(err.requestId).toBeNull();
  });

  it('does not redirect on 401 when skipAuthRedirect is set (login flow)', async () => {
    const toLoginSpy = vi.fn();
    const originalToLogin = authRedirect.toLogin;
    authRedirect.toLogin = toLoginSpy;
    try {
      fetchMock.mockResolvedValue(
        jsonResponse(401, { code: 'auth_failed', message: 'Invalid session.' }),
      );
      const err = (await api
        .post('/auth/login', { username: 'u', password: 'p' }, { skipAuthRedirect: true })
        .catch((e: unknown) => e)) as ApiError;
      expect(err).toBeInstanceOf(ApiError);
      expect(err.status).toBe(401);
      expect(toLoginSpy).not.toHaveBeenCalled();
    } finally {
      authRedirect.toLogin = originalToLogin;
    }
  });

  it('redirects to /login on 401 for protected endpoints', async () => {
    const toLoginSpy = vi.fn();
    const originalToLogin = authRedirect.toLogin;
    authRedirect.toLogin = toLoginSpy;
    try {
      fetchMock.mockResolvedValue(
        jsonResponse(401, { code: 'auth_failed', message: 'Sign-in required.' }),
      );
      await api.get('/documents').catch(() => undefined);
      expect(toLoginSpy).toHaveBeenCalledTimes(1);
      expect(toLoginSpy.mock.calls[0][0]).toContain('/login');
    } finally {
      authRedirect.toLogin = originalToLogin;
    }
  });

  it('normalises network failures into an actionable ApiError', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    const err = (await api.get('/health/ready').catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.code).toBe('network_error');
    expect(err.message).toMatch(/cannot reach the tracevault api/i);
  });
});
