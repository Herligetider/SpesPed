import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "../../api";
import type { WorkspaceProps, Session, SessionContent } from "./types";
import TeachingWorkspace from "./TeachingWorkspace";
import { AssignmentPanel } from "./Assignments";
import SessionEditor from "./SessionEditor";
import CreateSession from "./CreateSession";
import { ObservationForm } from "./Observations";
import { DeliveryForm } from "./Deliveries";
import Suggestions from "./Suggestions";
import { periodBounds } from "./DeliverySummary";
import { allPages, instant, localInput } from "./runtime";
const content: SessionContent = {
  title: "Syntetisk leseøkt",
  goal: "Lese øvingsord",
  preparation: "Legg frem kort",
  materials: ["Bildekort"],
  steps: [{ instruction: "Vis kort", minutes: 5 }],
  support: "Gi visuell støtte",
  simplification: "Ett kort",
  observation_focus: "Observer selvstendig forsøk",
};
const row: Session = {
  id: "session",
  version: 1,
  state: "draft",
  owner_id: "teacher",
  revision_id: "rev1",
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
};
const school = {
  id: "school",
  name: "Syntetisk skole",
  timezone: "Europe/Oslo",
  role: "teacher",
  kind: "primary",
};
const page = (items: unknown[]) => ({ items, total: items.length });
function response(value: unknown, status = 200) {
  return new Response(
    JSON.stringify(
      status >= 400
        ? { error: { message: String(value), code: "test" } }
        : value,
    ),
    { status, headers: { "content-type": "application/json" } },
  );
}
type Call = {
  path: string;
  method: string;
  body: Record<string, unknown>;
  url: URL;
};
function setup(handler: (call: Call) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const fetcher = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      const call = {
        path: url.pathname,
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : {},
        url,
      };
      calls.push(call);
      if (url.pathname === "/api/v1/schools") return response(page([school]));
      return handler(call);
    },
  );
  const client = new ApiClient(fetcher as typeof fetch);
  const props: WorkspaceProps = {
    client,
    schoolId: "school",
    learnerId: "learner",
    learnerName: "Demo-elev 001",
    mode: "teaching",
    currentUser: { id: "teacher", display_name: "Demo-pedagog" },
    language: "nb",
    formatError: (error) =>
      error instanceof Error ? error.message : String(error),
  };
  return { calls, client, props };
}
function defaultHandler(call: Call): Response {
  if (call.path.endsWith("/teaching-sessions")) return response(page([row]));
  if (call.path.endsWith("/teaching/sessions/session")) return response(row);
  if (call.path.endsWith("/teaching/bases/basis"))
    return response({
      id: "basis",
      source_status: "current",
      basis: {
        theme: "",
        arena: "Rom",
        materials: [],
        missing_information: [],
        learners: [
          { goals: [], profile: [], observations: [], source_bindings: [] },
        ],
      },
    });
  return response(page([]));
}
async function openSession() {
  await screen.findByRole("button", { name: /Syntetisk leseøkt.*revisjon 1/ });
  await userEvent.click(
    screen.getByRole("button", { name: /Syntetisk leseøkt.*revisjon 1/ }),
  );
  await screen.findByRole("heading", {
    name: "Syntetisk leseøkt · revisjon 1",
  });
}
async function fillObservation() {
  fireEvent.change(screen.getByLabelText(/Observert tidspunkt/), {
    target: { value: "2026-10-20T12:00" },
  });
  fireEvent.change(screen.getByLabelText("Konkret observasjon"), {
    target: { value: "Leste tre ord" },
  });
  fireEvent.change(screen.getByLabelText("Støtte som faktisk ble gitt"), {
    target: { value: "Bildekort" },
  });
}
describe("persisted teaching workflow", () => {
  it("keeps review and exact approval separate and refuses to approve an unsaved draft", async () => {
    const { props, calls } = setup((call) => {
      if (call.method === "POST" && call.path.endsWith("/review"))
        return response({ ...row, state: "in_review", version: 2 });
      if (
        call.path.endsWith("/teaching/sessions/session") &&
        calls.some((c) => c.method === "POST")
      )
        return response({ ...row, state: "in_review", version: 2 });
      return defaultHandler(call);
    });
    render(<TeachingWorkspace {...props} />);
    await openSession();
    fireEvent.change(
      screen.getByLabelText("Begrunnelse for kontroll og godkjenning"),
      { target: { value: "Kontrollert innhold" } },
    );
    expect(
      screen.getByRole("button", {
        name: "Godkjenn denne revisjonen for gjennomføring",
      }),
    ).toBeDisabled();
    await userEvent.click(
      screen.getByRole("button", { name: "Bekreft faglig gjennomgang" }),
    );
    await waitFor(() =>
      expect(
        calls.some((c) => c.path.endsWith("/review") && c.method === "POST"),
      ).toBe(true),
    );
    const review = calls.find(
      (c) => c.path.endsWith("/review") && c.method === "POST",
    )!;
    expect(review.body).toMatchObject({
      revision_id: "rev1",
      content_digest: "a".repeat(64),
      expected_version: 1,
    });
    expect(
      calls.some((c) => c.path.endsWith("/approve") && c.method === "POST"),
    ).toBe(false);
    await waitFor(() =>
      expect(
        screen.getByRole("button", {
          name: "Godkjenn denne revisjonen for gjennomføring",
        }),
      ).toBeDisabled(),
    );
    fireEvent.change(
      screen.getByLabelText("Begrunnelse for kontroll og godkjenning"),
      { target: { value: "Godkjenning" } },
    );
    await userEvent.click(screen.getByText("Rediger økten som ny revisjon"));
    fireEvent.change(screen.getByLabelText("Støtte"), {
      target: { value: "Egen ny støtte" },
    });
    expect(
      screen.getByRole("button", {
        name: "Godkjenn denne revisjonen for gjennomføring",
      }),
    ).toBeDisabled();
  });
  it("keeps manual edits and displays competing session after a conflict", async () => {
    let conflict = false;
    const { props } = setup((call) => {
      if (call.method === "POST" && call.path.endsWith("/revisions")) {
        conflict = true;
        return response("En annen versjon er lagret", 409);
      }
      if (call.path.endsWith("/teaching/sessions/session") && conflict)
        return response({
          ...row,
          revision_id: "rev2",
          revision: 2,
          version: 2,
          content: { ...content, support: "Annen pedagogs støtte" },
        });
      return defaultHandler(call);
    });
    render(<TeachingWorkspace {...props} />);
    await openSession();
    await userEvent.click(screen.getByText("Rediger økten som ny revisjon"));
    fireEvent.change(screen.getByLabelText("Støtte"), {
      target: { value: "Mitt beholdte utkast" },
    });
    fireEvent.change(screen.getByLabelText("Begrunnelse for ny revisjon"), {
      target: { value: "Tilpasset" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Lagre ny øktrevisjon" }),
    );
    await screen.findByText("Annen pedagogs støtte");
    expect(screen.getByLabelText("Støtte")).toHaveValue("Mitt beholdte utkast");
    expect(
      screen.getByRole("button", { name: "Lagre ny øktrevisjon" }),
    ).toBeDisabled();
  });
  it("retries the immutable observation command after an unknown outcome without losing newer text", async () => {
    let saved = 0;
    let finish: (value: Response) => void = () => {};
    const { props, calls } = setup((call) => {
      if (
        call.method === "POST" &&
        call.path.endsWith("/teaching/observations")
      ) {
        saved++;
        if (saved === 1) throw new TypeError("offline");
        return new Promise((resolve) => {
          finish = resolve;
        });
      }
      return response(page([]));
    });
    render(
      <ObservationForm {...props} learnerId="learner" zone="Europe/Oslo" />,
    );
    await fillObservation();
    await userEvent.click(
      screen.getByRole("button", { name: "Lagre observasjon" }),
    );
    await screen.findByRole("button", {
      name: "Prøv samme registrering igjen",
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Prøv samme registrering igjen" }),
    );
    fireEvent.change(screen.getByLabelText("Konkret observasjon"), {
      target: { value: "Nyere usendt tekst" },
    });
    await act(async () => finish(response({ id: "note", revision: 1 })));
    await screen.findByText(/Observasjonen er lagret/);
    const posted = calls.filter((c) => c.method === "POST");
    expect(posted).toHaveLength(2);
    expect(posted[0].body).toEqual(posted[1].body);
    expect(posted[0].body.content).toMatchObject({
      occurred_at: "2026-10-20T10:00:00.000Z",
      observation: "Leste tre ord",
    });
    expect(screen.getByLabelText("Konkret observasjon")).toHaveValue(
      "Nyere usendt tekst",
    );
  });
  it("allows manual basis creation when optional profile and evidence reads are forbidden", async () => {
    const { props, calls } = setup((call) => {
      if (call.path.endsWith("/learning-goals"))
        return response(
          page([
            {
              id: "goal",
              title: "Bekreftet ordinært lesemål",
              expected_action: "Les ett ord",
              arena: "Rom",
              support: "Bilde",
              kind: "ordinary",
            },
          ]),
        );
      if (
        call.path.endsWith("/support-profile") ||
        call.path.endsWith("/timeline")
      )
        return response("Tilgang mangler", 403);
      if (call.method === "POST" && call.path.endsWith("/teaching/bases"))
        return response({ id: "basis", source_status: "current", basis: {} });
      return response(page([]));
    });
    render(
      <CreateSession
        {...props}
        learnerId="learner"
        zone="Europe/Oslo"
        onCreated={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText(/Planlagt tidspunkt/), {
      target: { value: "2026-10-22T10:00" },
    });
    fireEvent.change(screen.getByLabelText("Arena"), {
      target: { value: "Syntetisk rom" },
    });
    await userEvent.click(
      await screen.findByRole("checkbox", {
        name: /Bekreftet ordinært lesemål/,
      }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Bekreft valgt grunnlag" }),
    );
    await screen.findByText("Praktisk manuelt opplegg");
    const body = calls.find((c) => c.method === "POST")!.body;
    expect(body.learners).toEqual([
      {
        learner_id: "learner",
        goal_revision_ids: ["goal"],
        profile_statement_ids: [],
        observation_revision_ids: [],
        sources: [],
      },
    ]);
  });
  it("assistant inbox works without reading any learner dossier and redacts stale instructions", async () => {
    const assignment = {
      id: "assignment",
      version: 1,
      learner_id: "learner",
      learner_name: "Demo-elev 001",
      state: "active",
      brief_state: "review_required",
      content: null,
      arena: null,
      role: null,
      follow_up_owner_name: "Demo-pedagog",
      planned_at: "2026-10-22T08:00:00Z",
      valid_from: "2026-10-01T00:00:00Z",
      valid_until: "2099-10-22T12:00:00Z",
    };
    const { props, calls } = setup((call) =>
      call.path.endsWith("/teaching/brief-assignments")
        ? response(page([assignment]))
        : call.path.endsWith("/brief-assignments/assignment")
          ? response(assignment)
          : response(page([])),
    );
    render(
      <TeachingWorkspace {...props} mode="assistant" learnerId={undefined} />,
    );
    await userEvent.click(
      await screen.findByRole("button", {
        name: /Demo-elev 001.*Trenger ny kontroll/,
      }),
    );
    await screen.findByText(/Kortet trenger ny pedagogisk kontroll/);
    expect(
      screen.queryByText("Materiell og plassering:"),
    ).not.toBeInTheDocument();
    expect(calls.some((c) => c.path.includes("/learners/"))).toBe(false);
    expect(
      screen.getByRole("button", { name: "Lagre observasjon" }),
    ).toBeInTheDocument();
  });
  it("ignores a late response from a different learner and resets scoped drafts", async () => {
    let resolveFirst: ((value: Response) => void) | undefined;
    const { props } = setup((call) =>
      call.path.includes("/learners/learner/teaching-sessions")
        ? new Promise((resolve) => {
            resolveFirst = resolve;
          })
        : response(page([])),
    );
    const view = render(<TeachingWorkspace {...props} />);
    await waitFor(() => expect(resolveFirst).not.toBeUndefined());
    view.rerender(
      <TeachingWorkspace
        {...props}
        learnerId="other"
        learnerName="Demo-elev 002"
      />,
    );
    await screen.findByText("Ingen lagrede undervisningsøkter.");
    await act(async () => resolveFirst!(response(page([row]))));
    expect(
      screen.queryByRole("button", { name: /Syntetisk leseøkt/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Undervisning · Demo-elev 002" }),
    ).toBeInTheDocument();
  });
  it("never represents staff role labels as qualification and requires explicit occurrence", async () => {
    const { props } = setup((call) =>
      response(
        page(
          call.path.endsWith("/teaching-staff")
            ? [{ id: "teacher", display_name: "Demo-pedagog" }]
            : [],
        ),
      ),
    );
    render(
      <DeliveryForm
        {...props}
        learnerId="learner"
        zone="Europe/Oslo"
        onSaved={() => {}}
      />,
    );
    expect(screen.getByLabelText(/Faktisk start/)).toHaveValue("");
    await userEvent.selectOptions(
      screen.getByLabelText("Støtteform, registrering 1"),
      "individually_adapted_education",
    );
    expect(
      screen.getByText(/Rollebetegnelser dokumenterer ikke ITO-kompetanse/),
    ).toBeInTheDocument();
  });
  it("shows a model diff and sends only explicitly selected replacement fields", async () => {
    const job = { id: "job", version: 1, state: "succeeded", error_code: null };
    let requested = false;
    const { props, calls } = setup((call) => {
      if (call.path.endsWith("/ai/choices"))
        return response(
          page([
            {
              policy_id: "policy",
              release_id: "release",
              label: "Gjennomgått lokal modell",
              model_version: "Syntetisk v1",
            },
          ]),
        );
      if (call.path.endsWith("/suggestions") && call.method === "POST") {
        requested = true;
        return response(job);
      }
      if (call.path.endsWith("/suggestions") && call.method === "GET")
        return response({
          items: requested
            ? [
                {
                  id: "job",
                  version: 1,
                  state: "succeeded",
                  attempts: 1,
                  created_at: "2026-10-21T08:00:00Z",
                  updated_at: "2026-10-21T08:01:00Z",
                  basis_id: "basis",
                  availability: "current",
                  review_outcome: null,
                },
              ]
            : [],
          total: requested ? 1 : 0,
          scope: "current_basis",
          session_revision_id: "rev1",
          manual_fallback_available: true,
        });
      if (call.path.endsWith("/ai/jobs/job")) return response(job);
      if (call.path.endsWith("/diff"))
        return response({
          expected_version: 1,
          current_revision_id: "rev1",
          job_id: "job",
          missing_evidence: ["Ingen mestring er bekreftet"],
          source_manifest: [],
          changes: [
            {
              field: "support",
              before: content.support,
              proposed: "Forslag om kort støtte",
              changed: true,
            },
            {
              field: "preparation",
              before: content.preparation,
              proposed: "Endret forberedelse",
              changed: true,
            },
          ],
        });
      if (call.path.endsWith("/suggestions/review"))
        return response({ ...row, revision: 2 });
      return response(page([]));
    });
    const updated = vi.fn();
    render(
      <Suggestions
        {...props}
        learnerId="learner"
        session={row}
        draft={content}
        hasUnsaved={false}
        onSaved={updated}
        onConflict={() => {}}
      />,
    );
    await screen.findByRole("option", {
      name: "Gjennomgått lokal modell · Syntetisk v1",
    });
    await userEvent.selectOptions(
      await screen.findByLabelText(
        "Gjennomgått lokal modell og behandlingsoppsett",
      ),
      "0",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Bestill forslag" }),
    );
    await screen.findByText("Forslag om kort støtte");
    await userEvent.click(
      screen.getByRole("checkbox", { name: /Støtte · endret/ }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Bruk valgte felt i ny øktrevisjon" }),
    );
    await waitFor(() => expect(updated).toHaveBeenCalled());
    expect(
      calls.find((c) => c.path.endsWith("/suggestions/review"))!.body,
    ).toMatchObject({
      selected_fields: ["support"],
      outcome: "accepted",
      expected_version: 1,
      job_id: "job",
    });
  });
});

it("retains seconds and microseconds for untouched observation corrections", async () => {
  const existing = {
    id: "note",
    revision_id: "note-r1",
    version: 1,
    revision: 1,
    state: "saved",
    confirmed: true,
    current: true,
    learner_id: "learner",
    occurred_at: "2026-10-20T10:00:47.123456Z",
    author_id: "teacher",
    session_revision_id: null,
    assignment_id: null,
    goal_revision_id: null,
    observation: "Tre ord",
    support: "Kort",
    interpretation: null,
    next_step: null,
    correction_reason: null,
  };
  const { props, calls } = setup((call) =>
    call.method === "POST"
      ? response({ ...existing, version: 2, revision: 2 })
      : response(page([])),
  );
  render(
    <ObservationForm
      {...props}
      learnerId="learner"
      zone="Europe/Oslo"
      existing={existing}
    />,
  );
  expect(screen.getByLabelText(/Observert tidspunkt/)).toHaveValue(
    "2026-10-20T12:00:47.123",
  );
  fireEvent.change(screen.getByLabelText("Begrunnelse for retting"), {
    target: { value: "Rettet skrivefeil" },
  });
  await userEvent.click(
    screen.getByRole("button", { name: "Lagre korrigert observasjon" }),
  );
  await waitFor(() =>
    expect(calls.some((call) => call.method === "POST")).toBe(true),
  );
  expect(
    calls.find((call) => call.method === "POST")!.body.content,
  ).toMatchObject({ occurred_at: existing.occurred_at });
});
it("does not label empty field lineage as model content and requires explicit independent replacement", () => {
  const view = render(
    <SessionEditor
      value={content}
      onChange={() => {}}
      lineage={{ support: [] }}
      replacements={[]}
      onReplacements={() => {}}
    />,
  );
  expect(
    screen.queryByText(/Feltet bygger på et modellforslag/),
  ).not.toBeInTheDocument();
  view.rerender(
    <SessionEditor
      value={content}
      onChange={() => {}}
      lineage={{ support: ["job"] }}
      replacements={[]}
      onReplacements={() => {}}
    />,
  );
  expect(
    screen.getByRole("checkbox", { name: /erstattet hele feltet/ }),
  ).not.toBeChecked();
  expect(
    screen.getByText(/Vanlig redigering bevarer kildeavhengigheten/),
  ).toBeInTheDocument();
});

describe("time and complete choice pagination", () => {
  it("uses inclusive local dates across DST and refuses a wholly skipped date", () => {
    const spring = periodBounds("2026-03-29", "2026-03-29", "Europe/Oslo");
    expect((Date.parse(spring.end) - Date.parse(spring.start)) / 3600000).toBe(
      23,
    );
    const autumn = periodBounds("2026-10-25", "2026-10-25", "Europe/Oslo");
    expect((Date.parse(autumn.end) - Date.parse(autumn.start)) / 3600000).toBe(
      25,
    );
    expect(() =>
      periodBounds("2011-12-30", "2011-12-30", "Pacific/Apia"),
    ).toThrow(/ingen reelle/);
  });

  it("uses school local time and rejects nonexistent and ambiguous times", () => {
    expect(instant("2026-07-01T10:00:47.123", "Europe/Oslo")).toBe(
      "2026-07-01T08:00:47.123Z",
    );
    const fold = "2026-10-25T01:30:47.123456Z";
    expect(instant(localInput(fold, "Europe/Oslo"), "Europe/Oslo", fold)).toBe(
      fold,
    );
    expect(instant("2026-07-01T10:00", "Europe/Oslo")).toBe(
      "2026-07-01T08:00:00.000Z",
    );
    expect(instant("2026-12-01T10:00", "Europe/Oslo")).toBe(
      "2026-12-01T09:00:00.000Z",
    );
    expect(() => instant("2026-03-29T02:30", "Europe/Oslo")).toThrow(
      /finnes ikke/,
    );
    expect(() => instant("2026-10-25T02:30", "Europe/Oslo")).toThrow(
      /to ganger/,
    );
  });
  it("loads entries beyond one hundred and sends encoded query values", async () => {
    const { client, calls } = setup((call) => {
      const offset = Number(call.url.searchParams.get("offset"));
      return response({
        items: Array.from(
          { length: offset === 0 ? 100 : 1 },
          (_, i) => offset + i,
        ),
        total: 101,
      });
    });
    expect(
      await allPages<number>(client, "school", [
        "teaching",
        "brief-assignments",
      ]),
    ).toHaveLength(101);
    expect(calls[1].url.searchParams.get("offset")).toBe("100");
  });
});

describe("independent review teaching regressions", () => {
  it("drops cached guidance and review prose on brief_stale, including late child responses", async () => {
    let recalled = false;
    let finishMessages: ((value: Response) => void) | undefined;
    let finishActuals: ((value: Response) => void) | undefined;
    const assignment = {
      id: "assigned",
      version: 1,
      state: "active",
      brief_state: "assigned",
      learner_id: "learner",
      learner_name: "Demo-elev",
      follow_up_owner_id: "teacher",
      planned_at: "2026-10-22T08:00:00Z",
      valid_from: "2026-01-01T00:00:00Z",
      valid_until: "2099-01-01T00:00:00Z",
      arena: "Rom",
      role: "Støtte",
      content: {
        simple_goal: "Tre ord",
        material_location: "Hylle",
        steps: ["Hent", "Øv", "Noter"],
        support: "Avtalt støtte",
        simplification: "Ett kort",
        help_when: "Ved tvil",
        contact: "Pedagogen",
        training_guidance: "Avtal opplæring",
      },
    };
    const message = {
      id: "guidance",
      kind: "guidance",
      author_id: "teacher",
      text: "Tilbakekalt veiledning",
      created_at: "2026-10-20T10:00:00Z",
    };
    const input = {
      id: "input",
      version: 1,
      state: "recorded",
      occurred_at: "2026-10-20T10:00:00Z",
      content: {
        occurred_at: "2026-10-20T10:00:00Z",
        duration_minutes: 10,
        status: "participated",
        category: "ordinary_teaching",
        activity: "Selvstendig registrert faktisk aktivitet",
        support: "Eget faktum",
        difficulty: "",
      },
      review_reason: "Tilbakekalt vurdering",
      review_history: [
        {
          id: "history",
          outcome: "recorded",
          reason: "Tilbakekalt historisk begrunnelse",
          historical: false,
          reviewed_at: "2026-10-20T11:00:00Z",
        },
      ],
    };
    const { props, calls } = setup((call) => {
      if (call.method === "POST") {
        recalled = true;
        return response("Kortet er utdatert", 409);
      }
      if (call.path.endsWith("/brief-assignments/assigned"))
        return response(
          recalled
            ? { ...assignment, content: null, brief_state: "review_required" }
            : assignment,
        );
      if (call.path.endsWith("/messages"))
        return recalled
          ? new Promise((resolve) => {
              finishMessages = resolve;
            })
          : response(page([message]));
      if (call.path.endsWith("/actual-inputs"))
        return recalled
          ? new Promise((resolve) => {
              finishActuals = resolve;
            })
          : response(page([input]));
      return response(page([]));
    });
    render(
      <AssignmentPanel
        {...props}
        mode="assistant"
        assignmentId="assigned"
        zone="Europe/Oslo"
      />,
    );
    await screen.findByText("Tilbakekalt veiledning");
    await screen.findByText("Vurdering: Tilbakekalt vurdering");
    await screen.findByText(/Tilbakekalt historisk begrunnelse/);
    fireEvent.change(
      screen.getByLabelText("Tekst til det konkrete oppdraget"),
      { target: { value: "Spørsmål etter tilbakekalling" } },
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Lagre spørsmål" }),
    );
    await screen.findByText(/Kortet trenger ny pedagogisk kontroll/);
    expect(
      screen.queryByText("Tilbakekalt veiledning"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Tilbakekalt vurdering/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Tilbakekalt historisk begrunnelse/),
    ).not.toBeInTheDocument();
    await waitFor(() => expect(finishMessages && finishActuals).toBeTruthy());
    await act(async () => {
      finishMessages!(response(page([message])));
      finishActuals!(response(page([input])));
    });
    expect(
      screen.queryByText("Tilbakekalt veiledning"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Tilbakekalt vurdering/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Tilbakekalt historisk begrunnelse/),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Selvstendig registrert faktisk aktivitet"),
    ).toBeVisible();
    expect(
      calls.filter((call) => call.path.endsWith("/actual-inputs")),
    ).toHaveLength(2);
  });

  it.each([null, "original-session-revision"])(
    "keeps an existing observation's %s factual session link when correcting prose",
    async (original) => {
      const existing = {
        id: "note",
        revision_id: "note-r1",
        version: 1,
        revision: 1,
        state: "saved",
        confirmed: true,
        current: true,
        learner_id: "learner",
        occurred_at: "2026-10-20T10:00:47.123456Z",
        author_id: "teacher",
        session_revision_id: original,
        assignment_id: original ? "original-assignment" : null,
        goal_revision_id: null,
        observation: "Uavhengig observasjon",
        support: "Original støtte",
        interpretation: null,
        next_step: null,
        correction_reason: null,
      };
      const { props, calls } = setup((call) =>
        call.method === "POST"
          ? response({ ...existing, revision: 2 })
          : response(page([])),
      );
      render(
        <ObservationForm
          {...props}
          learnerId="learner"
          zone="Europe/Oslo"
          existing={existing}
          session={{ ...row, revision_id: "unrelated-selected-session" }}
        />,
      );
      fireEvent.change(screen.getByLabelText("Støtte som faktisk ble gitt"), {
        target: { value: "Rettet støtte" },
      });
      fireEvent.change(screen.getByLabelText("Begrunnelse for retting"), {
        target: { value: "Rett kun støtte" },
      });
      await userEvent.click(
        screen.getByRole("button", { name: "Lagre korrigert observasjon" }),
      );
      await waitFor(() =>
        expect(calls.some((call) => call.method === "POST")).toBe(true),
      );
      expect(
        calls.find((call) => call.method === "POST")!.body.content,
      ).toMatchObject({
        session_revision_id: original,
        assignment_id: existing.assignment_id,
        occurred_at: existing.occurred_at,
        support: "Rettet støtte",
      });
    },
  );

  it("preserves visited session, observation and actual-delivery drafts across internal tabs", async () => {
    const { props } = setup(defaultHandler);
    render(<TeachingWorkspace {...props} />);
    await openSession();
    await userEvent.click(screen.getByText("Rediger økten som ny revisjon"));
    fireEvent.change(screen.getByLabelText("Forberedelse"), {
      target: { value: "Ulagret praktisk forberedelse" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Observasjoner" }),
    );
    const observations = within(
      document.querySelector(
        '[data-teaching-view="observations"]',
      ) as HTMLElement,
    );
    fireEvent.change(observations.getByLabelText("Konkret observasjon"), {
      target: { value: "Ulagret konkret observasjon" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Gjennomføring" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Registrer faktisk økt" }),
    );
    const delivery = within(
      document.querySelector('[data-teaching-view="delivery"]') as HTMLElement,
    );
    fireEvent.change(delivery.getByLabelText("Faktisk aktivitet"), {
      target: { value: "Ulagret faktisk aktivitet" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Undervisningsøkter" }),
    );
    expect(screen.getByLabelText("Forberedelse")).toHaveValue(
      "Ulagret praktisk forberedelse",
    );
    expect(screen.getByLabelText("Forberedelse")).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "Observasjoner" }),
    );
    expect(observations.getByLabelText("Konkret observasjon")).toHaveValue(
      "Ulagret konkret observasjon",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Gjennomføring" }),
    );
    expect(delivery.getByLabelText("Faktisk aktivitet")).toHaveValue(
      "Ulagret faktisk aktivitet",
    );
  });
});
