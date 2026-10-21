import { useState } from "react";
import type {
  Adaptation,
  Allocation,
  Binding,
  Context,
  Contribution,
  Decision,
  Goal,
  Plan,
  PlanContent,
} from "./types";
import {
  Dates,
  Field,
  QuantityFields,
  QuantityView,
  SourcePicker,
  SourceView,
  emptyPeriod,
  key,
  label,
  localInstant,
  localValue,
  period,
  useCommand,
} from "./shared";
export const newGoal = (): Goal => ({
  ...emptyPeriod(),
  goal_id: key(),
  parent_goal_id: null,
  status: "active",
  title: "",
  expected_action: "",
  arena: "",
  support: "",
  responsibility: "",
  evaluation_method: "",
  curriculum_reference: "",
});
export function blankPlan(): PlanContent {
  return {
    ...emptyPeriod(),
    title: "",
    rationale: "",
    organization: "",
    responsibility: "",
    evaluation_method: "",
    participation_record: "",
    decision_id: null,
    decision_revision_id: null,
    origin: "authored",
    sources: [],
    original_approval: null,
    goals: [newGoal()],
    adaptations: [],
    contributions: [],
    allocations: [],
  };
}
function draftOf(content: PlanContent): PlanContent {
  const d = structuredClone(content);
  d.effective_from = localValue(d.effective_from);
  d.effective_until = localValue(d.effective_until);
  d.goals = d.goals.map((g) => ({
    ...g,
    effective_from: localValue(g.effective_from),
    effective_until: localValue(g.effective_until),
  }));
  d.contributions = d.contributions.map((c) => ({
    ...c,
    occurred_at: localValue(c.occurred_at),
  }));
  d.allocations = d.allocations.map((a) => ({
    ...a,
    effective_from: localValue(a.effective_from),
    effective_until: localValue(a.effective_until),
  }));
  if (d.original_approval)
    d.original_approval.approved_at = localValue(
      d.original_approval.approved_at,
    );
  return d;
}
export function planCommand(value: PlanContent) {
  const clean = <T extends { id?: string }>(v: T) => {
    const { id, ...rest } = v;
    void id;
    return rest;
  };
  return {
    title: value.title,
    rationale: value.rationale,
    organization: value.organization,
    responsibility: value.responsibility,
    evaluation_method: value.evaluation_method,
    participation_record: value.participation_record,
    ...period(value),
    decision_id: value.decision_id,
    decision_revision_id: value.decision_revision_id,
    origin: value.origin,
    sources: value.sources,
    original_approval: value.original_approval
      ? {
          ...value.original_approval,
          approved_at: localInstant(value.original_approval.approved_at),
        }
      : null,
    goals: value.goals.map((g) => ({ ...clean(g), ...period(g) })),
    adaptations: value.adaptations.map(clean),
    contributions: value.contributions.map((c) => ({
      ...clean(c),
      occurred_at: localInstant(c.occurred_at),
    })),
    allocations: value.allocations.map((a) => ({ ...clean(a), ...period(a) })),
  };
}
export default function PlanEditor({
  ctx,
  initial,
  latest,
  decision,
  onSaved,
  onClose,
}: {
  ctx: Context;
  initial?: Plan;
  latest?: Plan;
  decision?: Decision | null;
  onSaved: (p: Plan) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<PlanContent>(() =>
      initial ? draftOf(initial.content) : blankPlan(),
    ),
    [kind, setKind] = useState<Plan["kind"]>(
      initial?.kind || "ordinary_teaching",
    ),
    [version, setVersion] = useState(initial?.version),
    [source, setSource] = useState<Binding | null>(null),
    [error, setError] = useState(""),
    [replaceFields, setReplaceFields] = useState<string[]>([]);
  const cmd = useCommand(ctx);
  const update = (part: Partial<PlanContent>) =>
    setDraft((d) => ({ ...d, ...part }));
  const isRevision = Boolean(initial);
  const chooseDecision = () => {
    if (
      !decision ||
      decision.source_status !== "current" ||
      decision.content.state !== "confirmed"
    )
      return;
    setKind("individual_education");
    update({
      decision_id: decision.id,
      decision_revision_id: decision.content.id,
      allocations: [],
    });
  };
  const selected =
    decision?.id === draft.decision_id &&
    decision?.content.id === draft.decision_revision_id
      ? decision
      : null;
  const fields = [
    "title",
    "rationale",
    "organization",
    "responsibility",
    "evaluation_method",
    "participation_record",
  ] as const;
  return (
    <form
      className="planning-editor"
      onSubmit={(e) => {
        e.preventDefault();
        setError("");
        try {
          const value = {
            ...draft,
            ...(isRevision
              ? { origin: "authored" as const, original_approval: null }
              : {}),
          };
          const body = {
            ...planCommand(value),
            request_key: key(),
            ...(isRevision
              ? {
                  expected_version: version,
                  sever_generation_fields: replaceFields,
                }
              : { kind }),
          };
          cmd.submit(
            isRevision
              ? ["education-plans", initial!.id, "revisions"]
              : ["learners", ctx.learnerId, "education-plans"],
            body,
            (v) => onSaved(v as Plan),
          );
        } catch (e) {
          setError(ctx.formatError(e));
        }
      }}
    >
      <fieldset disabled={cmd.busy || cmd.pending}>
        <legend>
          {isRevision
            ? `Rediger utkast fra revisjon ${initial!.content.revision}`
            : "Opprett undervisningsplan eller IOP"}
        </legend>
        {latest && version !== latest.version && (
          <div className="planning-warning">
            <p>
              Planen er endret siden redigeringen startet. Utkastet ditt er
              bevart. Gjeldende lagrede revisjon vises over skjemaet.
            </p>
            <p>
              Ny lagret versjon: {latest.content.title}, revisjon{" "}
              {latest.content.revision}. Les innholdet og historikken før du
              fortsetter.
            </p>
            <button type="button" onClick={() => setVersion(latest.version)}>
              Jeg har sammenlignet og vil lagre mitt utkast som ny revisjon av
              gjeldende versjon
            </button>
          </div>
        )}
        {!isRevision && (
          <label>
            Plantype
            <select
              value={kind}
              onChange={(e) => {
                const v = e.target.value as Plan["kind"];
                setKind(v);
                if (v === "ordinary_teaching")
                  update({
                    decision_id: null,
                    decision_revision_id: null,
                    allocations: [],
                  });
              }}
            >
              <option value="ordinary_teaching">
                Ordinær undervisningsplan
              </option>
              <option value="individual_education">
                Individuell opplæringsplan (IOP)
              </option>
            </select>
          </label>
        )}
        {kind === "individual_education" && (
          <div
            className={
              draft.decision_id ? "planning-basis" : "planning-warning"
            }
          >
            {draft.decision_id ? (
              <p>
                Planen er knyttet til en bestemt vedtaksrevisjon. Fordeling av
                omfang er registrert nedenfor.
              </p>
            ) : (
              <p>
                IOP krever bekreftet vedtak og egne fordelinger av omfang. Velg
                et vedtak under støttesaker.
              </p>
            )}
            {decision && !selected && (
              <button type="button" onClick={chooseDecision}>
                {draft.decision_id
                  ? "Erstatt vedtaksgrunnlag med valgt vedtak fra "
                  : "Knytt til valgt vedtak fra "}
                {decision.content.issuing_authority}
              </button>
            )}
            {selected && (
              <p>
                Valgt vedtak fra {selected.content.issuing_authority}, revisjon{" "}
                {selected.content.revision}. Eksisterende fordelinger beholdes.
              </p>
            )}
          </div>
        )}
        {fields.map((f) => (
          <Field
            key={f}
            title={label(f)}
            type={f === "title" ? "text" : "textarea"}
            value={draft[f]}
            onChange={(v) => update({ [f]: v })}
          />
        ))}
        <p className="planning-help">
          Registrer bare faktisk medvirkning. Manglende eller uavklarte innspill
          kan beskrives uttrykkelig.
        </p>
        <Dates value={draft} onChange={update} />
        {!isRevision && (
          <label>
            Opphav
            <select
              value={draft.origin}
              onChange={(e) =>
                update({
                  origin: e.target.value as PlanContent["origin"],
                  original_approval: null,
                })
              }
            >
              <option value="authored">Ny plan skrevet ved skolen</option>
              <option value="imported">
                Eksisterende godkjent plan registreres
              </option>
            </select>
          </label>
        )}
        {isRevision && initial!.content.origin === "imported" && (
          <p>
            Redigeringen lagres som nytt lokalt utkast. Den opprinnelige
            godkjenningen beholdes på den importerte revisjonen.
          </p>
        )}
        <SourcePicker
          ctx={ctx}
          value={source}
          onChange={setSource}
          title="Kilder til planen"
        />
        <button
          type="button"
          disabled={!source}
          onClick={() => {
            if (
              source &&
              !draft.sources.some(
                (b) => JSON.stringify(b) === JSON.stringify(source),
              )
            )
              update({ sources: [...draft.sources, source] });
          }}
        >
          Legg valgt kilde til planen
        </button>
        {draft.sources.map((b, i) => (
          <div key={i}>
            <SourceView ctx={ctx} value={b} />
            <button
              type="button"
              onClick={() =>
                update({ sources: draft.sources.filter((_, n) => n !== i) })
              }
            >
              Fjern plankilde {i + 1}
            </button>
          </div>
        ))}
        {draft.origin === "imported" && (
          <fieldset>
            <legend>Godkjenning i originaldokumentet</legend>
            {!draft.original_approval ? (
              <button
                type="button"
                disabled={!source}
                onClick={() =>
                  source &&
                  update({
                    original_approval: {
                      approver: "",
                      authority: "",
                      approved_at: "",
                      source,
                    },
                  })
                }
              >
                Registrer dokumentert originalgodkjenning
              </button>
            ) : (
              <>
                <Field
                  title="Opprinnelig godkjent av"
                  value={draft.original_approval.approver}
                  onChange={(approver) =>
                    update({
                      original_approval: {
                        ...draft.original_approval!,
                        approver,
                      },
                    })
                  }
                />
                <Field
                  title="Opprinnelig godkjenningsmyndighet"
                  value={draft.original_approval.authority}
                  onChange={(authority) =>
                    update({
                      original_approval: {
                        ...draft.original_approval!,
                        authority,
                      },
                    })
                  }
                />
                <Field
                  title="Faktisk opprinnelig godkjenningstidspunkt"
                  type="datetime-local"
                  value={draft.original_approval.approved_at}
                  onChange={(approved_at) =>
                    update({
                      original_approval: {
                        ...draft.original_approval!,
                        approved_at,
                      },
                    })
                  }
                />
                <SourcePicker
                  ctx={ctx}
                  value={draft.original_approval.source}
                  onChange={(b) =>
                    update({
                      original_approval: {
                        ...draft.original_approval!,
                        source: b,
                      },
                    })
                  }
                  title="Kilde for originalgodkjenningen"
                />
              </>
            )}
          </fieldset>
        )}
        <h4>Mål og delmål</h4>
        {draft.goals.map((g, i) => (
          <fieldset key={g.goal_id || i}>
            <legend>
              Mål {i + 1}: {g.title || "Nytt mål"}
            </legend>
            <GoalFields
              goal={g}
              goals={draft.goals}
              onChange={(v) =>
                update({
                  goals: draft.goals.map((old, n) => (n === i ? v : old)),
                })
              }
            />
            <button
              type="button"
              disabled={draft.goals.length === 1}
              onClick={() =>
                update({ goals: draft.goals.filter((_, n) => n !== i) })
              }
            >
              Fjern mål {i + 1} fra denne revisjonen
            </button>
          </fieldset>
        ))}
        <button
          type="button"
          onClick={() => update({ goals: [...draft.goals, newGoal()] })}
        >
          Legg til mål
        </button>
        <h4>Tilpasninger</h4>
        {draft.adaptations.map((a, i) => (
          <fieldset key={i}>
            <legend>Tilpasning {i + 1}</legend>
            <GoalSelect
              goals={draft.goals}
              value={a.goal_id}
              onChange={(goal_id) =>
                update({
                  adaptations: draft.adaptations.map((v, n) =>
                    n === i ? { ...v, goal_id } : v,
                  ),
                })
              }
            />
            {(
              [
                "measure",
                "arena",
                "responsibility",
                "evaluation_method",
              ] as const
            ).map((f) => (
              <Field
                key={f}
                title={f === "measure" ? "Tiltak" : label(f)}
                value={a[f]}
                type="textarea"
                onChange={(v) =>
                  update({
                    adaptations: draft.adaptations.map((old, n) =>
                      n === i ? { ...old, [f]: v } : old,
                    ),
                  })
                }
              />
            ))}
            <button
              type="button"
              onClick={() =>
                update({
                  adaptations: draft.adaptations.filter((_, n) => n !== i),
                })
              }
            >
              Fjern tilpasning {i + 1}
            </button>
          </fieldset>
        ))}
        <button
          type="button"
          onClick={() => {
            const a: Adaptation = {
              goal_id: null,
              measure: "",
              arena: "",
              responsibility: "",
              evaluation_method: "",
            };
            update({ adaptations: [...draft.adaptations, a] });
          }}
        >
          Legg til tilpasning
        </button>
        <h4>Elev- og foresattinnspill</h4>
        {draft.contributions.map((c, i) => (
          <ContributionFields
            key={i}
            ctx={ctx}
            contribution={c}
            goals={draft.goals}
            index={i}
            onChange={(v) =>
              update({
                contributions: draft.contributions.map((old, n) =>
                  n === i ? v : old,
                ),
              })
            }
            onRemove={() =>
              update({
                contributions: draft.contributions.filter((_, n) => n !== i),
              })
            }
          />
        ))}
        <button
          type="button"
          disabled={!source}
          onClick={() => {
            if (source) {
              const c: Contribution = {
                goal_id: null,
                participant: "",
                role: "learner",
                content: "",
                disagreement: false,
                response: "",
                occurred_at: "",
                source,
              };
              update({ contributions: [...draft.contributions, c] });
            }
          }}
        >
          Legg til faktisk innspill med valgt kilde
        </button>
        {kind === "individual_education" && (
          <>
            <h4>Planlagt fordeling innenfor vedtak</h4>
            {selected?.provisions.map((p) => (
              <button
                type="button"
                key={p.id}
                disabled={draft.allocations.some(
                  (a) => a.provision_id === p.id,
                )}
                onClick={() => {
                  const a: Allocation = {
                    provision_id: p.id!,
                    decision_id: selected.id,
                    decision_revision_id: selected.content.id,
                    amount: null,
                    unit: null,
                    counting_basis: null,
                    effective_from: localValue(p.effective_from),
                    effective_until: localValue(p.effective_until),
                  };
                  update({ allocations: [...draft.allocations, a] });
                }}
              >
                Fordel fra bestemmelse {p.clause}: {p.subject} ·{" "}
                <QuantityView value={p} />
              </button>
            ))}
            {draft.allocations.map((a, i) => (
              <fieldset key={a.provision_id}>
                <legend>
                  Fordeling {i + 1}
                  {selected?.provisions.find((p) => p.id === a.provision_id)
                    ?.subject
                    ? ` · ${selected.provisions.find((p) => p.id === a.provision_id)!.subject}`
                    : ""}
                </legend>
                <p>
                  Perioden og tellegrunnlaget må samsvare med bestemmelsen.
                  Programmet beregner ikke forholdsmessige rettigheter.
                </p>
                <QuantityFields
                  value={a}
                  optional={
                    selected?.provisions.find((p) => p.id === a.provision_id)
                      ?.category === "physical_adaptation"
                  }
                  onChange={(q) =>
                    update({
                      allocations: draft.allocations.map((old, n) =>
                        n === i ? { ...old, ...q } : old,
                      ),
                    })
                  }
                />
                <Dates
                  value={a}
                  onChange={(p) =>
                    update({
                      allocations: draft.allocations.map((old, n) =>
                        n === i ? { ...old, ...p } : old,
                      ),
                    })
                  }
                />
                <button
                  type="button"
                  onClick={() =>
                    update({
                      allocations: draft.allocations.filter((_, n) => n !== i),
                    })
                  }
                >
                  Fjern fordeling {i + 1}
                </button>
              </fieldset>
            ))}
          </>
        )}
        {initial?.content.generation_lineage && (
          <fieldset>
            <legend>Erstatt modelltekst med egen faglig formulering</legend>
            <p>
              Velg bare felt du selv har omskrevet. Uendrede felt beholder
              kildekravet til forslaget.
            </p>
            {Object.keys(initial.content.generation_lineage).map((path) => (
              <label key={path}>
                <input
                  type="checkbox"
                  checked={replaceFields.includes(path)}
                  onChange={(e) =>
                    setReplaceFields(
                      e.target.checked
                        ? [...replaceFields, path]
                        : replaceFields.filter((p) => p !== path),
                    )
                  }
                />{" "}
                Egen ny formulering av{" "}
                {path.startsWith("goals.")
                  ? `${draft.goals.find((g) => g.goal_id === path.split(".")[1])?.title || "Mål"}: ${label(path.split(".")[2])}`
                  : label(path)}
              </label>
            ))}
          </fieldset>
        )}
        <div className="planning-actions">
          <button
            type="submit"
            disabled={kind === "individual_education" && !draft.decision_id}
          >
            Lagre ny planrevisjon
          </button>
          <button type="button" onClick={onClose}>
            Lukk redigering
          </button>
        </div>
      </fieldset>
      {error && <p role="alert">{error}</p>}
      {cmd.status}
    </form>
  );
}
export function GoalSelect({
  goals,
  value,
  onChange,
}: {
  goals: Goal[];
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  return (
    <label>
      Tilknytning til mål
      <select
        value={value || ""}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">Hele planen</option>
        {goals
          .filter((g) => g.goal_id)
          .map((g) => (
            <option key={g.goal_id} value={g.goal_id!}>
              {g.title || "Mål uten tittel"}
            </option>
          ))}
      </select>
    </label>
  );
}
export function GoalFields({
  goal: g,
  goals,
  onChange,
}: {
  goal: Goal;
  goals: Goal[];
  onChange: (g: Goal) => void;
}) {
  return (
    <>
      {(
        [
          "title",
          "expected_action",
          "arena",
          "support",
          "responsibility",
          "evaluation_method",
          "curriculum_reference",
        ] as const
      ).map((f) => (
        <Field
          key={f}
          title={f === "title" ? "Måltittel" : label(f)}
          type={
            f === "title" || f === "curriculum_reference" ? "text" : "textarea"
          }
          value={g[f]}
          onChange={(v) => onChange({ ...g, [f]: v })}
        />
      ))}
      <label>
        Overordnet mål
        <select
          value={g.parent_goal_id || ""}
          onChange={(e) =>
            onChange({ ...g, parent_goal_id: e.target.value || null })
          }
        >
          <option value="">Ingen, selvstendig mål</option>
          {goals
            .filter((v) => v.goal_id && v.goal_id !== g.goal_id)
            .map((v) => (
              <option key={v.goal_id} value={v.goal_id!}>
                {v.title || "Mål uten tittel"}
              </option>
            ))}
        </select>
      </label>
      <label>
        Målstatus
        <select
          value={g.status}
          onChange={(e) =>
            onChange({ ...g, status: e.target.value as Goal["status"] })
          }
        >
          <option value="active">Aktivt</option>
          <option value="closed">Avsluttet</option>
        </select>
      </label>
      <Dates value={g} onChange={(p) => onChange({ ...g, ...p })} />
    </>
  );
}
function ContributionFields({
  ctx,
  contribution: c,
  goals,
  index,
  onChange,
  onRemove,
}: {
  ctx: Context;
  contribution: Contribution;
  goals: Goal[];
  index: number;
  onChange: (v: Contribution) => void;
  onRemove: () => void;
}) {
  return (
    <fieldset>
      <legend>Faktisk innspill {index + 1}</legend>
      <GoalSelect
        goals={goals}
        value={c.goal_id}
        onChange={(goal_id) => onChange({ ...c, goal_id })}
      />
      <label>
        Hvem ga innspillet
        <select
          value={c.role}
          onChange={(e) =>
            onChange({ ...c, role: e.target.value as Contribution["role"] })
          }
        >
          <option value="learner">Elev</option>
          <option value="guardian">Foresatt</option>
        </select>
      </label>
      <Field
        title="Deltakerens navn eller betegnelse"
        value={c.participant}
        onChange={(participant) => onChange({ ...c, participant })}
      />
      <Field
        title="Faktisk innspill"
        type="textarea"
        value={c.content}
        onChange={(content) => onChange({ ...c, content })}
      />
      <label>
        <input
          type="checkbox"
          checked={c.disagreement}
          onChange={(e) => onChange({ ...c, disagreement: e.target.checked })}
        />{" "}
        Innspillet uttrykker uenighet
      </label>
      <Field
        title="Hvordan innspillet er fulgt opp"
        type="textarea"
        value={c.response}
        onChange={(response) => onChange({ ...c, response })}
      />
      <Field
        title="Når innspillet faktisk ble gitt"
        type="datetime-local"
        value={c.occurred_at}
        onChange={(occurred_at) => onChange({ ...c, occurred_at })}
      />
      <SourcePicker
        ctx={ctx}
        value={c.source}
        onChange={(source) => onChange({ ...c, source })}
        title="Kilde til innspillet"
      />
      <button type="button" onClick={onRemove}>
        Fjern innspill {index + 1}
      </button>
    </fieldset>
  );
}
