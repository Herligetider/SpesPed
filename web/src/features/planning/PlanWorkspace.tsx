import { useRef, useState } from "react";
import type { Context, Decision, List, Plan } from "./types";
import {
  Field,
  ListBlock,
  Pager,
  QuantityView,
  SourceView,
  State,
  key,
  label,
  useCommand,
  useRead,
  when,
} from "./shared";
import PlanEditor from "./PlanEditor";
import PlanSuggestions from "./PlanSuggestions";
export default function PlanWorkspace({
  ctx,
  decision,
}: {
  ctx: Context;
  decision: Decision | null;
}) {
  const [selected, setSelected] = useState(""),
    [creating, setCreating] = useState(false);
  const checkedDecision = useRead<Decision>(
    ctx,
    decision
      ? ["support-cases", decision.case_id, "decisions", decision.id]
      : ["learners", ctx.learnerId, "education-plans"],
    undefined,
    Boolean(decision),
  );
  const currentDecision =
    checkedDecision.value?.source_status === "current" &&
    checkedDecision.value.content.state === "confirmed"
      ? checkedDecision.value
      : null;
  return (
    <section>
      <h3>Planer, IOP og mål</h3>
      <p>
        Ordinær undervisning kan planlegges uten vedtak. En IOP knyttes til en
        bekreftet vedtaksrevisjon.
      </p>
      {currentDecision && (
        <p role="status">
          Valgt plangrunnlag: {currentDecision.content.issuing_authority},
          vedtaksrevisjon {currentDecision.content.revision}.
        </p>
      )}
      <ListBlock<Plan>
        ctx={ctx}
        path={["learners", ctx.learnerId, "education-plans"]}
      >
        {(p) => (
          <article className="planning-card">
            <h4>
              {p.source_status === "current"
                ? p.content.title
                : "Plan med grunnlag som må vurderes på nytt"}
            </h4>
            <PlanState plan={p} />
            <State value={p.source_status} />
            <p>
              Revisjon {p.current_revision} ·{" "}
              {p.kind === "individual_education"
                ? "IOP"
                : "Ordinær undervisning"}
            </p>
            <button
              type="button"
              onClick={() => {
                setSelected(p.id);
                setCreating(false);
              }}
            >
              Åpne plan og revisjoner
            </button>
          </article>
        )}
      </ListBlock>
      <button
        type="button"
        onClick={() => {
          setCreating(true);
          setSelected("");
        }}
      >
        Opprett plan
      </button>
      {creating && (
        <PlanEditor
          ctx={ctx}
          decision={currentDecision}
          onClose={() => setCreating(false)}
          onSaved={(p) => {
            setCreating(false);
            setSelected(p.id);
          }}
        />
      )}
      {selected && (
        <PlanDetail
          key={selected}
          ctx={ctx}
          planId={selected}
          decision={currentDecision}
        />
      )}
    </section>
  );
}
function PlanDetail({
  ctx,
  planId,
  decision,
}: {
  ctx: Context;
  planId: string;
  decision: Decision | null;
}) {
  const load = useRead<Plan>(ctx, ["education-plans", planId]);
  const [editing, setEditing] = useState<Plan | null>(null);
  const retained = useRef<Plan | null>(null);
  if (load.value) retained.current = load.value;
  const plan = retained.current;
  if (!plan)
    return load.error ? (
      <p role="alert">{ctx.formatError(load.error)}</p>
    ) : (
      <p role="status">Henter gjeldende plan …</p>
    );
  return (
    <section className="planning-detail">
      <h4>Gjeldende lagrede revisjon</h4>
      <button type="button" onClick={ctx.changed}>
        Hent gjeldende plan og kildekontroll
      </button>
      <PlanState plan={plan} />
      <State value={plan.source_status} />
      {load.error !== undefined && (
        <p role="alert">{ctx.formatError(load.error)}</p>
      )}
      {!load.value && <p role="status">Kontrollerer gjeldende grunnlag …</p>}
      <div hidden={!load.value || load.value.source_status !== "current"}>
        <PlanView ctx={ctx} plan={plan} />
        <Lifecycle
          key={`${plan.content.id}:${plan.revision_state}`}
          ctx={ctx}
          plan={plan}
        />
        <button type="button" onClick={() => setEditing(plan)}>
          Rediger som ny revisjon
        </button>
        {editing && (
          <PlanEditor
            key={editing.content.id}
            ctx={ctx}
            initial={editing}
            latest={plan}
            decision={decision}
            onClose={() => setEditing(null)}
            onSaved={() => setEditing(null)}
          />
        )}
        {plan.source_status === "current" && (
          <PlanSuggestions
            ctx={ctx}
            plan={plan}
            onSaved={() => setEditing(null)}
          />
        )}
      </div>
      {load.value?.source_status !== "current" && load.value && (
        <p className="planning-warning">
          Planens grunnlag må vurderes på nytt. Tidligere kildetekst og
          modelltekst er skjult. Du kan opprette en egen manuell plan fra
          bekreftet grunnlag.
        </p>
      )}
      {plan.clarifications.length > 0 && (
        <div className="planning-warning">
          <h5>Avklaringer før planen kan tas i bruk</h5>
          <ul>
            {plan.clarifications.map((c, i) => (
              <li key={i}>{basisIssue(c.code)}</li>
            ))}
          </ul>
        </div>
      )}
      <History ctx={ctx} plan={plan} />
    </section>
  );
}
export function PlanView({ ctx, plan }: { ctx: Context; plan: Plan }) {
  if (plan.source_status !== "current")
    return <p>Grunnlaget må vurderes på nytt før innholdet kan vises.</p>;
  const p = plan.content;
  return (
    <article className="planning-plan">
      <h4>
        {p.title} · revisjon {p.revision}
      </h4>
      <p>
        {plan.approved_at
          ? `Denne revisjonen ble godkjent ${when(plan.approved_at)}.`
          : null}
      </p>
      <p>
        {label(p.origin)} · {when(p.effective_from)} – {when(p.effective_until)}{" "}
        (slutt ikke inkludert)
      </p>
      {(
        [
          "rationale",
          "organization",
          "responsibility",
          "evaluation_method",
          "participation_record",
        ] as const
      ).map((f) => (
        <section key={f}>
          <h5>{label(f)}</h5>
          <p>{p[f]}</p>
        </section>
      ))}
      {p.original_approval && (
        <section>
          <h5>Dokumentert originalgodkjenning</h5>
          <p>
            {p.original_approval.approver} · {p.original_approval.authority} ·{" "}
            {when(p.original_approval.approved_at)}
          </p>
          <SourceView ctx={ctx} value={p.original_approval.source} />
        </section>
      )}
      {p.sources.map((b, i) => (
        <SourceView key={i} ctx={ctx} value={b} />
      ))}
      <h5>Mål og delmål</h5>
      {p.goals.map((g, i) => (
        <article key={g.goal_id || i} className="planning-provision">
          <h5>
            {g.title} · {label(g.status)}
          </h5>
          {g.parent_goal_id && (
            <p>
              Delmål til{" "}
              {p.goals.find((v) => v.goal_id === g.parent_goal_id)?.title ||
                "tidligere mål"}
            </p>
          )}
          {(
            [
              "expected_action",
              "arena",
              "support",
              "responsibility",
              "evaluation_method",
              "curriculum_reference",
            ] as const
          ).map((f) => (
            <p key={f}>
              <strong>{label(f)}:</strong> {g[f]}
            </p>
          ))}
          <p>
            {when(g.effective_from)} – {when(g.effective_until)} (slutt ikke
            inkludert)
          </p>
        </article>
      ))}
      <h5>Tilpasninger</h5>
      {p.adaptations.length ? (
        p.adaptations.map((a, i) => (
          <div key={i}>
            <p>
              {a.measure} · {a.arena}
            </p>
            <p>
              Ansvar: {a.responsibility} · Evaluering: {a.evaluation_method}
            </p>
          </div>
        ))
      ) : (
        <p>Ingen særskilte tilpasninger registrert.</p>
      )}
      <h5>Faktiske innspill</h5>
      {p.contributions.length ? (
        p.contributions.map((c, i) => (
          <div key={i}>
            <p>
              {c.role === "learner" ? "Elev" : "Foresatt"}: {c.participant} ·{" "}
              {when(c.occurred_at)}
            </p>
            <p>
              {c.content}
              {c.disagreement ? " (uenighet registrert)" : ""}
            </p>
            <p>Oppfølging: {c.response}</p>
            <SourceView ctx={ctx} value={c.source} />
          </div>
        ))
      ) : (
        <p>
          Ingen separate innspill registrert. Se beskrivelsen av medvirkning.
        </p>
      )}
      {p.allocations.length > 0 && (
        <>
          <h5>Fordeling innenfor vedtak</h5>
          {p.allocations.map((a, i) => (
            <p key={i}>
              <QuantityView value={a} /> · {when(a.effective_from)} –{" "}
              {when(a.effective_until)} (slutt ikke inkludert)
            </p>
          ))}
        </>
      )}
    </article>
  );
}
function Lifecycle({ ctx, plan }: { ctx: Context; plan: Plan }) {
  const [reason, setReason] = useState(""),
    [checked, setChecked] = useState(false);
  const cmd = useCommand(ctx);
  const action =
    plan.revision_state === "draft"
      ? "review"
      : plan.revision_state === "in_review"
        ? "approve"
        : plan.revision_state === "approved"
          ? "activate"
          : null;
  const title =
    action === "review"
      ? "Send vist revisjon til faglig gjennomgang"
      : action === "approve"
        ? "Godkjenn vist revisjon"
        : "Aktiver godkjent revisjon";
  return action ? (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        cmd.submit(
          ["education-plans", plan.id, action],
          {
            request_key: key(),
            expected_version: plan.version,
            revision_id: plan.content.id,
            content_digest: plan.content_digest,
            reason,
          },
          () => setChecked(false),
        );
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
          Jeg har lest innholdet og kontrollert kildene for den viste revisjonen
        </label>
        <Field
          title="Faglig begrunnelse for dette steget"
          value={reason}
          onChange={setReason}
        />
        <button type="submit" disabled={!checked}>
          {title}
        </button>
      </fieldset>
      {cmd.status}
    </form>
  ) : (
    <p>
      {plan.revision_state === "active"
        ? "Denne revisjonen er aktiv. Endringer lagres som et nytt utkast."
        : "Denne revisjonen har ikke et tilgjengelig neste godkjenningssteg."}
    </p>
  );
}
function History({ ctx, plan }: { ctx: Context; plan: Plan }) {
  const [open, setOpen] = useState(false);
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Revisjonshistorikk og sammenligning</summary>
      {open && <HistoryContent ctx={ctx} plan={plan} />}
    </details>
  );
}
function HistoryContent({ ctx, plan }: { ctx: Context; plan: Plan }) {
  const [offset, setOffset] = useState(0),
    [selected, setSelected] = useState("");
  const load = useRead<List<Plan>>(
    ctx,
    ["education-plans", plan.id, "revisions"],
    new URLSearchParams({ offset: String(offset), limit: "50" }),
  );
  const old = load.value?.items.find((p) => p.content.id === selected);
  return load.error ? (
    <p role="alert">{ctx.formatError(load.error)}</p>
  ) : !load.value ? (
    <p>Henter historikk …</p>
  ) : (
    <>
      <label>
        Velg revisjon som skal sammenlignes med gjeldende
        <select
          value={old ? selected : ""}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">Velg revisjon …</option>
          {load.value.items.map((p) => (
            <option key={p.content.id} value={p.content.id}>
              Revisjon {p.content.revision} · {label(p.revision_state)} ·{" "}
              {label(p.source_status)}
            </option>
          ))}
        </select>
      </label>
      <Pager
        offset={offset}
        total={load.value.total}
        onChange={(n) => {
          setOffset(n);
          setSelected("");
        }}
      />
      {old && (
        <>
          <GoalComparison
            ctx={ctx}
            planId={plan.id}
            oldId={old.content.id!}
            newId={plan.content.id!}
            old={old}
            current={plan}
          />
          <div className="planning-two">
            <section>
              <h4>Tidligere valgt revisjon</h4>
              <PlanView ctx={ctx} plan={old} />
            </section>
            <section>
              <h4>Gjeldende lagrede revisjon</h4>
              <button type="button" onClick={ctx.changed}>
                Hent gjeldende plan og kildekontroll
              </button>
              <PlanView ctx={ctx} plan={plan} />
            </section>
          </div>
        </>
      )}
    </>
  );
}
function GoalComparison({
  ctx,
  planId,
  oldId,
  newId,
  old,
  current,
}: {
  ctx: Context;
  planId: string;
  oldId: string;
  newId: string;
  old: Plan;
  current: Plan;
}) {
  const load = useRead<{ items: { goal_id: string; change: string }[] }>(
    ctx,
    ["education-plans", planId, "compare"],
    new URLSearchParams({ old_revision_id: oldId, new_revision_id: newId }),
  );
  return load.value ? (
    <ul>
      {load.value.items.map((g) => (
        <li key={g.goal_id}>
          {(current.source_status === "current"
            ? current.content.goals.find((v) => v.goal_id === g.goal_id)?.title
            : undefined) ||
            (old.source_status === "current"
              ? old.content.goals.find((v) => v.goal_id === g.goal_id)?.title
              : undefined) ||
            "Mål"}
          : {label(g.change)}
        </li>
      ))}
    </ul>
  ) : load.error ? (
    <p role="alert">{ctx.formatError(load.error)}</p>
  ) : (
    <p>Sammenligner mål …</p>
  );
}

function basisIssue(code: string): string {
  const reasons: Record<string, string> = {
    generation_processing_changed:
      "Modellen eller behandlingsgrunnlaget er endret. Vurder kildegrunnlaget på nytt før planen godkjennes.",
    decision_required:
      "IOP mangler bekreftet vedtak eller fordeling fra vedtaket.",
    decision_period:
      "Planperioden eller fordelingen går utenfor vedtakets periode.",
    quantity_basis:
      "Fordelingen må bruke samme periode og tellegrunnlag som vedtaket.",
    decision_exceeded: "Planens omfang går utover en bekreftet bestemmelse.",
    ito_required:
      "IOP må ha en bekreftet bestemmelse om individuelt tilrettelagt opplæring.",
    plan_expired: "Planens gyldighet er utløpt. Avklar en ny datert revisjon.",
    source_review_required: "En kilde er endret og må vurderes på nytt.",
  };
  return (
    reasons[code] ||
    "Kilde-, vedtaks- eller modellgrunnlaget er endret. Kontroller grunnlaget før planen godkjennes eller aktiveres."
  );
}

function PlanState({ plan }: { plan: Plan }) {
  return (
    <div>
      <p>
        {plan.active_revision_id
          ? plan.active_revision_id === plan.content.id
            ? "Vist revisjon er aktiv."
            : "En tidligere revisjon er fortsatt aktiv."
          : "Planen har ingen aktiv revisjon."}
      </p>
      <p>
        Vist revisjon {plan.content.revision || plan.current_revision}:{" "}
        <State value={plan.revision_state} />
      </p>
    </div>
  );
}
