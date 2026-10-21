import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api";
import type { ApiClient } from "../../api";
import type { Session } from "../../types";
import DocumentWorkspace from "./DocumentWorkspace";
import type { DocumentCase, Workspace } from "./types";

const actor = { id: "staff-1", email: "teacher@example.test", display_name: "Lærer" } satisfies Session["user"];
const empty: Workspace = { documents: { items: [], total: 0 }, schedules: [], templates: [], dispatch_history: "unavailable" };
function client(get = vi.fn().mockResolvedValue(empty), command = vi.fn()) { return { schools: vi.fn().mockResolvedValue([{ id: "school-1", name: "Skole", kind: "primary", timezone: "Europe/Oslo", role: "teacher" }]), schoolGet: (school: string, path: readonly string[], query?: URLSearchParams) => path.at(-1) === "suggestions" || path.at(-1) === "contribution-inbox" ? Promise.resolve({ items: [], total: 0 }) : path[0] === "documents" && path.includes("choices") ? Promise.resolve({ items: path.at(-1) === "owners" ? [{ user_id: "staff-1", display_name: "Lærer", purpose: "owner", action: "documents.write", state: "eligible", assignment_purpose: null }] : path.at(-1) === "guardians" ? [{ relationship_id: "guardian-link-1", guardian_user_id: "guardian-1", display_name: "Foresatt", version: 3, state: "eligible_proposal", disclosure: "not_authorized" }] : [], total: ["owners", "guardians"].includes(String(path.at(-1))) ? 1 : 0, offset: 0, limit: 100, period: { starts_on: query?.get("starts_on"), ends_on: query?.get("ends_on"), timezone: "Europe/Oslo", starts_at: "2026-01-01T00:00:00+01:00", ends_at_exclusive: "2026-10-22T00:00:00+02:00" } }) : get(school, path, query), schoolCommand: command } as unknown as ApiClient; }
function props(api: ApiClient, currentUser = actor, learnerId = "learner-1") { return { client: api, schoolId: "school-1", learnerId, currentUser, language: "nb" as const, formatError: (error: unknown) => error instanceof Error ? error.message : "Feil" }; }

describe("DocumentWorkspace", () => {
  it("calculates school-local dates across Oslo midnight and year boundaries", async () => {
    const { calendarDateInZone } = await import("./DocumentWorkspace");
    expect(calendarDateInZone(new Date("2026-12-31T23:30:00.000Z"), "Europe/Oslo")).toBe("2027-01-01");
    expect(calendarDateInZone(new Date("2026-12-31T23:30:00.000Z"), "America/Los_Angeles")).toBe("2026-12-31");
  });
  it("drops interval selections when the user changes inclusive dates", async () => {
    const observation = { reference: { kind: "observation", id: "obs-oct", revision: 1 }, label: "October observation", source_type: "observation", occurred_at: "2026-10-10T12:00:00Z", classification: "interval_fact", state: "current" };
    const baseApi = client();
    const api = { ...baseApi, schoolGet: (_school: string, path: readonly string[], query?: URLSearchParams) => {
      if (path[0] === "documents" && path.includes("choices") && path.at(-1) === "sources") { const items = query?.get("source_mode") === "interval" && query?.get("starts_on") === "2026-10-01" ? [observation] : []; return Promise.resolve({ items, total: items.length }); }
      if (path[0] === "documents" && path.includes("choices")) { const category = path.at(-1); const items = category === "owners" ? [{ user_id: "staff-1", display_name: "Lærer", purpose: "owner", action: "documents.write", state: "eligible", assignment_purpose: null }] : []; return Promise.resolve({ items, total: items.length }); }
      return Promise.resolve(empty);
    } } as unknown as ApiClient;
    const command = vi.fn().mockResolvedValue({});
    api.schoolCommand = command;
    render(<DocumentWorkspace {...props(api)} />);
    await screen.findByText("Ingen dokumenter er opprettet for eleven ennå.");
    fireEvent.change(screen.getByLabelText("Fra dato"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("Til dato"), { target: { value: "2026-10-15" } });
    await userEvent.click((await screen.findAllByLabelText(/October observation/))[0]);
    fireEvent.change(screen.getByLabelText("Fra dato"), { target: { value: "2026-12-01" } });
    fireEvent.change(screen.getByLabelText("Til dato"), { target: { value: "2026-12-15" } });
    await waitFor(() => expect(screen.queryAllByLabelText(/October observation/)).toHaveLength(0));
    await userEvent.click(screen.getByRole("button", { name: "Opprett utkast" }));
    await waitFor(() => expect(command).toHaveBeenCalledOnce());
    expect(command.mock.calls[0][2].selection.references).toEqual([]);
  });
  it("ignores stale contribution workspace responses after selecting a different assignment", async () => {
    const itemA = { document_id: "doc-A", revision_id: "rev-A", version: 1, kind: "report", title: "Rapport A", sections: [{ key: "summary", label: "Sammendrag", required: true }] };
    const itemB = { document_id: "doc-B", revision_id: "rev-B", version: 2, kind: "report", title: "Rapport B", sections: [{ key: "summary", label: "Sammendrag", required: true }] };
    let resolveA!: (value: unknown) => void; let resolveB!: (value: unknown) => void;
    const deferredA = new Promise((resolve) => { resolveA = resolve; }); const deferredB = new Promise((resolve) => { resolveB = resolve; });
    const api = { ...client(), schoolGet: (_school: string, path: readonly string[]) => path.at(-1) === "contribution-inbox" ? Promise.resolve({ items: [itemA, itemB], total: 2 }) : path.at(-1) === "contribution-workspace" ? (path.at(-2) === "doc-A" ? deferredA : deferredB) : path.at(-1) === "suggestions" ? Promise.resolve({ items: [], total: 0 }) : Promise.resolve(empty) } as unknown as ApiClient;
    const assigned = (id: string, text: string) => ({ id, learner_id: "learner-1", version: 1, revision_id: `rev-${id}`, content_digest: "a".repeat(64), assigned_sections: [{ key: "summary", text: null, source_keys: [], missing_inputs: [] }], sources: [], source_status: { state: "current" }, contributions: [{ section_key: "summary", kind: "submitted", text, source_keys: [] }], whole_document_access: "denied" });
    render(<DocumentWorkspace {...props(api)} />);
    await userEvent.click(await screen.findByRole("button", { name: /Rapport A/ }));
    await userEvent.click(screen.getByRole("button", { name: /Rapport B/ }));
    resolveB(assigned("doc-B", "B assignment text"));
    expect(await screen.findByDisplayValue("B assignment text")).toBeInTheDocument();
    resolveA(assigned("doc-A", "A stale assignment text"));
    await waitFor(() => expect(screen.queryByDisplayValue("A stale assignment text")).not.toBeInTheDocument());
    expect(screen.getByDisplayValue("B assignment text")).toBeInTheDocument();
  });
  it("creates a separately bounded inactive plan with school-local schedule time and interval cadence", async () => {
    const command = vi.fn().mockResolvedValue({});
    render(<DocumentWorkspace {...props(client(vi.fn().mockResolvedValue(empty), command))} />);
    await screen.findByText("Ingen dokumenter er opprettet for eleven ennå.");
    fireEvent.change(screen.getByLabelText("Første kjøring i skolens tidssone"), { target: { value: "2026-12-31T09:00" } });
    fireEvent.change(screen.getByLabelText("Planen slutter"), { target: { value: "2027-01-31T09:00" } });
    await userEvent.click(screen.getByLabelText("Foresatt"));
    await userEvent.click(screen.getByRole("button", { name: "Opprett inaktiv plan" }));
    await waitFor(() => expect(command).toHaveBeenCalledOnce());
    expect(command.mock.calls[0][1]).toEqual(["documents", "schedules"]);
    expect(command.mock.calls[0][2].settings).toMatchObject({ owner_id: "staff-1", recipient_relationship_ids: ["guardian-link-1"], first_run_at: "2026-12-31T08:00:00.000Z", ends_at: "2027-01-31T08:00:00.000Z", recurrence: "months", recurrence_count: 1, period_rule: "rolling_days", period_days: 14, generation_mode: "manual" });
  });
  it("renders schedule and recovery controls in Nynorsk", async () => {
    const scheduleWorkspace = { ...empty, schedules: [{ id: "schedule-nn", version: 2, state: "paused", effective_state: "paused", next_run_at: "2026-11-01T08:00:00Z", next_period: { starts_on: "2026-10-01", ends_on: "2026-10-31" }, settings: {}, runs: [{ status: "draft_created", summary: { manual_review_required: true } }] }] };
    const nnProps = { ...props(client(vi.fn().mockResolvedValue(scheduleWorkspace))), language: "nn" as const };
    render(<DocumentWorkspace {...nnProps} />);
    expect(await screen.findByRole("heading", { name: "Dokument og rapportar" })).toBeInTheDocument();
    await screen.findByText("Ingen dokument er oppretta for eleven enno.");
    expect(screen.getByRole("heading", { name: "Valfrie utkastplanar" })).toBeInTheDocument();
    expect(screen.getByLabelText("Første køyring i skulen si tidssone")).toBeInTheDocument();
    expect(screen.getByLabelText("Planen sluttar")).toBeInTheDocument();
    expect(screen.getByLabelText("Tal månader mellom utkast")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Opprett inaktiv utkastplan" })).toBeInTheDocument();
    expect(screen.getByText("Set på pause")).toBeInTheDocument();
    expect(screen.getByText(/Utkast oppretta/)).toBeInTheDocument();
    expect(screen.getByText(/Krev manuell kontroll/)).toBeInTheDocument();
  });
  it("renders assigned contribution workflow controls in Nynorsk", async () => {
    const item = { document_id: "doc-assigned", revision_id: "rev-assigned", version: 1, kind: "local_semester_report", title: "Halvårsrapport", sections: [{ key: "summary", label: "Samandrag", required: true }] };
    const contribution = { id: "doc-assigned", learner_id: "learner-1", version: 1, revision_id: "rev-assigned", content_digest: "a".repeat(64), assigned_sections: [{ key: "summary", text: null, source_keys: [], missing_inputs: [] }], sources: [], source_status: { state: "current" }, contributions: [], whole_document_access: "denied" };
    const api = { ...client(), schoolGet: (_school: string, path: readonly string[]) => path.at(-1) === "contribution-inbox" ? Promise.resolve({ items: [item], total: 1, offset: 0, limit: 50 }) : path.at(-1) === "contribution-workspace" ? Promise.resolve(contribution) : path.at(-1) === "suggestions" ? Promise.resolve({ items: [], total: 0, offset: 0, limit: 100 }) : path[0] === "documents" && path.includes("choices") ? Promise.resolve({ items: path.at(-1) === "owners" ? [{ user_id: "staff-1", display_name: "Lærer", purpose: "owner", action: "documents.write", state: "eligible", assignment_purpose: null }] : [], total: path.at(-1) === "owners" ? 1 : 0 }) : Promise.resolve(empty) } as unknown as ApiClient;
    render(<DocumentWorkspace {...{ ...props(api), language: "nn" as const }} />);
    await userEvent.click(await screen.findByRole("button", { name: /Halvårsrapport/ }));
    expect(await screen.findByRole("heading", { name: "Mine tildelte bidrag" })).toBeInTheDocument();
    expect(screen.getByText(/Du ser berre tildelte seksjonar/)).toBeInTheDocument();
    expect(screen.getByLabelText("Bidragstekst")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lever bidrag til denne seksjonen" })).toBeInTheDocument();
  });
  it("creates a real typed manual report for the selected calendar interval", async () => {
    const command = vi.fn().mockResolvedValue({});
    const api = client(vi.fn().mockResolvedValue(empty), command);
    render(<DocumentWorkspace {...props(api)} />);
    await screen.findByText("Ingen dokumenter er opprettet for eleven ennå.");
    fireEvent.change(screen.getByLabelText("Fra dato"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("Til dato"), { target: { value: "2026-10-15" } });
    fireEvent.change(screen.getAllByLabelText("Tekst")[0], { target: { value: "Gjennomgått manuelt." } });
    await userEvent.click(screen.getByRole("button", { name: "Opprett utkast" }));
    await waitFor(() => expect(command).toHaveBeenCalledOnce());
    expect(command.mock.calls[0][1]).toEqual(["documents", "cases"]);
    expect(command.mock.calls[0][2]).toMatchObject({ learner_id: "learner-1", owner_id: "staff-1", kind: "local_semester_report", starts_on: "2026-10-01", ends_on: "2026-10-15", content: { sections: [{ key: "summary", text: "Gjennomgått manuelt.", source_keys: [], missing_inputs: [] }, { key: "next_steps", text: null }] } });
    expect(command.mock.calls[0][2].request_key).toEqual(expect.any(String));
  });

  it("retains a failed command and editor text for same-key retry", async () => {
    const command = vi.fn().mockRejectedValueOnce(new ApiError("Ukjent svar", 0, "NETWORK_ERROR")).mockResolvedValueOnce({});
    const api = client(vi.fn().mockResolvedValue(empty), command);
    render(<DocumentWorkspace {...props(api)} />);
    await screen.findByText("Ingen dokumenter er opprettet for eleven ennå.");
    fireEvent.change(screen.getAllByLabelText("Tekst")[0], { target: { value: "Behold denne formuleringen" } });
    await userEvent.click(screen.getByRole("button", { name: "Opprett utkast" }));
    await screen.findByRole("alert");
    expect(screen.getAllByLabelText("Tekst")[0]).toHaveValue("Behold denne formuleringen");
    const originalKey = command.mock.calls[0][2].request_key;
    await userEvent.click(screen.getByRole("button", { name: "Prøv samme lagring igjen" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(2));
    expect(command.mock.calls[1][2]).toEqual(command.mock.calls[0][2]);
    expect(command.mock.calls[1][2].request_key).toBe(originalKey);
  });

  it("handles a stale revision as a reload-and-reapply conflict while preserving local prose", async () => {
    const doc = { id: "doc-1", learner_id: "learner-1", owner_id: "staff-1", kind: "ordinary_subject_assessment", state: "draft", version: 2, current_revision: 1, revision_id: "rev-1", content_digest: "digest", dispatch: { state: "not_requested", automatic_send: false }, revision: { id: "rev-1", number: 1, digest: "digest", configuration: { purpose: "assessment" }, content: { subject: "", sections: [{ key: "summary", text: "Gamle ord", source_keys: [], missing_inputs: [] }], handled_gaps: {} }, source_status: "current", source_changes: { state: "current" }, snapshot: { manifest: { entries: [], gaps: [], period: { starts_on: "2026-10-01", ends_on: "2026-10-15" } } }, approval: null } };
    const workspace = { ...empty, documents: { items: [doc], total: 1 } };
    const get = vi.fn((_school: string, path: readonly string[]) => Promise.resolve(path.at(-1) === "choices" ? { items: [], total: 0 } : workspace));
    const command = vi.fn().mockRejectedValue(new ApiError("Revisjonen er utdatert", 409, "document_conflict"));
    render(<DocumentWorkspace {...props(client(get, command))} />);
    await screen.findByText("Gamle ord");
    const textareas = screen.getAllByLabelText("Tekst");
    await userEvent.clear(textareas[0]);
    await userEvent.type(textareas[0], "Min lokale endring");
    await userEvent.click(screen.getByRole("button", { name: "Lagre ny revisjon" }));
    await screen.findByRole("alert");
    expect(screen.getAllByDisplayValue("Min lokale endring")).toHaveLength(1);
    expect(command.mock.calls[0][2]).toMatchObject({ expected_version: 2, reason: expect.any(String), document: { request_key: expect.any(String), learner_id: "learner-1", kind: "ordinary_subject_assessment", language: "nb", length: "standard", topics: [] } });
    await userEvent.click(screen.getAllByRole("button", { name: "Last inn på nytt" })[0]);
    await waitFor(() => expect(get.mock.calls.length).toBeGreaterThanOrEqual(3));
    expect(screen.getAllByDisplayValue("Min lokale endring")).toHaveLength(1);
  });

  it("uses fresh actor and pupil scope and ignores prior late workspace responses", async () => {
    let resolveOld!: (value: Workspace) => void;
    const prior = new Promise<Workspace>((resolve) => { resolveOld = resolve; });
    const oldGet = vi.fn().mockReturnValue(prior);
    const fresh: Workspace = { ...empty, documents: { items: [{ id: "new-doc", learner_id: "learner-2", owner_id: "staff-2", kind: "ordinary_subject_assessment", state: "draft", version: 1, current_revision: 1, revision_id: "rev", content_digest: "digest", dispatch: { state: "not_requested", automatic_send: false }, revision: { id: "rev", number: 1, digest: "digest", content: null, source_status: "unavailable", source_changes: { state: "unavailable", content_withheld: true }, snapshot: null, approval: null } }], total: 1 } };
    const nextGet = vi.fn((_school: string, path: readonly string[]) => Promise.resolve(path.at(-1) === "choices" ? { items: [], total: 0 } : fresh));
    const first = props(client(oldGet), actor, "learner-1");
    const view = render(<DocumentWorkspace {...first} />);
    view.rerender(<DocumentWorkspace {...props(client(nextGet), { ...actor, id: "staff-2" }, "learner-2")} />);
    expect(await screen.findByRole("button", { name: /ordinary_subject_assessment/ })).toBeInTheDocument();
    resolveOld({ ...empty, documents: { items: [], total: 0 } });
    await waitFor(() => expect(screen.getByRole("button", { name: /ordinary_subject_assessment/ })).toBeInTheDocument());
    expect(nextGet.mock.calls[0][1]).toEqual(["documents", "learners", "learner-2", "workspace"]);
  });

  it("clears previously loaded section prose when the source basis becomes unavailable", async () => {
    const good: DocumentCase = { id: "doc-1", learner_id: "learner-1", owner_id: "staff-1", kind: "ordinary_subject_assessment", state: "draft", version: 1, current_revision: 1, revision_id: "rev-1", content_digest: "digest", dispatch: { state: "not_requested", automatic_send: false }, revision: { id: "rev-1", number: 1, digest: "digest", configuration: { purpose: "assessment" }, content: { subject: "", sections: [{ key: "summary", text: "Sensitive old prose", source_keys: [], missing_inputs: [] }], handled_gaps: {} }, source_status: "current", source_changes: { state: "current" }, snapshot: { manifest: { entries: [], gaps: [], period: { starts_on: "2026-10-01", ends_on: "2026-10-15" } } }, approval: null } };
    const stale = { ...good, version: 2, revision: { ...good.revision, source_status: "unavailable", source_changes: { state: "unavailable", content_withheld: true }, content: null, snapshot: null } };
    let current = { ...empty, documents: { items: [good], total: 1 } };
    const get = vi.fn((_school: string, path: readonly string[]) => Promise.resolve(path.at(-1) === "choices" ? { items: [], total: 0 } : current));
    const api = client(get);
    render(<DocumentWorkspace {...props(api)} />);
    await screen.findByText("Sensitive old prose");
    current = { ...empty, documents: { items: [stale], total: 1 } };
    fireEvent.click(screen.getByRole("button", { name: /ordinary_subject_assessment/ }));
    await userEvent.click(screen.getAllByRole("button", { name: "Last inn på nytt" })[0]);
    await waitFor(() => expect(screen.queryByText("Sensitive old prose")).not.toBeInTheDocument());
    expect(screen.queryByDisplayValue("Sensitive old prose")).not.toBeInTheDocument();
  });

  it("clears protected prose and proposal state after a denied workspace refresh", async () => {
    const doc: DocumentCase = { id: "doc-secret", learner_id: "learner-1", owner_id: "staff-1", kind: "ordinary_subject_assessment", state: "draft", version: 1, current_revision: 1, revision_id: "rev-secret", content_digest: "digest", dispatch: { state: "not_requested", automatic_send: false }, revision: { id: "rev-secret", number: 1, digest: "digest", configuration: { purpose: "assessment" }, content: { subject: "Secret title", sections: [{ key: "summary", text: "Secret saved prose", source_keys: [], missing_inputs: [] }], handled_gaps: {} }, source_status: "current", source_changes: { state: "current" }, snapshot: { manifest: { entries: [], gaps: [], period: { starts_on: "2026-10-01", ends_on: "2026-10-15" } } }, approval: null } };
    const workspace = { ...empty, documents: { items: [doc], total: 1 } };
    let denied = false;
    const get = vi.fn((_school: string, path: readonly string[]) => {
      if (path.at(-1) === "choices") return Promise.resolve({ items: [], total: 0 });
      if (denied) return Promise.reject(new ApiError("Access denied", 403, "forbidden"));
      return Promise.resolve(workspace);
    });
    render(<DocumentWorkspace {...props(client(get))} />);
    await screen.findByText("Secret saved prose");
    fireEvent.change(screen.getAllByLabelText("Tekst")[0], { target: { value: "Unsaved editor text" } });
    denied = true;
    await userEvent.click(screen.getAllByRole("button", { name: "Last inn på nytt" })[0]);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Access denied"));
    expect(screen.queryByText("Secret saved prose")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("Unsaved editor text")).not.toBeInTheDocument();
    expect(screen.queryByText("Secret title")).not.toBeInTheDocument();
  });
  it("keeps new draft controls independent and submits selected revision configuration with nested retry key", async () => {
    const doc: DocumentCase = { id: "doc-typed", learner_id: "learner-1", owner_id: "staff-1", kind: "ordinary_subject_assessment", state: "draft", version: 3, current_revision: 2, revision_id: "rev-2", content_digest: "digest", dispatch: { state: "not_requested", automatic_send: false }, revision: { id: "rev-2", number: 2, digest: "digest", configuration: { purpose: "assessment", language: "nn", length: "detailed", topics: ["lesing"], recipient_relationship_ids: [], selection: { discover_evidence: false, discover_observations: false, references: [] } }, content: { subject: "Saved subject", sections: [{ key: "summary", text: "Saved exact prose", source_keys: [], missing_inputs: ["Needs human input"] }], handled_gaps: { "no_observations": "No confirmed observations were supplied" } }, source_status: "current", source_changes: { state: "current" }, snapshot: { manifest: { entries: [], gaps: ["no_observations"], period: { starts_on: "2026-10-01", ends_on: "2026-10-15" } } }, approval: null } };
    const workspace = { ...empty, documents: { items: [doc], total: 1 } };
    const get = vi.fn((_school: string, path: readonly string[]) => Promise.resolve(path.at(-1) === "choices" ? { items: [], total: 0 } : workspace));
    const command = vi.fn().mockRejectedValue(new ApiError("offline", 0, "NETWORK_ERROR"));
    render(<DocumentWorkspace {...props(client(get, command))} />);
    await screen.findByText("Saved exact prose");
    expect(await screen.findByDisplayValue("Saved exact prose")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Språk", { selector: "select" }), { target: { value: "nb" } });
    fireEvent.change(screen.getByLabelText("Forklaring for no observations"), { target: { value: "Reviewed gap without inventing evidence" } });
    await userEvent.type(screen.getByLabelText("Begrunnelse"), "Checked revision");
    await userEvent.click(screen.getByRole("button", { name: "Lagre ny revisjon" }));
    await screen.findByRole("alert");
    const payload = command.mock.calls[0][2];
    expect(payload.document).toMatchObject({ request_key: expect.any(String), purpose: "assessment", language: "nn", length: "detailed", topics: ["lesing"], starts_on: "2026-10-01", ends_on: "2026-10-15", content: { sections: [{ key: "summary", text: "Saved exact prose", missing_inputs: ["Needs human input"] }], handled_gaps: { no_observations: "Reviewed gap without inventing evidence" } } });
    const nestedKey = payload.document.request_key;
    await userEvent.click(screen.getByRole("button", { name: "Prøv samme lagring igjen" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(2));
    expect(command.mock.calls[1][2].document.request_key).toBe(nestedKey);
  });
  it("rebuilds a withheld revision from currently authorized sources without rendering prior prose", async () => {
    const source = { reference: { kind: "observation", id: "obs-current", revision: 4 }, label: "Current class note", source_type: "observation", occurred_at: "2026-10-12T10:00:00Z", classification: "interval_fact", state: "current" };
    const stale: DocumentCase = { id: "doc-withheld", learner_id: "learner-1", owner_id: "staff-1", kind: "ordinary_subject_assessment", state: "draft", version: 4, current_revision: 2, revision_id: "rev-stale", content_digest: "digest", dispatch: { state: "not_requested", automatic_send: false }, revision: { id: "rev-stale", number: 2, digest: "digest", configuration: { purpose: "assessment", language: "nn", length: "detailed", starts_on: "2026-10-01", ends_on: "2026-10-15", topics: ["reading"], selection: { discover_evidence: false, discover_observations: false, references: [] } }, content: null, source_status: "review_required", source_changes: { state: "review_required", content_withheld: true }, snapshot: null, approval: null } };
    const workspace = { ...empty, documents: { items: [stale], total: 1 } };
    const get = vi.fn((_school: string, path: readonly string[], query?: URLSearchParams) => {
      if (path.at(-1) === "recovery") return Promise.resolve({ document_id: stale.id, version: stale.version, revision_id: stale.revision.id, content_digest: stale.revision.digest, section_keys: ["summary", "next_steps"], generated_fields: [] });
      if (path[0] === "documents" && path.includes("choices") && path.at(-1) === "sources") { const items = query?.get("source_mode") === "interval" ? [source] : []; return Promise.resolve({ items, total: items.length }); }
      if (path[0] === "documents" && path.includes("choices")) { const items = path.at(-1) === "owners" ? [{ user_id: "staff-1", display_name: "Lærer", purpose: "owner", action: "documents.write", state: "eligible", assignment_purpose: null }] : []; return Promise.resolve({ items, total: items.length }); }
      return Promise.resolve(path.at(-1) === "suggestions" ? { items: [], total: 0 } : workspace);
    });
    const command = vi.fn().mockRejectedValue(new ApiError("offline", 0, "NETWORK_ERROR"));
    const api = { ...client(), schoolGet: get, schoolCommand: command } as unknown as ApiClient;
    render(<DocumentWorkspace {...props(api)} />);
    expect(await screen.findByText(/Kildegrunnlaget er endret eller utilgjengelig/)).toBeInTheDocument();
    expect(screen.queryByText("old secret prose")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Kontroller og bygg nytt kildegrunnlag" }));
    const panel = within(screen.getByRole("article"));
    const currentSourceLabels = await panel.findAllByLabelText(/Current class note/);
    await userEvent.click(currentSourceLabels.at(-1)!);
    fireEvent.change(panel.getAllByLabelText("Tekst")[0], { target: { value: "New review based on current note" } });
    await userEvent.click(currentSourceLabels[0]);
    await userEvent.type(panel.getByLabelText("Begrunnelse"), "Rebuilt from current source");
    expect(panel.getByRole("button", { name: "Lagre ny revisjon med gjeldende kilder" })).toBeEnabled();
    await userEvent.click(panel.getByRole("button", { name: "Lagre ny revisjon med gjeldende kilder" }));
    await waitFor(() => expect(command).toHaveBeenCalledOnce());
    const rebuilt = command.mock.calls[0][2].document;
    expect(rebuilt).toMatchObject({ request_key: expect.any(String), language: "nn", length: "detailed", topics: ["reading"], selection: { references: [{ kind: "observation", id: "obs-current", revision: 4 }] } });
    expect(rebuilt.content.sections[0]).toMatchObject({ key: "summary", text: "New review based on current note", source_keys: ["observation:obs-current:4"] });
  });
  it("requires an explicit human field selection before applying a local suggestion", async () => {
    const doc: DocumentCase = { id: "doc-ai", learner_id: "learner-1", owner_id: "staff-1", kind: "ordinary_subject_assessment", state: "draft", version: 1, current_revision: 1, revision_id: "rev-ai", content_digest: "digest", dispatch: { state: "not_requested", automatic_send: false }, revision: { id: "rev-ai", number: 1, digest: "digest", configuration: { purpose: "assessment" }, content: { subject: "Eget emne", sections: [{ key: "summary", text: "Egen tekst", source_keys: [], missing_inputs: [] }], handled_gaps: {} }, source_status: "current", source_changes: { state: "current" }, snapshot: { manifest: { entries: [], gaps: [], period: { starts_on: "2026-10-01", ends_on: "2026-10-15" } } }, approval: null } };
    const workspace = { ...empty, documents: { items: [doc], total: 1 } };
    const diff = { document_id: doc.id, revision_id: "rev-ai", expected_version: 1, job_id: "job-ai", proposal_digest: "f".repeat(64), before: doc.revision.content, proposed: { subject: "Nytt emne", sections: [{ key: "summary", text: "Foreslått tekst", missing_evidence: [] }], missing_evidence: [] }, source_manifest: [], requires_human_review: true };
    const get = vi.fn((_school: string, path: readonly string[]) => Promise.resolve(path.at(-1) === "choices" ? { items: [{ policy_id: "policy-1", release_id: "release-1", label: "Lokal modell", model_version: "v1", reviewed_at: "2026-10-01T00:00:00Z" }], total: 1 } : path.at(-1) === "diff" ? diff : workspace));
    const command = vi.fn().mockImplementation((_school, path: string[]) => Promise.resolve(path.at(-1) === "suggestions" ? { id: "job-ai" } : { ...doc, version: 2 }));
    render(<DocumentWorkspace {...props(client(get, command))} />);
    await screen.findByText("Egen tekst");
    await userEvent.selectOptions(screen.getByLabelText("Gjennomgått modell og lokal behandling"), "0");
    await userEvent.click(screen.getByRole("button", { name: "Bestill rapportforslag" }));
    await screen.findAllByText("Foreslått tekst");
    expect(command).toHaveBeenCalledTimes(1);
    expect(command.mock.calls[0][1]).toEqual(["documents", "cases", "doc-ai", "suggestions"]);
    expect(screen.getAllByText("Egen tekst").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByLabelText("Bruk denne seksjonen"));
    await userEvent.type(screen.getByLabelText("Begrunnelse"), "Jeg har kontrollert forslaget");
    await userEvent.click(screen.getByRole("button", { name: "Lagre valgte felt som ny revisjon" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(2));
    expect(command.mock.calls[1][1]).toEqual(["documents", "cases", "doc-ai", "suggestion-review"]);
    expect(command.mock.calls[1][2]).toMatchObject({ revision_id: "rev-ai", job_id: "job-ai", proposal_digest: "f".repeat(64), selected_sections: ["summary"], select_subject: false, outcome: "applied", reason: "Jeg har kontrollert forslaget" });
  });
  function recoveryDocument(id = "recovery-A", kind = "ordinary_subject_assessment", bad = true): DocumentCase {
    return { id, learner_id: "learner-1", owner_id: "staff-1", kind, state: "draft", version: 4, current_revision: 2, revision_id: `rev-${id}`, content_digest: "a".repeat(64), dispatch: { state: "not_requested", automatic_send: false }, revision: { id: `rev-${id}`, number: 2, digest: "a".repeat(64), configuration: { purpose: "assessment", language: "nn", length: "detailed", starts_on: "2026-10-01", ends_on: "2026-10-15", recipient_relationship_ids: kind === "guardian_email" ? ["guardian-link-1"] : [], selection: { discover_evidence: false, discover_observations: false, references: [], goals: [{ goal_revision_id: "old-goal", applicable_at: "2026-10-02T12:00:00Z" }], actual_revision_ids: ["withdrawn-actual"], future_plan_revision_ids: ["old-plan"] } }, content: { subject: `Prior subject ${id}`, sections: [{ key: "body", text: `Withheld prose ${id}`, source_keys: [], missing_inputs: ["professional_input_missing"] }], handled_gaps: {} }, source_status: bad ? "review_required" : "current", source_changes: { state: bad ? "review_required" : "current" }, snapshot: { manifest: { entries: [], gaps: ["no_confirmed_observations_in_selected_period"], period: { starts_on: "2026-10-01", ends_on: "2026-10-15" } } }, approval: null } };
  }
  function recoveryClient(documents: DocumentCase[], options: { templates?: Promise<unknown>; generatedFields?: string[]; currentTyped?: boolean; deniedCategories?: string[]; recovery?: Promise<unknown> } = {}) {
    const command = vi.fn().mockRejectedValue(new ApiError("offline", 0, "NETWORK_ERROR"));
    const api = { ...client(), schoolCommand: command, schoolGet: (_school: string, path: readonly string[], query?: URLSearchParams) => {
      if (path.at(-1) === "workspace") return Promise.resolve({ ...empty, documents: { items: documents, total: documents.length } });
      if (path.at(-1) === "recovery") { const doc = documents.find((document) => document.id === path.at(-2))!; return options.recovery ?? Promise.resolve({ document_id: doc.id, version: doc.version, revision_id: doc.revision.id, content_digest: doc.revision.digest, section_keys: ["body"], generated_fields: options.generatedFields ?? [] }); }
      if (path.includes("choices") && path[0] === "documents") {
        if (options.deniedCategories?.includes(String(path.at(-1)))) return Promise.reject(new ApiError("Source choices unavailable", 403, "forbidden"));
        if (path.at(-1) === "templates" && query?.get("kind") === documents[0].kind && options.templates) return options.templates;
        const items = path.at(-1) === "owners" ? [{ user_id: "staff-1", display_name: "Teacher", purpose: "owner", state: "eligible" }] : path.at(-1) === "guardians" ? [{ relationship_id: "guardian-link-1", display_name: "Guardian", state: "eligible_proposal" }] : options.currentTyped && path.at(-1) === "goals" ? [{ goal_revision_id: "new-goal", title: "Current historical goal", applicable_at: "2026-10-02T12:00:00Z" }] : options.currentTyped && path.at(-1) === "actuals" ? [{ delivery_revision_id: "new-actual", label: "Current actual delivery", classification: "actual_delivery_not_learning_progress" }] : options.currentTyped && path.at(-1) === "future_plans" ? [{ session_revision_id: "new-plan", title: "Current future plan", classification: "future_plan_not_actual" }] : [];
        return Promise.resolve({ items, total: items.length });
      }
      return Promise.resolve({ items: [], total: 0 });
    } } as unknown as ApiClient;
    return { api, command };
  }
  it.each([["ordinary_subject_assessment", false], ["ordinary_subject_assessment", true], ["guardian_email", false], ["guardian_email", true]] as const)("preserves dirty prose, reason and all gap explanations after late template response for %s (failure=%s)", async (kind, fails) => {
    let resolve!: (value: unknown) => void;
    let reject!: (error: unknown) => void;
    const templates = new Promise((yes, no) => { resolve = yes; reject = no; });
    const doc = recoveryDocument("late", kind, false);
    const { api, command } = recoveryClient([doc], { templates });
    render(<DocumentWorkspace {...props(api)} />);
    const panel = within(await screen.findByRole("article"));
    await panel.findByDisplayValue("Withheld prose late");
    fireEvent.change(panel.getByLabelText("Tekst"), { target: { value: "Unsaved independent edit" } });
    fireEvent.change(panel.getByLabelText("Begrunnelse"), { target: { value: "Professional reason" } });
    for (const field of panel.getAllByLabelText(/Forklaring for/)) fireEvent.change(field, { target: { value: "Human gap explanation" } });
    await act(async () => { if (fails) reject(new Error("Inventory temporarily unavailable")); else resolve({ items: [], total: 0 }); });
    expect(panel.getByLabelText("Tekst")).toHaveValue("Unsaved independent edit");
    expect(panel.getByLabelText("Begrunnelse")).toHaveValue("Professional reason");
    for (const field of panel.getAllByLabelText(/Forklaring for/)) expect(field).toHaveValue("Human gap explanation");
    fireEvent.click(panel.getByRole("button", { name: "Lagre ny revisjon" }));
    await waitFor(() => expect(command).toHaveBeenCalledOnce());
    expect(command.mock.calls[0][2]).toMatchObject({ reason: "Professional reason", document: { content: { sections: [{ key: "body", text: "Unsaved independent edit", missing_inputs: ["professional_input_missing"] }], handled_gaps: { no_confirmed_observations_in_selected_period: "Human gap explanation", professional_input_missing: "Human gap explanation" } } } });
  });
  it("scopes rebuilding to one exact document and withholds the next document's prior prose", async () => {
    const { api } = recoveryClient([recoveryDocument("A"), recoveryDocument("B")]);
    render(<DocumentWorkspace {...props(api)} />);
    const begin = await screen.findByRole("button", { name: "Kontroller og bygg nytt kildegrunnlag" });
    await waitFor(() => expect(begin).toBeEnabled()); fireEvent.click(begin);
    expect(within(screen.getByRole("article")).getByLabelText("Tekst")).toHaveValue("");
    fireEvent.click(screen.getAllByRole("button", { name: "ordinary_subject_assessment · 2" })[1]);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Lagre ny revisjon med gjeldende kilder" })).not.toBeInTheDocument());
    expect(screen.queryByDisplayValue("Withheld prose B")).not.toBeInTheDocument();
    expect(screen.queryByText("Prior subject B")).not.toBeInTheDocument();
    expect(within(screen.getByRole("article")).queryByLabelText("Tekst")).not.toBeInTheDocument();
  });
  it("saves an honest gap-only recovery and removes every obsolete typed dependency", async () => {
    const { api, command } = recoveryClient([recoveryDocument("recovery-A", "guardian_email")]);
    render(<DocumentWorkspace {...props(api)} />);
    const begin = await screen.findByRole("button", { name: "Kontroller og bygg nytt kildegrunnlag" });
    await waitFor(() => expect(begin).toBeEnabled()); fireEvent.click(begin);
    const panel = within(screen.getByRole("article"));
    fireEvent.change(panel.getByLabelText("Emne"), { target: { value: "Human review of missing observations" } });
    fireEvent.change(panel.getByLabelText("Tekst"), { target: { value: "No confirmed observations remain; further observation is needed." } });
    fireEvent.click(panel.getByRole("button", { name: "Lagre ny revisjon med gjeldende kilder" }));
    await waitFor(() => expect(command).toHaveBeenCalledOnce());
    expect(command.mock.calls[0][2].document.selection).toEqual({ references: [], background_references: [], goals: [], actual_revision_ids: [], future_plan_revision_ids: [], discover_evidence: false, discover_observations: false });
    expect(command.mock.calls[0][2].sever_generation_fields).toBeUndefined();
    expect(panel.getByLabelText("Tekst")).toHaveValue("No confirmed observations remain; further observation is needed.");
  });
  it("offers fresh historical goals, actual delivery and future plans as distinct choices", async () => {
    const { api, command } = recoveryClient([recoveryDocument()], { currentTyped: true });
    render(<DocumentWorkspace {...props(api)} />);
    const begin = await screen.findByRole("button", { name: "Kontroller og bygg nytt kildegrunnlag" });
    await waitFor(() => expect(begin).toBeEnabled()); fireEvent.click(begin);
    const panel = within(screen.getByRole("article"));
    fireEvent.click(panel.getByLabelText(/Current historical goal/)); fireEvent.click(panel.getByLabelText(/Current actual delivery/)); fireEvent.click(panel.getByLabelText(/Current future plan/));
    fireEvent.click(panel.getByRole("button", { name: "Lagre ny revisjon med gjeldende kilder" }));
    await waitFor(() => expect(command).toHaveBeenCalledOnce());
    expect(command.mock.calls[0][2].document.selection).toMatchObject({ goals: [{ goal_revision_id: "new-goal", applicable_at: "2026-10-02T12:00:00Z" }], actual_revision_ids: ["new-actual"], future_plan_revision_ids: ["new-plan"] });
  });
  it("requires explicit independent new text before severing unavailable AI field provenance", async () => {
    const doc = recoveryDocument("recovery-A", "guardian_email"); doc.revision.content = null; doc.revision.snapshot = null;
    const { api, command } = recoveryClient([doc], { generatedFields: ["body", "subject"] });
    render(<DocumentWorkspace {...props(api)} />);
    const begin = await screen.findByRole("button", { name: "Kontroller og bygg nytt kildegrunnlag" });
    await waitFor(() => expect(begin).toBeEnabled()); fireEvent.click(begin);
    const panel = within(screen.getByRole("article"));
    const save = panel.getByRole("button", { name: "Lagre ny revisjon med gjeldende kilder" });
    expect(save).toBeDisabled();
    fireEvent.click(panel.getByLabelText(/Jeg har skrevet en selvstendig erstatning for body/));
    fireEvent.click(panel.getByLabelText(/Jeg har skrevet en selvstendig erstatning for Emne/));
    expect(save).toBeDisabled();
    fireEvent.change(panel.getByLabelText("Tekst"), { target: { value: "Independent human authored new report." } });
    fireEvent.change(panel.getByLabelText("Emne"), { target: { value: "Independent human subject" } });
    expect(save).toBeEnabled(); fireEvent.click(save);
    await waitFor(() => expect(command).toHaveBeenCalledOnce());
    expect(command.mock.calls[0][2]).toMatchObject({ expected_version: 4, sever_generation_fields: ["body", "subject"], document: { content: { subject: "Independent human subject", sections: [{ key: "body", text: "Independent human authored new report." }] } } });
  });
  it("ignores recovery metadata from another revision instead of guessing generated fields", async () => {
    const { api } = recoveryClient([recoveryDocument()], { recovery: Promise.resolve({ document_id: "recovery-A", version: 3, revision_id: "obsolete", content_digest: "a".repeat(64), section_keys: ["body"], generated_fields: ["body"] }) });
    render(<DocumentWorkspace {...props(api)} />);
    await screen.findByText(/Grunnlaget er endret. Last inn dokumentet på nytt/);
    expect(screen.getByRole("button", { name: "Kontroller og bygg nytt kildegrunnlag" })).toBeDisabled();
  });

  it("allows a manual empty basis when optional goal and teaching inventories are denied", async () => {
    const { api, command } = recoveryClient([recoveryDocument()], { deniedCategories: ["goals", "actuals", "future_plans"] });
    render(<DocumentWorkspace {...props(api)} />);
    const begin = await screen.findByRole("button", { name: "Kontroller og bygg nytt kildegrunnlag" });
    await waitFor(() => expect(begin).toBeEnabled()); fireEvent.click(begin);
    const panel = within(screen.getByRole("article"));
    expect(panel.getByText(/Source choices unavailable/)).toBeInTheDocument();
    fireEvent.click(panel.getByRole("button", { name: "Lagre ny revisjon med gjeldende kilder" }));
    await waitFor(() => expect(command).toHaveBeenCalledOnce());
    expect(command.mock.calls[0][2].document.selection).toMatchObject({ goals: [], actual_revision_ids: [], future_plan_revision_ids: [] });
  });
  it("preserves generated provenance for unchanged text in an ordinary readable revision", async () => {
    const doc = recoveryDocument("generated-current", "guardian_email", false);
    doc.revision.lineage = { body: { job_id: "job-1", basis_id: "basis-1", proposal_digest: "a".repeat(64) } };
    const { api, command } = recoveryClient([doc]);
    render(<DocumentWorkspace {...props(api)} />);
    const panel = within(await screen.findByRole("article"));
    await panel.findByDisplayValue("Withheld prose generated-current");
    fireEvent.click(panel.getByLabelText(/Jeg har skrevet en selvstendig erstatning for body/));
    expect(panel.getByRole("button", { name: "Lagre ny revisjon" })).toBeDisabled();
    fireEvent.click(panel.getByLabelText(/Jeg har skrevet en selvstendig erstatning for body/));
    fireEvent.click(panel.getByRole("button", { name: "Lagre ny revisjon" }));
    await waitFor(() => expect(command).toHaveBeenCalledOnce());
    expect(command.mock.calls[0][2].sever_generation_fields).toBeUndefined();
  });

  it("discards a late AI diff when the same revision becomes source-withheld", async () => {
    const documents = [recoveryDocument("late-ai", "guardian_email", false)];
    const { api } = recoveryClient(documents);
    const originalGet = api.schoolGet.bind(api);
    let resolveDiff!: (value: unknown) => void;
    const pendingDiff = new Promise((resolve) => { resolveDiff = resolve; });
    api.schoolGet = vi.fn((_school: string, path: readonly string[], query?: URLSearchParams) => {
      if (path.at(-1) === "suggestions") return Promise.resolve({ items: [{ id: "job-late", state: "succeeded", availability: "current", created_at: "2026-10-01T00:00:00Z", reviews: [] }], total: 1 });
      if (path.at(-1) === "diff") return pendingDiff;
      return originalGet(_school, path, query);
    }) as ApiClient["schoolGet"];
    render(<DocumentWorkspace {...props(api)} />);
    await screen.findByText("Henter valgt forslag …");
    documents[0] = { ...documents[0], revision: { ...documents[0].revision, source_status: "unavailable", source_changes: { state: "unavailable", content_withheld: true }, content: null, snapshot: null } };
    fireEvent.click(screen.getAllByRole("button", { name: "Last inn på nytt" })[0]);
    await screen.findByText(/Gammel tekst holdes tilbake/);
    await act(async () => { resolveDiff({ document_id: documents[0].id, revision_id: documents[0].revision.id, expected_version: 4, job_id: "job-late", proposal_digest: "a".repeat(64), before: { subject: "Withheld prior subject", sections: [] }, proposed: { subject: "Late withheld AI subject", sections: [{ key: "body", text: "Late withheld AI prose", missing_evidence: [] }], missing_evidence: [] }, source_manifest: [], requires_human_review: true }); });
    expect(screen.queryByText("Late withheld AI prose")).not.toBeInTheDocument();
    expect(screen.queryByText("Withheld prior subject")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Lagre valgte felt som ny revisjon" })).not.toBeInTheDocument();
  });

});
