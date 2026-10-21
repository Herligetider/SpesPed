import type { ApiClient } from "../../api";
export type SavedProposal = {
  id: string;
  version: number;
  state: string;
  attempts: number;
  created_at: string;
  updated_at: string;
  basis_id: string;
  availability: "current" | "review_required";
  review_outcome: string | null;
};
export type SavedPage = {
  items: SavedProposal[];
  total: number;
  manual_fallback_available: boolean;
  scope: "current_plan_revision" | "current_basis";
  plan_revision_id?: string;
  session_revision_id?: string;
};
export type JobStatus = {
  id: string;
  version: number;
  state: string;
  attempts: number;
  error_code: string | null;
};
export type VerifiedProposal<D> = {
  summary: SavedProposal;
  job?: JobStatus;
  diff?: D;
};
export type RecoveryConfig = {
  client: ApiClient;
  schoolId: string;
  learnerId: string;
  userId: string;
  ownerId: string;
  revisionId: string;
  basisId?: string;
  kind: "plan" | "teaching";
  refresh?: unknown;
  formatError: (error: unknown) => string;
  onConflict?: () => void;
  onReconciled?: (owner: unknown) => void;
};
export type Operation = {
  kind: "create" | "run" | "cancel" | "expire" | "review";
  path: readonly string[];
  body: Record<string, unknown>;
  jobId?: string;
  outcome?: string;
  diff?: unknown;
  onSuccess?: (value: unknown) => void;
};
export type ReadResult<T> = { value?: T; error?: unknown; loading: boolean };
