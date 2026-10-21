export type School = {
  id: string;
  name: string;
  kind: string;
  timezone: string;
  role: string;
};

export type User = {
  id: string;
  email: string;
  display_name: string;
};

export type Session = {
  user: User;
  csrf_token: string;
  schools: School[];
};

export type Learner = {
  id: string;
  display_name: string;
  grade: number;
  group_name: string | null;
  version: number;
};

export type LearnerProfile = Learner & {
  strengths?: string | null;
  interests?: string | null;
  languages?: string[];
  communication?: string | null;
  support_strategies?: string | null;
  updated_at?: string | null;
};

export type ListResponse<T> = { items: T[]; total: number };

export type IntakeSource = {
  id: string; version: number; state: string; current_revision: number; revision: number;
  external_scope: string; external_id: string;
  sender: string; document_type: string; received_at: string; original_at: string | null;
  filename: string; media_type: string; digest: string; byte_size: number;
  scan_state: string; extraction_state: string; issue: string | null; page_count: number;
  review_progress: Record<string, number>; pagination: string;
};
export type ExtractionProposal = {
  id: string; version: number; state: string; source_id: string; source_revision: number;
  page: number; span_start: number; span_end: number; field_name: string;
  proposed_value: string; reviewed_value: string | null; outcome: 'pending' | 'accepted' | 'edited' | 'rejected';
  review_reason: string | null; generation_job_id: string | null; unit: string | null;
  recovery_of_proposal_id: string | null;
};
export type Clarification = {
  id: string; version: number; state: 'open' | 'resolved'; source_id: string;
  source_revision: number; proposal_id: string | null; field_name: string | null;
  assignee_id: string; reason: string; detail: string; page: number | null;
  span_start: number | null; span_end: number | null; resolution: string | null;
};
