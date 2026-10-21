import type { ApiClient } from "../../api";
export type WorkspaceProps = {
  client: ApiClient;
  schoolId: string;
  mode: "teaching" | "assistant";
  learnerId?: string;
  learnerName?: string;
  currentUser: { id: string; display_name: string };
  language: "nb" | "nn";
  formatError: (error: unknown) => string;
};
export type Page<T> = { items: T[]; total: number };
export type Person = { id: string; display_name: string };
export type Goal = {
  id: string;
  title: string;
  expected_action: string;
  arena: string;
  support: string;
  kind: string;
};
export type ProfileStatement = {
  id: string;
  state: string;
  source_status: string;
  content: string | null;
  category: string;
};
export type Evidence = {
  id: string;
  revision: number;
  content: string;
  reporter: string;
  certainty: string;
  occurred_at: string;
  source: { link_id: string; revision: number; page: number };
};
export type Step = { instruction: string; minutes: number };
export type SessionContent = {
  title: string;
  goal: string;
  preparation: string;
  materials: string[];
  steps: Step[];
  support: string;
  simplification: string;
  observation_focus: string;
};
export type SessionField = keyof SessionContent;
export type Session = {
  id: string;
  version: number;
  state: string;
  owner_id: string;
  revision_id: string;
  revision: number;
  basis_id: string;
  content_digest: string;
  content: SessionContent | null;
  source_status: string;
  approved: boolean;
  planned_at: string;
  duration_minutes: number;
  delivery_state: string;
  field_job_ids: Partial<Record<SessionField, string[]>>;
};
export type Basis = { id: string; source_status: string; basis: unknown };
export type BriefContent = {
  simple_goal: string;
  material_location: string;
  steps: string[];
  support: string;
  simplification: string;
  help_when: string;
  contact: string;
  training_guidance: string;
};
export type Brief = {
  id: string;
  version: number;
  state: string;
  session_revision_id: string;
  learner_id: string;
  content: BriefContent | null;
  content_digest: string;
  assignments?: Assignment[];
};
export type Assignment = {
  id: string;
  version: number;
  state: string;
  brief_state: string;
  learner_id: string;
  learner_name?: string;
  assistant_id?: string;
  assistant_name?: string;
  follow_up_owner_id: string;
  follow_up_owner_name?: string;
  planned_at: string;
  arena: string | null;
  role: string | null;
  valid_from: string;
  valid_until: string;
  content: BriefContent | null;
};
export type Message = {
  id: string;
  author_id: string;
  kind: string;
  text: string | null;
  created_at: string;
};
export type ActualContent = {
  occurred_at: string;
  duration_minutes: number;
  status: string;
  category: string;
  activity: string;
  support: string;
  difficulty: string;
};
export type ActualInput = {
  author_name?: string | null;
  id: string;
  version: number;
  state: string;
  occurred_at: string;
  content: ActualContent | null;
  currently_reconciled?: boolean;
  review_reason?: string | null;
  review_history?: {
    id: string;
    outcome: string;
    reason: string | null;
    historical: boolean;
    reviewed_at: string;
  }[];
};
export type Observation = {
  author_name?: string | null;
  id: string;
  revision_id: string;
  version: number;
  revision: number;
  state: string;
  confirmed: boolean;
  current: boolean;
  learner_id: string;
  occurred_at: string;
  author_id: string;
  session_revision_id: string | null;
  assignment_id: string | null;
  goal_revision_id: string | null;
  observation: string;
  support: string;
  interpretation: string | null;
  next_step: string | null;
  correction_reason: string | null;
};
export type FollowUp = {
  id: string;
  version: number;
  state: string;
  reason_code: string;
  owner_id: string;
  owner_name?: string;
  action: string | null;
  resolution: string | null;
  source_status: string;
};
export type Category =
  | "ordinary_teaching"
  | "individually_adapted_education"
  | "personal_assistance"
  | "physical_adaptation";
export type Participation = {
  learner_id: string;
  goal_revision_ids: string[];
  status: string;
  minutes: number;
  category: Category;
  support: string;
  support_status: "assessed" | "unassessed";
  support_assessment?: string;
  provision: null;
  counting_basis: null;
  attributed_staff_minutes: null;
};
export type StaffTime = {
  staff_id: string;
  minutes: number;
  role: string;
  category: Category;
};
export type Delivery = {
  id: string;
  version: number;
  revision: number;
  revision_id: string;
  session_revision_id: string | null;
  state: string;
  occurred_at: string;
  recorded_at: string;
  duration_minutes: number;
  activity: string | null;
  cause: string | null;
  cause_detail: string | null;
  participants: Participation[];
  staff: StaffTime[] | null;
  staff_minutes: number | null;
  correction_reason?: string | null;
};
export type Job = {
  id: string;
  version: number;
  state: string;
  error_code: string | null;
};
export type Diff = {
  expected_version: number;
  current_revision_id: string;
  job_id: string;
  changes: {
    field: SessionField;
    before: SessionContent[SessionField];
    proposed: SessionContent[SessionField];
    changed: boolean;
  }[];
  missing_evidence: string[];
  source_manifest: unknown[];
};
export const fields: { key: SessionField; label: string }[] = [
  { key: "title", label: "Tittel" },
  { key: "goal", label: "Mål for økten" },
  { key: "preparation", label: "Forberedelse" },
  { key: "materials", label: "Materiell" },
  { key: "steps", label: "Praktiske steg" },
  { key: "support", label: "Støtte" },
  { key: "simplification", label: "Avtalt forenkling" },
  { key: "observation_focus", label: "Observasjonspunkt" },
];
export const categories: Record<Category, string> = {
  ordinary_teaching: "Ordinær undervisning",
  individually_adapted_education: "Individuelt tilrettelagt opplæring",
  personal_assistance: "Personlig assistanse",
  physical_adaptation: "Fysisk tilrettelegging",
};
export const emptySession = (): SessionContent => ({
  title: "",
  goal: "",
  preparation: "",
  materials: [],
  steps: [{ instruction: "", minutes: 0 }],
  support: "",
  simplification: "",
  observation_focus: "",
});
