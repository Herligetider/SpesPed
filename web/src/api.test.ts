import { describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError } from './api';
import { localizeApiError } from './i18n';

function response(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('ApiClient', () => {
  it('preserves the global receiver required by the default browser transport', async () => {
    const session = { user: { id: 'u1', email: 'a@b.no', display_name: 'A' }, csrf_token: 'csrf', schools: [] };
    const nativeLikeFetch = vi.fn(function (this: unknown) {
      if (this !== globalThis) throw new TypeError('Illegal invocation');
      return Promise.resolve(response(200, session));
    });
    vi.stubGlobal('fetch', nativeLikeFetch);
    try {
      await expect(new ApiClient().me()).resolves.toEqual(session);
      expect(nativeLikeFetch).toHaveBeenCalledOnce();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('keeps the CSRF token from login and sends it with writes and cookies', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response(200, { user: { id: 'u1', email: 'a@b.no', display_name: 'A' }, csrf_token: 'secret-csrf', schools: [] }))
      .mockResolvedValueOnce(response(204));
    const client = new ApiClient(fetcher);
    await client.login('a@b.no', 'pw');
    await client.logout();
    expect(fetcher.mock.calls[0][1]?.credentials).toBe('include');
    expect(fetcher.mock.calls[0][1]?.headers).not.toHaveProperty('X-CSRF-Token');
    expect(new Headers(fetcher.mock.calls[1][1]?.headers).get('X-CSRF-Token')).toBe('secret-csrf');
    expect(fetcher.mock.calls[1][1]?.credentials).toBe('include');
  });

  it('turns safe API error envelopes into useful errors', async () => {
    const client = new ApiClient(vi.fn<typeof fetch>().mockResolvedValue(response(403, { error: { code: 'forbidden', message: 'Du har ikke tilgang.' } })));
    await expect(client.learners('school-1')).rejects.toMatchObject({ name: 'ApiError', status: 403, code: 'forbidden', message: 'Du har ikke tilgang.' });
  });

  it('clears the session token and notifies the app when authorization expires', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response(200, { user: { id: 'u1', email: 'a@b.no', display_name: 'A' }, csrf_token: 'old', schools: [] }))
      .mockResolvedValueOnce(response(401, { error: { code: 'session_expired', message: 'Økten er utløpt.' } }))
      .mockResolvedValueOnce(response(204));
    const client = new ApiClient(fetcher);
    const expired = vi.fn();
    client.setSessionExpiredHandler(expired);
    await client.login('a@b.no', 'pw');
    await expect(client.learners('s1')).rejects.toBeInstanceOf(ApiError);
    expect(expired).toHaveBeenCalledOnce();
    await client.logout();
    expect(new Headers(fetcher.mock.calls[2][1]?.headers).has('X-CSRF-Token')).toBe(false);
  });

  it('uses the backend offset/limit pagination contract', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response(200, { items: [], total: 0 }));
    const client = new ApiClient(fetcher);
    await client.learners('school-1', 100, 100);
    expect(fetcher.mock.calls[0][0]).toBe('/api/v1/schools/school-1/learners?offset=100&limit=100');
  });

  it('does not let an old request 401 expire a newer login or clear its CSRF token', async () => {
    let releaseOldResponse!: (value: Response) => void;
    const oldResponse = new Promise<Response>((resolve) => { releaseOldResponse = resolve; });
    const session = (token: string) => ({ user: { id: 'u1', email: 'a@b.no', display_name: 'A' }, csrf_token: token, schools: [] });
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response(200, session('old-csrf')))
      .mockImplementationOnce(() => oldResponse)
      .mockResolvedValueOnce(response(200, session('new-csrf')))
      .mockResolvedValueOnce(response(204));
    const client = new ApiClient(fetcher);
    const expired = vi.fn();
    client.setSessionExpiredHandler(expired);
    await client.login('a@b.no', 'pw');
    const oldRequest = client.learners('school-1');
    await client.login('a@b.no', 'pw-again');
    releaseOldResponse(response(401, { error: { code: 'authentication_required', message: 'Sign in to continue.' } }));
    await expect(oldRequest).rejects.toMatchObject({ status: 401 });
    expect(expired).not.toHaveBeenCalled();
    await client.logout();
    expect(new Headers(fetcher.mock.calls[3][1]?.headers).get('X-CSRF-Token')).toBe('new-csrf');
  });

  it('localizes known error codes and preserves safe messages for unknown codes', () => {
    expect(localizeApiError('nn', 'invalid_credentials', 'The email or password is incorrect.')).toBe('E-postadressa eller passordet er feil.');
    expect(localizeApiError('nn', 'NETWORK_ERROR', 'network')).toBe('Fekk ikkje kontakt med SpesPed. Kontroller tilkoplinga og prøv igjen.');
    expect(localizeApiError('nb', 'school_specific_error', 'Skolen ber deg kontakte systemansvarlig.')).toBe('Skolen ber deg kontakte systemansvarlig.');
    expect(localizeApiError('nn', 'HTTP_503', '')).toBe('Noko gjekk gale. Prøv igjen, eller kontakt systemansvarleg.');
  });
});
