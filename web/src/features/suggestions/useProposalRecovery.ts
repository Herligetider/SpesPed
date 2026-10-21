import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api";
import { LocalValidationError } from "../../userErrors";
import type {
  JobStatus,
  Operation,
  ReadResult,
  RecoveryConfig,
  SavedPage,
  VerifiedProposal,
} from "./types";
const clients = new WeakMap<object, number>();
let clientSequence = 0;
export function proposalScopeKey(
  c: Pick<
    RecoveryConfig,
    | "client"
    | "schoolId"
    | "learnerId"
    | "userId"
    | "kind"
    | "ownerId"
    | "revisionId"
    | "basisId"
  >,
) {
  if (!clients.has(c.client)) clients.set(c.client, ++clientSequence);
  return JSON.stringify([
    clients.get(c.client),
    c.schoolId,
    c.learnerId,
    c.userId,
    c.kind,
    c.ownerId,
    c.revisionId,
    c.basisId,
  ]);
}
export function useRecoveryRead<T>(
  load: () => Promise<T>,
  dependencies: unknown[],
  enabled = true,
): ReadResult<T> {
  const [result, setResult] = useState<{
    scope: unknown[];
    value?: T;
    error?: unknown;
  }>();
  const scope = [...dependencies, enabled];
  const matches =
    result?.scope.length === scope.length &&
    result.scope.every((v, i) => Object.is(v, scope[i]));
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    load().then(
      (value) => {
        if (active) setResult({ scope, value });
      },
      (error) => {
        if (active) setResult({ scope, error });
      },
    );
    return () => {
      active = false;
    };
  }, scope);
  return enabled && matches
    ? { value: result?.value, error: result?.error, loading: false }
    : { loading: enabled };
}
export function recoveryMessage(config: RecoveryConfig, error: unknown) {
  if (error instanceof ApiError && error.code === "job_not_expired")
    return "Kjørefristen er ikke passert. Jobben er fortsatt registrert som pågående. Kontroller lagret status før du prøver igjen.";
  return error instanceof LocalValidationError
    ? error.message
    : config.formatError(error);
}
const invalid = (message: string) => new LocalValidationError(message);
export function ownerPath(c: RecoveryConfig): string[] {
  return c.kind === "plan"
    ? ["education-plans", c.ownerId]
    : ["teaching", "sessions", c.ownerId];
}
export function useProposalRecovery<D>(config: RecoveryConfig) {
  const scope = proposalScopeKey(config),
    configRef = useRef(config);
  configRef.current = config;
  const [offset, setOffset] = useState(0),
    [reload, setReload] = useState(0),
    [selectedId, setSelectedId] = useState(""),
    [busy, setBusy] = useState(false),
    [uncertain, setUncertain] = useState<Operation>(),
    [error, setError] = useState<unknown>(),
    [notice, setNotice] = useState("");
  const alive = useRef(true),
    active = useRef<Operation | undefined>(undefined),
    pending = useRef<Operation | undefined>(undefined),
    selection = useRef(0),
    chosenId = useRef("");
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const listPath = [...ownerPath(config), "suggestions"];
  function assertPage(page: SavedPage, allowChanged = false) {
    if (
      !page ||
      !Array.isArray(page.items) ||
      !Number.isFinite(page.total) ||
      page.scope !==
        (config.kind === "plan" ? "current_plan_revision" : "current_basis") ||
      typeof (page.plan_revision_id ?? page.session_revision_id) !== "string"
    )
      throw invalid(
        "Listen over lagrede forslag kunne ikke bekreftes. Fortsett manuelt og hent listen på nytt.",
      );
    if (
      !allowChanged &&
      (page.plan_revision_id ?? page.session_revision_id) !== config.revisionId
    )
      throw invalid(
        "Den lagrede planrevisjonen er endret. Hent gjeldende plan før du vurderer forslaget.",
      );
    return page;
  }
  async function pageAt(start: number, limit = 50, allowChanged = false) {
    return assertPage(
      await config.client.schoolGet<SavedPage>(
        config.schoolId,
        listPath,
        new URLSearchParams({ offset: String(start), limit: String(limit) }),
      ),
      allowChanged,
    );
  }
  async function find(id: string, allowChanged = false) {
    for (let start = 0; ; ) {
      const page = await pageAt(start, 100, allowChanged);
      const found = page.items.find((item) => item.id === id);
      if (found) {
        if (
          config.kind === "teaching" &&
          config.basisId &&
          found.basis_id !== config.basisId
        )
          throw invalid(
            "Forslaget gjelder et annet grunnlag. Hent gjeldende økt før du fortsetter.",
          );
        return found;
      }
      start += page.items.length;
      if (start >= page.total) return undefined;
      if (!page.items.length)
        throw invalid("Listen ble avbrutt. Hent forslagene på nytt.");
    }
  }
  async function verify(id: string): Promise<VerifiedProposal<D>> {
    const summary = await find(id);
    if (!summary)
      throw invalid(
        "Forslaget finnes ikke i gjeldende grunnlag. Tidligere tekst vises ikke. Fortsett manuelt eller hent gjeldende revisjon.",
      );
    if (
      summary.availability !== "current" ||
      summary.review_outcome ||
      summary.state === "cancelled"
    )
      return { summary };
    const raw = await config.client.schoolGet<JobStatus>(config.schoolId, [
      "ai",
      "jobs",
      id,
    ]);
    if (raw.id !== id || !Number.isFinite(raw.version))
      throw invalid("Forslagets status kunne ikke bekreftes.");
    const job: JobStatus = {
      id: raw.id,
      version: raw.version,
      state: raw.state,
      attempts: raw.attempts ?? summary.attempts,
      error_code: raw.error_code ?? null,
    };
    if (job.state !== "succeeded") return { summary, job };
    const diff = await config.client.schoolGet<D>(
      config.schoolId,
      config.kind === "plan"
        ? [...ownerPath(config), "suggestions", id]
        : [...ownerPath(config), "suggestions", id, "diff"],
      config.kind === "plan"
        ? new URLSearchParams({ basis_id: summary.basis_id })
        : undefined,
    );
    const binding = diff as {
      job_id?: string;
      plan_revision_id?: string;
      current_revision_id?: string;
      basis_id?: string;
    };
    if (
      binding.job_id !== id ||
      (binding.plan_revision_id ?? binding.current_revision_id) !==
        config.revisionId ||
      (config.kind === "plan" && binding.basis_id !== summary.basis_id)
    )
      throw invalid(
        "Forslaget gjelder ikke den viste revisjonen. Hent gjeldende plan før videre vurdering.",
      );
    return { summary, job, diff };
  }
  const page = useRecoveryRead(
    () => pageAt(offset),
    [scope, config.refresh, reload, offset],
  );
  const verified = useRecoveryRead(
    () => verify(selectedId),
    [scope, config.refresh, reload, selectedId],
    Boolean(selectedId),
  );
  function refresh() {
    setReload((n) => n + 1);
  }
  function select(id: string) {
    if (active.current && active.current.kind !== "create") return;
    selection.current += 1;
    chosenId.current = id;
    setSelectedId(id);
    setError(undefined);
    setNotice("");
  }
  function forgetPending(message: string) {
    pending.current = undefined;
    setUncertain(undefined);
    setError(undefined);
    setNotice(message);
    refresh();
  }
  async function preflight(operation: Operation) {
    if (operation.kind === "create") {
      await pageAt(0, 1);
      return;
    }
    if (operation.kind === "expire") {
      const summary = await find(operation.jobId!);
      if (
        !summary ||
        summary.state !== "running" ||
        summary.version !== operation.body.expected_version
      )
        throw invalid(
          "Den lagrede kjørestatusen er endret. Kontroller status før du avklarer kjørefristen.",
        );
      // Lease recovery uses current owner-bound metadata only. A recalled
      // processing binding must never require re-exposing its proposal output.
      return;
    }
    const fresh = await verify(operation.jobId!);
    if (
      fresh.summary.availability !== "current" ||
      fresh.summary.review_outcome
    )
      throw invalid(
        "Forslaget er allerede vurdert eller grunnlaget trenger ny kontroll. Ingen ny handling er utført.",
      );
    if (!fresh.job)
      throw invalid(
        "Forslaget er avbrutt eller kan ikke brukes. Fortsett manuelt.",
      );
    if (operation.kind === "review") {
      if (
        !fresh.diff ||
        JSON.stringify(fresh.diff) !== JSON.stringify(operation.diff)
      )
        throw invalid(
          "Forslaget eller planrevisjonen er endret. Kontroller de nye forskjellene før en ny vurdering.",
        );
    } else {
      if (fresh.job.version !== operation.body.expected_version)
        throw invalid(
          "Jobbstatusen er endret. Kontroller den lagrede statusen før du fortsetter.",
        );
      if (
        operation.kind === "run" &&
        !["queued", "failed", "unavailable"].includes(fresh.job.state)
      )
        throw invalid(
          "En pågående eller fullført modelljobb kjøres ikke på nytt. Kontroller lagret status.",
        );
      if (
        operation.kind === "cancel" &&
        ["succeeded", "cancelled"].includes(fresh.job.state)
      )
        throw invalid(
          "En fullført eller avbrutt jobb kan ikke avbrytes igjen.",
        );
    }
  }
  async function execute(operation: Operation, retrying = false) {
    if (active.current || (!retrying && pending.current)) return;
    const capture = selection.current;
    let submitted = false;
    active.current = operation;
    setBusy(true);
    setError(undefined);
    try {
      await preflight(operation);
      if (!alive.current || capture !== selection.current) return;
      submitted = true;
      const result = await config.client.schoolCommand(
        config.schoolId,
        operation.path,
        operation.body,
      );
      if (!alive.current || capture !== selection.current) return;
      pending.current = undefined;
      setUncertain(undefined);
      setNotice("Handlingen er lagret.");
      operation.onSuccess?.(result);
      refresh();
    } catch (cause) {
      if (!alive.current) return;
      setError(cause);
      if (
        submitted &&
        cause instanceof ApiError &&
        (cause.status === 0 || cause.status >= 500)
      ) {
        pending.current = operation;
        setUncertain(operation);
      } else if (!submitted && retrying) {
        // A failed recheck says nothing conclusive about the earlier write.
        pending.current = operation;
        setUncertain(operation);
      } else {
        pending.current = undefined;
        setUncertain(undefined);
        if (
          cause instanceof ApiError &&
          cause.status === 409 &&
          operation.kind !== "expire"
        )
          configRef.current.onConflict?.();
      }
      refresh();
    } finally {
      active.current = undefined;
      if (alive.current) setBusy(false);
    }
  }
  function command(operation: Operation) {
    const snapshot = {
      ...operation,
      path: [...operation.path],
      body: structuredClone(operation.body),
      diff:
        operation.diff === undefined
          ? undefined
          : structuredClone(operation.diff),
    };
    void execute(snapshot);
  }
  async function reconcile() {
    const operation = pending.current;
    if (!operation || active.current) return;
    setBusy(true);
    setError(undefined);
    try {
      if (operation.kind === "create") {
        await pageAt(0, 50);
        setNotice(
          "Kontroller listen over lagrede forslag. Du kan fortsette med et valgt forslag. Listen alene beviser ikke at det er samme opprinnelige bestilling.",
        );
        refresh();
        return;
      }
      if (operation.kind === "review") {
        let outcome: string | undefined;
        if (config.kind === "plan") {
          for (let start = 0; ; ) {
            const reviews = await config.client.schoolGet<{
              items: { job_id: string; outcome: string }[];
              total: number;
            }>(
              config.schoolId,
              [...ownerPath(config), "suggestion-reviews"],
              new URLSearchParams({ offset: String(start), limit: "100" }),
            );
            const record = reviews.items.find(
              (r) => r.job_id === operation.jobId,
            );
            if (record) {
              outcome = record.outcome;
              break;
            }
            start += reviews.items.length;
            if (start >= reviews.total) break;
            if (!reviews.items.length)
              throw invalid("Vurderingshistorikken ble avbrutt.");
          }
        } else
          outcome =
            (await find(operation.jobId!, true))?.review_outcome || undefined;
        if (outcome) {
          const owner = await config.client.schoolGet<unknown>(
            config.schoolId,
            ownerPath(config),
          );
          if (!alive.current) return;
          forgetPending(
            `En lagret vurdering er funnet: ${outcomeLabel(outcome)}. Den er ikke utført på nytt.`,
          );
          configRef.current.onReconciled?.(owner);
          return;
        }
        setNotice(
          "Ingen lagret vurdering ble funnet i det kontrollerte grunnlaget. Utkastet beholdes. Kontroller gjeldende revisjon før du eventuelt gjentar det samme forsøket.",
        );
        refresh();
        return;
      }
      const summary = await find(operation.jobId!);
      if (!summary)
        throw invalid(
          "Forslaget tilhører ikke lenger gjeldende grunnlag. Fortsett manuelt og kontroller gjeldende revisjon.",
        );
      if (
        operation.kind === "expire" &&
        summary.state !== "running" &&
        summary.version !== operation.body.expected_version
      ) {
        forgetPending(
          `Registrert jobbstatus: ${stateLabel(summary.state)}. Ingen ny kjøring er startet.`,
        );
        return;
      }
      const status =
        summary.availability === "current"
          ? await config.client.schoolGet<JobStatus>(config.schoolId, [
              "ai",
              "jobs",
              operation.jobId!,
            ])
          : undefined;
      if (
        status &&
        ((operation.kind === "run" &&
          status.version !== operation.body.expected_version) ||
          (operation.kind === "cancel" && status.state === "cancelled") ||
          (operation.kind === "expire" && status.state !== "running"))
      ) {
        forgetPending(
          `Registrert jobbstatus: ${stateLabel(status.state)}. Ingen ny kjøring er startet.`,
        );
        return;
      }
      setNotice(
        summary.availability === "current"
          ? "Utfallet er fortsatt uavklart. Det opprinnelige forsøket er bevart."
          : "Grunnlaget trenger ny kontroll. Utfallet av forsøket er fortsatt uavklart; fortsett manuelt.",
      );
      refresh();
    } catch (cause) {
      if (alive.current) {
        setError(cause);
        refresh();
      }
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function continueSaved() {
    if (pending.current?.kind !== "create" || !selectedId || active.current)
      return;
    setBusy(true);
    try {
      await verify(selectedId);
      if (alive.current)
        forgetPending(
          "Du fortsetter med det valgte lagrede forslaget. Dette bekrefter ikke utfallet av den tidligere bestillingen.",
        );
    } catch (cause) {
      if (alive.current) setError(cause);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  return {
    config,
    page,
    offset,
    setOffset,
    selectedId,
    select,
    verified,
    refresh,
    busy,
    uncertain,
    error,
    notice,
    command,
    reconcile,
    continueSaved,
    retry: () => {
      const operation = pending.current;
      if (operation) void execute(operation, true);
    },
  };
}
export const outcomeLabel = (value: string) =>
  (
    ({
      applied: "Valgte deler tatt inn i IOP-utkast",
      accepted: "Valgte felt tatt inn i øktutkast",
      edited: "Redigerte felt tatt inn i øktutkast",
      rejected: "Avvist",
      discarded: "Forkastet uten å ta inn tekst",
    }) as Record<string, string>
  )[value] || "Registrert vurdering";
export const stateLabel = (value: string) =>
  (
    ({
      queued: "Venter på kjøring",
      running: "Pågående kjøring",
      succeeded: "Kjøring fullført",
      failed: "Kjøring mislyktes",
      unavailable: "Kjøring utilgjengelig",
      cancelled: "Avbrutt",
    }) as Record<string, string>
  )[value] || "Uavklart status";
export type ProposalRecovery<D> = ReturnType<typeof useProposalRecovery<D>>;
