import { LocalValidationError } from "../../userErrors";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import type {
  WorkspaceProps,
  Basis,
  Goal,
  ProfileStatement,
  Evidence,
  Observation,
  Session,
  Person,
} from "./types";
import { emptySession, fields } from "./types";
import {
  allPages,
  CommandStatus,
  DateField,
  displayDate,
  Field,
  instant,
  lines,
  ReadStatus,
  useCommand,
  useRead,
} from "./runtime";
import SessionEditor from "./SessionEditor";
type Props = WorkspaceProps & {
  learnerId: string;
  zone: string;
  onCreated: (row: Session) => void;
  revise?: Session;
  active?: boolean;
};
export default function CreateSession(props: Props) {
  const { client, schoolId, learnerId, zone, formatError } = props;
  const [planned, setPlanned] = useState("");
  const [duration, setDuration] = useState(25);
  const [arena, setArena] = useState("");
  const [theme, setTheme] = useState("");
  const [materials, setMaterials] = useState("");
  const [missing, setMissing] = useState("");
  const [goalIds, setGoalIds] = useState<string[]>([]);
  const [profileIds, setProfileIds] = useState<string[]>([]);
  const [sourceIds, setSourceIds] = useState<string[]>([]);
  const [observationIds, setObservationIds] = useState<string[]>([]);
  const [basis, setBasis] = useState<Basis>();
  const [content, setContent] = useState(emptySession);
  const [revisionBase, setRevisionBase] = useState(props.revise);
  const [replacementConfirmed, setReplacementConfirmed] = useState(false);
  const [revisionReason, setRevisionReason] = useState("");
  const [localError, setLocalError] = useState("");
  const draft = useRef(content);
  draft.current = content;
  const [conflict, setConflict] = useState(false);
  const competing = useRead(
    () =>
      conflict && props.revise
        ? client.schoolGet<Session>(schoolId, [
            "teaching",
            "sessions",
            props.revise.id,
          ])
        : Promise.resolve(undefined),
    [client, schoolId, props.revise?.id, conflict],
  );
  const command = useCommand(client, schoolId, formatError, () => {
    setConflict(true);
    setBasis(undefined);
    goals.reload();
    profile.reload();
    evidence.reload();
    observations.reload();
    competing.reload();
  });
  const [owner, setOwner] = useState(props.currentUser.id);
  const owners = useRead(
    () =>
      allPages<Person>(
        client,
        schoolId,
        ["learners", learnerId, "teaching-staff"],
        new URLSearchParams({ purpose: "owner" }),
      ),
    [client, schoolId, learnerId, props.active],
  );
  let plannedAt = "";
  try {
    if (planned) plannedAt = instant(planned, zone);
  } catch {
    /* explicit validation appears on submit */
  }
  const goals = useRead(
    () =>
      plannedAt
        ? allPages<Goal>(
            client,
            schoolId,
            ["learners", learnerId, "learning-goals"],
            new URLSearchParams({ at: plannedAt }),
          )
        : Promise.resolve([]),
    [client, schoolId, learnerId, plannedAt, props.active],
  );
  const profile = useRead(
    () =>
      allPages<ProfileStatement>(client, schoolId, [
        "learners",
        learnerId,
        "support-profile",
      ]),
    [client, schoolId, learnerId, props.active],
  );
  const evidence = useRead(
    () =>
      allPages<Evidence>(
        client,
        schoolId,
        ["learners", learnerId, "timeline"],
        new URLSearchParams({ certainty: "confirmed" }),
      ),
    [client, schoolId, learnerId, props.active],
  );
  const observations = useRead(
    () =>
      allPages<Observation>(client, schoolId, [
        "learners",
        learnerId,
        "teaching-observations",
      ]),
    [client, schoolId, learnerId, props.active],
  );
  const select = (
    ids: string[],
    id: string,
    onChange: (ids: string[]) => void,
  ) => onChange(ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]);
  const choicesLoading =
    goals.loading ||
    profile.loading ||
    evidence.loading ||
    observations.loading ||
    owners.loading;
  const unavailableGoals = goalIds.filter(
    (id) => !goals.value?.some((goal) => goal.id === id),
  );
  const unavailableProfiles = profileIds.filter(
    (id) =>
      !profile.value?.some(
        (statement) =>
          statement.id === id &&
          statement.state === "confirmed" &&
          statement.source_status === "current",
      ),
  );
  const unavailableSources = sourceIds.filter(
    (id) => !evidence.value?.some((source) => source.id === id),
  );
  const unavailableObservations = observationIds.filter(
    (id) =>
      !observations.value?.some(
        (note) => note.revision_id === id && note.confirmed && note.current,
      ),
  );
  const unavailableCount =
    unavailableGoals.length +
    unavailableProfiles.length +
    unavailableSources.length +
    unavailableObservations.length;
  function saveBasis(event: FormEvent) {
    event.preventDefault();
    setLocalError("");
    try {
      const timestamp = instant(planned, zone);
      if (choicesLoading)
        throw new LocalValidationError(
          "Vent til valgte mål og opplysninger er kontrollert på nytt.",
        );
      if (unavailableCount)
        throw new LocalValidationError(
          "Valgte mål eller opplysninger er endret eller utilgjengelige. Kontroller valgene og fjern utdaterte valg før grunnlaget bekreftes.",
        );
      const activeGoals = goalIds.filter((id) =>
        goals.value?.some((g) => g.id === id),
      );
      if (!activeGoals.length)
        throw new LocalValidationError(
          "Velg minst ett aktivt, bekreftet mål for tidspunktet.",
        );
      command.run<Basis>(
        ["teaching", "bases"],
        {
          planned_at: timestamp,
          duration_minutes: duration,
          arena,
          theme,
          materials: lines(materials),
          missing_information: lines(missing),
          learners: [
            {
              learner_id: learnerId,
              goal_revision_ids: activeGoals,
              profile_statement_ids: profileIds.filter((id) =>
                profile.value?.some(
                  (p) =>
                    p.id === id &&
                    p.state === "confirmed" &&
                    p.source_status === "current",
                ),
              ),
              observation_revision_ids: observationIds.filter((id) =>
                observations.value?.some(
                  (o) => o.revision_id === id && o.confirmed && o.current,
                ),
              ),
              sources: (evidence.value ?? [])
                .filter((e) => sourceIds.includes(e.id))
                .map((e) => ({
                  evidence_id: e.id,
                  evidence_revision: e.revision,
                  link_id: e.source.link_id,
                })),
            },
          ],
        },
        (value) => setBasis(value),
      );
    } catch (err) {
      setLocalError(formatError(err));
    }
  }
  function save(event: FormEvent) {
    event.preventDefault();
    if (!basis) return;
    const savedDraft = content;
    command.run<Session>(
      props.revise
        ? ["teaching", "sessions", props.revise.id, "revisions"]
        : ["teaching", "sessions"],
      {
        basis_id: basis.id,
        owner_id: owner,
        content,
        ...(props.revise
          ? {
              expected_version: revisionBase?.version ?? props.revise.version,
              reason: revisionReason,
              manual_replacements: replacementConfirmed
                ? fields.map((field) => field.key)
                : [],
            }
          : {}),
      },
      (row) => {
        if (draft.current === savedDraft) props.onCreated(row);
      },
    );
  }
  return (
    <section>
      <h3>
        {props.revise
          ? "Nytt grunnlag for eksisterende økt"
          : "Ny undervisningsøkt"}
      </h3>
      <p>
        Velg tidspunkt og nøyaktig grunnlag. Ordinære bekreftede mål kan brukes
        uten IOP.
      </p>
      {!basis ? (
        <form onSubmit={saveBasis}>
          <fieldset disabled={command.busy || command.uncertain}>
            <legend>Grunnlag for økten</legend>
            <DateField
              label="Planlagt tidspunkt"
              zone={zone}
              value={planned}
              onChange={(value) => {
                setPlanned(value);
                setGoalIds([]);
              }}
            />
            <Field label="Planlagt varighet i minutter">
              <input
                type="number"
                required
                min={1}
                max={480}
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
              />
            </Field>
            <Field label="Arena">
              <input
                required
                maxLength={300}
                value={arena}
                onChange={(e) => setArena(e.target.value)}
              />
            </Field>
            <Field label="Klassens tema">
              <input
                maxLength={1000}
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
              />
            </Field>
            <Field label="Tilgjengelig materiell – ett per linje">
              <textarea
                value={materials}
                onChange={(e) => setMaterials(e.target.value)}
              />
            </Field>
            <fieldset>
              <legend>Aktive mål ved planlagt tidspunkt</legend>
              <ReadStatus {...goals} formatError={formatError} />
              {!planned && <p>Velg tidspunkt for å se aktuelle mål.</p>}
              {goals.value?.map((g) => (
                <label className="teaching-check" key={g.id}>
                  <input
                    type="checkbox"
                    checked={goalIds.includes(g.id)}
                    onChange={() => select(goalIds, g.id, setGoalIds)}
                  />
                  <span>
                    <strong>{g.title}</strong>
                    <br />
                    {g.expected_action}
                    <br />
                    {g.arena} · {g.support}
                  </span>
                </label>
              ))}
              {plannedAt && goals.value?.length === 0 && (
                <p>
                  Ingen aktive mål er tilgjengelige. Bekreft et ordinært mål
                  eller riktig plangrunnlag først.
                </p>
              )}
            </fieldset>
            <details>
              <summary>Velg bekreftet støtte og kilder (valgfritt)</summary>
              <p>
                En utilgjengelig kilde hindrer ikke manuell planlegging med
                bekreftede mål. Skriv hva som mangler.
              </p>
              <ReadStatus {...profile} formatError={formatError} />
              {profile.value
                ?.filter(
                  (p) =>
                    p.state === "confirmed" &&
                    p.source_status === "current" &&
                    p.content,
                )
                .map((p) => (
                  <label className="teaching-check" key={p.id}>
                    <input
                      type="checkbox"
                      checked={profileIds.includes(p.id)}
                      onChange={() => select(profileIds, p.id, setProfileIds)}
                    />
                    {p.content}
                  </label>
                ))}
              <ReadStatus {...evidence} formatError={formatError} />
              {evidence.value?.map((e) => (
                <label className="teaching-check" key={e.id}>
                  <input
                    type="checkbox"
                    checked={sourceIds.includes(e.id)}
                    onChange={() => select(sourceIds, e.id, setSourceIds)}
                  />
                  <span>
                    {e.content}
                    <br />
                    {e.reporter} · {displayDate(e.occurred_at, zone)} ·
                    kilderevisjon {e.source.revision}, side {e.source.page}
                  </span>
                </label>
              ))}
            </details>
            <details>
              <summary>Gjenbruk tidligere observasjoner</summary>
              <ReadStatus {...observations} formatError={formatError} />
              {observations.value
                ?.filter((o) => o.confirmed && o.current)
                .map((o) => (
                  <label className="teaching-check" key={o.revision_id}>
                    <input
                      type="checkbox"
                      checked={observationIds.includes(o.revision_id)}
                      onChange={() =>
                        select(observationIds, o.revision_id, setObservationIds)
                      }
                    />
                    <span>
                      {o.observation}
                      <br />
                      Støtte: {o.support}
                      <br />
                      {displayDate(o.occurred_at, zone)} · revisjon {o.revision}
                    </span>
                  </label>
                ))}
            </details>
            <Field label="Manglende eller motstridende informasjon – ett punkt per linje">
              <textarea
                value={missing}
                onChange={(e) => setMissing(e.target.value)}
              />
            </Field>
            {!choicesLoading && unavailableCount > 0 && (
              <div role="alert">
                <p>
                  {unavailableCount} tidligere valgte mål eller opplysninger er
                  endret eller utilgjengelige. Tidligere tekst er skjermet.
                  Øvrige valg og utkastet beholdes.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setGoalIds((ids) =>
                      ids.filter((id) => !unavailableGoals.includes(id)),
                    );
                    setProfileIds((ids) =>
                      ids.filter((id) => !unavailableProfiles.includes(id)),
                    );
                    setSourceIds((ids) =>
                      ids.filter((id) => !unavailableSources.includes(id)),
                    );
                    setObservationIds((ids) =>
                      ids.filter((id) => !unavailableObservations.includes(id)),
                    );
                  }}
                >
                  Fjern bare utdaterte valg
                </button>
              </div>
            )}
            <button
              type="submit"
              disabled={choicesLoading || unavailableCount > 0}
            >
              Bekreft valgt grunnlag
            </button>
          </fieldset>
        </form>
      ) : (
        <>
          <p role="status">
            Grunnlaget er lagret. Planlagt: {displayDate(plannedAt, zone)} ·{" "}
            {duration} minutter · {arena}
          </p>
          <form onSubmit={save}>
            <fieldset disabled={command.busy || command.uncertain}>
              <legend>Praktisk manuelt opplegg</legend>
              <ReadStatus {...owners} formatError={formatError} />
              <Field label="Ansvarlig pedagog">
                <select
                  required
                  value={owner}
                  onChange={(e) => setOwner(e.target.value)}
                >
                  <option value={props.currentUser.id}>
                    {props.currentUser.display_name}
                  </option>
                  {owners.value
                    ?.filter((person) => person.id !== props.currentUser.id)
                    .map((person) => (
                      <option key={person.id} value={person.id}>
                        {person.display_name}
                      </option>
                    ))}
                </select>
              </Field>
              <SessionEditor value={content} onChange={setContent} />
              <>
                {props.revise && (
                  <>
                    <Field label="Hvorfor grunnlaget og økten erstattes">
                      <textarea
                        required
                        maxLength={2000}
                        value={revisionReason}
                        onChange={(e) => setRevisionReason(e.target.value)}
                      />
                    </Field>
                    <label className="teaching-check">
                      <input
                        required
                        type="checkbox"
                        checked={replacementConfirmed}
                        onChange={(e) =>
                          setReplacementConfirmed(e.target.checked)
                        }
                      />
                      Alle feltene over er skrevet som selvstendig manuelt
                      innhold. Erstatt tidligere modellavhengighet for disse
                      feltene; det nye valgte grunnlaget bevares.
                    </label>
                  </>
                )}
                <button type="submit">
                  {props.revise
                    ? "Lagre manuelt erstattet øktrevisjon"
                    : "Lagre øktutkast"}
                </button>
              </>
            </fieldset>
          </form>
          <button
            type="button"
            disabled={command.busy || command.uncertain}
            onClick={() => setBasis(undefined)}
          >
            Velg nytt grunnlag
          </button>
        </>
      )}
      {localError && <p role="alert">{localError}</p>}
      {conflict && (
        <section role="alert">
          <p>
            Valgt grunnlag eller versjon er endret. Egen tekst beholdes, og mål
            og kilder hentes på nytt. Kontroller valgene før nytt grunnlag
            bekreftes.
          </p>
          {competing.value && (
            <>
              <p>
                Konkurrerende øktrevisjon {competing.value.revision}:{" "}
                {competing.value.content?.title ?? "Trenger ny kildekontroll"}
              </p>
              {competing.value.content && (
                <p>Gjeldende støtte: {competing.value.content.support}</p>
              )}
              <button
                type="button"
                onClick={() => {
                  setRevisionBase(competing.value);
                  setConflict(false);
                }}
              >
                Jeg har sammenlignet og vil bruke gjeldende versjon med nytt
                grunnlag og egen tekst
              </button>
            </>
          )}
        </section>
      )}
      <CommandStatus command={command} />
    </section>
  );
}
