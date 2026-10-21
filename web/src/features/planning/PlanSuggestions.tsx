import { useState } from "react";
import type {
  Assessment,
  Context,
  Diff,
  Job,
  List,
  Option,
  Period,
  Plan,
  Statement,
  SupportCase,
} from "./types";
import {
  Dates,
  Field,
  ListBlock,
  Pager,
  State,
  emptyPeriod,
  key,
  label,
  period,
  useCommand,
  useRead,
  when,
} from "./shared";
import { GoalSelect } from "./PlanEditor";
export default function PlanSuggestions({
  ctx,
  plan,
  onSaved,
}: {
  ctx: Context;
  plan: Plan;
  onSaved: (p: Plan) => void;
}) {
  const [offset, setOffset] = useState(0),
    [choice, setChoice] = useState<Option | null>(null),
    [caseId, setCaseId] = useState(""),
    [assessments, setAssessments] = useState<string[]>([]),
    [profile, setProfile] = useState<string[]>([]),
    [basis, setBasis] = useState<{
      id: string;
      plan_revision_id: string;
    } | null>(null),
    [job, setJob] = useState<Job | null>(null);
  const basisCmd = useCommand(ctx),
    requestCmd = useCommand(ctx),
    runCmd = useCommand(ctx);
  const options = useRead<List<Option>>(
    ctx,
    ["ai", "choices"],
    new URLSearchParams({
      purpose: "iep_drafting",
      learner_id: ctx.learnerId,
      offset: String(offset),
      limit: "50",
    }),
  );
  const jobStatus = useRead<Job>(
    ctx,
    job
      ? ["ai", "jobs", job.id]
      : ["learners", ctx.learnerId, "education-plans"],
    undefined,
    Boolean(job),
  );
  const currentJob = jobStatus.value || job;
  const usable =
    choice &&
    options.value?.items.find(
      (o) =>
        o.policy_id === choice.policy_id && o.release_id === choice.release_id,
    );
  return (
    <section>
      <h4>Forslag til IOP</h4>
      <p>
        Forslaget formulerer pedagogisk tekst. Fagpersonen velger vedtaksrammer,
        datoer, læreplanreferanser og faktisk medvirkning. Manuell redigering er
        tilgjengelig hele tiden.
      </p>
      {plan.kind !== "individual_education" ? (
        <p>
          Forslag krever en IOP med bekreftet vedtaksgrunnlag. Denne ordinære
          planen kan redigeres manuelt.
        </p>
      ) : (
        <>
          {options.error ? (
            <p role="status">
              Gjennomgåtte modellvalg er ikke tilgjengelige. Fortsett manuelt.{" "}
              {ctx.formatError(options.error)}
            </p>
          ) : options.value ? (
            <>
              {!options.value.items.length ? (
                <p>
                  Ingen gjennomgått lokal modell er tilgjengelig. Fortsett
                  manuelt.
                </p>
              ) : (
                <label>
                  Gjennomgått lokalt modellvalg
                  <select
                    value={
                      usable ? `${choice!.policy_id}:${choice!.release_id}` : ""
                    }
                    onChange={(e) =>
                      setChoice(
                        options.value!.items.find(
                          (o) =>
                            `${o.policy_id}:${o.release_id}` === e.target.value,
                        ) || null,
                      )
                    }
                  >
                    <option value="">Velg gjennomgått modell …</option>
                    {options.value.items.map((o) => (
                      <option
                        key={`${o.policy_id}:${o.release_id}`}
                        value={`${o.policy_id}:${o.release_id}`}
                      >
                        {o.label} · {o.model_version} · vurdert{" "}
                        {when(o.reviewed_at)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <Pager
                offset={offset}
                total={options.value.total}
                onChange={setOffset}
              />
            </>
          ) : (
            <p>Henter modellvalg …</p>
          )}
          <details>
            <summary>Velg bekreftet grunnlag til forslaget</summary>
            <h5>Sakkyndig vurdering i samme sak som vedtaket</h5>
            <ListBlock<SupportCase>
              ctx={ctx}
              path={["learners", ctx.learnerId, "support-cases"]}
            >
              {(c) => (
                <button
                  type="button"
                  aria-pressed={c.id === caseId}
                  onClick={() => {
                    setCaseId(c.id);
                    setAssessments([]);
                  }}
                >
                  {c.concern}
                </button>
              )}
            </ListBlock>
            {caseId && (
              <ListBlock<Assessment>
                key={caseId}
                ctx={ctx}
                path={["support-cases", caseId, "expert-assessments"]}
              >
                {(a) =>
                  a.state === "confirmed" && a.source_status === "current" ? (
                    <label>
                      <input
                        type="checkbox"
                        checked={assessments.includes(a.id)}
                        onChange={(e) =>
                          setAssessments(
                            e.target.checked
                              ? [...assessments, a.id]
                              : assessments.filter((id) => id !== a.id),
                          )
                        }
                      />
                      {a.issuer} · {when(a.assessment_at)} ·{" "}
                      {a.recommendations.map((r) => r.subject).join(", ")}
                    </label>
                  ) : (
                    <p>
                      <State value={a.state} />
                      <State value={a.source_status} />
                    </p>
                  )
                }
              </ListBlock>
            )}
            <h5>Bekreftede profilopplysninger (valgfritt)</h5>
            <ListBlock<Statement>
              ctx={ctx}
              path={["learners", ctx.learnerId, "support-profile"]}
            >
              {(s) =>
                s.state === "confirmed" && s.source_status === "current" ? (
                  <label>
                    <input
                      type="checkbox"
                      checked={profile.includes(s.id)}
                      onChange={(e) =>
                        setProfile(
                          e.target.checked
                            ? [...profile, s.id]
                            : profile.filter((id) => id !== s.id),
                        )
                      }
                    />
                    {label(s.category)}: {s.content}
                  </label>
                ) : null
              }
            </ListBlock>
            <button
              type="button"
              disabled={
                !assessments.length || basisCmd.busy || basisCmd.pending
              }
              onClick={() =>
                basisCmd.submit(
                  ["education-plans", plan.id, "generation-bases"],
                  {
                    request_key: key(),
                    expected_version: plan.version,
                    plan_revision_id: plan.content.id,
                    assessment_ids: assessments,
                    profile_statement_ids: profile,
                  },
                  (v) => {
                    setBasis(v as { id: string; plan_revision_id: string });
                    setJob(null);
                  },
                )
              }
            >
              Lagre valgt grunnlag for denne revisjonen
            </button>
            {basisCmd.status}
          </details>
          {basis && (
            <div>
              <p>
                {basis.plan_revision_id === plan.content.id
                  ? "Valgt grunnlag gjelder vist revisjon."
                  : "Planen er endret. Velg og lagre nytt grunnlag."}
              </p>
              <button
                type="button"
                disabled={
                  basis.plan_revision_id !== plan.content.id ||
                  !usable ||
                  requestCmd.busy ||
                  requestCmd.pending
                }
                onClick={() =>
                  requestCmd.submit(
                    ["education-plans", plan.id, "suggestions"],
                    {
                      request_key: key(),
                      basis_id: basis.id,
                      policy_id: usable!.policy_id,
                      release_id: usable!.release_id,
                    },
                    (v) => setJob(v as Job),
                  )
                }
              >
                Bestill forslag fra valgt grunnlag
              </button>
              {requestCmd.status}
            </div>
          )}
          {currentJob && (
            <div>
              <button type="button" onClick={ctx.changed}>
                Hent status for forslaget
              </button>
              {jobStatus.error !== undefined && (
                <p role="alert">
                  Forslagets status må avklares. Fortsett manuelt.{" "}
                  {ctx.formatError(jobStatus.error)}
                </p>
              )}
              <State value={currentJob.state} />
              {currentJob.error_code && (
                <p>
                  Forslaget er utilgjengelig eller trenger ny vurdering.
                  Fortsett manuelt.
                </p>
              )}
              {currentJob.state === "queued" && (
                <button
                  type="button"
                  disabled={runCmd.busy || runCmd.pending}
                  onClick={() =>
                    runCmd.submit(
                      ["ai", "jobs", currentJob.id, "run"],
                      { expected_version: currentJob.version },
                      (v) => setJob(v as Job),
                    )
                  }
                >
                  Lag forslaget lokalt
                </button>
              )}
              {runCmd.status}
              {currentJob.state === "succeeded" && basis && (
                <SuggestionDiff
                  key={currentJob.id}
                  ctx={ctx}
                  plan={plan}
                  basisId={basis.id}
                  job={currentJob}
                  onSaved={onSaved}
                />
              )}
            </div>
          )}
        </>
      )}
      <details>
        <summary>Historikk for vurderte forslag</summary>
        <ListBlock<{
          outcome: string;
          reason: string | null;
          source_status: string;
          reviewed_at: string;
          selected_fields: string[];
          selected_goal_keys: string[];
        }>
          ctx={ctx}
          path={["education-plans", plan.id, "suggestion-reviews"]}
        >
          {(r) => (
            <p>
              <State value={r.outcome} />
              <State value={r.source_status} /> {when(r.reviewed_at)} ·{" "}
              {r.reason || "Grunnlaget må vurderes på nytt"} ·{" "}
              {r.selected_fields.map(label).join(", ")} ·{" "}
              {r.selected_goal_keys.length} mål valgt
            </p>
          )}
        </ListBlock>
      </details>
    </section>
  );
}
export function SuggestionDiff({
  ctx,
  plan,
  basisId,
  job,
  onSaved,
}: {
  ctx: Context;
  plan: Plan;
  basisId: string;
  job: Job;
  onSaved: (p: Plan) => void;
}) {
  const load = useRead<Diff>(
    ctx,
    ["education-plans", plan.id, "suggestions", job.id],
    new URLSearchParams({ basis_id: basisId }),
  );
  const [fields, setFields] = useState<string[]>([]),
    [goals, setGoals] = useState<string[]>([]),
    [newGoals, setNewGoals] = useState<
      Record<
        string,
        Period & { parent_goal_id: string | null; curriculum_reference: string }
      >
    >({}),
    [reason, setReason] = useState(""),
    [outcome, setOutcome] = useState("applied"),
    [error, setError] = useState("");
  const cmd = useCommand(ctx);
  if (load.error)
    return (
      <p role="alert">
        Forslaget kan ikke brukes. Fortsett manuelt.{" "}
        {ctx.formatError(load.error)}
      </p>
    );
  if (!load.value) return <p>Kontrollerer forslagets grunnlag …</p>;
  const d = load.value;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setError("");
        try {
          cmd.submit(
            ["education-plans", plan.id, "suggestion-reviews"],
            {
              request_key: key(),
              expected_version: d.expected_version,
              plan_revision_id: d.plan_revision_id,
              basis_id: d.basis_id,
              job_id: d.job_id,
              proposal_digest: d.proposal_digest,
              outcome,
              reason,
              selected_fields: outcome === "applied" ? fields : [],
              selected_goal_keys: outcome === "applied" ? goals : [],
              new_goals:
                outcome === "applied"
                  ? goals
                      .filter(
                        (k) =>
                          d.goals.find((g) => g.proposal.proposal_key === k)
                            ?.proposal.target_goal_id === null,
                      )
                      .map((k) => ({
                        proposal_key: k,
                        ...newGoals[k],
                        ...period(newGoals[k]),
                      }))
                  : [],
            },
            (v) => onSaved(v as Plan),
          );
        } catch (e) {
          setError(ctx.formatError(e));
        }
      }}
    >
      <fieldset disabled={cmd.busy || cmd.pending}>
        <legend>Gjennomgå forskjellene før du velger</legend>
        <p className="planning-warning">
          Ubekreftet forslag. Bare uttrykkelig valgte felt og mål blir et nytt
          utkast.
        </p>
        {d.missing_evidence.length > 0 && (
          <div className="planning-warning">
            <h5>Manglende grunnlag</h5>
            <ul>
              {d.missing_evidence.map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
          </div>
        )}
        {d.fields.map((f) => (
          <div className="planning-card" key={f.field}>
            <h5>{label(f.field)}</h5>
            <div className="planning-two">
              <div>
                <strong>Lagret</strong>
                <p>{f.before}</p>
              </div>
              <div>
                <strong>Foreslått</strong>
                <p>{f.proposed}</p>
              </div>
            </div>
            <label>
              <input
                type="checkbox"
                disabled={outcome !== "applied"}
                checked={fields.includes(f.field)}
                onChange={(e) =>
                  setFields(
                    e.target.checked
                      ? [...fields, f.field]
                      : fields.filter((v) => v !== f.field),
                  )
                }
              />{" "}
              Ta inn foreslått {label(f.field).toLowerCase()}
            </label>
          </div>
        ))}
        {d.goals.map(({ proposal: g, before }) => (
          <div className="planning-card" key={g.proposal_key}>
            <h5>
              {before ? `Endring av ${before.title}` : "Foreslått nytt mål"}
            </h5>
            <div className="planning-two">
              {before && (
                <div>
                  <strong>Lagret mål</strong>
                  {(
                    [
                      "title",
                      "expected_action",
                      "arena",
                      "support",
                      "responsibility",
                      "evaluation_method",
                    ] as const
                  ).map((f) => (
                    <p key={f}>
                      {label(f)}: {before[f]}
                    </p>
                  ))}
                </div>
              )}
              <div>
                <strong>Foreslått mål</strong>
                {(
                  [
                    "title",
                    "expected_action",
                    "arena",
                    "support",
                    "responsibility",
                    "evaluation_method",
                  ] as const
                ).map((f) => (
                  <p key={f}>
                    {label(f)}: {g[f]}
                  </p>
                ))}
              </div>
            </div>
            <label>
              <input
                type="checkbox"
                disabled={outcome !== "applied"}
                checked={goals.includes(g.proposal_key)}
                onChange={(e) => {
                  setGoals(
                    e.target.checked
                      ? [...goals, g.proposal_key]
                      : goals.filter((v) => v !== g.proposal_key),
                  );
                  if (e.target.checked && !before && !newGoals[g.proposal_key])
                    setNewGoals({
                      ...newGoals,
                      [g.proposal_key]: {
                        ...emptyPeriod(),
                        parent_goal_id: null,
                        curriculum_reference: "",
                      },
                    });
                }}
              />{" "}
              Ta inn dette målforslaget
            </label>
            {!before &&
              goals.includes(g.proposal_key) &&
              newGoals[g.proposal_key] && (
                <>
                  <Field
                    title="Fagpersonens læreplanreferanse for nytt mål"
                    value={newGoals[g.proposal_key].curriculum_reference}
                    onChange={(v) =>
                      setNewGoals({
                        ...newGoals,
                        [g.proposal_key]: {
                          ...newGoals[g.proposal_key],
                          curriculum_reference: v,
                        },
                      })
                    }
                  />
                  <GoalSelect
                    goals={plan.content.goals}
                    value={newGoals[g.proposal_key].parent_goal_id}
                    onChange={(v) =>
                      setNewGoals({
                        ...newGoals,
                        [g.proposal_key]: {
                          ...newGoals[g.proposal_key],
                          parent_goal_id: v,
                        },
                      })
                    }
                  />
                  <Dates
                    value={newGoals[g.proposal_key]}
                    onChange={(p) =>
                      setNewGoals({
                        ...newGoals,
                        [g.proposal_key]: { ...newGoals[g.proposal_key], ...p },
                      })
                    }
                  />
                </>
              )}
          </div>
        ))}
        <label>
          Hva vil du gjøre med forslaget
          <select
            value={outcome}
            onChange={(e) => {
              setOutcome(e.target.value);
              if (e.target.value !== "applied") {
                setFields([]);
                setGoals([]);
              }
            }}
          >
            <option value="applied">Ta bare inn valgte deler</option>
            <option value="rejected">Avvis med faglig begrunnelse</option>
            <option value="discarded">Forkast uten å ta i bruk tekst</option>
          </select>
        </label>
        <Field
          title="Begrunnelse for vurdering av forslaget"
          type="textarea"
          value={reason}
          onChange={setReason}
        />
        <button
          type="submit"
          disabled={outcome === "applied" && !fields.length && !goals.length}
        >
          Lagre vurdering av forslaget
        </button>
      </fieldset>
      {error && <p role="alert">{error}</p>}
      {cmd.status}
    </form>
  );
}
