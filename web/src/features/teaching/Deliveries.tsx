import { LocalValidationError } from "../../userErrors";
import { useState } from "react";
import DeliverySummary from "./DeliverySummary";
import type { FormEvent } from "react";
import type {
  WorkspaceProps,
  Category,
  Delivery,
  Participation,
  Person,
  Session,
  StaffTime,
} from "./types";
import { categories } from "./types";
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
  active?: boolean;
  session?: Session;
  onChanged?: () => void;
};
function participant(learner: string): Participation {
  return {
    learner_id: learner,
    goal_revision_ids: [],
    status: "participated",
    minutes: 0,
    category: "ordinary_teaching",
    support: "",
    support_status: "assessed",
    provision: null,
    counting_basis: null,
    attributed_staff_minutes: null,
  };
}
function CategorySelect({
  value,
  onChange,
  id,
}: {
  id?: string;
  value: Category;
  onChange: (value: Category) => void;
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value as Category)}
    >
      {Object.entries(categories).map(([key, label]) => (
        <option key={key} value={key}>
          {label}
        </option>
      ))}
    </select>
  );
}
export function DeliveryForm(
  props: Props & { existing?: Delivery; onSaved: (row: Delivery) => void },
) {
  const { client, schoolId, learnerId, zone, formatError, existing } = props;
  const [linkSession, setLinkSession] = useState(
    props.session?.approved ?? false,
  );
  const [date, setDate] = useState(
    existing ? localInput(existing.occurred_at, zone) : "",
  );
  const [duration, setDuration] = useState(existing?.duration_minutes ?? 0);
  const [status, setStatus] = useState(existing?.state ?? "delivered");
  const [activity, setActivity] = useState(existing?.activity ?? "");
  const [participants, setParticipants] = useState<Participation[]>(
    existing?.participants.map(({ support_assessment, ...p }) => {
      void support_assessment;
      return p;
    }) ?? [participant(learnerId)],
  );
  const [staff, setStaff] = useState<StaffTime[]>(existing?.staff ?? []);
  const [cause, setCause] = useState(existing?.cause ?? "");
  const [detail, setDetail] = useState(existing?.cause_detail ?? "");
  const [owner, setOwner] = useState(
    (existing as Delivery & { follow_up_owner_id?: string })
      ?.follow_up_owner_id ?? "",
  );
  const [followup, setFollowup] = useState(
    (existing as Delivery & { follow_up?: string })?.follow_up ?? "",
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const people = useRead(
    () =>
      allPages<Person>(
        client,
        schoolId,
        ["learners", learnerId, "teaching-staff"],
        new URLSearchParams({ purpose: "delivery" }),
      ),
    [client, schoolId, learnerId],
  );
  const owners = useRead(
    () =>
      allPages<Person>(
        client,
        schoolId,
        ["learners", learnerId, "teaching-staff"],
        new URLSearchParams({ purpose: "follow_up" }),
      ),
    [client, schoolId, learnerId],
  );
  const learners = useRead(async () => {
    const result: { id: string; display_name: string }[] = [];
    for (let offset = 0; ;) {
      const page = await client.learners(schoolId, offset, 100);
      result.push(...page.items);
      offset += page.items.length;
      if (offset >= page.total) return result;
      if (!page.items.length)
        throw new LocalValidationError("Elevlisten ble avbrutt.");
    }
  }, [client, schoolId]);
  const [conflict, setConflict] = useState(false);
  const [expectedVersion, setExpectedVersion] = useState(existing?.version);
  const competing = useRead(
    () =>
      !conflict
        ? Promise.resolve([])
        : existing
          ? client
              .schoolGet<Delivery>(schoolId, [
                "teaching",
                "deliveries",
                existing.id,
              ])
              .then((value) => [value])
          : allPages<Delivery>(client, schoolId, [
              "learners",
              learnerId,
              "teaching-deliveries",
            ]),
    [client, schoolId, learnerId, existing?.id, conflict],
  );
  const command = useCommand(client, schoolId, formatError, () => {
    setConflict(true);
    competing.reload();
  });
  function update(index: number, change: Partial<Participation>) {
    setParticipants((rows) =>
      rows.map((p, i) => (i === index ? { ...p, ...change } : p)),
    );
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const occurred = instant(date, zone, existing?.occurred_at);
      if (new Date(occurred).getTime() + duration * 60000 > Date.now())
        throw new LocalValidationError(
          "Registrer en faktisk økt først etter at hele hendelsen har skjedd.",
        );
      if (
        status !== "cancelled" &&
        participants.some(
          (p) =>
            p.category === "individually_adapted_education" && p.minutes > 0,
        ) &&
        status !== "partial"
      )
        throw new LocalValidationError(
          "ITO uten vurdert kvalifikasjonsgrunnlag registreres som delvis gjennomføring med årsak og ansvarlig oppfølging.",
        );
      const content = {
        session_revision_id: existing
          ? existing.session_revision_id
          : linkSession
            ? (props.session?.revision_id ?? null)
            : null,
        occurred_at: occurred,
        duration_minutes: duration,
        status,
        activity,
        participants,
        staff,
        cause: cause || null,
        cause_detail: detail,
        follow_up_owner_id: owner || null,
        follow_up: followup || null,
      };
      command.run<Delivery>(
        existing
          ? ["teaching", "deliveries", existing.id, "corrections"]
          : ["teaching", "deliveries"],
        existing
          ? { content, expected_version: expectedVersion, reason }
          : { content },
        props.onSaved,
      );
    } catch (err) {
      setError(formatError(err));
    }
  }
  return (
    <form onSubmit={submit}>
      <fieldset disabled={command.busy || command.uncertain}>
        <legend>
          {existing
            ? "Korriger faktisk gjennomføring"
            : "Registrer faktisk gjennomføring"}
        </legend>
        <p>
          Planlagt tidspunkt, godkjent plan og åpnet assistentkort oppretter
          ingen gjennomførte minutter. Registrer det som faktisk skjedde.
        </p>
        {!existing && props.session && (
          <label className="teaching-check">
            <input
              type="checkbox"
              checked={linkSession}
              disabled={!props.session.approved}
              onChange={(e) => setLinkSession(e.target.checked)}
            />
            Koble til valgt godkjent øktrevisjon {props.session.revision}.
            Elevgruppen må være nøyaktig den planlagte. Fjern valget for å
            registrere en separat faktisk hendelse.
          </label>
        )}
        <DateField
          label="Faktisk start"
          value={date}
          onChange={setDate}
          zone={zone}
        />
        <Field label="Faktisk hendelsesvarighet i minutter">
          <input
            type="number"
            required
            min={0}
            max={480}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
          />
        </Field>
        <Field label="Gjennomføringsstatus">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="delivered">Gjennomført</option>
            <option value="partial">
              Delvis gjennomført / uavklart støtte
            </option>
            <option value="cancelled">Avlyst</option>
          </select>
        </Field>
        <Field label="Faktisk aktivitet">
          <textarea
            required
            maxLength={3000}
            value={activity}
            onChange={(e) => setActivity(e.target.value)}
          />
        </Field>
        <ReadStatus {...learners} formatError={formatError} />
        {participants.map((p, index) => (
          <fieldset key={index}>
            <legend>Deltakelse og støtteform {index + 1}</legend>
            <Field label={`Elev, registrering ${index + 1}`}>
              <select
                required
                value={p.learner_id}
                onChange={(e) =>
                  update(index, {
                    learner_id: e.target.value,
                    goal_revision_ids: [],
                  })
                }
              >
                <option value="">Velg elev</option>
                <option value={learnerId}>
                  {props.learnerName ?? "Valgt elev"}
                </option>
                {learners.value
                  ?.filter((l) => l.id !== learnerId)
                  .map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.display_name}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label={`Støtteform, registrering ${index + 1}`}>
              <CategorySelect
                value={p.category}
                onChange={(category) =>
                  update(index, {
                    category,
                    support_status:
                      category === "individually_adapted_education"
                        ? "unassessed"
                        : "assessed",
                    provision: null,
                    counting_basis: null,
                    attributed_staff_minutes: null,
                  })
                }
              />
            </Field>
            <Field label={`Deltakelse, registrering ${index + 1}`}>
              <select
                value={p.status}
                onChange={(e) => update(index, { status: e.target.value })}
              >
                <option value="participated">Deltok</option>
                <option value="partial">Deltok delvis</option>
                <option value="absent">Fraværende</option>
              </select>
            </Field>
            <Field label={`Faktiske elevminutter, registrering ${index + 1}`}>
              <input
                required
                type="number"
                min={0}
                max={duration}
                value={p.minutes}
                onChange={(e) =>
                  update(index, { minutes: Number(e.target.value) })
                }
              />
            </Field>
            <Field label={`Støtte som ble gitt, registrering ${index + 1}`}>
              <textarea
                required
                maxLength={1500}
                value={p.support}
                onChange={(e) => update(index, { support: e.target.value })}
              />
            </Field>
            {p.category === "individually_adapted_education" && (
              <p className="teaching-notice">
                Kvalifikasjon er uavklart. Rollebetegnelser dokumenterer ikke
                ITO-kompetanse. Denne registreringen får uavklart støtte med
                årsak og eier; den dokumenterer ikke oppfylt vedtak.
                Produksjonskilden for vurdert kvalifikasjon er ikke
                tilgjengelig.
              </p>
            )}
            {participants.length > 1 && (
              <button
                type="button"
                onClick={() =>
                  setParticipants((rows) => rows.filter((_, i) => i !== index))
                }
              >
                Fjern deltakelse {index + 1}
              </button>
            )}
          </fieldset>
        ))}
        <button
          type="button"
          disabled={participants.length >= 20}
          onClick={() =>
            setParticipants((rows) => [...rows, participant(learnerId)])
          }
        >
          Legg til elev eller annen støtteform
        </button>
        <fieldset>
          <legend>Faktisk ansattressurs</legend>
          <p>
            Elevtid og ansattressurs telles separat. To elever kan ha 30
            minutter hver mens én ansatt bruker 30 minutter. Ingen automatisk
            fordeling.
          </p>
          <ReadStatus {...people} formatError={formatError} />
          {staff.map((s, index) => (
            <div className="teaching-card" key={index}>
              <Field label={`Ansatt ${index + 1}`}>
                <select
                  required
                  value={s.staff_id}
                  onChange={(e) =>
                    setStaff((rows) =>
                      rows.map((row, i) =>
                        i === index
                          ? { ...row, staff_id: e.target.value }
                          : row,
                      ),
                    )
                  }
                >
                  <option value="">Velg ansatt</option>
                  {people.value?.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.display_name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={`Ansattminutter ${index + 1}`}>
                <input
                  type="number"
                  required
                  min={1}
                  max={duration}
                  value={s.minutes}
                  onChange={(e) =>
                    setStaff((rows) =>
                      rows.map((row, i) =>
                        i === index
                          ? { ...row, minutes: Number(e.target.value) }
                          : row,
                      ),
                    )
                  }
                />
              </Field>
              <Field label={`Rapportert rolle ${index + 1}`}>
                <input
                  required
                  maxLength={500}
                  value={s.role}
                  onChange={(e) =>
                    setStaff((rows) =>
                      rows.map((row, i) =>
                        i === index ? { ...row, role: e.target.value } : row,
                      ),
                    )
                  }
                />
              </Field>
              <Field label={`Ansattens støtteform ${index + 1}`}>
                <CategorySelect
                  value={s.category}
                  onChange={(category) =>
                    setStaff((rows) =>
                      rows.map((row, i) =>
                        i === index ? { ...row, category } : row,
                      ),
                    )
                  }
                />
              </Field>
              <button
                type="button"
                onClick={() =>
                  setStaff((rows) => rows.filter((_, i) => i !== index))
                }
              >
                Fjern ansatt {index + 1}
              </button>
            </div>
          ))}
          <button
            type="button"
            disabled={staff.length >= 30}
            onClick={() =>
              setStaff((rows) => [
                ...rows,
                {
                  staff_id: "",
                  minutes: 0,
                  role: "",
                  category: "ordinary_teaching",
                },
              ])
            }
          >
            Legg til faktisk ansattressurs
          </button>
        </fieldset>
        <fieldset>
          <legend>Avvik og ansvar</legend>
          <Field label="Årsak">
            <select
              required={status !== "delivered"}
              value={cause}
              onChange={(e) => setCause(e.target.value)}
            >
              <option value="">Ingen registrert årsak</option>
              <option value="learner_absence">Elevfravær</option>
              <option value="staff_unavailable">Manglende bemanning</option>
              <option value="changed_activity">Endret aktivitet</option>
              <option value="other">
                Annen årsak / uavklart kvalifikasjon
              </option>
            </select>
          </Field>
          <Field label="Beskriv årsaken">
            <textarea
              required={cause === "other"}
              maxLength={2000}
              value={detail}
              onChange={(e) => setDetail(e.target.value)}
            />
          </Field>
          <ReadStatus {...owners} formatError={formatError} />
          <Field label="Ansvarlig for oppfølging">
            <select
              required={status !== "delivered" || !!followup}
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
            >
              <option value="">Velg ansvarlig</option>
              {owners.value?.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.display_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Hva skal følges opp">
            <textarea
              required={status !== "delivered" || !!owner}
              maxLength={2000}
              value={followup}
              onChange={(e) => setFollowup(e.target.value)}
            />
          </Field>
        </fieldset>
        {existing &&
          (existing as Delivery & { follow_up_source_status?: string })
            .follow_up_source_status === "review_required" && (
            <p role="alert">
              Tidligere oppfølgingsbeskrivelse er skjermet etter kildeendring.
              Skriv en ny selvstendig handling og velg ansvarlig.
            </p>
          )}
        {existing && (
          <Field label="Begrunnelse for korrigering">
            <textarea
              required
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
        )}
        <button type="submit" disabled={conflict}>
          {existing
            ? "Lagre korrigert gjennomføring"
            : "Bekreft faktisk gjennomføring"}
        </button>
      </fieldset>
      {error && <p role="alert">{error}</p>}
      <CommandStatus command={command} />
      {conflict && (
        <section role="alert">
          <h4>Konkurrerende gjennomføring</h4>
          <p>
            Utkastet beholdes. Kontroller den lagrede registreringen før videre
            retting.
          </p>
          <ReadStatus {...competing} formatError={formatError} />
          {competing.value?.map((value) => (
            <DeliveryView key={value.revision_id} row={value} zone={zone} />
          ))}
          {existing && competing.value?.[0] && (
            <button
              type="button"
              onClick={() => {
                setExpectedVersion(competing.value![0].version);
                setConflict(false);
              }}
            >
              Jeg har sammenlignet og vil lagre korrigeringen mot gjeldende
              versjon
            </button>
          )}
        </section>
      )}
    </form>
  );
}
function DeliveryHistory({ props, row }: { props: Props; row: Delivery }) {
  const history = useRead(
    () =>
      allPages<Delivery>(props.client, props.schoolId, [
        "teaching",
        "deliveries",
        row.id,
        "revisions",
      ]),
    [props.client, props.schoolId, row.id, row.version],
  );
  return (
    <>
      <ReadStatus {...history} formatError={props.formatError} />
      {history.value?.map((d) => (
        <DeliveryView key={d.revision_id} row={d} zone={props.zone} />
      ))}
    </>
  );
}
export function DeliveryView({ row, zone }: { row: Delivery; zone: string }) {
  return (
    <article className="teaching-card">
      <h4>
        {displayDate(row.occurred_at, zone)} · revisjon {row.revision}
      </h4>
      <p>
        {row.state === "cancelled"
          ? "Avlyst"
          : row.state === "partial"
            ? "Delvis gjennomført"
            : "Gjennomført"}{" "}
        · Hendelsesvarighet: {row.duration_minutes} min
      </p>
      {row.activity && <p>{row.activity}</p>}
      <ul>
        {row.participants.map((p, i) => (
          <li key={i}>
            {categories[p.category]}: {p.minutes} elevminutter ·{" "}
            {p.status === "absent"
              ? "fravær"
              : p.status === "partial"
                ? "delvis deltakelse"
                : "deltok"}{" "}
            ·{" "}
            {p.support_assessment === "unassessed"
              ? "støtte uavklart"
              : "registrert støtte"}
            <br />
            {p.support}
          </li>
        ))}
      </ul>
      {row.staff_minutes !== null && (
        <p>
          Samlet ansattressurs i gruppen: {row.staff_minutes} min. Dette er ikke
          sum elevtid.
        </p>
      )}
      {row.cause && (
        <p>
          Avvik:{" "}
          {row.cause_detail ||
            ({
              learner_absence: "Elevfravær",
              staff_unavailable: "Manglende bemanning",
              changed_activity: "Endret aktivitet",
              other: "Annen årsak",
            }[row.cause] ??
              "Registrert årsak")}
        </p>
      )}
      {row.correction_reason && <p>Rettelse: {row.correction_reason}</p>}
    </article>
  );
}
export default function Deliveries(props: Props) {
  const list = useRead(
    () =>
      allPages<Delivery>(props.client, props.schoolId, [
        "learners",
        props.learnerId,
        "teaching-deliveries",
      ]),
    [props.client, props.schoolId, props.learnerId, props.active],
  );
  const [selected, setSelected] = useState("");
  const [newForm, setNewForm] = useState(false);
  const [success, setSuccess] = useState<Delivery>();
  const full = useRead(
    () =>
      selected
        ? props.client.schoolGet<Delivery>(props.schoolId, [
            "teaching",
            "deliveries",
            selected,
          ])
        : Promise.resolve(undefined),
    [props.client, props.schoolId, selected],
  );
  return (
    <section>
      <h3>Faktisk gjennomføring og avvik</h3>
      <DeliverySummary {...props} />
      <p>
        Samme kategori kan sammenstilles; assistanse og ITO holdes atskilt.
        Uregistrert tid er manglende dokumentasjon, ikke null gjennomføring.
      </p>
      <button
        type="button"
        onClick={() => {
          setNewForm(!newForm);
          setSuccess(undefined);
        }}
      >
        Registrer faktisk økt
      </button>
      {newForm && (
        <DeliveryForm
          {...props}
          onSaved={(row) => {
            setNewForm(false);
            setSuccess(row);
            list.reload();
            props.onChanged?.();
          }}
        />
      )}
      {success && (
        <>
          <p role="status">Gjennomføringen er lagret.</p>
          <DeliveryView row={success} zone={props.zone} />
        </>
      )}
      <ReadStatus {...list} formatError={props.formatError} />
      {list.value?.length === 0 && <p>Ingen gjennomføring er registrert.</p>}
      {list.value?.map((d) => (
        <div key={d.id}>
          <DeliveryView row={d} zone={props.zone} />
          <button type="button" onClick={() => setSelected(d.id)}>
            Åpne gruppeinnhold, retting og historikk
          </button>
        </div>
      ))}
      {selected && (
        <section>
          <h4>Kontroll av eksakt gjennomføring</h4>
          <button type="button" onClick={() => setSelected("")}>
            Lukk gjennomføring
          </button>
          <ReadStatus {...full} formatError={props.formatError} />
          {full.value && (
            <>
              <DeliveryForm
                key={full.value.revision_id}
                {...props}
                existing={full.value}
                onSaved={() => {
                  full.reload();
                  list.reload();
                  props.onChanged?.();
                }}
              />
              <details>
                <summary>Revisjonshistorikk</summary>
                <DeliveryHistory props={props} row={full.value} />
              </details>
            </>
          )}
        </section>
      )}
    </section>
  );
}
