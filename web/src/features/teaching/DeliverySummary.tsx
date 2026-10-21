import { LocalValidationError } from "../../userErrors";
import { useState } from "react";
import type { FormEvent } from "react";
import type { WorkspaceProps, Category } from "./types";
import { categories } from "./types";
import { Field, ReadStatus, useRead } from "./runtime";
type Summary = {
  actual_minutes_by_category: Partial<Record<Category, number>>;
  assessed_minutes_by_category: Partial<Record<Category, number>>;
  unassessed_claimed_minutes_by_category: Partial<Record<Category, number>>;
  entitlement_fulfilment: string;
};
/** First real instant of a civil date, including shifted or repeated midnight. */
export function firstDateInstant(date: string, zone: string): string {
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
    new Date(date + "T12:00:00Z").toISOString().slice(0, 10) !== date
  )
    throw new LocalValidationError("Velg en gyldig dato.");
  const formatter = new Intl.DateTimeFormat("sv-SE", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const target = Date.parse(date + "T00:00:00Z");
  for (
    let candidate = target - 14 * 3600000;
    candidate <= target + 38 * 3600000;
    candidate += 60000
  ) {
    const civil = formatter.format(new Date(candidate));
    if (civil >= date) return new Date(candidate).toISOString();
  }
  throw new LocalValidationError(
    "Datoperioden inneholder ingen reelle tidspunkter.",
  );
}
export function periodBounds(start: string, end: string, zone: string) {
  if (!start || !end || start > end)
    throw new LocalValidationError(
      "Velg fra- og til-dato i riktig rekkefølge.",
    );
  const after = new Date(end + "T12:00:00Z");
  after.setUTCDate(after.getUTCDate() + 1);
  const from = firstDateInstant(start, zone),
    until = firstDateInstant(after.toISOString().slice(0, 10), zone);
  if (from >= until)
    throw new LocalValidationError(
      "Datoperioden inneholder ingen reelle tidspunkter.",
    );
  return { start: from, end: until };
}
export default function DeliverySummary(
  props: WorkspaceProps & { learnerId: string; zone: string },
) {
  const [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [error, setError] = useState("");
  const [bounds, setBounds] = useState<{ start: string; end: string }>();
  const summary = useRead(
    () =>
      bounds
        ? props.client.schoolGet<Summary>(
            props.schoolId,
            ["learners", props.learnerId, "teaching-summary"],
            new URLSearchParams(bounds),
          )
        : Promise.resolve(undefined),
    [props.client, props.schoolId, props.learnerId, bounds?.start, bounds?.end],
  );
  function submit(event: FormEvent) {
    event.preventDefault();
    try {
      setBounds(periodBounds(start, end, props.zone));
      setError("");
    } catch (err) {
      setError(props.formatError(err));
    }
  }
  return (
    <details>
      <summary>Sammenstill registrerte elevminutter i valgt periode</summary>
      <form onSubmit={submit}>
        <Field label={`Fra og med dato (${props.zone})`}>
          <input
            required
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </Field>
        <Field label={`Til og med dato (${props.zone})`}>
          <input
            required
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </Field>
        <button type="submit">Vis valgt periode</button>
      </form>
      {error && <p role="alert">{error}</p>}
      <ReadStatus {...summary} formatError={props.formatError} />
      {summary.value && (
        <>
          <p>
            Begge valgte datoer inngår. Minuttene er registrerte faktiske
            opplysninger. Manglende registreringer betyr manglende
            dokumentasjon.
          </p>
          <div className="teaching-table-wrap">
            <table>
              <caption>Faktiske elevminutter per støtteform</caption>
              <thead>
                <tr>
                  <th scope="col">Støtteform</th>
                  <th scope="col">Registrerte elevminutter</th>
                  <th scope="col">Vurdert støtte</th>
                  <th scope="col">Uavklart støtte</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(summary.value.actual_minutes_by_category).map(
                  ([category, minutes]) => (
                    <tr key={category}>
                      <th scope="row">{categories[category as Category]}</th>
                      <td>{minutes}</td>
                      <td>
                        {summary.value!.assessed_minutes_by_category[
                          category as Category
                        ] ?? 0}
                      </td>
                      <td>
                        {summary.value!.unassessed_claimed_minutes_by_category[
                          category as Category
                        ] ?? 0}
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
          {Object.keys(summary.value.actual_minutes_by_category).length ===
            0 && (
            <p>
              Ingen registrert gjennomføring i perioden. Dette fastslår ikke at
              støtten uteble.
            </p>
          )}
          <p>
            Oppfyllelse av vedtak er uavklart. Assistentstøtte og ITO summeres
            ikke som samme ytelse. Ansattminutter er egne ressursopplysninger.
            Vurdert ITO krever serverkontrollert kvalifikasjonsbevis for hele
            hendelsesintervallet; produksjonskilden er ikke tilgjengelig.
          </p>
        </>
      )}
    </details>
  );
}
