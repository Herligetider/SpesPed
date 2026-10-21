import type { ProposalRecovery } from "./useProposalRecovery";
import {
  outcomeLabel,
  recoveryMessage,
  stateLabel,
} from "./useProposalRecovery";
const date = (value: string) =>
  new Date(value).toLocaleString("nb-NO", {
    dateStyle: "medium",
    timeStyle: "short",
  });
export function SavedProposals<D>({
  recovery: r,
}: {
  recovery: ProposalRecovery<D>;
}) {
  return (
    <section aria-label="Lagrede modellforslag">
      <h5>Lagrede forslag</h5>
      <p>
        {r.config.kind === "plan"
          ? "Listen gjelder den gjeldende IOP-revisjonen."
          : "Listen gjelder øktens gjeldende grunnlag. Flere økter kan dele grunnlag og forslag. Vurderingen som vises, gjelder denne økten."}{" "}
        Åpning bestiller eller kjører ingen ny modelljobb.
      </p>
      <button type="button" disabled={r.busy} onClick={r.refresh}>
        Hent lagrede forslag og status
      </button>
      {r.page.loading && <p role="status">Henter lagrede forslag …</p>}
      {r.page.error !== undefined && (
        <p role="alert">
          {recoveryMessage(r.config, r.page.error)} Manuell planlegging er
          tilgjengelig.
        </p>
      )}
      {r.page.value && (
        <>
          <ul>
            {r.page.value.items.map((item, i) => (
              <li key={item.id}>
                <p>
                  Forslag {r.offset + i + 1} · bestilt {date(item.created_at)} ·{" "}
                  {stateLabel(item.state)} · {item.attempts} registrerte
                  kjøreforsøk
                </p>
                <p>
                  {item.availability === "current"
                    ? "Grunnlaget er kontrollert nå"
                    : "Grunnlaget eller modellvalget må vurderes på nytt"}
                  .{" "}
                  {item.review_outcome
                    ? outcomeLabel(item.review_outcome)
                    : r.config.kind === "plan"
                      ? "Ikke vurdert i denne planen"
                      : "Ikke vurdert i denne økten"}
                  .
                </p>
                <button
                  type="button"
                  disabled={r.busy}
                  aria-pressed={r.selectedId === item.id}
                  onClick={() => r.select(item.id)}
                >
                  Åpne lagret forslag {r.offset + i + 1}
                </button>
              </li>
            ))}
          </ul>
          {!r.page.value.items.length && (
            <p>Ingen lagrede forslag for dette grunnlaget.</p>
          )}
          <nav aria-label="Flere lagrede forslag">
            <button
              type="button"
              disabled={r.busy || !r.offset}
              onClick={() => r.setOffset(Math.max(0, r.offset - 50))}
            >
              Forrige forslagsside
            </button>
            <span>
              {r.page.value.total
                ? `${r.offset + 1}–${Math.min(r.offset + 50, r.page.value.total)} av ${r.page.value.total}`
                : "0 forslag"}
            </span>
            <button
              type="button"
              disabled={r.busy || r.offset + 50 >= r.page.value.total}
              onClick={() => r.setOffset(r.offset + 50)}
            >
              Neste forslagsside
            </button>
          </nav>
        </>
      )}
    </section>
  );
}
export function RecoveryStatus<D>({
  recovery: r,
}: {
  recovery: ProposalRecovery<D>;
}) {
  return (
    <div aria-live="polite">
      {r.busy && <p role="status">Kontrollerer eller lagrer …</p>}
      {r.error !== undefined && (
        <p role="alert">{recoveryMessage(r.config, r.error)}</p>
      )}
      {r.notice && <p role="status">{r.notice}</p>}
      {r.uncertain && (
        <fieldset disabled={r.busy}>
          <legend>Uavklart svar på lagringsforsøket</legend>
          <p>
            Det opprinnelige forsøket og utkastet er bevart. Kontroller lagret
            status før du fortsetter.
          </p>
          <button type="button" onClick={() => void r.reconcile()}>
            Avklar mot lagret status
          </button>
          <button type="button" onClick={r.retry}>
            Gjenta det opprinnelige forsøket
          </button>
          {r.uncertain.kind === "create" && r.selectedId && (
            <button type="button" onClick={() => void r.continueSaved()}>
              Fortsett med valgt lagret forslag
            </button>
          )}
        </fieldset>
      )}
    </div>
  );
}
export function SelectedProposal<D>({
  recovery: r,
}: {
  recovery: ProposalRecovery<D>;
}) {
  const value = r.verified.value;
  return (
    <section aria-label="Valgt lagret forslag">
      {r.selectedId && (
        <button type="button" disabled={r.busy} onClick={r.refresh}>
          Kontroller jobbstatus og forslag på nytt
        </button>
      )}
      {r.verified.loading && (
        <p role="status">Kontrollerer valgt forslag og grunnlag …</p>
      )}
      {r.verified.error !== undefined && (
        <p role="alert">
          Valgt forslag kan ikke vises nå.{" "}
          {recoveryMessage(r.config, r.verified.error)} Fortsett manuelt.
        </p>
      )}
      {value && (
        <>
          <p>
            Registrert kjøring:{" "}
            {stateLabel(value.job?.state || value.summary.state)}.
          </p>
          {value.summary.review_outcome && (
            <p>
              Lagret vurdering: {outcomeLabel(value.summary.review_outcome)}.
              Ingen ny vurdering utføres ved åpning.
            </p>
          )}
          {value.summary.availability !== "current" && (
            <p role="status">
              Tidligere forslagstekst er skjult fordi grunnlaget eller
              modellvalget må vurderes på nytt. Manuell planlegging er
              tilgjengelig.
            </p>
          )}
          {value.summary.availability !== "current" &&
            value.summary.state === "running" &&
            !value.summary.review_outcome && (
              <div>
                <p>
                  Du kan avklare en mulig utløpt kjørefrist uten å åpne
                  tilbakekalt forslagstekst. Serveren avgjør om fristen faktisk
                  er passert. Dette lager eller godkjenner ingen tekst.
                </p>
                <button
                  type="button"
                  disabled={r.busy || Boolean(r.uncertain)}
                  onClick={() =>
                    r.command({
                      kind: "expire",
                      jobId: value.summary.id,
                      path: ["ai", "jobs", value.summary.id, "expire"],
                      body: { expected_version: value.summary.version },
                    })
                  }
                >
                  Avklar utløpt kjøring hvis fristen er passert
                </button>
              </div>
            )}
          {value.summary.state === "cancelled" && (
            <p>Forslaget er avbrutt og kan ikke brukes.</p>
          )}
          {value.job &&
            !value.summary.review_outcome &&
            value.summary.availability === "current" && (
              <>
                <p>
                  {value.job.attempts} registrerte kjøreforsøk. Serveren
                  kontrollerer om flere forsøk er tillatt.
                </p>
                {["queued", "failed", "unavailable"].includes(
                  value.job.state,
                ) && (
                  <button
                    type="button"
                    disabled={r.busy || Boolean(r.uncertain)}
                    onClick={() =>
                      r.command({
                        kind: "run",
                        jobId: value.job!.id,
                        path: ["ai", "jobs", value.job!.id, "run"],
                        body: { expected_version: value.job!.version },
                      })
                    }
                  >
                    {value.job.state === "queued"
                      ? "Kjør lagret modelljobb"
                      : "Prøv den samme lagrede modelljobben igjen"}
                  </button>
                )}
                {value.job.state === "running" && (
                  <>
                    <p>
                      Kjøringen er fortsatt registrert som pågående. Kontroller
                      status før du prøver igjen. Bare serveren kan bekrefte om
                      kjørefristen er utløpt.
                    </p>
                    <button
                      type="button"
                      disabled={r.busy || Boolean(r.uncertain)}
                      onClick={() =>
                        r.command({
                          kind: "expire",
                          jobId: value.job!.id,
                          path: ["ai", "jobs", value.job!.id, "expire"],
                          body: { expected_version: value.job!.version },
                        })
                      }
                    >
                      Avklar utløpt kjøring hvis fristen er passert
                    </button>
                  </>
                )}
                {!["succeeded", "cancelled"].includes(value.job.state) && (
                  <button
                    type="button"
                    disabled={r.busy || Boolean(r.uncertain)}
                    onClick={() =>
                      r.command({
                        kind: "cancel",
                        jobId: value.job!.id,
                        path: ["ai", "jobs", value.job!.id, "cancel"],
                        body: { expected_version: value.job!.version },
                      })
                    }
                  >
                    Avbryt denne lagrede modelljobben
                  </button>
                )}
              </>
            )}
        </>
      )}
    </section>
  );
}
