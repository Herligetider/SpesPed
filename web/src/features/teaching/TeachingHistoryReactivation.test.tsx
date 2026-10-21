import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "../../api";
import TeachingWorkspace from "./TeachingWorkspace";
import type { Session, SessionContent, WorkspaceProps } from "./types";

// Proposal recovery is verified in its own suite. These tests exercise the
// saved-history authority boundary through the actual retained workspace.
vi.mock("./Suggestions", () => ({ default: () => null }));
const content: SessionContent = {
  title: "Safe manual current",
  goal: "Read three words",
  preparation: "Current preparation",
  materials: ["Cards"],
  steps: [{ instruction: "Practice", minutes: 20 }],
  support: "Independent current support",
  simplification: "One word",
  observation_focus: "Independent attempts",
};
const current: Session = {
  id: "session",
  version: 5,
  state: "draft",
  owner_id: "teacher",
  revision_id: "r3",
  revision: 3,
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
const generated: Session = {
  ...current,
  revision_id: "r2",
  revision: 2,
  state: "approved",
  approved: true,
  content: {
    ...content,
    title: "Older generated revision",
    support: "Previously authorized generated support",
  },
  field_job_ids: { support: ["job"] },
};
const redacted: Session = {
  ...generated,
  content: null,
  source_status: "review_required",
  approved: false,
};
const page = (items: unknown[]) => ({ items, total: items.length });
const reply = (value: unknown, status = 200) =>
  new Response(
    JSON.stringify(
      status < 400
        ? value
        : {
            error: {
              code: "history_unavailable",
              message: "History authority unavailable",
            },
          },
    ),
    { status, headers: { "content-type": "application/json" } },
  );
type Mode = "authorized" | "redacted" | "held" | "failed";
function fixture(paginated = false) {
  let mode: Mode = "authorized";
  const held: ((response: Response) => void)[] = [];
  const offsets: number[] = [];
  const authorized = paginated
    ? Array.from({ length: 101 }, (_, index) =>
        index === 0
          ? generated
          : {
              ...current,
              revision_id: "history-" + index,
              revision: index + 10,
              content: {
                ...content,
                title:
                  index === 100
                    ? "Oldest authorized revision"
                    : "Authorized history " + index,
              },
            },
      )
    : [current, generated];
  const client = new ApiClient((async (input) => {
    const url = new URL(String(input), "http://test"),
      path = url.pathname;
    if (path === "/api/v1/schools")
      return reply(
        page([
          {
            id: "school",
            name: "Synthetic school",
            kind: "public",
            timezone: "Europe/Oslo",
            role: "teacher",
          },
        ]),
      );
    if (path.endsWith("/teaching-sessions")) return reply(page([current]));
    if (path.endsWith("/teaching/sessions/session"))
      return reply({ ...current });
    if (path.endsWith("/sessions/session/revisions")) {
      offsets.push(Number(url.searchParams.get("offset")));
      if (mode === "held")
        return new Promise<Response>((resolve) => held.push(resolve));
      if (mode === "failed") return reply(null, 503);
      const items = mode === "redacted" ? [current, redacted] : authorized;
      const offset = Number(url.searchParams.get("offset"));
      return reply({
        items: items.slice(offset, offset + 100),
        total: items.length,
      });
    }
    if (path.endsWith("/teaching/bases/basis"))
      return reply({
        id: "basis",
        source_status: "current",
        basis: {
          theme: "",
          arena: "Room",
          materials: [],
          missing_information: [],
          learners: [],
        },
      });
    return reply(page([]));
  }) as typeof fetch);
  const props: WorkspaceProps = {
    client,
    schoolId: "school",
    mode: "teaching",
    learnerId: "learner",
    learnerName: "Synthetic pupil",
    currentUser: { id: "teacher", display_name: "Synthetic teacher" },
    language: "nb",
    formatError: (error) =>
      error instanceof Error ? error.message : String(error),
  };
  return {
    props,
    held,
    offsets,
    mode: (next: Mode) => {
      mode = next;
    },
    release: async (value: unknown, status = 200) => {
      await act(async () => {
        for (const resolve of held.splice(0)) resolve(reply(value, status));
      });
    },
  };
}
async function open(props: WorkspaceProps) {
  render(<TeachingWorkspace {...props} />);
  await userEvent.click(
    await screen.findByRole("button", {
      name: /Safe manual current.*revisjon 3/,
    }),
  );
  await userEvent.click(await screen.findByText("Lagret revisjonshistorikk"));
  const view = within(
    screen.getByText("Lagret revisjonshistorikk").parentElement!,
  );
  await view.findByText("Previously authorized generated support");
  return view;
}
async function tab(name: string) {
  await userEvent.click(screen.getByRole("button", { name }));
}
async function refresh() {
  await userEvent.click(
    screen.getByRole("button", { name: "Kontroller lagrede økter på nytt" }),
  );
}
async function recalled(view: ReturnType<typeof within>) {
  await view.findByRole("heading", {
    name: "Økt trenger ny kontroll · revisjon 2",
  });
  expect(
    view.queryByText("Previously authorized generated support"),
  ).not.toBeInTheDocument();
  expect(view.getByText("Independent current support")).toBeVisible();
}

describe("saved history reactivation authority", () => {
  it("keeps normal persisted historical rows accessible and reads pages beyond 100", async () => {
    const f = fixture(true),
      view = await open(f.props);
    expect(
      await view.findByRole("heading", {
        name: "Oldest authorized revision · revisjon 110",
      }),
    ).toBeVisible();
    expect(f.offsets).toContain(100);
  });
  it("revalidates older history after tab reactivation while the independent current version stays unchanged", async () => {
    const f = fixture(),
      view = await open(f.props);
    await tab("Observasjoner");
    f.mode("redacted");
    await tab("Undervisningsøkter");
    await recalled(view);
    expect(
      screen.getByRole("button", { name: /Safe manual current.*revisjon 3/ }),
    ).toBeVisible();
  });
  it("invalidates history on explicit current refresh even when the returned revision and version are identical", async () => {
    const f = fixture(),
      view = await open(f.props);
    f.mode("redacted");
    await refresh();
    await recalled(view);
  });
  it("hides retained rows during pending and failed history revalidation, then retries independently of the valid current record", async () => {
    const f = fixture(),
      view = await open(f.props);
    f.mode("held");
    await refresh();
    await waitFor(() => expect(f.held.length).toBeGreaterThan(0));
    expect(
      view.queryByText("Previously authorized generated support"),
    ).not.toBeInTheDocument();
    await screen.findByRole("heading", {
      name: "Safe manual current · revisjon 3",
    });
    f.mode("failed");
    await f.release(null, 503);
    await view.findByText("History authority unavailable");
    expect(
      view.queryByText("Previously authorized generated support"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Safe manual current · revisjon 3" }),
    ).toBeVisible();
    f.mode("redacted");
    await userEvent.click(view.getByRole("button", { name: "Hent på nytt" }));
    await recalled(view);
  });
  it("rejects a held pre-recall history reply after a later activated read has returned authoritative redaction", async () => {
    const f = fixture(),
      view = await open(f.props);
    f.mode("held");
    await refresh();
    await waitFor(() => expect(f.held.length).toBeGreaterThan(0));
    await tab("Observasjoner");
    f.mode("redacted");
    await tab("Undervisningsøkter");
    await recalled(view);
    await f.release(page([current, generated]));
    expect(
      view.queryByText("Previously authorized generated support"),
    ).not.toBeInTheDocument();
    expect(
      view.getByRole("heading", {
        name: "Økt trenger ny kontroll · revisjon 2",
      }),
    ).toBeVisible();
  });
});
