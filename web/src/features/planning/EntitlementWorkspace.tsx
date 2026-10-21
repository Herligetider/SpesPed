import { useState } from "react";
import type {
  Assessment,
  Binding,
  Context,
  Decision,
  Period,
  Provision,
  Recommendation,
  SupportCase,
} from "./types";
import {
  Dates,
  Field,
  ListBlock,
  QuantityFields,
  QuantityView,
  SourcePicker,
  SourceView,
  State,
  emptyPeriod,
  key,
  label,
  localInstant,
  period,
  useCommand,
  useRead,
  when,
} from "./shared";
const categories = [
  "individually_adapted_education",
  "personal_assistance",
  "physical_adaptation",
];
export function EntitlementWorkspace({
  ctx,
  onDecision,
}: {
  ctx: Context;
  onDecision: (d: Decision) => void;
}) {
  const [selected, setSelected] = useState<SupportCase | null>(null),
    [concern, setConcern] = useState(""),
    [created, setCreated] = useState(false);
  const cmd = useCommand(ctx);
  return (
    <section>
      <h3>Støttesaker og bekreftet grunnlag</h3>
      <p>
        Sakkyndige anbefalinger og vedtatte rettigheter vises hver for seg.
        Opprettelse gir ikke automatisk lesetilgang til saken.
      </p>
      <ListBlock<SupportCase>
        ctx={ctx}
        path={["learners", ctx.learnerId, "support-cases"]}
      >
        {(c) => (
          <article className="planning-card">
            <h4>{c.concern}</h4>
            <State value={c.state} />
            <button type="button" onClick={() => setSelected(c)}>
              Åpne støttesak
            </button>
          </article>
        )}
      </ListBlock>
      <details>
        <summary>Opprett støttesak</summary>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            cmd.submit(
              ["learners", ctx.learnerId, "support-cases"],
              { request_key: key(), concern, owner_id: ctx.currentUser.id },
              () => {
                setConcern("");
                setCreated(true);
              },
            );
          }}
        >
          <fieldset disabled={cmd.busy || cmd.pending}>
            <legend>Ny støttesak</legend>
            <p>
              Registrert ansvarlig: {ctx.currentUser.display_name}. Fullmakt
              kontrolleres ved lagring.
            </p>
            <Field
              title="Behov og formål med saken"
              type="textarea"
              value={concern}
              onChange={setConcern}
            />
            <button type="submit">Opprett sak</button>
          </fieldset>
          {cmd.status}
        </form>
      </details>
      {created && (
        <p role="status">
          Saken er opprettet. Opprettelsen gir ikke i seg selv lesetilgang til
          saksinnhold. Hvis saken ikke vises i oversikten, må ansvarlig med
          fullmakt gi særskilt sakstilgang før videre arbeid. Dette
          administreres utenfor denne arbeidsflaten.
        </p>
      )}
      {selected && (
        <CaseDetail
          key={selected.id}
          ctx={ctx}
          identity={selected.id}
          onClose={() => setSelected(null)}
          onDecision={onDecision}
        />
      )}
    </section>
  );
}
function CaseDetail({
  ctx,
  identity,
  onClose,
  onDecision,
}: {
  ctx: Context;
  identity: string;
  onClose: () => void;
  onDecision: (d: Decision) => void;
}) {
  const load = useRead<SupportCase>(ctx, ["support-cases", identity]);
  if (load.error) return <p role="alert">{ctx.formatError(load.error)}</p>;
  if (!load.value) return <p>Henter sak …</p>;
  return (
    <section className="planning-case">
      <div className="planning-actions">
        <h4>{load.value.concern}</h4>
        <button type="button" onClick={onClose}>
          Lukk sak
        </button>
      </div>
      <State value={load.value.state} />
      <div className="planning-two">
        <section>
          <h4>Sakkyndige anbefalinger</h4>
          <p>
            En anbefaling er et faglig grunnlag. Den fastsetter ikke elevens
            rettigheter.
          </p>
          <ListBlock<Assessment>
            ctx={ctx}
            path={["support-cases", identity, "expert-assessments"]}
          >
            {(a) => (
              <article className="planning-card">
                <h5>{a.issuer || "Sakkyndig vurdering"}</h5>
                <State value={a.state} />
                <State value={a.source_status} />
                <p>
                  Vurdert {when(a.assessment_at)} · gyldig til{" "}
                  {when(a.valid_until)}
                </p>
                {a.source_status === "current" && (
                  <>
                    <SourceView ctx={ctx} value={a.source} />
                    {a.recommendations.map((r, i) => (
                      <ProvisionView
                        key={r.id || i}
                        ctx={ctx}
                        value={r}
                        recommendation
                      />
                    ))}
                    {a.state !== "confirmed" && (
                      <Confirm
                        ctx={ctx}
                        path={[
                          "support-cases",
                          identity,
                          "expert-assessments",
                          a.id,
                          "confirm",
                        ]}
                        version={a.version}
                        title="Bekreft sakkyndig vurdering"
                      />
                    )}
                  </>
                )}
              </article>
            )}
          </ListBlock>
          <EvidenceEntry ctx={ctx} caseId={identity} mode="assessment" />
        </section>
        <section>
          <h4>Vedtak og bestemmelser</h4>
          <ListBlock<Decision>
            ctx={ctx}
            path={["support-cases", identity, "decisions"]}
          >
            {(d) => (
              <article className="planning-card">
                <h5>{d.content.issuing_authority || "Vedtak"}</h5>
                <State value={d.content.state} />
                <State value={d.source_status} />
                {d.source_status === "current" && (
                  <>
                    <p>Vedtaksmyndighet: {d.content.issuing_authority}</p>
                    <p>Myndighetsgrunnlag: {d.content.authority_basis}</p>
                    <p>Utstedt {when(d.content.issued_at)}</p>
                    <p>
                      Gyldig {when(d.content.effective_from)} –{" "}
                      {when(d.content.effective_until)} (slutt ikke inkludert)
                    </p>
                    <SourceView ctx={ctx} value={d.content.source} />
                    {d.provisions.map((p, i) => (
                      <ProvisionView key={p.id || i} ctx={ctx} value={p} />
                    ))}
                    {d.content.state !== "confirmed" && (
                      <Confirm
                        ctx={ctx}
                        path={[
                          "support-cases",
                          identity,
                          "decisions",
                          d.id,
                          "confirm",
                        ]}
                        version={d.version}
                        title="Bekreft vedtak og bestemmelser"
                      />
                    )}
                    {d.content.state === "confirmed" && (
                      <button type="button" onClick={() => onDecision(d)}>
                        Bruk dette vedtaket som plangrunnlag
                      </button>
                    )}
                  </>
                )}
                <details>
                  <summary>Vedtaksrevisjoner</summary>
                  <ListBlock<Decision>
                    ctx={ctx}
                    path={[
                      "support-cases",
                      identity,
                      "decisions",
                      d.id,
                      "history",
                    ]}
                  >
                    {(h) => (
                      <article>
                        <h5>Revisjon {h.content.revision}</h5>
                        <State value={h.content.state} />
                        <State value={h.source_status} />
                        {h.source_status === "current" &&
                          h.provisions.map((p, i) => (
                            <ProvisionView key={i} ctx={ctx} value={p} />
                          ))}
                      </article>
                    )}
                  </ListBlock>
                </details>
              </article>
            )}
          </ListBlock>
          <EvidenceEntry ctx={ctx} caseId={identity} mode="decision" />
        </section>
      </div>
      <Comparison ctx={ctx} caseId={identity} />
      <details>
        <summary>Datert saksforløp</summary>
        <ListBlock<{ kind: string; occurred_at: string; state?: string }>
          ctx={ctx}
          path={["support-cases", identity, "timeline"]}
        >
          {(v) => (
            <p>
              {when(v.occurred_at)} ·{" "}
              {(
                {
                  case_created: "Sak opprettet",
                  expert_assessment: "Sakkyndig vurdering",
                  decision_received: "Vedtak mottatt",
                  clarification: "Avklaring",
                } as Record<string, string>
              )[v.kind] || "Registrert sakshendelse"}{" "}
              {v.state && label(v.state)}
            </p>
          )}
        </ListBlock>
      </details>
    </section>
  );
}
export function Confirm({
  ctx,
  path,
  version,
  title,
}: {
  ctx: Context;
  path: string[];
  version: number;
  title: string;
}) {
  const [reason, setReason] = useState(""),
    [checked, setChecked] = useState(false);
  const cmd = useCommand(ctx);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        cmd.submit(path, {
          request_key: key(),
          expected_version: version,
          reason,
        });
      }}
    >
      <fieldset disabled={cmd.busy || cmd.pending}>
        <legend>{title}</legend>
        <label>
          <input
            type="checkbox"
            required
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
          />{" "}
          Jeg har kontrollert de viste feltene mot kilden
        </label>
        <Field
          title="Begrunnelse for bekreftelsen"
          value={reason}
          onChange={setReason}
        />
        <button type="submit" disabled={!checked}>
          {title}
        </button>
      </fieldset>
      {cmd.status}
    </form>
  );
}
export function ProvisionView({
  ctx,
  value: r,
  recommendation = false,
}: {
  ctx: Context;
  value: Recommendation | Provision;
  recommendation?: boolean;
}) {
  const p = r as Provision;
  return (
    <div className="planning-provision">
      <h5>
        {recommendation ? "Anbefaling" : `Bestemmelse ${p.clause}`} ·{" "}
        {label(r.category)} · {r.subject}
      </h5>
      <p>{r.content}</p>
      <p>
        <QuantityView value={r} />
      </p>
      <p>
        {when(r.effective_from)} – {when(r.effective_until)} (slutt ikke
        inkludert)
      </p>
      {!recommendation && (
        <>
          <p>Organisering: {p.organization}</p>
          <p>Kompetanse: {p.competence}</p>
        </>
      )}
      <SourceView ctx={ctx} value={r.source} />
    </div>
  );
}
function EvidenceEntry({
  ctx,
  caseId,
  mode,
}: {
  ctx: Context;
  caseId: string;
  mode: "assessment" | "decision";
}) {
  const [source, setSource] = useState<Binding | null>(null),
    [issuer, setIssuer] = useState(""),
    [authority, setAuthority] = useState(""),
    [date, setDate] = useState(""),
    [validUntil, setValidUntil] = useState(""),
    [dates, setDates] = useState<Period>(emptyPeriod()),
    [rows, setRows] = useState<Provision[]>([]),
    [validation, setValidation] = useState("");
  const cmd = useCommand(ctx);
  const add = () => {
    if (source)
      setRows([
        ...rows,
        {
          ...emptyPeriod(),
          clause: String(rows.length + 1),
          category: "individually_adapted_education",
          subject: "",
          content: "",
          organization: "",
          competence: "",
          amount: null,
          unit: null,
          counting_basis: null,
          source,
        },
      ]);
  };
  return (
    <details>
      <summary>
        {mode === "assessment"
          ? "Registrer sakkyndig vurdering"
          : "Registrer eksisterende vedtak"}
      </summary>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setValidation("");
          if (!source) return;
          try {
            const values = rows.map((r) => ({ ...r, ...period(r) }));
            const payload =
              mode === "assessment"
                ? {
                    issuer,
                    assessment_at: localInstant(date),
                    valid_until: validUntil ? localInstant(validUntil) : null,
                    source,
                    recommendations: values.map(
                      ({ clause, organization, competence, ...r }) => {
                        void clause;
                        void organization;
                        void competence;
                        return r;
                      },
                    ),
                  }
                : {
                    issuing_authority: issuer,
                    authority_basis: authority,
                    issued_at: localInstant(date),
                    ...period(dates),
                    source,
                    provisions: values,
                  };
            cmd.submit(
              [
                "support-cases",
                caseId,
                mode === "assessment" ? "expert-assessments" : "decisions",
              ],
              { request_key: key(), ...payload },
            );
          } catch (e) {
            setValidation(ctx.formatError(e));
          }
        }}
      >
        <fieldset disabled={cmd.busy || cmd.pending}>
          <legend>
            {mode === "assessment"
              ? "Sakkyndig vurdering med anbefalinger"
              : "Vedtak med egne bestemmelser"}
          </legend>
          <Field
            title={
              mode === "assessment"
                ? "Utsteder av vurderingen"
                : "Vedtaksmyndighet"
            }
            value={issuer}
            onChange={setIssuer}
          />
          {mode === "decision" && (
            <Field
              title="Myndighetsgrunnlag"
              type="textarea"
              value={authority}
              onChange={setAuthority}
            />
          )}
          <Field
            title={
              mode === "assessment"
                ? "Vurderingens dato og tid"
                : "Vedtaksdato og tid"
            }
            type="datetime-local"
            value={date}
            onChange={setDate}
          />
          {mode === "assessment" ? (
            <Field
              title="Gyldig til (hvis oppgitt)"
              required={false}
              type="datetime-local"
              value={validUntil}
              onChange={setValidUntil}
            />
          ) : (
            <Dates value={dates} onChange={setDates} />
          )}
          <SourcePicker ctx={ctx} value={source} onChange={setSource} />
          {rows.map((r, i) => (
            <fieldset key={i}>
              <legend>
                {mode === "assessment" ? "Anbefaling" : "Bestemmelse"} {i + 1}
              </legend>
              <ProvisionFields
                ctx={ctx}
                value={r}
                onChange={(v) =>
                  setRows(rows.map((old, n) => (n === i ? v : old)))
                }
                recommendation={mode === "assessment"}
              />
              <button
                type="button"
                onClick={() => setRows(rows.filter((_, n) => n !== i))}
              >
                Fjern {mode === "assessment" ? "anbefaling" : "bestemmelse"}{" "}
                {i + 1}
              </button>
            </fieldset>
          ))}
          <button type="button" disabled={!source} onClick={add}>
            Legg til {mode === "assessment" ? "anbefaling" : "bestemmelse"}
          </button>
          <button type="submit" disabled={!source || !rows.length}>
            Lagre til kontroll
          </button>
        </fieldset>
        {validation && <p role="alert">{validation}</p>}
        {cmd.status}
      </form>
    </details>
  );
}
function ProvisionFields({
  ctx,
  value: r,
  onChange,
  recommendation,
}: {
  ctx: Context;
  value: Provision;
  onChange: (r: Provision) => void;
  recommendation: boolean;
}) {
  return (
    <>
      {!recommendation && (
        <Field
          title="Bestemmelsens nummer eller navn"
          value={r.clause}
          onChange={(clause) => onChange({ ...r, clause })}
        />
      )}
      <label>
        Støttekategori
        <select
          value={r.category}
          onChange={(e) => onChange({ ...r, category: e.target.value })}
        >
          {categories.map((c) => (
            <option key={c} value={c}>
              {label(c)}
            </option>
          ))}
        </select>
      </label>
      <Field
        title="Fag eller område"
        value={r.subject}
        onChange={(subject) => onChange({ ...r, subject })}
      />
      <Field
        title={recommendation ? "Anbefalt innhold" : "Vedtatt innhold"}
        type="textarea"
        value={r.content}
        onChange={(content) => onChange({ ...r, content })}
      />
      {!recommendation && (
        <>
          <Field
            title="Organisering"
            value={r.organization}
            onChange={(organization) => onChange({ ...r, organization })}
          />
          <Field
            title="Kompetansekrav"
            value={r.competence}
            onChange={(competence) => onChange({ ...r, competence })}
          />
        </>
      )}
      <QuantityFields
        value={r}
        optional={recommendation || r.category === "physical_adaptation"}
        onChange={(q) => onChange({ ...r, ...q })}
      />
      <Dates value={r} onChange={(p) => onChange({ ...r, ...p })} />
      <SourcePicker
        ctx={ctx}
        value={r.source}
        onChange={(source) => onChange({ ...r, source })}
        title={
          recommendation ? "Kilde for anbefalingen" : "Kilde for bestemmelsen"
        }
      />
    </>
  );
}
function Comparison({ ctx, caseId }: { ctx: Context; caseId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Sammenlign anbefalinger med vedtak</summary>
      {open && <ComparisonContent ctx={ctx} caseId={caseId} />}
    </details>
  );
}
function ComparisonContent({ ctx, caseId }: { ctx: Context; caseId: string }) {
  const load = useRead<{
    differences: {
      subject?: string;
      category?: string;
      recommended_amount?: string;
      recommended_unit?: string;
      decided_amount?: string;
      decided_unit?: string;
      comparable?: boolean;
      difference_minutes?: string;
      issue: string | null;
    }[];
  }>(ctx, ["support-cases", caseId, "comparison"]);
  return load.error ? (
    <p role="alert">{ctx.formatError(load.error)}</p>
  ) : load.value ? (
    <>
      <p>
        Omfang sammenlignes bare når periode og tellegrunnlag samsvarer. Ulike
        myndigheter og perioder slås ikke sammen.
      </p>
      {load.value.differences.length ? (
        <table>
          <thead>
            <tr>
              <th>Område</th>
              <th>Anbefalt</th>
              <th>Vedtatt</th>
              <th>Avklaring</th>
            </tr>
          </thead>
          <tbody>
            {load.value.differences.map((d, i) => (
              <tr key={i}>
                <td>
                  {d.subject || "Anbefaling uten tilsvarende bestemmelse"} ·{" "}
                  {d.category && label(d.category)}
                </td>
                <td>
                  {d.recommended_amount}{" "}
                  {d.recommended_unit && label(d.recommended_unit)}
                </td>
                <td>
                  {d.decided_amount} {d.decided_unit && label(d.decided_unit)}
                </td>
                <td>
                  {d.comparable
                    ? `Forskjell: ${d.difference_minutes} minutter`
                    : d.issue === "no_matching_decision_provision"
                      ? "Ingen tilsvarende bestemmelse"
                      : "Ulikt eller uavklart grunnlag"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>Ingen registrerte sammenligningspunkter.</p>
      )}
    </>
  ) : (
    <p>Henter sammenligning …</p>
  );
}
