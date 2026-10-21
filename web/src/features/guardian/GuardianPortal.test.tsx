import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import GuardianPortal from "./GuardianPortal";
import type { GuardianGrant, GuardianPayload } from "./types";

const grant = (id = "opaque-grant-id", version = 2): GuardianGrant => ({ id, version, state: "active", created_at: "2026-10-20T11:30:00Z", expires_at: "2026-10-30T11:30:00Z" });
const letter: GuardianPayload = { subject: "Oppsummering", body: "Trygg tekst <script>alert('x')</script>\nNeste avsnitt", attachments: [{ id: "att-1", filename: "notat.txt", content_type: "text/plain", size_bytes: 12 }] };
function setup(overrides: { schoolId?: string; userId?: string; list?: ReturnType<typeof vi.fn>; command?: ReturnType<typeof vi.fn>; payload?: ReturnType<typeof vi.fn>; blob?: ReturnType<typeof vi.fn> } = {}) {
  const schoolGet = overrides.list ?? vi.fn(async (_school: string, _segments: readonly string[], query?: URLSearchParams) => {
    if (query) return { items: [grant()], total: 1 };
    return letter;
  });
  const schoolCommand = overrides.command ?? vi.fn(async (_school: string, _path: readonly string[], body: { expected_version: number }) => ({ ...grant("opaque-grant-id", body.expected_version + 1) }));
  const client = { schoolGet, schoolCommand, schoolBlob: overrides.blob ?? vi.fn(async () => new Blob(["attachment"])) } as never;
  const view = render(<GuardianPortal client={client} schoolId={overrides.schoolId ?? "school-a"} currentUser={{ id: overrides.userId ?? "guardian-a", email: "a@example.test", display_name: "A" }} language="nb" timezone="Europe/Oslo" formatError={(error) => error instanceof Error ? error.message : "Feil"} />);
  return { ...view, schoolGet, schoolCommand };
}

describe("GuardianPortal", () => {
  it("pages metadata and opens one exact letter, with an explicit separate read receipt", async () => {
    const schoolGet = vi.fn(async (_school: string, _segments: readonly string[], query?: URLSearchParams) => query?.has("offset") ? (query.get("offset") === "20" ? { items: [grant("second-id")], total: 21 } : { items: [grant()], total: 21 }) : letter);
    const schoolCommand = vi.fn(async (_school: string, _path: readonly string[], body: { expected_version: number }) => ({ ...grant("second-id", body.expected_version + 1) }));
    const { schoolGet: get, schoolCommand: command } = setup({ list: schoolGet, command: schoolCommand });
    await screen.findByText("Melding fra skolen");
    expect(screen.getByText("20. oktober 2026 kl. 13:30")).toBeInTheDocument();
    expect(command).not.toHaveBeenCalled();
    expect(screen.queryByText("Oppsummering")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Eldre brev" }));
    await waitFor(() => expect(get.mock.calls.some((call) => call[2]?.get("offset") === "20")).toBe(true));
    fireEvent.click(await screen.findByRole("button", { name: "Åpne brev" }));
    expect(await screen.findByRole("heading", { name: "Oppsummering" })).toBeInTheDocument();
    expect(screen.getByText(/<script>alert\('x'\)<\/script>/)).toBeInTheDocument();
    expect(command).toHaveBeenCalledTimes(1);
    expect(command.mock.calls[0][1]).toEqual(["communication", "portal", "grants", "second-id", "open"]);
    expect(command.mock.calls[0][2]).toMatchObject({ expected_version: 2, request_key: expect.any(String) });
    expect(command.mock.calls[0][1]).not.toContain("read-receipt");
    expect(screen.getByRole("button", { name: "Bekreft lest" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Bekreft lest" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(2));
    expect(command.mock.calls[1][1]).toEqual(["communication", "portal", "grants", "second-id", "read-receipt"]);
    expect(command.mock.calls[1][2]).toMatchObject({ expected_version: 3, request_key: expect.any(String) });
  });

  it("retries a lost open reply with the same key and exact body", async () => {
    const error = Object.assign(new Error("Nettverksbrudd"), { status: 0 });
    const command = vi.fn().mockRejectedValueOnce(error).mockResolvedValueOnce({ ...grant(), version: 3 });
    setup({ command });
    fireEvent.click(await screen.findByRole("button", { name: "Åpne brev" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Prøv samme handling igjen" }));
    await screen.findByRole("heading", { name: "Oppsummering" });
    expect(command.mock.calls[0][2]).toEqual(command.mock.calls[1][2]);
  });

  it("keeps an in-flight open valid across focus refresh and restores usable controls", async () => {
    let finishOpen!: (value: GuardianGrant) => void;
    const command = vi.fn(() => new Promise<GuardianGrant>((resolve) => { finishOpen = resolve; }));
    const { schoolGet } = setup({ command });
    fireEvent.click(await screen.findByRole("button", { name: "Åpne brev" }));
    await waitFor(() => expect(finishOpen).toBeTypeOf("function"));
    fireEvent.focus(window);
    await waitFor(() => expect(schoolGet.mock.calls.length).toBeGreaterThan(1));
    await act(async () => { finishOpen(grant("opaque-grant-id", 3)); });
    expect(await screen.findByRole("heading", { name: "Oppsummering" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bekreft lest" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Oppdater" })).toBeEnabled();
  });

  it("does not redisplay a late payload after refresh removes its pending grant", async () => {
    let release!: (value: GuardianPayload) => void;
    let listCalls = 0;
    const schoolGet = vi.fn((_school: string, _segments: readonly string[], query?: URLSearchParams) => {
      if (query) {
        listCalls++;
        return Promise.resolve(listCalls === 1 ? { items: [grant()], total: 1 } : { items: [], total: 0 });
      }
      return new Promise<GuardianPayload>((resolve) => { release = resolve; });
    });
    setup({ list: schoolGet });
    fireEvent.click(await screen.findByRole("button", { name: "Åpne brev" }));
    await waitFor(() => expect(release).toBeTypeOf("function"));
    fireEvent.focus(window);
    await screen.findByText("Du har ingen tilgjengelige brev nå.");
    await act(async () => { release(letter); });
    expect(screen.queryByRole("heading", { name: "Oppsummering" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Trygg tekst/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Last ned" })).not.toBeInTheDocument();
  });

  it("clears an open letter when a refresh is denied by the backend", async () => {
    let calls = 0;
    const list = vi.fn(async (_school: string, _segments: readonly string[], query?: URLSearchParams) => {
      if (!query) return letter;
      calls++;
      if (calls > 1) throw Object.assign(new Error("Stale authorization"), { status: 409 });
      return { items: [grant()], total: 1 };
    });
    setup({ list });
    fireEvent.click(await screen.findByRole("button", { name: "Åpne brev" }));
    await screen.findByRole("heading", { name: "Oppsummering" });
    fireEvent.focus(window);
    expect(await screen.findByText("Dette brevet er ikke lenger tilgjengelig. Innhold og vedlegg er fjernet.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Oppsummering" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Trygg tekst/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Last ned" })).not.toBeInTheDocument();
  });

  it.each([403, 409])("withholds displayed text and denies attachments after a %s", async (status) => {
    const blob = vi.fn().mockRejectedValue(Object.assign(new Error("Ikke tilgjengelig"), { status }));
    const { schoolCommand } = setup({ blob });
    fireEvent.click(await screen.findByRole("button", { name: "Åpne brev" }));
    await screen.findByRole("heading", { name: "Oppsummering" });
    fireEvent.click(screen.getByRole("button", { name: "Last ned" }));
    await screen.findByText("Dette brevet er ikke lenger tilgjengelig. Innhold og vedlegg er fjernet.");
    expect(screen.queryByRole("heading", { name: "Oppsummering" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Trygg tekst/)).not.toBeInTheDocument();
    expect(blob).toHaveBeenCalledWith("school-a", ["communication", "portal", "grants", "opaque-grant-id", "attachments", "att-1"]);
    expect(schoolCommand).toHaveBeenCalledTimes(1);
  });

  it("discards a late payload after the guardian identity changes", async () => {
    let resolvePayload!: (value: GuardianPayload) => void;
    const schoolGet = vi.fn((_school: string, _segments: readonly string[], query?: URLSearchParams) => query ? Promise.resolve({ items: [grant()], total: 1 }) : new Promise<GuardianPayload>((resolve) => { resolvePayload = resolve; }));
    const { rerender } = setup({ list: schoolGet });
    fireEvent.click(await screen.findByRole("button", { name: "Åpne brev" }));
    await waitFor(() => expect(resolvePayload).toBeTypeOf("function"));
    rerender(<GuardianPortal client={{ schoolGet, schoolCommand: vi.fn(async () => grant()), schoolBlob: vi.fn() } as never} schoolId="school-a" currentUser={{ id: "guardian-b", email: "b@example.test", display_name: "B" }} language="nb" timezone="Europe/Oslo" formatError={() => "Feil"} />);
    await act(async () => { resolvePayload(letter); });
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Oppsummering" })).not.toBeInTheDocument());
  });
});
