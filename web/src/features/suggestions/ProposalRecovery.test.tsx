import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import { ApiClient } from "../../api";
import PlanSuggestions from "../planning/PlanSuggestions";
import TeachingSuggestions from "../teaching/Suggestions";
import type { Plan, Context, Diff as PlanDiff } from "../planning/types";
import type {
  Session,
  SessionContent,
  Diff as TeachingDiff,
} from "../teaching/types";
import type { SavedProposal, SavedPage } from "./types";
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const content: SessionContent = {
  title: "Syntetisk lagret økt",
  goal: "Les kjente ord",
  preparation: "Kort",
  materials: ["Bildekort"],
  steps: [{ instruction: "Les ord", minutes: 5 }],
  support: "Lærerstøtte",
  simplification: "Ett ord",
  observation_focus: "Faktisk støtte",
};
const session = (id = "owner", revision = "rev-1"): Session => ({
  id,
  version: 1,
  state: "draft",
  owner_id: "teacher",
  revision_id: revision,
  revision: 1,
  basis_id: "basis",
  content_digest: "a".repeat(64),
  content,
  source_status: "current",
  approved: false,
  planned_at: "2026-10-22T08:00:00Z",
  duration_minutes: 25,
  delivery_state: "not_recorded",
  field_job_ids: {},
});
const plan = (id = "owner", revision = "rev-1"): Plan => ({
  id,
  learner_id: "learner",
  kind: "individual_education",
  version: 1,
  state: "draft",
  current_revision: 1,
  revision_state: "draft",
  content_digest: "a".repeat(64),
  active_revision_id: null,
  source_status: "current",
  clarifications: [],
  content: {
    id: revision,
    revision: 1,
    title: "Syntetisk IOP",
    rationale: "Bekreftet kilde",
    organization: "Klasserom",
    responsibility: "Lærer",
    evaluation_method: "Observer",
    participation_record: "Innspill avklares",
    effective_from: "2026-10-01T08:00:00Z",
    effective_until: "2027-06-01T08:00:00Z",
    decision_id: "decision",
    decision_revision_id: "decision-1",
    origin: "authored",
    original_approval: null,
    sources: [],
    goals: [],
    adaptations: [],
    contributions: [],
    allocations: [],
  },
});
const formatError = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
function common(client: ApiClient) {
  return {
    client,
    schoolId: "school",
    learnerId: "learner",
    learnerName: "Syntetisk elev",
    currentUser: { id: "teacher", display_name: "Syntetisk lærer" },
    language: "nb" as const,
    formatError,
  };
}
type Kind = "plan" | "teaching";
function job(id = "job-1", change: Partial<SavedProposal> = {}): SavedProposal {
  return {
    id,
    version: 1,
    state: "succeeded",
    attempts: 1,
    created_at: "2026-10-21T08:00:00Z",
    updated_at: "2026-10-21T08:01:00Z",
    basis_id: "basis",
    availability: "current",
    review_outcome: null,
    ...change,
  };
}
function page(
  kind: Kind,
  items: SavedProposal[],
  total = items.length,
  revision = "rev-1",
): SavedPage {
  return {
    items,
    total,
    scope: kind === "plan" ? "current_plan_revision" : "current_basis",
    ...(kind === "plan"
      ? { plan_revision_id: revision }
      : { session_revision_id: revision }),
    manual_fallback_available: true,
  };
}
function diff(
  kind: Kind,
  id = "job-1",
  revision = "rev-1",
  text = "Syntetisk forslag som må vurderes",
): PlanDiff | TeachingDiff {
  return kind === "plan"
    ? {
        expected_version: 1,
        plan_revision_id: revision,
        basis_id: "basis",
        job_id: id,
        proposal_digest: "b".repeat(64),
        fields: [{ field: "title", before: "Lagret tittel", proposed: text }],
        goals: [],
        missing_evidence: ["Elevinnspill må avklares"],
      }
    : {
        expected_version: 1,
        current_revision_id: revision,
        job_id: id,
        changes: [
          {
            field: "support",
            before: "Lagret støtte",
            proposed: text,
            changed: true,
          },
        ],
        missing_evidence: ["Elevinnspill må avklares"],
        source_manifest: [],
      };
}
function Screen({
  kind,
  client,
  owner = "owner",
  revision = "rev-1",
  saved = vi.fn(),
  hasUnsaved = false,
  onConflict = vi.fn(),
}: {
  kind: Kind;
  client: ApiClient;
  owner?: string;
  revision?: string;
  saved?: (value: never) => void;
  hasUnsaved?: boolean;
  onConflict?: () => void;
}) {
  return kind === "plan" ? (
    <PlanSuggestions
      ctx={{ ...common(client), refresh: 0, changed: onConflict } as Context}
      plan={plan(owner, revision)}
      onSaved={saved as (p: Plan) => void}
      hasUnsaved={hasUnsaved}
    />
  ) : (
    <TeachingSuggestions
      {...common(client)}
      mode="teaching"
      session={session(owner, revision)}
      draft={content}
      onSaved={saved as (s: Session) => void}
      onConflict={onConflict}
      hasUnsaved={hasUnsaved}
    />
  );
}
type Call = { url: URL; method: string; body: Record<string, unknown> };
function setup(
  kind: Kind,
  handler?: (call: Call) => Promise<Response> | Response | undefined,
) {
  const calls: Call[] = [];
  const jobs = [job()];
  const fetcher = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      const call = {
        url,
        method: init?.method || "GET",
        body: init?.body ? JSON.parse(String(init.body)) : {},
      };
      calls.push(call);
      const override = await handler?.(call);
      if (override) return override;
      if (url.pathname.endsWith("/ai/choices"))
        return response({
          items: [
            {
              policy_id: "policy",
              release_id: "release",
              label: "Gjennomgått lokal modell",
              model_version: "syntetisk",
              reviewed_at: "2026-10-20T08:00:00Z",
            },
          ],
          total: 1,
        });
      if (url.pathname.endsWith("/suggestions"))
        return response(page(kind, jobs));
      if (url.pathname.includes("/ai/jobs/"))
        return response({
          ...(jobs.find((j) => url.pathname.endsWith("/" + j.id)) || jobs[0]),
          error_code: null,
        });
      if (
        url.pathname.includes("/suggestions/") &&
        (url.pathname.endsWith("/diff") || kind === "plan")
      ) {
        const parts = url.pathname.split("/");
        return response(
          diff(kind, kind === "plan" ? parts.at(-1)! : parts.at(-2)!),
        );
      }
      if (url.pathname.endsWith("/owner"))
        return response(kind === "plan" ? plan() : session());
      return response({ items: [], total: 0 });
    },
  );
  return { client: new ApiClient(fetcher as typeof fetch), calls, jobs };
}
async function openFirst() {
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Åpne lagret forslag 1" }),
  );
  return user;
}
describe.each<Kind>(["plan", "teaching"])(
  "%s durable proposal recovery",
  (kind) => {
    it("recovers a persisted complete proposal after remount without creating or rerunning it", async () => {
      const e = setup(kind);
      const view = render(<Screen kind={kind} client={e.client} />);
      await openFirst();
      expect(
        await screen.findByText("Syntetisk forslag som må vurderes"),
      ).toBeVisible();
      view.unmount();
      render(<Screen kind={kind} client={e.client} />);
      await openFirst();
      expect(
        await screen.findByText("Syntetisk forslag som må vurderes"),
      ).toBeVisible();
      expect(e.calls.filter((c) => c.method !== "GET")).toHaveLength(0);
      expect(
        screen.queryByRole("button", { name: /Kjør lagret modelljobb/ }),
      ).not.toBeInTheDocument();
    });
    it("paginates actual saved proposal controls past one hundred", async () => {
      const e = setup(kind, (call) => {
        if (call.url.pathname.endsWith("/suggestions")) {
          const offset = Number(call.url.searchParams.get("offset") || 0),
            limit = Number(call.url.searchParams.get("limit") || 50);
          return response(
            page(
              kind,
              Array.from({ length: 103 }, (_, i) => job("job-" + i)).slice(
                offset,
                offset + limit,
              ),
              103,
            ),
          );
        }
      });
      render(<Screen kind={kind} client={e.client} />);
      const user = userEvent.setup();
      await user.click(
        await screen.findByRole("button", { name: "Neste forslagsside" }),
      );
      await screen.findByRole("button", { name: "Åpne lagret forslag 51" });
      await user.click(
        screen.getByRole("button", { name: "Neste forslagsside" }),
      );
      expect(
        await screen.findByRole("button", { name: "Åpne lagret forslag 103" }),
      ).toBeVisible();
      expect(e.calls.filter((c) => c.method !== "GET")).toHaveLength(0);
    });
    it("keeps reviewed, cancelled and unavailable binding states separate from completed execution", async () => {
      const rows = [
        job("reviewed", {
          review_outcome: kind === "plan" ? "discarded" : "rejected",
        }),
        job("cancelled", { state: "cancelled" }),
        job("recalled", { availability: "review_required" }),
      ];
      const e = setup(kind, (call) =>
        call.url.pathname.endsWith("/suggestions")
          ? response(page(kind, rows))
          : undefined,
      );
      render(<Screen kind={kind} client={e.client} />);
      const user = await openFirst();
      expect(await screen.findByText(/Lagret vurdering:/)).toBeVisible();
      await user.click(
        screen.getByRole("button", { name: "Åpne lagret forslag 2" }),
      );
      expect(
        await screen.findByText("Forslaget er avbrutt og kan ikke brukes."),
      ).toBeVisible();
      await user.click(
        screen.getByRole("button", { name: "Åpne lagret forslag 3" }),
      );
      expect(
        await screen.findByText(/Tidligere forslagstekst er skjult/),
      ).toBeVisible();
      expect(
        e.calls.filter((c) => c.url.pathname.includes("/ai/jobs/")),
      ).toHaveLength(0);
    });
    it("suppresses cached diff prose when the fresh job check fails after a recall", async () => {
      let recalled = false;
      const e = setup(kind, (call) =>
        call.url.pathname.includes("/ai/jobs/") && recalled
          ? response(
              {
                error: {
                  code: "configuration_changed",
                  message: "Modellen er trukket tilbake",
                },
              },
              503,
            )
          : undefined,
      );
      render(<Screen kind={kind} client={e.client} />);
      const user = await openFirst();
      expect(
        await screen.findByText("Syntetisk forslag som må vurderes"),
      ).toBeVisible();
      recalled = true;
      await user.click(
        screen.getByRole("button", {
          name: "Kontroller jobbstatus og forslag på nytt",
        }),
      );
      await screen.findByText(/Valgt forslag kan ikke vises nå/);
      for (const n of screen.queryAllByText(
        "Syntetisk forslag som må vurderes",
      ))
        expect(n).not.toBeVisible();
      expect(
        screen.queryByRole("button", {
          name:
            kind === "plan"
              ? "Lagre vurdering av forslaget"
              : "Bruk valgte felt i ny øktrevisjon",
        }),
      ).not.toBeInTheDocument();
    });
    it("does not show a late prior-owner revision or selected-job response", async () => {
      let finish!: (v: Response) => void;
      const e = setup(kind, (call) => {
        if (
          (kind === "plan" &&
            call.url.pathname.endsWith("/suggestions/job-1")) ||
          (kind === "teaching" &&
            call.url.pathname.endsWith("/suggestions/job-1/diff"))
        )
          return new Promise<Response>((resolve) => {
            finish = resolve;
          });
      });
      const view = render(<Screen kind={kind} client={e.client} />);
      await openFirst();
      await waitFor(() => expect(finish).toBeTypeOf("function"));
      view.rerender(<Screen kind={kind} client={e.client} revision="rev-2" />);
      await act(async () =>
        finish(response(diff(kind, "job-1", "rev-1", "Sent gammelt forslag"))),
      );
      expect(
        screen.queryByText("Sent gammelt forslag"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", {
          name: "Kontroller jobbstatus og forslag på nytt",
        }),
      ).not.toBeInTheDocument();
    });
    it("reconciles an unknown committed model-run response without rerunning the completed model", async () => {
      let state = "queued",
        version = 1,
        runs = 0;
      const e = setup(kind, (call) => {
        if (call.url.pathname.endsWith("/suggestions"))
          return response(
            page(kind, [job("job-1", { state, version, attempts: runs })]),
          );
        if (call.url.pathname.endsWith("/ai/jobs/job-1"))
          return response({
            ...job("job-1", { state, version, attempts: runs }),
            error_code: null,
          });
        if (call.url.pathname.endsWith("/run")) {
          runs++;
          state = "succeeded";
          version = 3;
          throw new TypeError("response dropped after commit");
        }
      });
      render(<Screen kind={kind} client={e.client} />);
      const user = await openFirst();
      await user.click(
        await screen.findByRole("button", { name: "Kjør lagret modelljobb" }),
      );
      await screen.findByText("Uavklart svar på lagringsforsøket");
      await user.click(
        screen.getByRole("button", { name: "Avklar mot lagret status" }),
      );
      expect(
        await screen.findByText(/Registrert jobbstatus: Kjøring fullført/),
      ).toBeVisible();
      expect(
        await screen.findByText("Syntetisk forslag som må vurderes"),
      ).toBeVisible();
      expect(runs).toBe(1);
      expect(
        screen.queryByRole("button", {
          name: "Gjenta det opprinnelige forsøket",
        }),
      ).not.toBeInTheDocument();
    });
  },
);

describe.each<Kind>(["plan", "teaching"])(
  "%s command reconciliation and isolation",
  (kind) => {
    it("opens a saved queued job after a lost create response without claiming the old request is identified", async () => {
      let created = false,
        creates = 0;
      const e = setup(kind, (call) => {
        if (call.url.pathname.endsWith("/suggestions")) {
          if (call.method === "POST") {
            created = true;
            creates++;
            throw new TypeError("created response lost");
          }
          return response(
            page(
              kind,
              created
                ? [job("saved-created", { state: "queued", attempts: 0 })]
                : [],
            ),
          );
        }
        if (call.url.pathname.endsWith("/ai/jobs/saved-created"))
          return response({
            ...job("saved-created", { state: "queued", attempts: 0 }),
            error_code: null,
          });
        if (call.url.pathname.endsWith("/generation-bases"))
          return response({ id: "basis", plan_revision_id: "rev-1" });
        if (call.url.pathname.endsWith("/support-cases"))
          return response({
            items: [{ id: "case", concern: "Syntetisk støttesak" }],
            total: 1,
          });
        if (call.url.pathname.endsWith("/expert-assessments"))
          return response({
            items: [
              {
                id: "assessment",
                issuer: "Syntetisk PPT",
                assessment_at: "2026-10-20T08:00:00Z",
                state: "confirmed",
                source_status: "current",
                recommendations: [],
              },
            ],
            total: 1,
          });
      });
      render(<Screen kind={kind} client={e.client} />);
      const user = userEvent.setup();
      if (kind === "plan") {
        await user.click(
          screen.getByText("Velg bekreftet grunnlag til forslaget"),
        );
        await user.click(
          await screen.findByRole("button", { name: "Syntetisk støttesak" }),
        );
        await user.click(
          await screen.findByRole("checkbox", { name: /Syntetisk PPT/ }),
        );
        await user.click(
          screen.getByRole("button", {
            name: "Lagre valgt grunnlag for denne revisjonen",
          }),
        );
        await user.selectOptions(
          screen.getByRole("combobox", {
            name: "Gjennomgått lokalt modellvalg",
          }),
          "policy:release",
        );
        await user.click(
          await screen.findByRole("button", {
            name: "Bestill forslag fra valgt grunnlag",
          }),
        );
      } else {
        await screen.findByRole("option", {
          name: /Gjennomgått lokal modell ·/,
        });
        await user.selectOptions(
          await screen.findByRole("combobox", {
            name: "Gjennomgått lokal modell og behandlingsoppsett",
          }),
          "0",
        );
        await user.click(
          screen.getByRole("button", { name: "Bestill forslag" }),
        );
      }
      await screen.findByText("Uavklart svar på lagringsforsøket");
      await user.click(
        screen.getByRole("button", { name: "Avklar mot lagret status" }),
      );
      await user.click(
        await screen.findByRole("button", { name: "Åpne lagret forslag 1" }),
      );
      await screen.findByText("Registrert kjøring: Venter på kjøring.");
      await user.click(
        screen.getByRole("button", {
          name: "Fortsett med valgt lagret forslag",
        }),
      );
      expect(
        await screen.findByText(
          /Dette bekrefter ikke utfallet av den tidligere bestillingen/,
        ),
      ).toBeVisible();
      expect(creates).toBe(1);
      expect(
        e.calls.filter(
          (call) =>
            call.url.pathname.endsWith("/run") && call.method === "POST",
        ),
      ).toHaveLength(0);
      expect(
        screen.getByRole("button", { name: "Kjør lagret modelljobb" }),
      ).toBeEnabled();
    });
    it("reconciles a committed review against durable consumer state without applying twice", async () => {
      let reviewed = false,
        reviews = 0;
      const saved = vi.fn();
      const e = setup(kind, (call) => {
        if (call.url.pathname.endsWith("/suggestions") && call.method === "GET")
          return response(
            page(
              kind,
              kind === "plan" && reviewed
                ? []
                : [
                    job("job-1", {
                      review_outcome: reviewed ? "accepted" : null,
                    }),
                  ],
              reviewed && kind === "plan" ? 0 : 1,
              reviewed ? "rev-2" : "rev-1",
            ),
          );
        if (
          (call.url.pathname.endsWith("/suggestions/review") ||
            call.url.pathname.endsWith("/suggestion-reviews")) &&
          call.method === "POST"
        ) {
          reviewed = true;
          reviews++;
          throw new TypeError("review response lost after commit");
        }
        if (
          call.url.pathname.endsWith("/suggestion-reviews") &&
          call.method === "GET"
        )
          return response({
            items: reviewed ? [{ job_id: "job-1", outcome: "applied" }] : [],
            total: reviewed ? 1 : 0,
          });
        if (call.url.pathname.endsWith("/owner"))
          return response(
            kind === "plan"
              ? plan("owner", reviewed ? "rev-2" : "rev-1")
              : session("owner", reviewed ? "rev-2" : "rev-1"),
          );
      });
      render(<Screen kind={kind} client={e.client} saved={saved} />);
      const user = await openFirst();
      await screen.findByText("Syntetisk forslag som må vurderes");
      await user.click(
        screen.getByRole("checkbox", {
          name: kind === "plan" ? "Ta inn foreslått tittel" : /Støtte · endret/,
        }),
      );
      if (kind === "plan")
        await user.type(
          screen.getByLabelText("Begrunnelse for vurdering av forslaget"),
          "Kontrollert kilde",
        );
      await user.click(
        screen.getByRole("button", {
          name:
            kind === "plan"
              ? "Lagre vurdering av forslaget"
              : "Bruk valgte felt i ny øktrevisjon",
        }),
      );
      await screen.findByText("Uavklart svar på lagringsforsøket");
      await user.click(
        screen.getByRole("button", { name: "Avklar mot lagret status" }),
      );
      expect(
        await screen.findByText(/En lagret vurdering er funnet:/),
      ).toBeVisible();
      expect(reviews).toBe(1);
      expect(
        screen.queryByRole("button", {
          name: "Gjenta det opprinnelige forsøket",
        }),
      ).not.toBeInTheDocument();
      if (kind === "teaching") expect(saved).toHaveBeenCalledOnce();
    });
    it("discards a late response for a previously selected job within the same owner", async () => {
      let resolveOld!: (value: Response) => void;
      const rows = [job("old-job"), job("new-job")];
      const e = setup(kind, (call) => {
        if (call.url.pathname.endsWith("/suggestions"))
          return response(page(kind, rows));
        if (call.url.pathname.includes("/ai/jobs/"))
          return response({
            ...rows.find((row) => call.url.pathname.endsWith("/" + row.id)),
            error_code: null,
          });
        if (
          (kind === "plan" &&
            call.url.pathname.endsWith("/suggestions/old-job")) ||
          (kind === "teaching" &&
            call.url.pathname.endsWith("/suggestions/old-job/diff"))
        )
          return new Promise<Response>((resolve) => {
            resolveOld = resolve;
          });
        if (
          (kind === "plan" &&
            call.url.pathname.endsWith("/suggestions/new-job")) ||
          (kind === "teaching" &&
            call.url.pathname.endsWith("/suggestions/new-job/diff"))
        )
          return response(
            diff(kind, "new-job", "rev-1", "Gjeldende valgt forslag"),
          );
      });
      render(<Screen kind={kind} client={e.client} />);
      const user = await openFirst();
      await waitFor(() => expect(resolveOld).toBeTypeOf("function"));
      await user.click(
        screen.getByRole("button", { name: "Åpne lagret forslag 2" }),
      );
      expect(await screen.findByText("Gjeldende valgt forslag")).toBeVisible();
      await act(async () =>
        resolveOld(
          response(
            diff(kind, "old-job", "rev-1", "Forsinket tidligere forslag"),
          ),
        ),
      );
      expect(
        screen.queryByText("Forsinket tidligere forslag"),
      ).not.toBeInTheDocument();
    });
  },
);

it("keeps a manual IOP editor open while reconciling a saved job, and prevents review from closing it", async () => {
  const { default: PlanWorkspace } = await import("../planning/PlanWorkspace");
  let state = "queued",
    version = 1;
  const e = setup("plan", (call) => {
    if (call.url.pathname.endsWith("/education-plans"))
      return response({ items: [plan()], total: 1 });
    if (call.url.pathname.endsWith("/revisions"))
      return response({ items: [plan()], total: 1 });
    if (call.url.pathname.endsWith("/suggestions"))
      return response(page("plan", [job("job-1", { state, version })]));
    if (call.url.pathname.endsWith("/ai/jobs/job-1"))
      return response({
        ...job("job-1", { state, version }),
        error_code: null,
      });
    if (call.url.pathname.endsWith("/run")) {
      state = "succeeded";
      version = 3;
      throw new TypeError("run reply lost");
    }
  });
  function Harness() {
    const [refresh, setRefresh] = useState(0);
    return (
      <PlanWorkspace
        ctx={
          {
            ...common(e.client),
            refresh,
            changed: () => setRefresh((n) => n + 1),
          } as Context
        }
        decision={null}
      />
    );
  }
  render(<Harness />);
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Åpne plan og revisjoner" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Rediger som ny revisjon" }),
  );
  await user.clear(screen.getByRole("textbox", { name: "Tittel" }));
  await user.type(
    screen.getByRole("textbox", { name: "Tittel" }),
    "Mitt selvstendige manuelle utkast",
  );
  await user.click(
    await screen.findByRole("button", { name: "Åpne lagret forslag 1" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Kjør lagret modelljobb" }),
  );
  await screen.findByText("Uavklart svar på lagringsforsøket");
  await user.click(
    screen.getByRole("button", { name: "Avklar mot lagret status" }),
  );
  await screen.findByText("Syntetisk forslag som må vurderes");
  expect(screen.getByRole("textbox", { name: "Tittel" })).toHaveValue(
    "Mitt selvstendige manuelle utkast",
  );
  expect(
    screen.getByRole("button", { name: "Lagre vurdering av forslaget" }),
  ).toBeDisabled();
  expect(
    e.calls.filter(
      (call) =>
        call.method === "POST" &&
        call.url.pathname.endsWith("/suggestion-reviews"),
    ),
  ).toHaveLength(0);
});

it("keeps running and expired-lease recovery honest, then explicitly retries the same unavailable job", async () => {
  let state = "running",
    version = 2,
    expired = false,
    runs = 0;
  const e = setup("teaching", (call) => {
    if (call.url.pathname.endsWith("/suggestions"))
      return response(
        page("teaching", [job("job-1", { state, version, attempts: 1 })]),
      );
    if (call.url.pathname.endsWith("/ai/jobs/job-1"))
      return response({
        ...job("job-1", { state, version, attempts: 1 }),
        error_code: null,
      });
    if (call.url.pathname.endsWith("/expire")) {
      if (!expired)
        return response(
          {
            error: {
              code: "job_not_expired",
              message: "Kjørefristen er ikke passert",
            },
          },
          409,
        );
      state = "unavailable";
      version = 3;
      return response({ id: "job-1", version, state });
    }
    if (call.url.pathname.endsWith("/run")) {
      runs++;
      state = "failed";
      version = 4;
      return response({
        ...job("job-1", { state, version, attempts: 2 }),
        error_code: "provider_unavailable",
      });
    }
  });
  render(<Screen kind="teaching" client={e.client} />);
  const user = await openFirst();
  await user.click(
    await screen.findByRole("button", {
      name: "Avklar utløpt kjøring hvis fristen er passert",
    }),
  );
  await screen.findByText(/Kjørefristen er ikke passert/);
  expect(
    screen.queryByRole("button", { name: "Kjør lagret modelljobb" }),
  ).not.toBeInTheDocument();
  expect(runs).toBe(0);
  expired = true;
  await user.click(
    screen.getByRole("button", {
      name: "Avklar utløpt kjøring hvis fristen er passert",
    }),
  );
  await user.click(
    await screen.findByRole("button", {
      name: "Prøv den samme lagrede modelljobben igjen",
    }),
  );
  expect(
    await screen.findByText("Registrert kjøring: Kjøring mislyktes."),
  ).toBeVisible();
  expect(runs).toBe(1);
  expect(
    e.calls.filter(
      (c) => c.method === "POST" && c.url.pathname.endsWith("/suggestions"),
    ),
  ).toHaveLength(0);
});

it("keeps the exact retry body for a committed create response and never silently creates a second logical request", async () => {
  let created = false;
  const writes: Record<string, unknown>[] = [];
  const e = setup("teaching", (call) => {
    if (call.url.pathname.endsWith("/suggestions")) {
      if (call.method === "POST") {
        writes.push(call.body);
        created = true;
        if (writes.length === 1) throw new TypeError("created reply lost");
        return response(job("saved-created", { state: "queued", attempts: 0 }));
      }
      return response(
        page(
          "teaching",
          created
            ? [job("saved-created", { state: "queued", attempts: 0 })]
            : [],
        ),
      );
    }
    if (call.url.pathname.endsWith("/ai/jobs/saved-created"))
      return response({
        ...job("saved-created", { state: "queued", attempts: 0 }),
        error_code: null,
      });
  });
  render(<Screen kind="teaching" client={e.client} />);
  const user = userEvent.setup();
  await screen.findByRole("option", { name: /Gjennomgått lokal modell ·/ });
  await user.selectOptions(
    screen.getByRole("combobox", {
      name: "Gjennomgått lokal modell og behandlingsoppsett",
    }),
    "0",
  );
  await user.click(screen.getByRole("button", { name: "Bestill forslag" }));
  await screen.findByText("Uavklart svar på lagringsforsøket");
  await user.click(
    screen.getByRole("button", { name: "Gjenta det opprinnelige forsøket" }),
  );
  await screen.findByText("Registrert kjøring: Venter på kjøring.");
  expect(writes).toHaveLength(2);
  expect(writes[0]).toEqual(writes[1]);
  expect(
    e.calls.filter(
      (c) => c.method === "POST" && c.url.pathname.endsWith("/run"),
    ),
  ).toHaveLength(0);
});

it("hides old diff text when the owner-list boundary changes despite a successful job read", async () => {
  let revision = "rev-1";
  const e = setup("teaching", (call) =>
    call.url.pathname.endsWith("/suggestions")
      ? response(page("teaching", [job()], 1, revision))
      : undefined,
  );
  render(<Screen kind="teaching" client={e.client} />);
  const user = await openFirst();
  expect(
    await screen.findByText("Syntetisk forslag som må vurderes"),
  ).toBeVisible();
  revision = "rev-2";
  await user.click(
    screen.getByRole("button", {
      name: "Kontroller jobbstatus og forslag på nytt",
    }),
  );
  await screen.findByText(/Valgt forslag kan ikke vises nå/);
  for (const node of screen.queryAllByText("Syntetisk forslag som må vurderes"))
    expect(node).not.toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Bruk valgte felt i ny øktrevisjon" }),
  ).not.toBeInTheDocument();
});

describe.each(["plan", "teaching"] as const)(
  "%s recalled running lease",
  (kind) => {
    it("uses fresh owner metadata without reading recalled prose, handles an early deadline and reconciles a committed expiry", async () => {
      let state = "running",
        version = 2,
        expires = 0;
      const e = setup(kind, (call) => {
        if (call.url.pathname.endsWith("/suggestions"))
          return response(
            page(kind, [
              job("job-1", { state, version, availability: "review_required" }),
            ]),
          );
        if (call.url.pathname.endsWith("/expire")) {
          expires++;
          expect(call.body).toEqual({ expected_version: 2 });
          if (expires === 1)
            return response(
              {
                error: {
                  code: "job_not_expired",
                  message: "Kjørefristen er ikke passert",
                },
              },
              409,
            );
          state = "unavailable";
          version = 3;
          throw new TypeError("expiry committed, response lost");
        }
        if (call.url.pathname.includes("/ai/jobs/"))
          throw new Error("recalled prose must never be requested");
      });
      const conflict = vi.fn();
      render(<Screen kind={kind} client={e.client} onConflict={conflict} />);
      const user = await openFirst();
      const expire = () =>
        screen.getByRole("button", {
          name: "Avklar utløpt kjøring hvis fristen er passert",
        });
      await user.click(
        await screen.findByRole("button", {
          name: "Avklar utløpt kjøring hvis fristen er passert",
        }),
      );
      await screen.findByText(/Kjørefristen er ikke passert/);
      expect(expire()).toBeEnabled();
      expect(conflict).not.toHaveBeenCalled();
      await user.click(expire());
      await screen.findByText("Uavklart svar på lagringsforsøket");
      await user.click(
        screen.getByRole("button", { name: "Avklar mot lagret status" }),
      );
      await screen.findByText("Registrert kjøring: Kjøring utilgjengelig.");
      expect(
        screen.queryByRole("button", {
          name: "Gjenta det opprinnelige forsøket",
        }),
      ).not.toBeInTheDocument();
      expect(
        e.calls.filter(
          (c) => c.url.pathname.includes("/ai/jobs/") && c.method === "GET",
        ),
      ).toHaveLength(0);
      expect(
        e.calls.filter((c) => c.url.pathname.endsWith("/run")),
      ).toHaveLength(0);
      expect(
        e.calls.filter(
          (c) => c.method === "POST" && c.url.pathname.endsWith("/expire"),
        ),
      ).toHaveLength(2);
      expect(
        screen.queryByText("Syntetisk forslag som må vurderes"),
      ).not.toBeInTheDocument();
    });
  },
);

it("refuses recalled lease expiry if the fresh owner row changed since selection", async () => {
  let version = 2;
  const e = setup("teaching", (call) => {
    if (call.url.pathname.endsWith("/suggestions"))
      return response(
        page("teaching", [
          job("job-1", {
            state: "running",
            version,
            availability: "review_required",
          }),
        ]),
      );
  });
  render(<Screen kind="teaching" client={e.client} />);
  const user = await openFirst();
  const button = await screen.findByRole("button", {
    name: "Avklar utløpt kjøring hvis fristen er passert",
  });
  version = 3;
  await user.click(button);
  await screen.findByText(
    "Den lagrede kjørestatusen er endret. Kontroller status før du avklarer kjørefristen.",
  );
  expect(e.calls.filter((c) => c.method === "POST")).toHaveLength(0);
});

it("keeps a retry from an already failed job uncertain when persisted version has not changed", async () => {
  const failed = job("job-1", { state: "failed", version: 4 });
  const e = setup("teaching", (call) => {
    if (call.url.pathname.endsWith("/suggestions"))
      return response(page("teaching", [failed]));
    if (call.url.pathname.endsWith("/ai/jobs/job-1")) return response(failed);
    if (call.url.pathname.endsWith("/run"))
      throw new TypeError("unknown retry reply");
  });
  render(<Screen kind="teaching" client={e.client} />);
  const user = await openFirst();
  await user.click(
    await screen.findByRole("button", {
      name: "Prøv den samme lagrede modelljobben igjen",
    }),
  );
  await screen.findByText("Uavklart svar på lagringsforsøket");
  await user.click(
    screen.getByRole("button", { name: "Avklar mot lagret status" }),
  );
  await screen.findByText(
    "Utfallet er fortsatt uavklart. Det opprinnelige forsøket er bevart.",
  );
  expect(
    screen.getByRole("button", { name: "Gjenta det opprinnelige forsøket" }),
  ).toBeEnabled();
  expect(
    e.calls.filter(
      (c) => c.method === "POST" && c.url.pathname.endsWith("/run"),
    ),
  ).toHaveLength(1);
});

describe.each(["plan", "teaching"] as const)(
  "%s combined recovery reads",
  (kind) => {
    it("keeps exact recall metadata authoritative over a successful diff computed before recall", async () => {
      let refreshing = false;
      let releasePage!: (value: Response) => void;
      let releaseDiff!: (value: Response) => void;
      const e = setup(kind, (call) => {
        if (
          call.url.pathname.endsWith("/suggestions") &&
          call.method === "GET"
        ) {
          if (refreshing && call.url.searchParams.get("limit") === "50")
            return new Promise<Response>((resolve) => {
              releasePage = resolve;
            });
          return response(page(kind, [job()]));
        }
        if (
          refreshing &&
          ((kind === "plan" &&
            call.url.pathname.endsWith("/suggestions/job-1")) ||
            (kind === "teaching" &&
              call.url.pathname.endsWith("/suggestions/job-1/diff")))
        )
          return new Promise<Response>((resolve) => {
            releaseDiff = resolve;
          });
      });
      render(<Screen kind={kind} client={e.client} />);
      const user = await openFirst();
      await screen.findByText("Syntetisk forslag som må vurderes");
      refreshing = true;
      await user.click(
        screen.getByRole("button", {
          name: "Kontroller jobbstatus og forslag på nytt",
        }),
      );
      await waitFor(() => {
        expect(releasePage).toBeTypeOf("function");
        expect(releaseDiff).toBeTypeOf("function");
      });
      await act(async () =>
        releasePage(
          response(
            page(kind, [job("job-1", { availability: "review_required" })]),
          ),
        ),
      );
      expect(
        await screen.findByText(
          /Grunnlaget eller modellvalget må vurderes på nytt/,
        ),
      ).toBeVisible();
      await act(async () => releaseDiff(response(diff(kind))));
      expect(
        screen.queryByText("Syntetisk forslag som må vurderes"),
      ).not.toBeVisible();
      expect(
        screen.queryByRole("button", {
          name:
            kind === "plan"
              ? "Lagre vurdering av forslaget"
              : "Bruk valgte felt i ny øktrevisjon",
        }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByText(/Tidligere forslagstekst er skjult/),
      ).toBeVisible();
    });

    it("does not deny a selected proposal merely because another pagination page omits it", async () => {
      const rows = Array.from({ length: 101 }, (_, index) =>
        job(index ? `other-${index}` : "job-1"),
      );
      const e = setup(kind, (call) => {
        if (call.url.pathname.endsWith("/suggestions")) {
          const offset = Number(call.url.searchParams.get("offset")),
            limit = Number(call.url.searchParams.get("limit"));
          return response(
            page(kind, rows.slice(offset, offset + limit), rows.length),
          );
        }
      });
      render(<Screen kind={kind} client={e.client} />);
      const user = await openFirst();
      await screen.findByText("Syntetisk forslag som må vurderes");
      await user.click(
        screen.getByRole("button", { name: "Neste forslagsside" }),
      );
      await screen.findByRole("button", { name: "Åpne lagret forslag 51" });
      expect(
        screen.getByText("Syntetisk forslag som må vurderes"),
      ).toBeVisible();
      expect(
        screen.getByRole("button", {
          name:
            kind === "plan"
              ? "Lagre vurdering av forslaget"
              : "Bruk valgte felt i ny øktrevisjon",
        }),
      ).toBeVisible();
    });

    it("resolves a lost run reply after recall from exact changed metadata without opening output or rerunning", async () => {
      let recalled = false,
        runs = 0;
      const e = setup(kind, (call) => {
        if (call.url.pathname.endsWith("/suggestions"))
          return response(
            page(kind, [
              job(
                "job-1",
                recalled
                  ? {
                      state: "succeeded",
                      version: 3,
                      availability: "review_required",
                    }
                  : { state: "queued", version: 1, attempts: 0 },
              ),
            ]),
          );
        if (call.url.pathname.endsWith("/run")) {
          recalled = true;
          runs++;
          throw new TypeError("committed run reply lost before recall");
        }
        if (call.url.pathname.endsWith("/ai/jobs/job-1")) {
          if (recalled)
            throw new Error("recalled job output must never be read");
          return response(
            job("job-1", { state: "queued", version: 1, attempts: 0 }),
          );
        }
      });
      render(<Screen kind={kind} client={e.client} />);
      const user = await openFirst();
      await user.click(
        await screen.findByRole("button", { name: "Kjør lagret modelljobb" }),
      );
      await screen.findByText("Uavklart svar på lagringsforsøket");
      const readsBefore = e.calls.filter(
        (call) =>
          call.method === "GET" && call.url.pathname.includes("/ai/jobs/"),
      ).length;
      await user.click(
        screen.getByRole("button", { name: "Avklar mot lagret status" }),
      );
      await screen.findByText(
        /Registrert jobbstatus: Kjøring fullført.*beviser ikke hvem/,
      );
      expect(
        screen.queryByText("Uavklart svar på lagringsforsøket"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByText("Syntetisk forslag som må vurderes"),
      ).not.toBeInTheDocument();
      expect(
        e.calls.filter(
          (call) =>
            call.method === "GET" && call.url.pathname.includes("/ai/jobs/"),
        ),
      ).toHaveLength(readsBefore);
      expect(runs).toBe(1);
    });
  },
);
