import type { ApiClient } from "../../api";
import type { Session } from "../../types";

export type GuardianPortalProps = {
  client: ApiClient;
  schoolId: string;
  currentUser: Session["user"];
  language: "nb" | "nn";
  formatError: (error: unknown) => string;
  timezone: string;
};

export type GuardianGrant = {
  id: string;
  version: number;
  state: string;
  created_at: string;
  expires_at: string;
};

export type GuardianPayload = {
  subject: string;
  body: string;
  attachments: { id: string; filename: string; content_type: string; size_bytes: number }[];
};
