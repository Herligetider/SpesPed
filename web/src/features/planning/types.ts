import type { ApiClient } from "../../api";
export type Props = {
  client: ApiClient;
  schoolId: string;
  learnerId: string;
  learnerName: string;
  currentUser: { id: string; display_name: string };
  language: "nb" | "nn";
  formatError: (error: unknown) => string;
};
export type Context = Props & { refresh: number; changed: () => void };
export type List<T> = { items: T[]; total: number };
export type Binding = {
  evidence_id: string;
  evidence_revision: number;
  link_id: string;
};
export type Evidence = {
  id: string;
  revision: number;
  content: string;
  certainty: string;
  reporter: string;
  occurred_at: string;
  source: {
    link_id: string;
    source_id: string;
    revision: number;
    page: number;
  };
};
export type Statement = {
  id: string;
  version: number;
  category: string;
  content: string | null;
  state: string;
  source_status: string;
  observed_at: string;
  confirmed_by: string | null;
  reviewed_at: string | null;
  source: Binding | null;
  review_reason: string | null;
};
export type SupportCase = {
  id: string;
  version: number;
  state: string;
  concern: string;
  owner_id: string;
  created_at?: string;
};
export type Period = { effective_from: string; effective_until: string };
export type Quantity = {
  amount: string | null;
  unit: "minutes" | "hours" | null;
  counting_basis: "learner_time" | "staff_time" | null;
};
export type Provision = Period &
  Quantity & {
    id?: string;
    decision_id?: string;
    decision_revision_id?: string;
    clause: string;
    category: string;
    subject: string;
    content: string;
    organization: string;
    competence: string;
    source: Binding;
  };
export type Recommendation = Period &
  Quantity & {
    id?: string;
    category: string;
    subject: string;
    content: string;
    source: Binding;
  };
export type Assessment = {
  id: string;
  version: number;
  issuer: string | null;
  assessment_at: string;
  valid_until: string | null;
  state: string;
  source_status: string;
  source: Binding | null;
  recommendations: Recommendation[];
};
export type Decision = {
  id: string;
  case_id: string;
  version: number;
  state: string;
  source_status: string;
  content: Period & {
    id: string;
    revision: number;
    state: string;
    issuing_authority?: string;
    authority_basis?: string;
    issued_at?: string;
    source?: Binding;
  };
  provisions: Provision[];
};
export type Goal = Period & {
  id?: string;
  goal_id?: string | null;
  parent_goal_id: string | null;
  status: "active" | "closed";
  title: string;
  expected_action: string;
  arena: string;
  support: string;
  responsibility: string;
  evaluation_method: string;
  curriculum_reference: string;
};
export type Adaptation = {
  id?: string;
  goal_id: string | null;
  measure: string;
  arena: string;
  responsibility: string;
  evaluation_method: string;
};
export type Contribution = {
  id?: string;
  goal_id: string | null;
  participant: string;
  role: "learner" | "guardian";
  content: string;
  disagreement: boolean;
  response: string;
  occurred_at: string;
  source: Binding;
};
export type Allocation = Period &
  Quantity & {
    id?: string;
    provision_id: string;
    decision_id: string;
    decision_revision_id: string;
  };
export type Approval = {
  approver: string;
  authority: string;
  approved_at: string;
  source: Binding;
};
export type PlanContent = Period & {
  id?: string;
  revision?: number;
  title: string;
  rationale: string;
  organization: string;
  responsibility: string;
  evaluation_method: string;
  participation_record: string;
  decision_id: string | null;
  decision_revision_id: string | null;
  origin: "authored" | "imported";
  sources: Binding[];
  original_approval: Approval | null;
  goals: Goal[];
  adaptations: Adaptation[];
  contributions: Contribution[];
  allocations: Allocation[];
  generation_lineage?: Record<string, unknown>;
};
export type Plan = {
  id: string;
  learner_id: string;
  kind: "individual_education" | "ordinary_teaching";
  version: number;
  state: string;
  current_revision: number;
  revision_state: string;
  content_digest: string;
  active_revision_id: string | null;
  source_status: string;
  content: PlanContent;
  clarifications: { code: string; message: string }[];
  approved_by?: string;
  approved_at?: string;
};
export type Option = {
  policy_id: string;
  release_id: string;
  label: string;
  model_version: string;
  reviewed_at: string;
};
export type Job = {
  id: string;
  version: number;
  state: string;
  error_code?: string;
  output?: unknown;
};
export type ProposalGoal = {
  proposal_key: string;
  target_goal_id: string | null;
  title: string;
  expected_action: string;
  arena: string;
  support: string;
  responsibility: string;
  evaluation_method: string;
};
export type Diff = {
  expected_version: number;
  plan_revision_id: string;
  basis_id: string;
  job_id: string;
  proposal_digest: string;
  fields: { field: string; before: string; proposed: string }[];
  goals: { proposal: ProposalGoal; before: Goal | null }[];
  missing_evidence: string[];
};
