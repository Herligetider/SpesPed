import type { Clarification, ExtractionProposal, IntakeSource, Learner, LearnerProfile, ListResponse, School, Session } from './types';

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
    private readonly fetcher: typeof fetch = (input, init) => globalThis.fetch(input, init),
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

  async intake(schoolId: string): Promise<ListResponse<IntakeSource>> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake?limit=100`);
  }
  async intakeSource(schoolId: string, sourceId: string): Promise<IntakeSource> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}`);
  }
  async intakePage(schoolId: string, sourceId: string, revision: number, page: number): Promise<{page:number;text:string;source_revision:number}> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}/revisions/${revision}/pages/${page}`);
  }
  async intakeOriginal(schoolId: string, sourceId: string, revision: number): Promise<Blob> {
    return this.requestBlob(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}/revisions/${revision}/original`);
  }
  async intakeProposals(schoolId: string, sourceId: string, revision: number): Promise<ListResponse<ExtractionProposal>> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}/proposals?revision=${revision}&limit=100`);
  }
  async recoveryCandidates(schoolId: string, sourceId: string): Promise<ListResponse<Pick<ExtractionProposal,'id'|'source_id'|'source_revision'|'page'|'span_start'|'span_end'|'field_name'>>> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}/proposals/recovery-candidates?limit=100`);
  }
  async intakeClarifications(schoolId: string, sourceId: string): Promise<ListResponse<Clarification>> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}/clarifications?limit=100`);
  }
  async createIntakeNote(schoolId: string, body: Record<string, unknown>): Promise<IntakeSource> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/notes`, {method:'POST', body:JSON.stringify(body)});
  }
  async uploadIntake(schoolId: string, file: File, metadata: Record<string, unknown>): Promise<IntakeSource> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/files`, {method:'POST', body:file, headers:{'X-Evidence-Filename':file.name, 'X-Evidence-Metadata':JSON.stringify(metadata)}});
  }
  async reviseIntake(schoolId:string,sourceId:string,version:number,file:File,metadata:Record<string,unknown>):Promise<IntakeSource>{
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}/revisions`,{method:'POST',body:file,headers:{'X-Expected-Version':String(version),'X-Evidence-Filename':file.name,'X-Evidence-Metadata':JSON.stringify(metadata)}});
  }
  async reviewProposal(schoolId:string, proposalId:string, body:Record<string,unknown>):Promise<ExtractionProposal> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/extraction-proposals/${encodeURIComponent(proposalId)}/review`, {method:'POST',body:JSON.stringify(body)});
  }
  async proposeField(schoolId:string, sourceId:string, body:Record<string,unknown>):Promise<ExtractionProposal> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}/proposals`, {method:'POST',body:JSON.stringify(body)});
  }
  async recoverManualField(schoolId:string, sourceId:string, body:Record<string,unknown>):Promise<ExtractionProposal> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}/proposals/manual-recovery`, {method:'POST',body:JSON.stringify(body)});
  }
  async createClarification(schoolId:string, sourceId:string, body:Record<string,unknown>):Promise<Clarification> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}/clarifications`, {method:'POST',body:JSON.stringify(body)});
  }
  async resolveClarification(schoolId:string, sourceId:string, taskId:string, body:Record<string,unknown>):Promise<Clarification> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}/clarifications/${encodeURIComponent(taskId)}/resolve`, {method:'POST',body:JSON.stringify(body)});
  }
  async reopenClarification(schoolId:string, sourceId:string, taskId:string, body:Record<string,unknown>):Promise<Clarification> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/intake/${encodeURIComponent(sourceId)}/clarifications/${encodeURIComponent(taskId)}/reopen`, {method:'POST',body:JSON.stringify(body)});
  }
  async correctEvidence(schoolId:string,evidenceId:string,body:Record<string,unknown>):Promise<unknown> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/evidence/${encodeURIComponent(evidenceId)}/corrections`,{method:'POST',body:JSON.stringify(body)});
  }
  async reviewEvidence(schoolId:string, proposalId:string, body:Record<string,unknown>):Promise<unknown> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/extraction-proposals/${encodeURIComponent(proposalId)}/confirm`, {method:'POST',body:JSON.stringify(body)});
  }
  async timeline(schoolId:string, learnerId:string):Promise<ListResponse<Record<string,unknown>>> {
    return this.request(`/schools/${encodeURIComponent(schoolId)}/learners/${encodeURIComponent(learnerId)}/timeline?limit=100`);
  }

  private async requestBlob(path:string):Promise<Blob> {
    const generation = this.authGeneration;
    const response = await this.fetcher(`${this.baseUrl}${path}`, {credentials:'include'});
    if (response.status === 401 && generation === this.authGeneration) {
      this.csrfToken = null; this.authGeneration += 1; this.onSessionExpired?.();
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({})) as ErrorPayload;
      throw new ApiError(payload.error?.message || 'Originalen kunne ikke åpnes.', response.status, payload.error?.code || `HTTP_${response.status}`);
    }
    return response.blob();
  }

  private async request<T>(path: string, init: RequestInit = {}, ignoreUnauthorized = false): Promise<T> {
    const requestGeneration = this.authGeneration;
    const headers = new Headers(init.headers);
    if (typeof init.body === 'string') headers.set('Content-Type', 'application/json');
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
