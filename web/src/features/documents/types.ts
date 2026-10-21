import type { ApiClient } from "../../api";
import type { Session } from "../../types";

export type DocumentWorkspaceProps = {
  client: ApiClient;
  schoolId: string;
  learnerId: string;
  currentUser: Session["user"];
  language: "nb" | "nn";
  formatError: (error: unknown) => string;
};

export type Source = {
  key: string;
  reference: { kind: string; id: string; revision: number };
  classification: string;
  value: Record<string, unknown>;
};
export type Section = {
  key: string;
  text: string | null;
  source_keys: string[];
  missing_inputs: string[];
};
export type Revision = {
  id: string;
  digest: string;
  number: number;
  configuration?: { purpose?: string; language?: string; length?: string; starts_on?: string; ends_on?: string; topics?: string[]; recipient_relationship_ids?: string[]; template_revision_id?: string | null; obligation_id?: string | null; selection?: Record<string, unknown> };
  content: { subject: string | null; sections: Section[]; handled_gaps: Record<string, string> } | null;
  source_status: string;
  source_changes: { state: string; late_sources?: Source[]; recalled_sources?: Source[]; content_withheld?: boolean };
  snapshot: { manifest: { entries: Source[]; gaps: string[]; period: { starts_on: string; ends_on: string }; template?: { state: string; content?: { title: string; sections: { key: string; label: string }[] } | null }; rule?: { state: string } | null } } | null;
  approval: { state: string; revision_id: string; digest: string } | null;
  missing_contributions?: string[];
};
export type DocumentCase = {
  id: string;
  learner_id: string;
  owner_id: string;
  kind: string;
  state: string;
  version: number;
  current_revision: number;
  revision_id: string;
  content_digest: string;
  revision: Revision;
  dispatch: { state: string; automatic_send: false };
};
export type Template = {
  id: string;
  version: number;
  state: string;
  revision_id: string;
  content_digest: string;
  reviewed: boolean;
  content: { kind: string; title: string; effective_from: string; effective_until: string; requirement_version_id?: string | null; sections: { key: string; label: string; required?: boolean }[] };
};
export type Schedule = {
  id: string;
  version: number;
  state: string;
  effective_state: string;
  next_run_at: string;
  next_period: { starts_on: string; ends_on: string };
  settings: Record<string, unknown>;
  runs: { status: string; summary: Record<string, unknown> }[];
};
export type Workspace = { documents: { items: DocumentCase[]; total: number }; schedules: Schedule[]; templates: Template[]; dispatch_history: string };
