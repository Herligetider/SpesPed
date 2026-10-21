import { LocalValidationError } from "../../userErrors";
import {
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import type { ReactElement, ReactNode } from "react";
import { ApiError } from "../../api";
import type { ApiClient } from "../../api";
import type { Page } from "./types";

export async function allPages<T>(
  client: ApiClient,
  school: string,
  path: readonly string[],
  query = new URLSearchParams(),
): Promise<T[]> {
  const items: T[] = [];
  for (let offset = 0; ;) {
    const params = new URLSearchParams(query);
    params.set("offset", String(offset));
    params.set("limit", "100");
    const page = await client.schoolGet<Page<T>>(school, path, params);
    items.push(...page.items);
    offset += page.items.length;
    if (offset >= page.total) return items;
    if (!page.items.length)
      throw new LocalValidationError("Listen ble avbrutt. Last inn på nytt.");
  }
}
export function useRead<T>(load: () => Promise<T>, dependencies: unknown[]) {
  const [value, setValue] = useState<T>();
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const completedScope = useRef<unknown[] | undefined>(undefined);
  const scope = [...dependencies, revision];
  const scopeCurrent =
    !!completedScope.current &&
    completedScope.current.length === scope.length &&
    completedScope.current.every((part, index) =>
      Object.is(part, scope[index]),
    );
  useEffect(() => {
    let active = true;
    setLoading(true);
    setValue(undefined);
    setError(undefined);
    load()
      .then(
        (data) => {
          if (active) {
            completedScope.current = scope;
            setValue(data);
          }
        },
        (err) => {
          if (active) {
            completedScope.current = scope;
            setError(err);
          }
        },
      )
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [...dependencies, revision]); // Every caller supplies the complete read scope.
  return {
    value: scopeCurrent ? value : undefined,
    error: scopeCurrent ? error : undefined,
    loading: loading || !scopeCurrent,
    reload: () => setRevision((x) => x + 1),
  };
}
type Pending = {
  path: readonly string[];
  body: unknown;
  apply: (value: unknown) => void;
};
export function useCommand(
  client: ApiClient,
  school: string,
  formatError: (error: unknown) => string,
  onConflict?: () => void,
) {
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState<Pending>();
  const pending = useRef<Pending | undefined>(undefined);
  async function execute(command: Pending) {
    if (pending.current) return;
    pending.current = command;
    setBusy(true);
    setError("");
    try {
      const result = await client.schoolCommand(
        school,
        command.path,
        command.body,
      );
      if (alive.current) {
        setUncertain(undefined);
        command.apply(result);
      }
    } catch (err) {
      if (alive.current) {
        setError(formatError(err));
        if (err instanceof ApiError && (err.status === 0 || err.status >= 500))
          setUncertain(command);
        else {
          setUncertain(undefined);
          if (err instanceof ApiError && err.status === 409) onConflict?.();
        }
      }
    } finally {
      pending.current = undefined;
      if (alive.current) setBusy(false);
    }
  }
  function run<T>(
    path: readonly string[],
    body: Record<string, unknown>,
    apply: (value: T) => void,
    keyed = true,
  ) {
    if (pending.current || uncertain) return;
    // Snapshot once: retries always carry the same payload and logical command key.
    const snapshot = structuredClone(
      keyed ? { request_key: crypto.randomUUID(), ...body } : body,
    );
    void execute({
      path: [...path],
      body: snapshot,
      apply: (value) => apply(value as T),
    });
  }
  return {
    run,
    busy,
    error,
    uncertain: !!uncertain,
    retry: () => {
      if (uncertain) void execute(uncertain);
    },
    clearError: () => setError(""),
  };
}
export function CommandStatus({
  command,
}: {
  command: ReturnType<typeof useCommand>;
}) {
  return (
    <>
      {command.error && <p role="alert">{command.error}</p>}
      {command.uncertain && (
        <div role="alert">
          <p>
            Lagringssvaret er uklart. Utkastet beholdes. Kontroller samme
            registrering med et uendret nytt forsøk før du oppretter noe mer.
          </p>
          <button type="button" disabled={command.busy} onClick={command.retry}>
            Prøv samme registrering igjen
          </button>
        </div>
      )}
      {command.busy && <p role="status">Lagrer …</p>}
    </>
  );
}
export function ReadStatus({
  loading,
  error,
  formatError,
  reload,
}: {
  loading: boolean;
  error: unknown;
  formatError: (error: unknown) => string;
  reload: () => void;
}) {
  return (
    <>
      {loading && <p role="status">Henter …</p>}
      {!!error && (
        <div role="alert">
          <p>{formatError(error)}</p>
          <button type="button" onClick={reload}>
            Hent på nytt
          </button>
        </div>
      )}
    </>
  );
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className="teaching-field">
      <label htmlFor={id}>{label}</label>
      {isValidElement(children)
        ? cloneElement(children as ReactElement<{ id?: string }>, { id })
        : children}
    </div>
  );
}
export function lines(text: string): string[] {
  return text
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
}
export function pretty(value: unknown): string {
  if (Array.isArray(value))
    return value
      .map((item) =>
        typeof item === "string"
          ? item
          : `${item.minutes} min: ${item.instruction}`,
      )
      .join("\n");
  return String(value ?? "");
}
export function displayDate(value: string, zone: string) {
  return new Intl.DateTimeFormat("nb-NO", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: zone,
  }).format(new Date(value));
}
export function localInput(value: string, zone: string) {
  const date = new Date(value);
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(date);
  return (
    parts.replace(" ", "T") +
    "." +
    String(date.getUTCMilliseconds()).padStart(3, "0")
  );
}
export function instant(
  value: string,
  zone: string,
  original?: string,
): string {
  // An untouched existing instant retains its exact precision and fold choice.
  if (original && localInput(original, zone) === value) return original;
  const match =
    /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?$/.exec(
      value,
    );
  if (!match)
    throw new LocalValidationError("Velg en uttrykkelig dato og klokkeslett.");
  const normalized =
    match[1] + ":" + (match[2] ?? "00") + "." + (match[3] ?? "").padEnd(3, "0");
  const utc = Date.parse(normalized + "Z");
  if (!Number.isFinite(utc))
    throw new LocalValidationError("Velg en gyldig dato og klokkeslett.");
  const matches: string[] = [];
  for (let minutes = -14 * 60; minutes <= 14 * 60; minutes += 15) {
    const iso = new Date(utc - minutes * 60000).toISOString();
    if (localInput(iso, zone) === normalized) matches.push(iso);
  }
  if (matches.length !== 1)
    throw new LocalValidationError(
      matches.length
        ? "Klokkeslettet forekommer to ganger ved overgang til vintertid. Velg et entydig klokkeslett."
        : "Klokkeslettet finnes ikke i skolens tidssone. Velg et annet klokkeslett.",
    );
  return matches[0];
}
export function DateField({
  label,
  value,
  onChange,
  zone,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  zone: string;
}) {
  return (
    <Field label={`${label} (${zone})`}>
      <input
        type="datetime-local"
        step="0.001"
        required
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}
