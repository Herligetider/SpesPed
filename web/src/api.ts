import type { Learner, LearnerProfile, ListResponse, School, Session } from './types';

type ErrorPayload = { error?: { code?: string; message?: string; details?: unknown } };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export class ApiClient {
  private csrfToken: string | null = null;
  private onSessionExpired: (() => void) | undefined;
  private authGeneration = 0;

  constructor(
    private readonly fetcher: typeof fetch = fetch,
    private readonly baseUrl = '/api/v1',
  ) {}

  setSessionExpiredHandler(handler: () => void): void {
    this.onSessionExpired = handler;
  }

  resetSession(): void {
    this.csrfToken = null;
    this.authGeneration += 1;
  }

  async login(email: string, password: string): Promise<Session> {
    const generation = ++this.authGeneration;
    this.csrfToken = null;
    const session = await this.request<Session>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }, true);
    if (generation === this.authGeneration) this.csrfToken = session.csrf_token;
    return session;
  }

  async me(): Promise<Session> {
    const generation = this.authGeneration;
    const session = await this.request<Session>('/auth/me');
    if (generation === this.authGeneration) this.csrfToken = session.csrf_token;
    return session;
  }

  async logout(): Promise<void> {
    const generation = this.authGeneration;
    await this.request<void>('/auth/logout', { method: 'POST' });
    if (generation === this.authGeneration) this.resetSession();
  }

  async schools(): Promise<School[]> {
    const result = await this.request<ListResponse<School>>('/schools');
    return result.items;
  }

  async learners(schoolId: string, offset = 0, limit = 50): Promise<ListResponse<Learner>> {
    const query = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    return this.request<ListResponse<Learner>>(`/schools/${encodeURIComponent(schoolId)}/learners?${query}`);
  }

  async learner(schoolId: string, learnerId: string): Promise<LearnerProfile> {
    return this.request<LearnerProfile>(
      `/schools/${encodeURIComponent(schoolId)}/learners/${encodeURIComponent(learnerId)}`,
    );
  }

  private async request<T>(path: string, init: RequestInit = {}, ignoreUnauthorized = false): Promise<T> {
    const requestGeneration = this.authGeneration;
    const headers = new Headers(init.headers);
    if (init.body !== undefined) headers.set('Content-Type', 'application/json');
    if (init.method && init.method.toUpperCase() !== 'GET') {
      if (this.csrfToken) headers.set('X-CSRF-Token', this.csrfToken);
    }

    let response: Response;
    try {
      response = await this.fetcher(`${this.baseUrl}${path}`, {
        ...init,
        headers,
        credentials: 'include',
      });
    } catch {
      throw new ApiError('Fikk ikke kontakt med SpesPed. Kontroller tilkoblingen og prøv igjen.', 0, 'NETWORK_ERROR');
    }

    if (response.status === 401 && !ignoreUnauthorized && requestGeneration === this.authGeneration) {
      this.csrfToken = null;
      this.authGeneration += 1;
      this.onSessionExpired?.();
    }
    if (!response.ok) {
      const payload = (await response.json().catch(() => ({}))) as ErrorPayload;
      throw new ApiError(
        payload.error?.message || 'Noe gikk galt. Prøv igjen, eller kontakt systemansvarlig.',
        response.status,
        payload.error?.code || `HTTP_${response.status}`,
      );
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }
}

export const api = new ApiClient();
