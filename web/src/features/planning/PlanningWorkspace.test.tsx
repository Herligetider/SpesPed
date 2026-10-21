import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeAll, afterAll } from "vitest";
import { ApiClient } from "../../api";
import { SuggestionDiff } from "./PlanSuggestions";
import { useState } from "react";
import PlanningWorkspace from "./PlanningWorkspace";
import PlanEditor, { blankPlan } from "./PlanEditor";
import PlanWorkspace from "./PlanWorkspace";
import type { Context, Diff, Plan, Props } from "./types";
import { localChoices, localInstant, localValue } from "./shared";
beforeAll(() => vi.stubEnv("TZ", "Europe/Oslo"));
afterAll(() => vi.unstubAllEnvs());
const response = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const props = (client: ApiClient): Props => ({
  client,
  schoolId: "school-a",
  learnerId: "pupil-a",
  learnerName: "Syntetisk elev",
  currentUser: { id: "teacher-a", display_name: "Syntetisk lærer" },
  language: "nb",
  formatError: (e) => (e instanceof Error ? e.message : String(e)),
});
const context = (client: ApiClient): Context => ({
  ...props(client),
  refresh: 0,
  changed: vi.fn(),
});
function fixture(): Plan {
  const content = blankPlan();
  Object.assign(content, {
    id: "revision-a",
    revision: 1,
    title: "Syntetisk plan",
    rationale: "Bekreftet behov",
    organization: "Klasserom",
    responsibility: "Lærer",
    evaluation_method: "Observasjon",
    participation_record: "Innspill er ikke innhentet ennå",
    effective_from: "2026-10-01T07:00:00Z",
    effective_until: "2027-06-30T13:00:00Z",
  });
  Object.assign(content.goals[0], {
    title: "Les kjente ord",
    expected_action: "Les tre kjente ord",
    arena: "Klasserom",
    support: "Bildekort",
    responsibility: "Lærer",
    evaluation_method: "Observer ord lest",
    curriculum_reference: "Lokal læreplan",
    effective_from: content.effective_from,
    effective_until: content.effective_until,
  });
  return {
    id: "plan-a",
    learner_id: "pupil-a",
    kind: "ordinary_teaching",
    version: 1,
    state: "draft",
    current_revision: 1,
    revision_state: "draft",
    content_digest: "a".repeat(64),
    active_revision_id: null,
    source_status: "current",
    content,
    clarifications: [],
  };
}
describe("planning workspace invariants", () => {
  it("suppresses previous scope prose synchronously and ignores a late response after learner/client changes", async () => {
    let finish!: (r: Response) => void;
    const client = new ApiClient(
      vi.fn(async (input) => {
        const url = String(input);
        if (url.includes("pupil-a/support-profile"))
          return response({
            items: [
              {
                id: "s",
                category: "strength",
                content: "Privat gammel profil",
                state: "confirmed",
                source_status: "current",
                observed_at: "2026-01-01T00:00:00Z",
                reviewed_at: null,
                source: null,
              },
            ],
            total: 1,
          });
        if (url.includes("pupil-b/support-profile"))
          return new Promise<Response>((r) => {
            finish = r;
          });
        return response({ items: [], total: 0 });
      }),
    );
    const { rerender } = render(<PlanningWorkspace {...props(client)} />);
    expect(await screen.findByText("Privat gammel profil")).toBeVisible();
    rerender(
      <PlanningWorkspace
        {...props(client)}
        learnerId="pupil-b"
        learnerName="Ny elev"
      />,
    );
    expect(screen.queryByText("Privat gammel profil")).not.toBeInTheDocument();
    const other = new ApiClient(
      vi.fn(async () => response({ items: [], total: 0 })),
    );
    rerender(<PlanningWorkspace {...props(other)} learnerId="pupil-b" />);
    await act(async () =>
      finish(
        response({
          items: [
            {
              id: "late",
              category: "strength",
              content: "Sent gammelt svar",
              state: "confirmed",
              source_status: "current",
            },
          ],
          total: 1,
        }),
      ),
    );
    expect(screen.queryByText("Sent gammelt svar")).not.toBeInTheDocument();
  });
  it("preserves immutable command and freezes fields until an ambiguous save is retried", async () => {
    const user = userEvent.setup();
    const writes: unknown[] = [];
    const client = new ApiClient(
      vi.fn(async (_input, init) => {
        if (init?.method === "POST") {
          writes.push(JSON.parse(String(init.body)));
          if (writes.length === 1)
            throw new TypeError("connection interrupted");
          return response(fixture());
        }
        return response({ items: [], total: 0 });
      }),
    );
    const done = vi.fn();
    render(
      <PlanEditor
        ctx={context(client)}
        initial={fixture()}
        onSaved={done}
        onClose={() => {}}
      />,
    );
    await user.clear(screen.getByLabelText("Tittel"));
    await user.type(screen.getByLabelText("Tittel"), "Eget bevart utkast");
    await user.click(
      screen.getByRole("button", { name: "Lagre ny planrevisjon" }),
    );
    expect(
      await screen.findByText(/Lagringen har et uavklart svar/),
    ).toBeVisible();
    expect(screen.getByLabelText("Tittel")).toBeDisabled();
    await user.click(
      screen.getByRole("button", { name: "Avklar ved å gjenta samme forsøk" }),
    );
    await waitFor(() => expect(done).toHaveBeenCalledOnce());
    expect(writes).toHaveLength(2);
    expect(writes[0]).toEqual(writes[1]);
    expect(writes[0]).toMatchObject({
      expected_version: 1,
      title: "Eget bevart utkast",
      origin: "authored",
      original_approval: null,
    });
  });
  it("keeps a conflict draft and only rebases expected version after an explicit comparison choice", async () => {
    const user = userEvent.setup();
    const writes: Record<string, unknown>[] = [];
    const client = new ApiClient(
      vi.fn(async (_input, init) => {
        if (init?.method === "POST") {
          writes.push(JSON.parse(String(init.body)));
          return response(
            {
              error: {
                code: "revision_conflict",
                message: "En annen har lagret",
              },
            },
            409,
          );
        }
        return response({ items: [], total: 0 });
      }),
    );
    const p = fixture();
    const ctx = context(client);
    const { rerender } = render(
      <PlanEditor
        ctx={ctx}
        initial={p}
        latest={p}
        onSaved={() => {}}
        onClose={() => {}}
      />,
    );
    await user.clear(screen.getByLabelText("Tittel"));
    await user.type(screen.getByLabelText("Tittel"), "Mitt konfliktutkast");
    await user.click(
      screen.getByRole("button", { name: "Lagre ny planrevisjon" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Utkastet er bevart",
    );
    const latest = {
      ...p,
      version: 2,
      content: { ...p.content, title: "Annen lærers endring", revision: 2 },
    };
    rerender(
      <PlanEditor
        ctx={ctx}
        initial={p}
        latest={latest}
        onSaved={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByLabelText("Tittel")).toHaveValue("Mitt konfliktutkast");
    await user.click(
      screen.getByRole("button", { name: /Jeg har sammenlignet/ }),
    );
    await user.click(
      screen.getByRole("button", { name: "Lagre ny planrevisjon" }),
    );
    await waitFor(() => expect(writes).toHaveLength(2));
    expect(writes[1]).toMatchObject({
      expected_version: 2,
      title: "Mitt konfliktutkast",
    });
    expect(writes[0].request_key).not.toEqual(writes[1].request_key);
  });
  it("keeps manual plan work available when ancillary generation reads are forbidden and recalled prose is hidden", async () => {
    const user = userEvent.setup();
    const p = fixture();
    p.source_status = "review_required";
    p.content = { id: "revision-a", revision: 1 } as Plan["content"];
    const client = new ApiClient(
      vi.fn(async (input) => {
        const url = String(input);
        if (url.includes("/education-plans/plan-a/revisions"))
          return response({ items: [p], total: 1 });
        if (url.endsWith("/education-plans/plan-a")) return response(p);
        if (url.includes("/education-plans?"))
          return response({ items: [p], total: 1 });
        if (url.includes("/ai/"))
          return response(
            {
              error: { code: "access_denied", message: "Ingen modelltilgang" },
            },
            403,
          );
        return response({ items: [], total: 0 });
      }),
    );
    render(<PlanWorkspace ctx={context(client)} decision={null} />);
    await user.click(
      await screen.findByRole("button", { name: "Åpne plan og revisjoner" }),
    );
    expect(
      await screen.findByText(/Tidligere kildetekst og modelltekst er skjult/),
    ).toBeVisible();
    expect(screen.queryByText("Les kjente ord")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Opprett plan" }));
    expect(screen.getByLabelText("Tittel")).toBeEnabled();
  });
  it("reaches profile records beyond one hundred without exposing a raw identifier field", async () => {
    const user = userEvent.setup();
    const offsets: string[] = [];
    const client = new ApiClient(
      vi.fn(async (input) => {
        const url = new URL(String(input), "http://test");
        if (url.pathname.endsWith("support-profile")) {
          const offset = url.searchParams.get("offset") || "0";
          offsets.push(offset);
          return response({
            items: [
              {
                id: "s" + offset,
                category: "strength",
                content: "Syntetisk profil " + offset,
                state: "confirmed",
                source_status: "current",
                source: null,
              },
            ],
            total: 151,
          });
        }
        return response({ items: [], total: 0 });
      }),
    );
    render(<PlanningWorkspace {...props(client)} />);
    await screen.findByText("Syntetisk profil 0");
    await user.click(
      screen
        .getAllByRole("button", { name: "Neste side" })
        .find((b) => !(b as HTMLButtonElement).disabled)!,
    );
    await screen.findByText("Syntetisk profil 50");
    await user.click(
      screen
        .getAllByRole("button", { name: "Neste side" })
        .find((b) => !(b as HTMLButtonElement).disabled)!,
    );
    expect(await screen.findByText("Syntetisk profil 100")).toBeVisible();
    expect(offsets).toEqual(["0", "50", "100"]);
    expect(
      screen.queryByLabelText(/UUID|evidence_id|learner_id/),
    ).not.toBeInTheDocument();
  });
  it("converts explicitly entered local instants and rejects impossible local dates", () => {
    expect(localInstant("2026-10-21T14:30")).toBe(
      new Date(2026, 9, 21, 14, 30).toISOString(),
    );
    expect(() => localInstant("2026-02-30T14:30")).toThrow();
  });
});

const proposalFixture = (): Diff => ({
  expected_version: 3,
  plan_revision_id: "revision-a",
  basis_id: "basis-a",
  job_id: "job-a",
  proposal_digest: "b".repeat(64),
  fields: [
    { field: "title", before: "Original plan", proposed: "Foreslått tittel" },
  ],
  goals: [
    {
      before: null,
      proposal: {
        proposal_key: "new-reading",
        target_goal_id: null,
        title: "Nytt lesemål",
        expected_action: "Les kjente ord",
        arena: "Klasserom",
        support: "Bildekort",
        responsibility: "Lærer",
        evaluation_method: "Observer ord",
      },
    },
  ],
  missing_evidence: ["Elevinnspill må avklares"],
});
describe("proposal selection and editor refresh", () => {
  it("requires human dates and curriculum for a selected new goal and applies only selected content", async () => {
    const user = userEvent.setup(),
      writes: Record<string, unknown>[] = [];
    const client = new ApiClient(
      vi.fn(async (_input, init) => {
        if (init?.method === "POST") {
          writes.push(JSON.parse(String(init.body)));
          return response(fixture());
        }
        return response(proposalFixture());
      }),
    );
    render(
      <SuggestionDiff
        ctx={context(client)}
        plan={fixture()}
        basisId="basis-a"
        job={{ id: "job-a", version: 1, state: "succeeded" }}
        onSaved={() => {}}
      />,
    );
    expect(await screen.findByText("Elevinnspill må avklares")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Lagre vurdering av forslaget" }),
    ).toBeDisabled();
    await user.click(screen.getByLabelText("Ta inn dette målforslaget"));
    expect(screen.getByLabelText("Gyldig fra (lokal dato og tid)")).toHaveValue(
      "",
    );
    expect(
      screen.getByLabelText("Fagpersonens læreplanreferanse for nytt mål"),
    ).toHaveValue("");
    await user.type(
      screen.getByLabelText("Fagpersonens læreplanreferanse for nytt mål"),
      "Lokal lesereferanse",
    );
    await user.type(
      screen.getByLabelText("Gyldig fra (lokal dato og tid)"),
      "2026-10-22T09:00",
    );
    await user.type(
      screen.getByLabelText("Gyldig til, ikke inkludert (lokal dato og tid)"),
      "2027-06-20T14:00",
    );
    await user.type(
      screen.getByLabelText("Begrunnelse for vurdering av forslaget"),
      "Nytt mål kontrollert manuelt",
    );
    await user.click(
      screen.getByRole("button", { name: "Lagre vurdering av forslaget" }),
    );
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({
      expected_version: 3,
      plan_revision_id: "revision-a",
      basis_id: "basis-a",
      job_id: "job-a",
      selected_fields: [],
      selected_goal_keys: ["new-reading"],
      new_goals: [
        {
          proposal_key: "new-reading",
          curriculum_reference: "Lokal lesereferanse",
          effective_from: localInstant("2026-10-22T09:00"),
          effective_until: localInstant("2027-06-20T14:00"),
        },
      ],
    });
  });
  it("can reject a partly selected proposal without inventing dates or applying its text", async () => {
    const user = userEvent.setup(),
      writes: Record<string, unknown>[] = [];
    const client = new ApiClient(
      vi.fn(async (_input, init) => {
        if (init?.method === "POST") {
          writes.push(JSON.parse(String(init.body)));
          return response(fixture());
        }
        return response(proposalFixture());
      }),
    );
    render(
      <SuggestionDiff
        ctx={context(client)}
        plan={fixture()}
        basisId="basis-a"
        job={{ id: "job-a", version: 1, state: "succeeded" }}
        onSaved={() => {}}
      />,
    );
    await user.click(await screen.findByLabelText("Ta inn dette målforslaget"));
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Hva vil du gjøre med forslaget" }),
      "rejected",
    );
    await user.type(
      screen.getByLabelText("Begrunnelse for vurdering av forslaget"),
      "Manglende faktisk medvirkning",
    );
    await user.click(
      screen.getByRole("button", { name: "Lagre vurdering av forslaget" }),
    );
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0]).toMatchObject({
      outcome: "rejected",
      selected_fields: [],
      selected_goal_keys: [],
      new_goals: [],
    });
  });
  it("preserves an edited draft while the current plan is reloaded for conflict comparison", async () => {
    const user = userEvent.setup();
    let p = fixture();
    const client = new ApiClient(
      vi.fn(async (input) => {
        const url = String(input);
        if (url.includes("/education-plans/plan-a/revisions"))
          return response({ items: [p], total: 1 });
        if (url.endsWith("/education-plans/plan-a")) return response(p);
        if (url.includes("/education-plans?"))
          return response({ items: [p], total: 1 });
        return response({ items: [], total: 0 });
      }),
    );
    function Harness() {
      const [refresh, setRefresh] = useState(0);
      return (
        <PlanWorkspace
          ctx={{
            ...context(client),
            refresh,
            changed: () => setRefresh((n) => n + 1),
          }}
          decision={null}
        />
      );
    }
    render(<Harness />);
    await user.click(
      await screen.findByRole("button", { name: "Åpne plan og revisjoner" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Rediger som ny revisjon" }),
    );
    await user.clear(screen.getByLabelText("Tittel"));
    await user.type(
      screen.getByLabelText("Tittel"),
      "Utkast som skal overleve kildekontroll",
    );
    p = {
      ...p,
      version: 2,
      content: { ...p.content, title: "Ny konkurrerende plan", revision: 2 },
    };
    await user.click(
      screen.getByRole("button", {
        name: "Hent gjeldende plan og kildekontroll",
      }),
    );
    expect(
      await screen.findByRole("button", { name: /Jeg har sammenlignet/ }),
    ).toBeVisible();
    expect(screen.getByLabelText("Tittel")).toHaveValue(
      "Utkast som skal overleve kildekontroll",
    );
  });
});

describe("optional model access", () => {
  it("does not block otherwise authorized IOP reading or manual editing on an ancillary403", async () => {
    const user = userEvent.setup();
    const p = fixture();
    p.kind = "individual_education";
    const client = new ApiClient(
      vi.fn(async (input) => {
        const url = String(input);
        if (url.includes("/education-plans/plan-a/revisions"))
          return response({ items: [p], total: 1 });
        if (url.endsWith("/education-plans/plan-a")) return response(p);
        if (url.includes("/education-plans?"))
          return response({ items: [p], total: 1 });
        if (url.includes("/ai/choices"))
          return response(
            {
              error: { code: "access_denied", message: "Ingen modelltilgang" },
            },
            403,
          );
        return response({ items: [], total: 0 });
      }),
    );
    render(<PlanWorkspace ctx={context(client)} decision={null} />);
    await user.click(
      await screen.findByRole("button", { name: "Åpne plan og revisjoner" }),
    );
    expect(
      await screen.findByText(/Gjennomgåtte modellvalg er ikke tilgjengelige/),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Rediger som ny revisjon" }),
    );
    expect(screen.getByLabelText("Tittel")).toHaveValue("Syntetisk plan");
    expect(screen.getByLabelText("Tittel")).toBeEnabled();
  });
});

describe("exact source period timestamps", () => {
  it("round trips unchanged imported seconds and milliseconds without shifting entitlement periods", () => {
    for (const instant of [
      "2026-10-21T07:15:37.456Z",
      "2026-10-21T07:15:37Z",
      "2027-03-28T01:15:12.123Z",
    ]) {
      expect(localInstant(localValue(instant))).toBe(
        new Date(instant).toISOString(),
      );
    }
  });
  it("requires explicit repeated-clock occurrence and preserves an existing exact occurrence", () => {
    if (Intl.DateTimeFormat().resolvedOptions().timeZone !== "Europe/Oslo")
      return;
    const values = localChoices("2026-10-25T02:30");
    expect(values).toEqual([
      "2026-10-25T00:30:00.000Z",
      "2026-10-25T01:30:00.000Z",
    ]);
    expect(() => localInstant("2026-10-25T02:30")).toThrow(/to ganger/);
    expect(localInstant("2026-10-25T02:30@" + values[1])).toBe(values[1]);
    expect(localInstant(localValue(values[1]))).toBe(values[1]);
    expect(() => localInstant("2026-03-29T02:30")).toThrow();
  });
});

it("preserves imported microseconds beyond browser input precision until the user edits that time", () => {
  const source = "2026-10-21T07:15:37.123456Z";
  expect(localInstant(localValue(source))).toBe(source);
  expect(localInstant(localValue(source).split("@")[0])).toBe(
    "2026-10-21T07:15:37.123Z",
  );
});

it("submits an untouched imported late fold with microseconds through valid native form controls", async () => {
  if (Intl.DateTimeFormat().resolvedOptions().timeZone !== "Europe/Oslo")
    throw new Error("Run this regression with TZ=Europe/Oslo");
  const user = userEvent.setup(),
    writes: Record<string, unknown>[] = [];
  const instant = "2026-10-25T01:30:00.123456Z",
    p = fixture();
  p.kind = "individual_education";
  p.content.effective_from = instant;
  p.content.goals[0].effective_from = instant;
  p.content.decision_id = "decision-a";
  p.content.decision_revision_id = "decision-revision-a";
  p.content.allocations = [
    {
      provision_id: "provision-a",
      decision_id: "decision-a",
      decision_revision_id: "decision-revision-a",
      amount: "100",
      unit: "hours",
      counting_basis: "learner_time",
      effective_from: instant,
      effective_until: p.content.effective_until,
    },
  ];
  const client = new ApiClient(
    vi.fn(async (_input, init) => {
      if (init?.method === "POST") {
        writes.push(JSON.parse(String(init.body)));
        return response(p);
      }
      return response({ items: [], total: 0 });
    }),
  );
  render(
    <PlanEditor
      ctx={context(client)}
      initial={p}
      onSaved={() => {}}
      onClose={() => {}}
    />,
  );
  const folds = screen.getAllByRole("combobox", {
    name: /Gjentatt klokkeslett/,
  }) as HTMLSelectElement[];
  expect(folds).toHaveLength(3);
  for (const fold of folds) {
    expect(fold.value).toBe(instant);
    expect(fold.selectedOptions[0].textContent).toContain("Andre forekomst");
    expect(fold.checkValidity()).toBe(true);
    expect([...fold.options].map((option) => option.value)).toEqual([
      "",
      "2026-10-25T00:30:00.123456Z",
      instant,
    ]);
  }
  const title = screen.getByRole("textbox", { name: "Tittel" });
  await user.clear(title);
  await user.type(title, "Bare tittel er endret");
  const form = title.closest("form")!;
  expect(form.checkValidity()).toBe(true);
  await user.click(
    screen.getByRole("button", { name: "Lagre ny planrevisjon" }),
  );
  await waitFor(() => expect(writes).toHaveLength(1));
  expect(writes[0]).toMatchObject({
    effective_from: instant,
    goals: [{ effective_from: instant }],
    allocations: [{ effective_from: instant }],
    title: "Bare tittel er endret",
  });
});

describe("independent history reauthorization", () => {
  it.each(["failed current read", "stale successful current read"])(
    "hides recalled current prose on %s while authorized manual history remains readable",
    async (mode) => {
      const user = userEvent.setup();
      const p = fixture();
      p.content.id = "generated-revision";
      p.content.revision = 3;
      p.current_revision = 3;
      p.content.title = "Privat gammel modelltekst";
      p.content.rationale = "Privat gammel modellbegrunnelse";
      const manual = structuredClone(p);
      manual.content = {
        ...manual.content,
        id: "manual-revision",
        revision: 1,
        title: "Uavhengig manuelt grunnlag",
        rationale: "Bekreftet manuelt grunnlag",
      };
      let recalled = false;
      const client = new ApiClient(
        vi.fn(async (input) => {
          const url = String(input);
          if (url.includes("/education-plans/plan-a/revisions")) {
            const redacted = {
              ...p,
              source_status: "review_required",
              content: { id: p.content.id, revision: 3 },
            };
            if (new URL(url, "http://test").searchParams.get("limit") === "1")
              return response({ items: [p], total: 3 });
            return response({
              items: [recalled ? redacted : p, manual],
              total: 3,
            });
          }
          if (url.endsWith("/education-plans/plan-a")) {
            if (recalled && mode === "failed current read")
              throw new TypeError("lost current response");
            return response(p);
          }
          if (url.includes("/education-plans?"))
            return response({
              items: [
                recalled
                  ? {
                      ...p,
                      source_status: "review_required",
                      content: { id: p.content.id, revision: 3 },
                    }
                  : p,
              ],
              total: 1,
            });
          return response({ items: [], total: 0 });
        }),
      );
      function Harness() {
        const [refresh, setRefresh] = useState(0);
        return (
          <PlanWorkspace
            ctx={{
              ...context(client),
              refresh,
              changed: () => setRefresh((n) => n + 1),
            }}
            decision={null}
          />
        );
      }
      render(<Harness />);
      await user.click(
        await screen.findByRole("button", { name: "Åpne plan og revisjoner" }),
      );
      await user.click(
        await screen.findByText("Revisjonshistorikk og sammenligning"),
      );
      await user.selectOptions(
        await screen.findByRole("combobox", {
          name: "Velg revisjon som skal sammenlignes med gjeldende",
        }),
        "manual-revision",
      );
      expect(
        await screen.findByRole("heading", {
          name: "Uavhengig manuelt grunnlag · revisjon 1",
        }),
      ).toBeVisible();
      expect(
        screen.getAllByRole("heading", {
          name: "Privat gammel modelltekst · revisjon 3",
        }),
      ).toHaveLength(2);
      recalled = true;
      await user.click(
        screen.getAllByRole("button", {
          name: "Hent gjeldende plan og kildekontroll",
        })[0],
      );
      await waitFor(() =>
        expect(
          screen.queryAllByRole("heading", {
            name: "Privat gammel modelltekst · revisjon 3",
          }),
        ).toHaveLength(0),
      );
      expect(
        await screen.findByRole("heading", {
          name: "Uavhengig manuelt grunnlag · revisjon 1",
        }),
      ).toBeVisible();
      for (const node of screen.queryAllByText(
        "Privat gammel modellbegrunnelse",
      ))
        expect(node).not.toBeVisible();
      expect(
        screen.getByText(
          /Gjeldende revisjon er ikke kontrollert mot dagens grunnlag/,
        ),
      ).toBeVisible();
    },
  );
});
