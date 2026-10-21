import { describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError } from './api';

function response(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('ApiClient', () => {
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
});
