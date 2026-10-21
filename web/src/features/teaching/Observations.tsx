import { useRef, useState } from "react";
import type { FormEvent } from "react";
import type {
  WorkspaceProps,
  Goal,
  Observation,
  Session,
  Person,
} from "./types";
import {
  allPages,
  CommandStatus,
  DateField,
  displayDate,
  Field,
  instant,
  localInput,
  ReadStatus,
  useCommand,
  useRead,
} from "./runtime";
type Props = WorkspaceProps & {
  learnerId: string;
  zone: string;
  session?: Session;
  assignmentId?: string;
};
export function ObservationForm(
  props: Props & {
    existing?: Observation;
    onSaved?: (row: Observation) => void;
  },
) {
  const { client, schoolId, learnerId, zone, formatError, existing } = props;
  const [selectedLearner, setSelectedLearner] = useState(learnerId);
  const learners = useRead(
    () =>
      existing && props.mode !== "assistant"
        ? allPages<Person>(client, schoolId, ["learners"])
        : Promise.resolve([]),
    [client, schoolId, existing?.id, props.mode],
  );
  const [date, setDate] = useState(
    existing ? localInput(existing.occurred_at, zone) : "",
  );
  const [observation, setObservation] = useState(existing?.observation ?? "");
  const [support, setSupport] = useState(existing?.support ?? "");
  const [interpretation, setInterpretation] = useState(
    existing?.interpretation ?? "",
  );
  const [next, setNext] = useState(existing?.next_step ?? "");
  const [goal, setGoal] = useState(existing?.goal_revision_id ?? "");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Observation>();
  const fingerprint = JSON.stringify([
    selectedLearner,
    date,
    observation,
    support,
    interpretation,
    next,
    goal,
    reason,
  ]);
  const draft = useRef(fingerprint);
  draft.current = fingerprint;
  const [conflict, setConflict] = useState(false);
  const [expectedVersion, setExpectedVersion] = useState(existing?.version);
  const competing = useRead(
    () =>
      conflict && existing
        ? client.schoolGet<Observation>(schoolId, [
            "teaching",
            "observations",
            existing.id,
          ])
        : Promise.resolve(undefined),
    [client, schoolId, existing?.id, conflict],
  );
  const command = useCommand(client, schoolId, formatError, () => {
    setConflict(true);
    competing.reload();
  });
  const goals = useRead(
    () =>
      props.assignmentId
        ? Promise.resolve([])
        : props.session && selectedLearner === learnerId
          ? client
              .schoolGet<{
                basis: {
                  learners: { learner_id: string; goals: { goal: Goal }[] }[];
                } | null;
              }>(schoolId, ["teaching", "bases", props.session.basis_id])
              .then(
                (value) =>
                  value.basis?.learners
                    .find((learner) => learner.learner_id === selectedLearner)
                    ?.goals.map((binding) => binding.goal) ?? [],
              )
          : allPages<Goal>(client, schoolId, [
              "learners",
              selectedLearner,
              "learning-goals",
            ]),
    [
      client,
      schoolId,
      selectedLearner,
      props.assignmentId,
      props.session?.basis_id,
    ],
  );
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const occurrence = instant(date, zone, existing?.occurred_at);
      const snapshot = fingerprint;
      const content = {
        learner_id: selectedLearner,
        occurred_at: occurrence,
        session_revision_id:
          selectedLearner !== learnerId
            ? null
            : (props.session?.revision_id ??
              existing?.session_revision_id ??
              null),
        assignment_id:
          selectedLearner !== learnerId
            ? null
            : (props.assignmentId ?? existing?.assignment_id ?? null),
        goal_revision_id: goal || null,
        observation,
        support,
        interpretation: interpretation || null,
        next_step: next || null,
        input_method: "manual",
        transcript_reviewed: false,
      };
      const body = existing
        ? { content, save: true, expected_version: expectedVersion, reason }
        : { content, save: true };
      command.run<Observation>(
        existing
          ? ["teaching", "observations", existing.id, "corrections"]
          : ["teaching", "observations"],
        body,
        (row) => {
          setSaved(row);
          if (draft.current === snapshot && !existing) {
            setDate("");
            setObservation("");
            setSupport("");
            setInterpretation("");
            setNext("");
          }
          props.onSaved?.(row);
        },
      );
    } catch (err) {
      setError(formatError(err));
    }
  }
  return (
    <form onSubmit={submit}>
      <fieldset disabled={command.busy || command.uncertain}>
        <legend>
          {existing ? "Rett observasjonen med ny revisjon" : "Kort observasjon"}
        </legend>
        {existing && props.mode !== "assistant" && (
          <>
            <ReadStatus {...learners} formatError={formatError} />
            <Field label="Korriger elevtilordning">
              <select
                required
                value={selectedLearner}
                onChange={(event) => {
                  setSelectedLearner(event.target.value);
                  setGoal("");
                }}
              >
                <option value={learnerId}>
                  {props.learnerName ?? "Valgt elev"}
                </option>
                {learners.value
                  ?.filter((person) => person.id !== learnerId)
                  .map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.display_name}
                    </option>
                  ))}
              </select>
            </Field>
            {selectedLearner !== learnerId && (
              <p>
                Rettelsen flytter notatet til valgt elev og fjerner tidligere
                økt-, oppdrags- og målkobling. Tidligere avledet grunnlag
                trenger ny kontroll.
              </p>
            )}
          </>
        )}
        <DateField
          label="Observert tidspunkt"
          value={date}
          onChange={setDate}
          zone={zone}
        />
        {!props.assignmentId && (
          <>
            <ReadStatus {...goals} formatError={formatError} />
            <Field label="Mål (valgfritt)">
              <select value={goal} onChange={(e) => setGoal(e.target.value)}>
                <option value="">Uten målkobling</option>
                {goal && !goals.value?.some((item) => item.id === goal) && (
                  <option value={goal}>
                    Tidligere eksakt målkobling (beholdes)
                  </option>
                )}
                {goals.value?.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.title}
                  </option>
                ))}
              </select>
            </Field>
          </>
        )}
        <Field label="Konkret observasjon">
          <textarea
            required
            maxLength={3000}
            value={observation}
            onChange={(e) => setObservation(e.target.value)}
          />
        </Field>
        <Field label="Støtte som faktisk ble gitt">
          <textarea
            required
            maxLength={1500}
            value={support}
            onChange={(e) => setSupport(e.target.value)}
          />
        </Field>
        <details>
          <summary>Tolkning og neste steg (valgfritt)</summary>
          <Field label="Faglig tolkning – holdes atskilt fra observasjonen">
            <textarea
              maxLength={2000}
              value={interpretation}
              onChange={(e) => setInterpretation(e.target.value)}
            />
          </Field>
          <Field label="Neste steg">
            <textarea
              maxLength={2000}
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          </Field>
        </details>
        {existing && (
          <Field label="Begrunnelse for retting">
            <textarea
              required
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
        )}
        <button type="submit" disabled={conflict}>
          {existing ? "Lagre korrigert observasjon" : "Lagre observasjon"}
        </button>
      </fieldset>
      {error && <p role="alert">{error}</p>}
      <CommandStatus command={command} />
      {conflict && (
        <section role="alert">
          <h4>Konkurrerende observasjonsrevisjon</h4>
          <p>Utkastet beholdes.</p>
          <ReadStatus {...competing} formatError={formatError} />
          {competing.value && (
            <>
              <p>{competing.value.observation}</p>
              <p>Støtte: {competing.value.support}</p>
              <button
                type="button"
                onClick={() => {
                  setExpectedVersion(competing.value!.version);
                  setConflict(false);
                }}
              >
                Jeg har sammenlignet og vil rette gjeldende observasjonsversjon
              </button>
            </>
          )}
        </section>
      )}
      {saved && (
        <p role="status">
          Observasjonen er lagret som revisjon {saved.revision}. Opphav og
          observert tidspunkt følger notatet.
        </p>
      )}
    </form>
  );
}
function ObservationHistory({
  props,
  row,
}: {
  props: Props;
  row: Observation;
}) {
  const history = useRead(
    () =>
      allPages<Observation>(props.client, props.schoolId, [
        "teaching",
        "observations",
        row.id,
        "revisions",
      ]),
    [props.client, props.schoolId, row.id, row.version],
  );
  return (
    <>
      <ReadStatus {...history} formatError={props.formatError} />
      {history.value?.map((o) => (
        <article key={o.revision_id}>
          <h5>
            Revisjon {o.revision} · {displayDate(o.occurred_at, props.zone)}
          </h5>
          <p>
            Forfatter:{" "}
            {o.author_name ??
              (o.author_id === props.currentUser.id
                ? props.currentUser.display_name
                : "opprinnelig registrert forfatter")}
          </p>
          <p>{o.observation}</p>
          <p>Støtte: {o.support}</p>
          {o.interpretation && <p>Tolkning: {o.interpretation}</p>}
          {o.next_step && <p>Neste steg: {o.next_step}</p>}
          {o.correction_reason && <p>Rettelse: {o.correction_reason}</p>}
        </article>
      ))}
    </>
  );
}
export default function Observations(props: Props) {
  const list = useRead(
    () =>
      allPages<Observation>(props.client, props.schoolId, [
        "learners",
        props.learnerId,
        "teaching-observations",
      ]),
    [props.client, props.schoolId, props.learnerId],
  );
  const [editing, setEditing] = useState<Observation>();
  const [history, setHistory] = useState<Observation>();
  return (
    <section>
      <h3>Observasjoner til neste økt</h3>
      <p>
        Observasjon, støtte og faglig tolkning lagres hver for seg. Velg lagrede
        observasjoner under grunnlaget til neste økt.
      </p>
      <ObservationForm {...props} onSaved={() => list.reload()} />
      <ReadStatus {...list} formatError={props.formatError} />
      {list.value?.length === 0 && <p>Ingen lagrede observasjoner.</p>}
      {list.value?.map((o) => (
        <article className="teaching-card" key={o.id}>
          <h4>
            {displayDate(o.occurred_at, props.zone)} · revisjon {o.revision}
          </h4>
          <p>
            Forfatter:{" "}
            {o.author_name ??
              (o.author_id === props.currentUser.id
                ? props.currentUser.display_name
                : "opprinnelig registrert forfatter")}
          </p>
          <p>{o.observation}</p>
          <p>Støtte: {o.support}</p>
          {o.interpretation && <p>Tolkning: {o.interpretation}</p>}
          {o.next_step && <p>Neste steg: {o.next_step}</p>}
          {o.author_id === props.currentUser.id && (
            <button type="button" onClick={() => setEditing(o)}>
              Rett eget notat
            </button>
          )}
          <button type="button" onClick={() => setHistory(o)}>
            Vis revisjonshistorikk
          </button>
        </article>
      ))}
      {editing && (
        <section>
          <button type="button" onClick={() => setEditing(undefined)}>
            Lukk retting
          </button>
          <ObservationForm
            key={editing.revision_id}
            {...props}
            existing={editing}
            onSaved={() => {
              setEditing(undefined);
              list.reload();
            }}
          />
        </section>
      )}
      {history && (
        <section>
          <h4>Historiske observasjoner</h4>
          <button type="button" onClick={() => setHistory(undefined)}>
            Lukk historikk
          </button>
          <ObservationHistory props={props} row={history} />
        </section>
      )}
    </section>
  );
}
