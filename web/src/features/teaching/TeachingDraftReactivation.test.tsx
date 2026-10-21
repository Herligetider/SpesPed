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
import TeachingWorkspace from "./TeachingWorkspace";
import CreateSession from "./CreateSession";
import type {
  Evidence,
  Goal,
  Observation,
  Person,
  ProfileStatement,
  Session,
  SessionContent,
  WorkspaceProps,
} from "./types";

// The proposal surface has its own independent suite. These regressions exercise
// the teaching edit buffer and authorized choice reads, without generating jobs.
vi.mock("./Suggestions", () => ({ default: () => null }));
const content: SessionContent = {
  title: "Syntetisk økt",
  goal: "Les tre ord",
  preparation: "Lagret forberedelse",
  materials: ["Kort"],
  steps: [{ instruction: "Øv", minutes: 20 }],
  support: "Visuell støtte",
  simplification: "Ett ord",
  observation_focus: "Selvstendig forsøk",
};
const initial: Session = {
  id: "session",
  version: 1,
  state: "draft",
  owner_id: "teacher",
  revision_id: "r1",
  revision: 1,
  basis_id: "basis",
  content_digest: "a".repeat(64),
  content,
  source_status: "current",
  approved: false,
  planned_at: "2027-01-10T09:00:00Z",
  duration_minutes: 25,
  delivery_state: "not_recorded",
  field_job_ids: {},
};
const school = {
  id: "school",
  name: "Syntetisk skole",
  kind: "public",
  timezone: "Europe/Oslo",
  role: "teacher",
};
const goal: Goal = {
  id: "goal",
  title: "Bekreftet lesemål",
  expected_action: "Les ord",
  arena: "Rom",
  support: "Kort",
  kind: "ordinary_teaching",
};
const profile: ProfileStatement = {
  id: "profile",
  state: "confirmed",
  source_status: "current",
  content: "Bekreftet støtte med bilder",
  category: "support_strategy",
};
const evidence: Evidence = {
  id: "evidence",
  revision: 1,
  content: "Bekreftet valgt kilde",
  reporter: "Syntetisk avsender",
  certainty: "confirmed",
  occurred_at: "2026-10-20T10:00:00Z",
  source: { link_id: "link", revision: 1, page: 1 },
};
const person: Person = { id: "teacher", display_name: "Demo-pedagog" };
function note(id: string, text: string): Observation {
  return {
    id,
    revision_id: id + "-r1",
    revision: 1,
    version: 1,
    state: "saved",
    confirmed: true,
    current: true,
    learner_id: "learner",
    occurred_at: "2026-10-20T10:00:00Z",
    author_id: "teacher",
    session_revision_id: null,
    assignment_id: null,
    goal_revision_id: null,
    observation: text,
    support: "Ett hint",
    interpretation: null,
    next_step: null,
    correction_reason: null,
  };
}
const page = (items: unknown[]) => ({ items, total: items.length });
function reply(value: unknown, status = 200) {
  return new Response(
    JSON.stringify(
      status < 400
        ? value
        : { error: { code: "test", message: String(value) } },
    ),
    { status, headers: { "content-type": "application/json" } },
  );
}
type Call = {
  path: string;
  method: string;
  body: Record<string, unknown>;
  query: URLSearchParams;
};
function setup(handler: (call: Call) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const client = new ApiClient((async (input, init) => {
    const url = new URL(String(input), "http://test");
    const call = {
      path: url.pathname,
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : {},
      query: url.searchParams,
    };
    calls.push(call);
    if (call.path === "/api/v1/schools") return reply(page([school]));
    return handler(call);
  }) as typeof fetch);
  const props: WorkspaceProps = {
    client,
    schoolId: "school",
    mode: "teaching",
    learnerId: "learner",
    learnerName: "Demo-elev",
    currentUser: person,
    language: "nb",
    formatError: (error) =>
      error instanceof Error ? error.message : String(error),
  };
  return { props, calls };
}
function basic(call: Call) {
  if (call.path.endsWith("/learning-goals")) return reply(page([goal]));
  if (call.path.endsWith("/support-profile")) return reply(page([profile]));
  if (call.path.endsWith("/timeline")) return reply(page([evidence]));
  if (call.path.endsWith("/teaching-staff")) return reply(page([person]));
  if (call.path.endsWith("/teaching/bases/basis"))
    return reply({
      id: "basis",
      source_status: "current",
      basis: {
        theme: "",
        arena: "Rom",
        materials: [],
        missing_information: [],
        learners: [
          {
            learner_id: "learner",
            goals: [],
            profile: [],
            observations: [],
            source_bindings: [],
          },
        ],
      },
    });
  return reply(page([]));
}
async function open() {
  await userEvent.click(
    await screen.findByRole("button", { name: /Syntetisk økt.*revisjon 1/ }),
  );
  await screen.findAllByRole("heading", { name: "Syntetisk økt · revisjon 1" });
  await userEvent.click(screen.getByText("Rediger økten som ny revisjon"));
}
async function tab(name: string) {
  await userEvent.click(screen.getByRole("button", { name }));
}
async function preparation() {
  const field = screen.getByLabelText("Forberedelse");
  await waitFor(() => expect(field).toBeVisible());
  return field;
}
function sessionFixture() {
  let server = initial;
  const { props, calls } = setup((call) => {
    if (call.path.endsWith("/teaching-sessions")) return reply(page([server]));
    if (call.path.endsWith("/teaching/sessions/session")) return reply(server);
    if (call.path.endsWith("/sessions/session/revisions")) {
      if (call.method === "GET")
        return reply(
          page(
            server.revision === 1
              ? [initial]
              : [server, { ...initial, version: server.version }],
          ),
        );
      server = {
        ...server,
        revision: server.revision + 1,
        version: server.version + 1,
        revision_id: "r" + (server.revision + 1),
        content: call.body.content as SessionContent,
      };
      return reply(server, 201);
    }
    return basic(call);
  });
  return {
    props,
    calls,
    current: () => server,
    change: (next: Session) => {
      server = next;
    },
  };
}

describe("retained session drafts across fresh server revisions", () => {
  it("keeps local preparation and reason, then writes only after deliberate comparison using the new expected version", async () => {
    const fixture = sessionFixture();
    render(<TeachingWorkspace {...fixture.props} />);
    await open();
    fireEvent.change(await preparation(), {
      target: { value: "Min ulagrede forberedelse" },
    });
    fireEvent.change(screen.getByLabelText("Begrunnelse for ny revisjon"), {
      target: { value: "Min begrunnelse beholdes" },
    });
    await tab("Observasjoner");
    fixture.change({
      ...initial,
      version: 2,
      revision: 2,
      revision_id: "r2",
      content: {
        ...content,
        preparation: "En annen pedagogs lagrede forberedelse",
      },
    });
    await tab("Undervisningsøkter");
    await screen.findAllByRole("heading", {
      name: "Syntetisk økt · revisjon 2",
    });
    expect(await preparation()).toHaveValue("Min ulagrede forberedelse");
    expect(screen.getByLabelText("Begrunnelse for ny revisjon")).toHaveValue(
      "Min begrunnelse beholdes",
    );
    expect(
      screen
        .getAllByText("En annen pedagogs lagrede forberedelse")
        .some((element) => element.closest("details") === null),
    ).toBe(true);
    expect(
      screen.getByRole("button", { name: "Lagre ny øktrevisjon" }),
    ).toBeDisabled();
    expect(fixture.calls.filter((call) => call.method === "POST")).toHaveLength(
      0,
    );
    await userEvent.click(
      screen.getByRole("button", {
        name: /Jeg har sammenlignet og vil lagre eget utkast/,
      }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Lagre ny øktrevisjon" }),
    );
    await screen.findAllByRole("heading", {
      name: "Syntetisk økt · revisjon 3",
    });
    expect(
      fixture.calls.find((call) => call.method === "POST")!.body,
    ).toMatchObject({
      expected_version: 2,
      reason: "Min begrunnelse beholdes",
      content: { preparation: "Min ulagrede forberedelse" },
    });
    expect(screen.getByLabelText("Begrunnelse for ny revisjon")).toHaveValue(
      "",
    );
    expect(await preparation()).toHaveValue("Min ulagrede forberedelse");
  });
  it("replaces the local buffer only when the user explicitly chooses the saved current revision", async () => {
    const fixture = sessionFixture();
    render(<TeachingWorkspace {...fixture.props} />);
    await open();
    fireEvent.change(await preparation(), { target: { value: "Eget utkast" } });
    await tab("Observasjoner");
    fixture.change({
      ...initial,
      version: 2,
      revision: 2,
      revision_id: "r2",
      content: { ...content, preparation: "Ny lagret tekst" },
    });
    await tab("Undervisningsøkter");
    await screen.findAllByRole("heading", {
      name: "Syntetisk økt · revisjon 2",
    });
    expect(await preparation()).toHaveValue("Eget utkast");
    await userEvent.click(
      screen.getByRole("button", {
        name: "Forkast eget utkast og bruk gjeldende lagret revisjon",
      }),
    );
    expect(await preparation()).toHaveValue("Ny lagret tekst");
    expect(fixture.calls.filter((call) => call.method === "POST")).toHaveLength(
      0,
    );
  });
  it.each(["withdrawn", "unavailable"])(
    "hides older source-derived draft text when historical authorization is %s, even if the new revision is valid",
    async (mode) => {
      let server = initial;
      const { props } = setup((call) => {
        if (call.path.endsWith("/teaching-sessions"))
          return reply(page([server]));
        if (call.path.endsWith("/teaching/sessions/session"))
          return reply(server);
        if (call.path.endsWith("/sessions/session/revisions"))
          return server.version === 1
            ? reply(page([initial]))
            : mode === "unavailable"
              ? reply("Historisk kontroll utilgjengelig", 503)
              : reply(
                  page([
                    server,
                    {
                      ...initial,
                      content: null,
                      source_status: "review_required",
                    },
                  ]),
                );
        return basic(call);
      });
      render(<TeachingWorkspace {...props} />);
      await open();
      fireEvent.change(await preparation(), {
        target: { value: "Tekst med tidligere kildeavhengighet" },
      });
      await tab("Observasjoner");
      server = {
        ...initial,
        version: 2,
        revision: 2,
        revision_id: "r2",
        content: { ...content, preparation: "Ny uavhengig lagret tekst" },
      };
      await tab("Undervisningsøkter");
      await screen.findAllByRole("heading", {
        name: "Syntetisk økt · revisjon 2",
      });
      await screen.findByText(
        /Det tidligere utkastets kildegrunnlag er ikke bekreftet tilgjengelig/,
      );
      expect(screen.getByLabelText("Forberedelse")).not.toBeVisible();
      expect(
        screen.getByRole("button", {
          name: /Jeg har sammenlignet og vil lagre eget utkast/,
        }),
      ).toBeDisabled();
      await userEvent.click(
        screen.getByRole("button", {
          name: "Forkast eget utkast og bruk gjeldende lagret revisjon",
        }),
      );
      expect(await preparation()).toHaveValue("Ny uavhengig lagret tekst");
    },
  );
  it("rechecks an already authorized historical buffer when returning to an unchanged current revision", async () => {
    let server = initial;
    let withdrawn = false;
    const { props } = setup((call) => {
      if (call.path.endsWith("/teaching-sessions"))
        return reply(page([server]));
      if (call.path.endsWith("/teaching/sessions/session"))
        return reply({ ...server });
      if (call.path.endsWith("/sessions/session/revisions"))
        return reply(
          page(
            server.version === 1
              ? [initial]
              : [
                  server,
                  withdrawn
                    ? {
                        ...initial,
                        content: null,
                        source_status: "review_required",
                      }
                    : initial,
                ],
          ),
        );
      return basic(call);
    });
    render(<TeachingWorkspace {...props} />);
    await open();
    fireEvent.change(await preparation(), {
      target: { value: "Earlier authorized local buffer" },
    });
    await tab("Observasjoner");
    server = {
      ...initial,
      version: 2,
      revision: 2,
      revision_id: "r2",
      content: {
        ...content,
        preparation: "Independent safe current preparation",
      },
    };
    await tab("Undervisningsøkter");
    expect(await preparation()).toHaveValue("Earlier authorized local buffer");
    await tab("Observasjoner");
    withdrawn = true;
    await tab("Undervisningsøkter");
    await screen.findByText(
      /Det tidligere utkastets kildegrunnlag er ikke bekreftet tilgjengelig/,
    );
    expect(screen.getByLabelText("Forberedelse")).not.toBeVisible();
    expect(
      screen.getByRole("button", {
        name: /Jeg har sammenlignet og vil lagre eget utkast/,
      }),
    ).toBeDisabled();
    await userEvent.click(
      screen.getByRole("button", {
        name: "Forkast eget utkast og bruk gjeldende lagret revisjon",
      }),
    );
    expect(await preparation()).toHaveValue(
      "Independent safe current preparation",
    );
  });
  it("preserves edits made after an immutable save started instead of replacing them with its late success", async () => {
    let server = initial;
    let finish: ((value: Response) => void) | undefined;
    const { props, calls } = setup((call) => {
      if (call.path.endsWith("/teaching-sessions"))
        return reply(page([server]));
      if (call.path.endsWith("/teaching/sessions/session"))
        return reply(server);
      if (call.path.endsWith("/sessions/session/revisions")) {
        if (call.method === "GET")
          return reply(
            page(server.revision === 1 ? [initial] : [server, initial]),
          );
        return new Promise((resolve) => {
          finish = resolve;
        });
      }
      return basic(call);
    });
    render(<TeachingWorkspace {...props} />);
    await open();
    fireEvent.change(await preparation(), {
      target: { value: "Innsendt tekst" },
    });
    fireEvent.change(screen.getByLabelText("Begrunnelse for ny revisjon"), {
      target: { value: "Begrunnelse" },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Lagre ny øktrevisjon" }),
    );
    await waitFor(() => expect(finish).toBeDefined());
    fireEvent.change(screen.getByLabelText("Forberedelse"), {
      target: { value: "Nyere tekst som ikke er sendt" },
    });
    server = {
      ...initial,
      version: 2,
      revision: 2,
      revision_id: "r2",
      content: { ...content, preparation: "Innsendt tekst" },
    };
    await act(async () => finish!(reply(server, 201)));
    await screen.findAllByRole("heading", {
      name: "Syntetisk økt · revisjon 2",
    });
    expect(await preparation()).toHaveValue("Nyere tekst som ikke er sendt");
    expect(calls.filter((call) => call.method === "POST")).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "Lagre ny øktrevisjon" }),
    ).toBeDisabled();
  });
});

describe("retained next-session basis choices", () => {
  it("offers the observation saved in another tab and preserves the exact prior goal/source/profile/observation selection", async () => {
    const previous = note("old", "Tidligere valgt observasjon");
    let notes = [previous];
    const fresh = note("new", "Ny observasjon fra annen fane");
    const { props, calls } = setup((call) => {
      if (call.path.endsWith("/teaching-sessions")) return reply(page([]));
      if (call.path.endsWith("/teaching-observations"))
        return reply(page(notes));
      if (
        call.path.endsWith("/teaching/observations") &&
        call.method === "POST"
      ) {
        notes = [fresh, ...notes];
        return reply(fresh, 201);
      }
      if (call.path.endsWith("/teaching/bases") && call.method === "POST")
        return reply(
          { id: "new-basis", source_status: "current", basis: {} },
          201,
        );
      return basic(call);
    });
    render(<TeachingWorkspace {...props} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Planlegg ny økt" }),
    );
    fireEvent.change(
      screen.getByLabelText("Planlagt tidspunkt (Europe/Oslo)"),
      { target: { value: "2027-01-10T10:00" } },
    );
    fireEvent.change(screen.getByLabelText("Arena"), {
      target: { value: "Min beholdte arena" },
    });
    fireEvent.change(screen.getByLabelText("Klassens tema"), {
      target: { value: "Mitt tema" },
    });
    await userEvent.click(
      await screen.findByRole("checkbox", { name: /Bekreftet lesemål/ }),
    );
    await userEvent.click(
      screen.getByText("Velg bekreftet støtte og kilder (valgfritt)"),
    );
    await userEvent.click(
      await screen.findByRole("checkbox", {
        name: "Bekreftet støtte med bilder",
      }),
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: /Bekreftet valgt kilde/ }),
    );
    await userEvent.click(screen.getByText("Gjenbruk tidligere observasjoner"));
    await userEvent.click(
      await screen.findByRole("checkbox", {
        name: /Tidligere valgt observasjon/,
      }),
    );
    await tab("Observasjoner");
    const view = within(
      document.querySelector(
        '[data-teaching-view="observations"]',
      ) as HTMLElement,
    );
    fireEvent.change(view.getByLabelText("Observert tidspunkt (Europe/Oslo)"), {
      target: { value: "2026-10-20T12:00" },
    });
    fireEvent.change(view.getByLabelText("Konkret observasjon"), {
      target: { value: fresh.observation },
    });
    fireEvent.change(view.getByLabelText("Støtte som faktisk ble gitt"), {
      target: { value: "Hint" },
    });
    await userEvent.click(
      view.getByRole("button", { name: "Lagre observasjon" }),
    );
    await view.findByText(/Observasjonen er lagret/);
    await tab("Undervisningsøkter");
    await screen.findByRole("checkbox", {
      name: /Ny observasjon fra annen fane/,
    });
    expect(screen.getByLabelText("Arena")).toHaveValue("Min beholdte arena");
    expect(screen.getByLabelText("Klassens tema")).toHaveValue("Mitt tema");
    expect(
      screen.getByRole("checkbox", { name: /Bekreftet lesemål/ }),
    ).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "Bekreftet støtte med bilder" }),
    ).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: /Bekreftet valgt kilde/ }),
    ).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: /Tidligere valgt observasjon/ }),
    ).toBeChecked();
    await userEvent.click(
      screen.getByRole("checkbox", { name: /Ny observasjon fra annen fane/ }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Bekreft valgt grunnlag" }),
    );
    await screen.findByText("Praktisk manuelt opplegg");
    expect(
      calls.find(
        (call) =>
          call.method === "POST" && call.path.endsWith("/teaching/bases"),
      )!.body.learners,
    ).toEqual([
      {
        learner_id: "learner",
        goal_revision_ids: ["goal"],
        profile_statement_ids: ["profile"],
        observation_revision_ids: ["old-r1", "new-r1"],
        sources: [
          { evidence_id: "evidence", evidence_revision: 1, link_id: "link" },
        ],
      },
    ]);
  });
  it.each(["observation", "profile", "source"])(
    "requires explicit removal of an unavailable selected %s while retaining other values",
    async (kind) => {
      let current = true;
      const previous = note("old", "Valgt notat som kan rettes");
      const { props, calls } = setup((call) => {
        if (call.path.endsWith("/teaching-observations"))
          return reply(
            page(current || kind !== "observation" ? [previous] : []),
          );
        if (call.path.endsWith("/support-profile"))
          return reply(page(current || kind !== "profile" ? [profile] : []));
        if (call.path.endsWith("/timeline"))
          return reply(page(current || kind !== "source" ? [evidence] : []));
        if (call.path.endsWith("/teaching/bases") && call.method === "POST")
          return reply({ id: "b", source_status: "current", basis: {} }, 201);
        return basic(call);
      });
      const rendered = render(
        <CreateSession
          {...props}
          learnerId="learner"
          zone="Europe/Oslo"
          active
          onCreated={() => {}}
        />,
      );
      fireEvent.change(
        screen.getByLabelText("Planlagt tidspunkt (Europe/Oslo)"),
        { target: { value: "2027-01-10T10:00" } },
      );
      fireEvent.change(screen.getByLabelText("Arena"), {
        target: { value: "Beholdt arena" },
      });
      await userEvent.click(
        await screen.findByRole("checkbox", { name: /Bekreftet lesemål/ }),
      );
      await userEvent.click(
        screen.getByText("Velg bekreftet støtte og kilder (valgfritt)"),
      );
      await userEvent.click(
        screen.getByText("Gjenbruk tidligere observasjoner"),
      );
      await userEvent.click(
        await screen.findByRole("checkbox", {
          name:
            kind === "profile"
              ? "Bekreftet støtte med bilder"
              : kind === "source"
                ? /Bekreftet valgt kilde/
                : /Valgt notat som kan rettes/,
        }),
      );
      rendered.rerender(
        <CreateSession
          {...props}
          learnerId="learner"
          zone="Europe/Oslo"
          active={false}
          onCreated={() => {}}
        />,
      );
      current = false;
      rendered.rerender(
        <CreateSession
          {...props}
          learnerId="learner"
          zone="Europe/Oslo"
          active
          onCreated={() => {}}
        />,
      );
      await screen.findByRole("button", { name: "Fjern bare utdaterte valg" });
      expect(screen.getByLabelText("Arena")).toHaveValue("Beholdt arena");
      expect(
        screen.getByRole("checkbox", { name: /Bekreftet lesemål/ }),
      ).toBeChecked();
      expect(
        screen.getByRole("button", { name: "Bekreft valgt grunnlag" }),
      ).toBeDisabled();
      expect(calls.filter((call) => call.method === "POST")).toHaveLength(0);
      await userEvent.click(
        screen.getByRole("button", { name: "Fjern bare utdaterte valg" }),
      );
      await userEvent.click(
        screen.getByRole("button", { name: "Bekreft valgt grunnlag" }),
      );
      await screen.findByText("Praktisk manuelt opplegg");
      expect(
        calls.find((call) => call.method === "POST")!.body.learners,
      ).toEqual([
        {
          learner_id: "learner",
          goal_revision_ids: ["goal"],
          profile_statement_ids: [],
          observation_revision_ids: [],
          sources: [],
        },
      ]);
    },
  );
  it("refreshes named staff candidates without replacing the practical draft or chosen owner", async () => {
    let people = [person];
    const { props } = setup((call) => {
      if (call.path.endsWith("/teaching-staff")) return reply(page(people));
      if (call.path.endsWith("/teaching/bases") && call.method === "POST")
        return reply({ id: "b", source_status: "current", basis: {} }, 201);
      return basic(call);
    });
    const rendered = render(
      <CreateSession
        {...props}
        learnerId="learner"
        zone="Europe/Oslo"
        active
        onCreated={() => {}}
      />,
    );
    fireEvent.change(
      screen.getByLabelText("Planlagt tidspunkt (Europe/Oslo)"),
      { target: { value: "2027-01-10T10:00" } },
    );
    fireEvent.change(screen.getByLabelText("Arena"), {
      target: { value: "Rom" },
    });
    await userEvent.click(
      await screen.findByRole("checkbox", { name: /Bekreftet lesemål/ }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Bekreft valgt grunnlag" }),
    );
    await screen.findByText("Praktisk manuelt opplegg");
    fireEvent.change(screen.getByLabelText("Forberedelse"), {
      target: { value: "Ulagret praktisk nytt utkast" },
    });
    rendered.rerender(
      <CreateSession
        {...props}
        learnerId="learner"
        zone="Europe/Oslo"
        active={false}
        onCreated={() => {}}
      />,
    );
    people = [person, { id: "second", display_name: "Ny navngitt pedagog" }];
    rendered.rerender(
      <CreateSession
        {...props}
        learnerId="learner"
        zone="Europe/Oslo"
        active
        onCreated={() => {}}
      />,
    );
    await screen.findByRole("option", { name: "Ny navngitt pedagog" });
    expect(screen.getByLabelText("Ansvarlig pedagog")).toHaveValue("teacher");
    expect(screen.getByLabelText("Forberedelse")).toHaveValue(
      "Ulagret praktisk nytt utkast",
    );
  });
});
