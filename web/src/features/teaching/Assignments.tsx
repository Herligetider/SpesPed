import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type {
  WorkspaceProps,
  ActualInput,
  Assignment,
  BriefContent,
  Delivery,
  Message,
} from "./types";
import { categories } from "./types";
import {
  allPages,
  CommandStatus,
  DateField,
  displayDate,
  Field,
  instant,
  ReadStatus,
  useCommand,
  useRead,
} from "./runtime";
import { ObservationForm } from "./Observations";
export function BriefView({ content }: { content: BriefContent }) {
  return (
    <div className="teaching-brief">
      <h4>Mål: {content.simple_goal}</h4>
      <p>
        <strong>Materiell og plassering:</strong> {content.material_location}
      </p>
      <ol>
        {content.steps.map((step, index) => (
          <li key={index}>{step}</li>
        ))}
      </ol>
      <p>
        <strong>Slik støtter du:</strong> {content.support}
      </p>
      <p>
        <strong>Avtalt forenkling:</strong> {content.simplification}
      </p>
      <p>
        <strong>Hent hjelp når:</strong> {content.help_when}
      </p>
      <p>
        <strong>Kontakt:</strong> {content.contact}
      </p>
      <p>
        <strong>Opplæring og veiledning:</strong> {content.training_guidance}
      </p>
    </div>
  );
}
function ActualForm(
  props: WorkspaceProps & {
    assignment: Assignment;
    zone: string;
    onSaved: () => void;
  },
) {
  const [date, setDate] = useState("");
  const [minutes, setMinutes] = useState(0);
  const [status, setStatus] = useState("participated");
  const [category, setCategory] = useState("personal_assistance");
  const [activity, setActivity] = useState("");
  const [support, setSupport] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const fingerprint = JSON.stringify([
    date,
    minutes,
    status,
    category,
    activity,
    support,
    difficulty,
  ]);
  const current = useRef(fingerprint);
  current.current = fingerprint;
  const command = useCommand(props.client, props.schoolId, props.formatError);
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const timestamp = instant(date, props.zone);
      const snapshot = fingerprint;
      command.run<ActualInput>(
        ["teaching", "brief-assignments", props.assignment.id, "actual-inputs"],
        {
          content: {
            occurred_at: timestamp,
            duration_minutes: minutes,
            status,
            category,
            activity,
            support,
            difficulty,
          },
        },
        () => {
          setSaved(true);
          if (current.current === snapshot) {
            setDate("");
            setMinutes(0);
            setActivity("");
            setSupport("");
            setDifficulty("");
          }
          props.onSaved();
        },
      );
    } catch (err) {
      setError(props.formatError(err));
    }
  }
  return (
    <form onSubmit={submit}>
      <fieldset disabled={command.busy || command.uncertain}>
        <legend>Hva ble faktisk gjort?</legend>
        <p>
          Dette er assistentens innspill. Ansvarlig pedagog må sammenholde det
          med en separat gjennomføringsregistrering før det kan avstemmes.
        </p>
        <DateField
          label="Faktisk start"
          value={date}
          onChange={setDate}
          zone={props.zone}
        />
        <Field label="Faktiske minutter">
          <input
            required
            type="number"
            min={0}
            max={480}
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value))}
          />
        </Field>
        <Field label="Deltakelse">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="participated">Deltok</option>
            <option value="partial">Deltok delvis</option>
            <option value="absent">Fraværende</option>
          </select>
        </Field>
        <Field label="Faktisk støtteform">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {Object.entries(categories)
              .filter(([key]) => key !== "individually_adapted_education")
              .map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
          </select>
        </Field>
        <Field label="Aktiviteten som faktisk ble gjort">
          <textarea
            required
            maxLength={2000}
            value={activity}
            onChange={(e) => setActivity(e.target.value)}
          />
        </Field>
        <Field label="Støtte som ble gitt">
          <textarea
            required
            maxLength={1500}
            value={support}
            onChange={(e) => setSupport(e.target.value)}
          />
        </Field>
        <Field label="Hva var vanskelig / hva trenger avklaring?">
          <textarea
            maxLength={2000}
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
          />
        </Field>
        <button type="submit">Lagre innspill til pedagogen</button>
      </fieldset>
      {error && <p role="alert">{error}</p>}
      <CommandStatus command={command} />
      {saved && (
        <p role="status">
          Innspillet er lagret. Dette oppretter ingen bekreftet gjennomføring.
        </p>
      )}
    </form>
  );
}
function Reconcile(
  props: WorkspaceProps & {
    row: ActualInput;
    active?: boolean;
    learnerId: string;
    zone: string;
    onSaved: () => void;
  },
) {
  const [outcome, setOutcome] = useState("needs_clarification");
  const [delivery, setDelivery] = useState("");
  const [reason, setReason] = useState("");
  const command = useCommand(props.client, props.schoolId, props.formatError);
  const deliveries = useRead(
    () =>
      allPages<Delivery>(props.client, props.schoolId, [
        "learners",
        props.learnerId,
        "teaching-deliveries",
      ]),
    [props.client, props.schoolId, props.learnerId, props.active],
  );
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        command.run(
          ["teaching", "actual-inputs", props.row.id, "review"],
          {
            expected_version: props.row.version,
            outcome,
            reason,
            delivery_revision_id: outcome === "recorded" ? delivery : null,
          },
          props.onSaved,
        );
      }}
    >
      <fieldset disabled={command.busy || command.uncertain}>
        <legend>Pedagogens avstemming</legend>
        <Field label="Vurdering av innspillet">
          <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="needs_clarification">Trenger avklaring</option>
            <option value="recorded">
              Sammenholdt med faktisk gjennomføring
            </option>
            <option value="rejected">Avvist med begrunnelse</option>
          </select>
        </Field>
        {outcome === "recorded" && (
          <>
            <ReadStatus {...deliveries} formatError={props.formatError} />
            <Field label="Eksakt registrert gjennomføringsrevisjon">
              <select
                required
                value={delivery}
                onChange={(e) => setDelivery(e.target.value)}
              >
                <option value="">Velg gjennomføring</option>
                {deliveries.value
                  ?.filter((d) => d.state !== "cancelled")
                  .map((d) => (
                    <option key={d.revision_id} value={d.revision_id}>
                      {displayDate(d.occurred_at, props.zone)} ·{" "}
                      {d.duration_minutes} min · revisjon {d.revision}
                    </option>
                  ))}
              </select>
            </Field>
            <p>
              Kontroller tidspunkt, elev, kategori og faktisk deltakelse. Et
              innspill er aldri alene dokumentasjon på gjennomført undervisning.
            </p>
          </>
        )}
        <Field label="Begrunnelse for avstemming">
          <textarea
            required
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </Field>
        <button type="submit">Lagre vurdering av innspill</button>
      </fieldset>
      <CommandStatus command={command} />
    </form>
  );
}
export function AssignmentPanel(
  props: WorkspaceProps & {
    assignmentId: string;
    zone: string;
    active?: boolean;
  },
) {
  const { client, schoolId, formatError, assignmentId, zone } = props;
  const [accessRevision, setAccessRevision] = useState(0);
  const assignment = useRead(
    () =>
      client
        .schoolGet<Assignment>(schoolId, [
          "teaching",
          "brief-assignments",
          assignmentId,
        ])
        .then((row) => ({ row, accessRevision })),
    [client, schoolId, assignmentId, accessRevision],
  );
  const messages = useRead(
    () =>
      allPages<Message>(client, schoolId, [
        "teaching",
        "brief-assignments",
        assignmentId,
        "messages",
      ]),
    [client, schoolId, assignmentId, accessRevision],
  );
  const actuals = useRead(
    () =>
      allPages<ActualInput>(client, schoolId, [
        "teaching",
        "brief-assignments",
        assignmentId,
        "actual-inputs",
      ]),
    [client, schoolId, assignmentId, accessRevision],
  );
  const [kind, setKind] = useState(
    props.mode === "assistant" ? "question" : "guidance",
  );
  const [text, setText] = useState("");
  const [responds, setResponds] = useState("");
  const [needsFollowup, setNeedsFollowup] = useState(false);
  function refreshAccess() {
    setAccessRevision((revision) => revision + 1);
  }
  const previouslyActive = useRef(props.active ?? true);
  useEffect(() => {
    const active = props.active ?? true;
    if (active && !previouslyActive.current) refreshAccess();
    previouslyActive.current = active;
  }, [props.active]);
  const command = useCommand(client, schoolId, formatError, refreshAccess);
  const textRef = useRef(text);
  textRef.current = text;
  const freshRow =
    assignment.value?.accessRevision === accessRevision
      ? assignment.value.row
      : undefined;
  const retainedRow = useRef<Assignment | undefined>(undefined);
  if (freshRow) retainedRow.current = freshRow;
  const row = retainedRow.current;
  const accessCurrent = !!freshRow && !assignment.loading && !assignment.error;
  const [checkedAt, setCheckedAt] = useState(() => Date.now());
  useEffect(() => {
    if (!row || props.mode !== "assistant") return;
    const remaining = Date.parse(row.valid_until) - Date.now();
    const timer = setTimeout(
      () => setCheckedAt(Date.now()),
      Math.max(0, Math.min(remaining + 1, 2147483647)),
    );
    return () => clearTimeout(timer);
  }, [row?.valid_until, props.mode]);
  const expired =
    props.mode === "assistant" &&
    !!row &&
    Math.max(checkedAt, Date.now()) >= Date.parse(row.valid_until);
  function message(event: FormEvent) {
    event.preventDefault();
    const snapshot = text;
    command.run<Message>(
      ["teaching", "brief-assignments", assignmentId, "messages"],
      {
        kind,
        text,
        responds_to_id: kind === "answer" ? responds : null,
        needs_follow_up: needsFollowup,
      },
      () => {
        if (textRef.current === snapshot) setText("");
        refreshAccess();
      },
    );
  }
  return (
    <section>
      <ReadStatus {...assignment} formatError={formatError} />
      {expired && (
        <p role="alert">
          Tildelingen er utløpt. Kontakt ansvarlig pedagog om et nytt avgrenset
          oppdrag.
        </p>
      )}
      {row && !expired && (
        <div hidden={!accessCurrent}>
          <h3>
            {row.learner_name ?? "Tildelt elev"} ·{" "}
            {displayDate(row.planned_at, zone)}
          </h3>
          <p>
            {row.arena ?? "Sted trenger ny kontroll"} ·{" "}
            {row.role ?? "Oppdrag trenger ny kontroll"}
          </p>
          <p>
            Tildelt fra {displayDate(row.valid_from, zone)} til{" "}
            {displayDate(row.valid_until, zone)}. Ansvarlig:{" "}
            {row.follow_up_owner_name ?? "ansvarlig pedagog"}.
          </p>
          <p>
            Åpning dokumenterer tilgang. Det bekrefter verken forståelse eller
            utført oppdrag. Kortet erstatter ikke opplæring og veiledning.
          </p>
          <button
            type="button"
            onClick={() => {
              refreshAccess();
            }}
          >
            Kontroller oppdrag og kildegrunnlag på nytt
          </button>
          {row.content ? (
            <BriefView content={row.content} />
          ) : (
            <p role="alert">
              Kortet trenger ny pedagogisk kontroll. Kildeavledet instruksjon er
              utilgjengelig. Kontakt ansvarlig pedagog.
            </p>
          )}
          <h4>Spørsmål og veiledning</h4>
          <ReadStatus {...messages} formatError={formatError} />
          {messages.value?.map((m) => (
            <article className="teaching-card" key={m.id}>
              <strong>
                {{
                  question: "Spørsmål",
                  answer: "Svar",
                  guidance: "Veiledning",
                  feedback: "Tilbakemelding",
                }[m.kind] ?? "Melding"}{" "}
                · {displayDate(m.created_at, zone)}
              </strong>
              <p>
                {row.content
                  ? (m.text ?? "Innhold trenger kildekontroll.")
                  : "Innhold trenger kildekontroll."}
              </p>
            </article>
          ))}
          {row.content && (
            <form onSubmit={message}>
              <fieldset disabled={command.busy || command.uncertain}>
                <legend>
                  {props.mode === "assistant"
                    ? "Still spørsmål eller gi tilbakemelding"
                    : "Svar eller gi veiledning"}
                </legend>
                <Field label="Meldingstype">
                  <select
                    value={kind}
                    onChange={(e) => setKind(e.target.value)}
                  >
                    {props.mode === "assistant" ? (
                      <>
                        <option value="question">Spørsmål</option>
                        <option value="feedback">Tilbakemelding</option>
                      </>
                    ) : (
                      <>
                        <option value="guidance">Veiledning</option>
                        <option value="answer">Svar på spørsmål</option>
                      </>
                    )}
                  </select>
                </Field>
                {kind === "answer" && (
                  <Field label="Spørsmålet du svarer på">
                    <select
                      required
                      value={responds}
                      onChange={(e) => setResponds(e.target.value)}
                    >
                      <option value="">Velg spørsmål</option>
                      {messages.value
                        ?.filter((m) => m.kind === "question" && m.text)
                        .map((m) => (
                          <option value={m.id} key={m.id}>
                            {m.text}
                          </option>
                        ))}
                    </select>
                  </Field>
                )}
                <Field label="Tekst til det konkrete oppdraget">
                  <textarea
                    required
                    maxLength={3000}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                </Field>
                <label className="teaching-check">
                  <input
                    type="checkbox"
                    checked={needsFollowup}
                    onChange={(e) => setNeedsFollowup(e.target.checked)}
                  />
                  Trenger ansvarlig oppfølging
                </label>
                <button type="submit">
                  Lagre{" "}
                  {kind === "question"
                    ? "spørsmål"
                    : kind === "answer"
                      ? "svar"
                      : kind === "guidance"
                        ? "veiledning"
                        : "tilbakemelding"}
                </button>
              </fieldset>
              <CommandStatus command={command} />
            </form>
          )}
          {props.mode === "assistant" && (
            <>
              <ActualForm {...props} assignment={row} onSaved={refreshAccess} />
              <ObservationForm
                {...props}
                learnerId={row.learner_id}
                assignmentId={row.id}
              />
            </>
          )}
          <h4>Assistentens innspill og vurderingshistorikk</h4>
          <ReadStatus {...actuals} formatError={formatError} />
          {actuals.value?.map((input) => (
            <article className="teaching-card" key={input.id}>
              <h5>
                {displayDate(input.occurred_at, zone)} ·{" "}
                {input.currently_reconciled
                  ? "Avstemt mot gjeldende gjennomføring"
                  : input.state === "rejected"
                    ? "Avvist"
                    : "Trenger pedagogens vurdering"}
              </h5>
              <p>
                Forfatter:{" "}
                {input.author_name ?? "opprinnelig registrert assistent"}
              </p>
              {input.content && (
                <>
                  <p>{input.content.activity}</p>
                  <p>
                    {input.content.duration_minutes} minutter ·{" "}
                    {
                      categories[
                        input.content.category as keyof typeof categories
                      ]
                    }{" "}
                    ·{" "}
                    {input.content.status === "absent"
                      ? "fravær"
                      : input.content.status === "partial"
                        ? "delvis deltakelse"
                        : "deltok"}
                  </p>
                  <p>Støtte: {input.content.support}</p>
                  <p>Avklaring: {input.content.difficulty}</p>
                </>
              )}
              {row.content && input.review_reason && (
                <p>Vurdering: {input.review_reason}</p>
              )}
              {input.review_history?.map((review) => (
                <p key={review.id}>
                  {displayDate(review.reviewed_at, zone)} ·{" "}
                  {review.historical
                    ? "Historisk vurdering"
                    : "Gjeldende vurdering"}
                  :{" "}
                  {row.content
                    ? (review.reason ?? "Kildegrunnlag trenger kontroll")
                    : "Kildegrunnlag trenger kontroll"}
                </p>
              ))}
              {props.mode === "teaching" && row.content && (
                <Reconcile
                  key={`${input.id}:${input.version}`}
                  {...props}
                  row={input}
                  learnerId={row.learner_id}
                  onSaved={refreshAccess}
                />
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
export default function AssistantInbox(
  props: WorkspaceProps & { zone: string },
) {
  const list = useRead(
    () =>
      allPages<Assignment>(props.client, props.schoolId, [
        "teaching",
        "brief-assignments",
      ]),
    [props.client, props.schoolId],
  );
  const [selected, setSelected] = useState("");
  return (
    <>
      <h2>
        {props.language === "nn"
          ? "Mine assistentoppdrag"
          : "Mine assistentoppdrag"}
      </h2>
      <p>
        Her vises bare gjeldende tildelte kort. Oppdraget gir nødvendig
        veiledning innenfor den daterte tildelingen.
      </p>
      <ReadStatus {...list} formatError={props.formatError} />
      <button
        type="button"
        onClick={() => {
          setSelected("");
          list.reload();
        }}
      >
        Oppdater oppdragsinnboksen
      </button>
      {list.value?.length === 0 && <p>Du har ingen aktive assistentoppdrag.</p>}
      <div className="teaching-list">
        {list.value?.map((a) => (
          <button
            type="button"
            key={a.id}
            onClick={() => setSelected(a.id)}
            aria-pressed={a.id === selected}
          >
            {a.learner_name ?? "Tildelt elev"} ·{" "}
            {displayDate(a.planned_at, props.zone)} ·{" "}
            {a.brief_state === "review_required"
              ? "Trenger ny kontroll"
              : "Tildelt kort"}
          </button>
        ))}
      </div>
      {selected && (
        <AssignmentPanel key={selected} {...props} assignmentId={selected} />
      )}
    </>
  );
}
