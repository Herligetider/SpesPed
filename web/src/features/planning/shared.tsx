import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError } from "../../api";
import type {
  Binding,
  Context,
  Evidence,
  List,
  Period,
  Quantity,
} from "./types";
export const labels: Record<string, string> = {
  strength: "Styrke",
  interest: "Interesse",
  language: "Språk",
  communication: "Kommunikasjon",
  support_strategy: "Støtte som virker",
  proposed: "Foreslått",
  confirmed: "Bekreftet",
  disputed: "Bestridt",
  rejected: "Avvist",
  superseded: "Erstattet",
  preparation: "Forberedelse",
  awaiting_basis: "Venter på grunnlag",
  follow_up: "Oppfølging",
  closed: "Avsluttet",
  draft: "Utkast",
  in_review: "Til faglig gjennomgang",
  reviewed: "Faglig gjennomgått",
  approved: "Godkjent",
  active: "Aktiv",
  historical: "Historisk",
  imported: "Importert",
  authored: "Skrevet ved skolen",
  current: "Kilde kontrollert",
  review_required: "Grunnlaget må vurderes på nytt",
  individually_adapted_education: "Individuelt tilrettelagt opplæring",
  personal_assistance: "Personlig assistanse",
  physical_adaptation: "Fysisk tilrettelegging",
  minutes: "minutter",
  hours: "timer",
  learner_time: "elevtid",
  staff_time: "ansattid",
  title: "Tittel",
  rationale: "Pedagogisk begrunnelse",
  organization: "Organisering",
  responsibility: "Ansvar",
  evaluation_method: "Evaluering",
  expected_action: "Forventet handling",
  arena: "Arena",
  support: "Støtte",
  curriculum_reference: "Læreplanreferanse",
  participation_record: "Faktisk medvirkning og uavklarte innspill",
  queued: "Venter på kjøring",
  succeeded: "Forslag klart",
  failed: "Forslag mislyktes",
  unavailable: "Forslag utilgjengelig",
  cancelled: "Avbrutt",
  model_recalled: "Modell trukket tilbake",
  applied: "Valgte deler tatt inn",
  discarded: "Forkastet",
  added: "Lagt til",
  changed: "Endret",
  continued: "Videreført",
};
export const label = (v: string) => labels[v] || v;
export const key = () => crypto.randomUUID();
export const when = (v: string | null | undefined) =>
  v
    ? new Date(v).toLocaleString("nb-NO", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Ikke registrert";
function localText(d: Date): string {
  const pad = (v: number) => String(v).padStart(2, "0");
  const base = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return (
    base +
    (d.getSeconds() || d.getMilliseconds() ? `:${pad(d.getSeconds())}` : "") +
    (d.getMilliseconds()
      ? `.${String(d.getMilliseconds()).padStart(3, "0")}`
      : "")
  );
}
export function localChoices(value: string): string[] {
  const text = value.split("@")[0];
  const match = text.match(
    /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)(?::(\d\d)(?:\.(\d{1,3}))?)?$/,
  );
  if (!match) return [];
  const parsed = new Date(text);
  if (!Number.isFinite(parsed.getTime())) return [];
  const expected = [
    Number(match[1]),
    Number(match[2]),
    Number(match[3]),
    Number(match[4]),
    Number(match[5]),
    Number(match[6] || 0),
    Number((match[7] || "").padEnd(3, "0")),
  ];
  const candidates: number[] = [];
  for (const minutes of [-120, -90, -60, -30, 0, 30, 60, 90, 120]) {
    const d = new Date(parsed.getTime() + minutes * 60000);
    if (
      [
        d.getFullYear(),
        d.getMonth() + 1,
        d.getDate(),
        d.getHours(),
        d.getMinutes(),
        d.getSeconds(),
        d.getMilliseconds(),
      ].every((v, i) => v === expected[i])
    )
      candidates.push(d.getTime());
  }
  return [...new Set(candidates)]
    .sort((a, b) => a - b)
    .map((t) => new Date(t).toISOString());
}
function retainedLocalInstant(
  value: string,
  choices: string[],
): string | undefined {
  const selected = value.split("@")[1];
  if (
    selected &&
    /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z$/.test(selected) &&
    choices.some(
      (choice) => new Date(choice).getTime() === new Date(selected).getTime(),
    )
  )
    return selected;
  return undefined;
}
export function localInstant(value: string): string {
  const choices = localChoices(value),
    selected = retainedLocalInstant(value, choices);
  if (selected) return selected;
  if (choices.length === 1 && !value.includes("@")) return choices[0];
  throw new ApiError(
    choices.length > 1
      ? "Klokkeslettet forekommer to ganger. Velg første eller andre forekomst ved tidsfeltet."
      : "Velg et gyldig lokalt tidspunkt. Datoer og klokkeslett som ikke finnes ved overgang til sommertid kan ikke lagres.",
    422,
    "planning_local_time",
  );
}
export const localValue = (v: string) => {
  if (!v) return "";
  const d = new Date(v),
    text = localText(d);
  const fraction = v.match(/\.(\d+)(?:Z|[+-]\d\d:\d\d)$/)?.[1];
  const exact =
    fraction && fraction.length > 3
      ? d.toISOString().replace(/\.\d{3}Z$/, `.${fraction}Z`)
      : d.toISOString();
  return localChoices(text).length > 1 || (fraction && fraction.length > 3)
    ? `${text}@${exact}`
    : text;
};
export function period(p: Period): Period {
  return {
    effective_from: localInstant(p.effective_from),
    effective_until: localInstant(p.effective_until),
  };
}
export function Field({
  title,
  value,
  onChange,
  type = "text",
  required = true,
}: {
  title: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
}) {
  const choices = type === "datetime-local" ? localChoices(value) : [];
  const retained = retainedLocalInstant(value, choices);
  // The native input represents milliseconds. An untouched imported instant may
  // carry more precision; its required fold selector must represent that exact
  // instant too, rather than leave the controlled selection without an option.
  const fraction = retained?.match(/\.(\d+)Z$/)?.[1];
  const foldChoices =
    fraction && fraction.length > 3
      ? choices.map((instant) => instant.replace(/\.\d{3}Z$/, `.${fraction}Z`))
      : choices;
  return (
    <>
      <label className="planning-field">
        {title}
        {type === "textarea" ? (
          <textarea
            required={required}
            value={value}
            onChange={(e) => onChange(e.target.value)}
          />
        ) : (
          <input
            type={type}
            step={
              type === "number"
                ? "any"
                : type === "datetime-local"
                  ? "0.001"
                  : undefined
            }
            min={type === "number" ? 0 : undefined}
            required={required}
            value={type === "datetime-local" ? value.split("@")[0] : value}
            onChange={(e) => onChange(e.target.value)}
          />
        )}
      </label>
      {choices.length > 1 && (
        <label>
          Gjentatt klokkeslett: {title}
          <select
            required
            value={retained || ""}
            onChange={(e) =>
              onChange(
                value.split("@")[0] +
                  (e.target.value ? `@${e.target.value}` : ""),
              )
            }
          >
            <option value="">Velg hvilken forekomst …</option>
            {foldChoices.map((instant, i) => {
              const offset = -new Date(instant).getTimezoneOffset();
              const zone = `UTC${offset < 0 ? "-" : "+"}${String(Math.floor(Math.abs(offset) / 60)).padStart(2, "0")}:${String(Math.abs(offset) % 60).padStart(2, "0")}`;
              return (
                <option key={instant} value={instant}>
                  {i === 0 ? "Første" : "Andre"} forekomst ({zone})
                </option>
              );
            })}
          </select>
        </label>
      )}
    </>
  );
}
export function Dates({
  value,
  onChange,
}: {
  value: Period;
  onChange: (v: Period) => void;
}) {
  return (
    <div className="planning-grid">
      <Field
        title="Gyldig fra (lokal dato og tid)"
        type="datetime-local"
        value={value.effective_from}
        onChange={(v) => onChange({ ...value, effective_from: v })}
      />
      <Field
        title="Gyldig til, ikke inkludert (lokal dato og tid)"
        type="datetime-local"
        value={value.effective_until}
        onChange={(v) => onChange({ ...value, effective_until: v })}
      />
    </div>
  );
}
export function QuantityFields({
  value,
  onChange,
  optional = false,
}: {
  value: Quantity;
  onChange: (v: Quantity) => void;
  optional?: boolean;
}) {
  return (
    <div className="planning-grid">
      <Field
        title={optional ? "Omfang (valgfritt)" : "Omfang"}
        required={!optional}
        type="number"
        value={value.amount ?? ""}
        onChange={(amount) =>
          onChange({
            ...value,
            amount: amount || null,
            unit: amount ? value.unit || "hours" : null,
            counting_basis: amount
              ? value.counting_basis || "learner_time"
              : null,
          })
        }
      />
      <label>
        Enhet
        <select
          value={value.unit || ""}
          onChange={(e) =>
            onChange({ ...value, unit: e.target.value as Quantity["unit"] })
          }
        >
          <option value="">Velg enhet</option>
          <option value="minutes">Minutter</option>
          <option value="hours">Timer</option>
        </select>
      </label>
      <label>
        Hva telles
        <select
          value={value.counting_basis || ""}
          onChange={(e) =>
            onChange({
              ...value,
              counting_basis: e.target.value as Quantity["counting_basis"],
            })
          }
        >
          <option value="">Velg grunnlag</option>
          <option value="learner_time">Elevtid</option>
          <option value="staff_time">Ansattid</option>
        </select>
      </label>
    </div>
  );
}
export function QuantityView({ value }: { value: Quantity }) {
  return (
    <>
      {value.amount == null
        ? "Omfang ikke angitt"
        : `${value.amount} ${label(value.unit || "")} (${label(value.counting_basis || "")})`}
    </>
  );
}
export const emptyPeriod = (): Period => ({
  effective_from: "",
  effective_until: "",
});
export function useRead<T>(
  ctx: Context,
  path: readonly string[],
  query?: URLSearchParams,
  enabled = true,
) {
  const token = JSON.stringify([path, query?.toString(), ctx.refresh, enabled]);
  const [load, setLoad] = useState<{
    token: string;
    value?: T;
    error?: unknown;
  }>({ token: "" });
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    ctx.client
      .schoolGet<T>(ctx.schoolId, path, query)
      .then((value) => {
        if (active) setLoad({ token, value });
      })
      .catch((error) => {
        if (active) setLoad({ token, error });
      });
    return () => {
      active = false;
    };
  }, [ctx.client, ctx.schoolId, token]);
  return load.token === token ? load : { token };
}
export function Pager({
  offset,
  total,
  onChange,
}: {
  offset: number;
  total: number;
  onChange: (n: number) => void;
}) {
  return (
    <nav aria-label="Flere resultater" className="planning-actions">
      <button
        type="button"
        disabled={!offset}
        onClick={() => onChange(Math.max(0, offset - 50))}
      >
        Forrige side
      </button>
      <span>
        {total
          ? `${offset + 1}–${Math.min(offset + 50, total)} av ${total}`
          : "Ingen registrerte"}
      </span>
      <button
        type="button"
        disabled={offset + 50 >= total}
        onClick={() => onChange(offset + 50)}
      >
        Neste side
      </button>
    </nav>
  );
}
export function ListBlock<T>({
  ctx,
  path,
  children,
  query,
  empty = "Ingen registrerte opplysninger.",
}: {
  ctx: Context;
  path: readonly string[];
  children: (v: T) => ReactNode;
  query?: Record<string, string>;
  empty?: string;
}) {
  const [offset, setOffset] = useState(0);
  const params = new URLSearchParams({
    ...query,
    offset: String(offset),
    limit: "50",
  });
  const load = useRead<List<T>>(ctx, path, params);
  return (
    <>
      {load.error ? (
        <p role="alert">{ctx.formatError(load.error)}</p>
      ) : !load.value ? (
        <p role="status">Henter …</p>
      ) : (
        <>
          <div className="planning-list">
            {load.value.items.length ? (
              load.value.items.map((v, i) => (
                <div
                  key={
                    v && typeof v === "object" && "id" in v ? String(v.id) : i
                  }
                >
                  {children(v)}
                </div>
              ))
            ) : (
              <p>{empty}</p>
            )}
          </div>
          <Pager
            offset={offset}
            total={load.value.total}
            onChange={setOffset}
          />
        </>
      )}
    </>
  );
}
// A pending command owns its immutable payload until a definitive reply. A conflict
// never changes the draft or expected revision behind the practitioner's back.
export function useCommand(ctx: Context) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [pending, setPending] = useState(false),
    [notice, setNotice] = useState("");
  const alive = useRef(true);
  const attempt = useRef<{
    path: readonly string[];
    body: unknown;
    done?: (v: unknown) => void;
    method: "POST" | "PATCH";
  } | null>(null);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const send = async () => {
    const a = attempt.current;
    if (!a || busy) return;
    setBusy(true);
    setError(undefined);
    try {
      const value = await ctx.client.schoolCommand(
        ctx.schoolId,
        a.path,
        a.body,
        a.method,
      );
      if (!alive.current) return;
      attempt.current = null;
      setPending(false);
      setNotice("Lagret.");
      a.done?.(value);
      ctx.changed();
    } catch (e) {
      if (!alive.current) return;
      setError(e);
      const uncertain =
        !(e instanceof ApiError) || e.status === 0 || e.status >= 500;
      setPending(uncertain);
      if (!uncertain) attempt.current = null;
    } finally {
      if (alive.current) setBusy(false);
    }
  };
  return {
    busy,
    pending,
    error,
    notice,
    submit: (
      path: readonly string[],
      body: unknown,
      done?: (v: unknown) => void,
      method: "POST" | "PATCH" = "POST",
    ) => {
      if (attempt.current || busy) return;
      attempt.current = {
        path: [...path],
        body: structuredClone(body),
        done,
        method,
      };
      void send();
    },
    status: (
      <div aria-live="polite">
        {error !== undefined && (
          <p role="alert">
            {ctx.formatError(error)}
            {error instanceof ApiError && error.status === 409
              ? " Utkastet er bevart. Les den oppdaterte versjonen og avklar forskjellene før du lager et nytt forsøk."
              : ""}
          </p>
        )}
        {pending && (
          <div className="planning-warning">
            <p>
              Lagringen har et uavklart svar. Feltene er låst til det samme
              forsøket er avklart.
            </p>
            <button type="button" disabled={busy} onClick={() => void send()}>
              Avklar ved å gjenta samme forsøk
            </button>
          </div>
        )}
        {notice && <p role="status">{notice}</p>}
      </div>
    ),
  };
}
export const binding = (e: Evidence): Binding => ({
  evidence_id: e.id,
  evidence_revision: e.revision,
  link_id: e.source.link_id,
});
export function SourcePicker({
  ctx,
  value,
  onChange,
  title = "Kildegrunnlag",
}: {
  ctx: Context;
  value: Binding | null;
  onChange: (b: Binding) => void;
  title?: string;
}) {
  const [offset, setOffset] = useState(0),
    [query, setQuery] = useState(""),
    [selected, setSelected] = useState<Evidence | null>(null);
  const params = new URLSearchParams({
    offset: String(offset),
    limit: "50",
    certainty: "confirmed",
    ...(query ? { query } : {}),
  });
  const load = useRead<List<Evidence>>(
    ctx,
    ["learners", ctx.learnerId, "timeline"],
    params,
  );
  const excerpt = useRead<{ excerpt: string; page: number; revision: number }>(
    ctx,
    value
      ? ["source-excerpts", value.link_id]
      : ["learners", ctx.learnerId, "timeline"],
    undefined,
    Boolean(value),
  );
  return (
    <fieldset className="planning-source">
      <legend>{title}</legend>
      <Field
        title="Søk i bekreftet grunnlag"
        value={query}
        required={false}
        onChange={(v) => {
          setOffset(0);
          setQuery(v);
        }}
      />
      {load.error ? (
        <p role="alert">{ctx.formatError(load.error)}</p>
      ) : !load.value ? (
        <p>Henter kilder …</p>
      ) : (
        <>
          <label>
            Velg opplysning
            <select
              value={
                load.value.items.some((e) => e.id === value?.evidence_id)
                  ? value?.evidence_id
                  : ""
              }
              onChange={(ev) => {
                const e = load.value!.items.find(
                  (v) => v.id === ev.target.value,
                );
                if (e) {
                  setSelected(e);
                  onChange(binding(e));
                }
              }}
            >
              <option value="">Velg en kilde …</option>
              {load.value.items.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.content.slice(0, 100)} · {e.reporter} ·{" "}
                  {when(e.occurred_at)}
                </option>
              ))}
            </select>
          </label>
          <Pager
            offset={offset}
            total={load.value.total}
            onChange={setOffset}
          />
        </>
      )}
      {value && (
        <div>
          <p>
            Valgt kilde, opplysningsversjon {value.evidence_revision}
            {selected?.id === value.evidence_id
              ? ` · ${selected.reporter}`
              : ""}
          </p>
          {excerpt.value?.excerpt && (
            <blockquote>
              {excerpt.value.excerpt}
              <footer>
                Side {excerpt.value.page}, kildeversjon {excerpt.value.revision}
              </footer>
            </blockquote>
          )}
          {excerpt.error !== undefined && (
            <p role="alert">
              Kilden må kontrolleres: {ctx.formatError(excerpt.error)}
            </p>
          )}
        </div>
      )}
      <p className="planning-help">
        Mangler grunnlag? Registrer og bekreft dokumentet eller notatet i
        innboksen først.
      </p>
    </fieldset>
  );
}
export function SourceView({
  ctx,
  value,
}: {
  ctx: Context;
  value: Binding | null | undefined;
}) {
  const [open, setOpen] = useState(false);
  return value ? (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        Kilde og utdrag · opplysningsversjon {value.evidence_revision}
      </summary>
      {open && <Excerpt ctx={ctx} value={value} />}
    </details>
  ) : null;
}
function Excerpt({ ctx, value }: { ctx: Context; value: Binding }) {
  const data = useRead<{ excerpt: string; page: number; revision: number }>(
    ctx,
    ["source-excerpts", value.link_id],
  );
  return data.error ? (
    <p role="alert">{ctx.formatError(data.error)}</p>
  ) : data.value ? (
    <blockquote>
      {data.value.excerpt}
      <footer>
        Side {data.value.page}, kildeversjon {data.value.revision}
      </footer>
    </blockquote>
  ) : (
    <p>Henter kilde …</p>
  );
}
export function State({ value }: { value: string }) {
  return (
    <span
      className={`planning-state ${value === "review_required" || value === "disputed" ? "planning-warning" : ""}`}
    >
      {label(value)}
    </span>
  );
}
