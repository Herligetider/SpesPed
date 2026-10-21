import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "../../api";
import type { DocumentWorkspaceProps } from "./types";
import type { DocumentCase, Revision, Section, Source, Workspace } from "./types";
import "./documents.css";

const clients = new WeakMap<object, number>();
let nextClient = 1;
function clientKey(client: object) { let key = clients.get(client); if (!key) { key = nextClient++; clients.set(client, key); } return key; }
async function allChoices<T>(client: DocumentWorkspaceProps["client"], schoolId: string, segments: string[], query: URLSearchParams): Promise<T[]> {
  const all: T[] = [];
  for (let offset = 0; ; offset += 100) {
    const pageQuery = new URLSearchParams(query); pageQuery.set("offset", String(offset)); pageQuery.set("limit", "100");
    const page = await client.schoolGet<{ items: T[]; total: number }>(schoolId, segments, pageQuery);
    all.push(...page.items);
    if (all.length >= page.total) return all;
    if (!page.items.length) throw new Error("Listen over godkjente valg kunne ikke fullføres.");
  }
}
const labels = {
  nb: { heading: "Dokumenter og rapporter", new: "Nytt dokumentutkast", kind: "Dokumenttype", purpose: "Formål", from: "Fra dato", to: "Til dato", email: "E-postutkast til foresatte", annual: "Årlig ITO-evaluering", local: "Lokal halvårsrapport", subject: "Ordinær fagvurdering", create: "Opprett utkast", list: "Dokumenter for eleven", loading: "Henter dokumenter …", empty: "Ingen dokumenter er opprettet for eleven ennå.", reload: "Last inn på nytt", title: "Emne", section: "Seksjon", text: "Tekst", sources: "Kilder i fryst grunnlag", gaps: "Avklaringsbehov", submit: "Send til faglig kontroll", approve: "Godkjenn denne revisjonen", recall: "Tilbakekall godkjenning", newRevision: "Lagre ny revisjon", reason: "Begrunnelse", reviewReason: "Begrunnelse for godkjenning", status: "Status", manual: "Manuelt arbeidsutkast uten bekreftet mal", template: "Gjennomgått mal", none: "Ingen tilgjengelig gjennomgått mal for dette valget.", sourceWarn: "Kildegrunnlaget er endret eller utilgjengelig. Gammel tekst holdes tilbake til kildene er kontrollert.", contentApproval: "Innholdsgodkjenning", disclosure: "Delingsgodkjenning håndteres separat. Godkjent innhold betyr ikke at noe er sendt.", createError: "Utkastet kunne ikke opprettes.", emailUnavailable: "Mottakervalg er ikke tilgjengelig ennå. E-postutkast er deaktivert til en godkjent foresattrelasjon kan velges.", obligationUnavailable: "Pliktvalg for perioden er ikke tilgjengelig. Dette kan derfor bare opprettes som manuelt arbeidsutkast, ikke som ferdig lovpålagt rapport.", contributions: "Bidrag", dispatch: "Ikke sendt", rangeError: "Fra-dato må være før eller lik til-dato.", retry: "Prøv samme lagring igjen", reloadConflict: "Revisjonen ble endret. Last inn nyeste versjon og bruk lokale endringer på nytt.", loadingError: "Kunne ikke hente dokumenter.", schedules: "Valgfrie utkastplaner", scheduleUnavailable: "Utkastplan krever valgbare foresattrelasjoner og tilgjengelige planvalg.", languages: "Språk", length: "Lengde", standard: "Standard", save: "Lagre", noText: "Ingen tekst", sourceCited: "Siteres i seksjon", unsupported: "AI-forslag er utilgjengelig fordi godkjent lokal modellkonfigurasjon ikke er tilgjengelig." },
  nn: { heading: "Dokument og rapportar", new: "Nytt dokumentutkast", kind: "Dokumenttype", purpose: "Føremål", from: "Frå dato", to: "Til dato", email: "E-postutkast til føresette", annual: "Årleg ITO-evaluering", local: "Lokal halvårsrapport", subject: "Ordinær fagvurdering", create: "Opprett utkast", list: "Dokument for eleven", loading: "Hentar dokument …", empty: "Ingen dokument er oppretta for eleven enno.", reload: "Last inn på nytt", title: "Emne", section: "Seksjon", text: "Tekst", sources: "Kjelder i fryst grunnlag", gaps: "Avklaringsbehov", submit: "Send til fagleg kontroll", approve: "Godkjenn denne revisjonen", recall: "Kall godkjenninga tilbake", newRevision: "Lagre ny revisjon", reason: "Grunngjeving", reviewReason: "Grunngjeving for godkjenning", status: "Status", manual: "Manuelt arbeidsutkast utan stadfesta mal", template: "Gjennomgått mal", none: "Ingen tilgjengeleg gjennomgått mal for dette valet.", sourceWarn: "Kjeldegrunnlaget er endra eller utilgjengeleg. Gammal tekst blir halden tilbake til kjeldene er kontrollerte.", contentApproval: "Innhaldsgodkjenning", disclosure: "Delingsgodkjenning blir handtert separat. Godkjent innhald tyder ikkje at noko er sendt.", createError: "Utkastet kunne ikkje opprettast.", emailUnavailable: "Mottakarval er ikkje tilgjengeleg enno. E-postutkast er deaktivert til ein godkjend føresetterelasjon kan veljast.", obligationUnavailable: "Pliktval for perioden er ikkje tilgjengeleg. Dette kan difor berre opprettast som manuelt arbeidsutkast, ikkje som ferdig lovpålagd rapport.", contributions: "Bidrag", dispatch: "Ikkje sendt", rangeError: "Frå-dato må vere før eller lik til-dato.", retry: "Prøv same lagring igjen", reloadConflict: "Revisjonen vart endra. Last inn siste versjon og bruk lokale endringar på nytt.", loadingError: "Klarte ikkje hente dokument.", schedules: "Valfrie utkastplanar", scheduleUnavailable: "Utkastplan krev valbare føresetterelasjonar og tilgjengelege planval.", languages: "Språk", length: "Lengd", standard: "Standard", save: "Lagre", noText: "Ingen tekst", sourceCited: "Sitert i seksjon", unsupported: "AI-forslag er ikkje tilgjengeleg fordi godkjend lokal modellkonfigurasjon ikkje er tilgjengeleg." },
};
function tr(language: "nb" | "nn", bokmal: string, nynorsk: string) { return language === "nn" ? nynorsk : bokmal; }
function statusLabel(language: "nb" | "nn", status: string) {
  const labelsByState: Record<string, [string, string]> = {
    draft: ["Utkast", "Utkast"], in_review: ["Til faglig kontroll", "Til fagleg kontroll"], approved: ["Godkjent innhold", "Godkjent innhald"], discarded: ["Forkastet", "Forkasta"],
    active: ["Aktiv", "Aktiv"], inactive: ["Inaktiv", "Inaktiv"], paused: ["Satt på pause", "Sett på pause"], ended: ["Avsluttet", "Avslutta"],
    current: ["Gjeldende", "Gjeldande"], unavailable: ["Utilgjengelig", "Utilgjengeleg"], review_required: ["Ny kontroll kreves", "Ny kontroll krevst"],
    applied: ["Brukt i ny revisjon", "Brukt i ny revisjon"], rejected: ["Forkastet", "Forkasta"],
    failed: ["Kunne ikke fullføres", "Klarte ikkje å fullføre"], reconciliation_required: ["Krever avklaring", "Krev avklaring"], created: ["Utkast opprettet", "Utkast oppretta"],
    pending: ["Venter", "Ventar"], queued: ["Lagt i kø", "Lagt i kø"], running: ["Behandles", "Blir handsama"], succeeded: ["Fullført", "Fullført"], blocked: ["Stanset", "Stansa"], draft_created: ["Utkast opprettet", "Utkast oppretta"], not_requested: ["Ikke bestilt", "Ikkje bestilt"],
    eligible: ["Tilgjengelig valg", "Tilgjengeleg val"], eligible_proposal: ["Mulig mottakerforslag", "Mogleg mottakarframlegg"], unresolved: ["Må avklares", "Må avklarast"], applicable: ["Gjelder perioden", "Gjeld perioden"],
    authority_review_required: ["Ny myndighetskontroll kreves", "Ny myndigheitskontroll krevst"], source_changed: ["Kildene er endret", "Kjeldene er endra"],
    not_authorized: ["Ikke godkjent for deling", "Ikkje godkjend for deling"], awaiting_review: ["Venter på kontroll", "Ventar på kontroll"], no_confirmed_observations_in_selected_period: ["Ingen bekreftede observasjoner i valgt periode", "Ingen stadfesta observasjonar i vald periode"],
  };
  return labelsByState[status]?.[language === "nb" ? 0 : 1] ?? status;
}
function gapLabel(language: "nb" | "nn", code: string) {
  const known: Record<string, [string, string]> = {
    no_confirmed_observations_in_selected_period: ["Ingen bekreftede observasjoner i den valgte perioden", "Ingen stadfesta observasjonar i den valde perioden"],
    no_confirmed_evidence_in_selected_period: ["Ingen bekreftede evidenskilder i den valgte perioden", "Ingen stadfesta evidenskjelder i den valde perioden"],
    no_applicable_template: ["Ingen gjennomgått mal gjelder perioden", "Ingen gjennomgått mal gjeld perioden"],
    no_applicable_obligation: ["Lovpålagt plikt for perioden må avklares", "Lovpålagd plikt for perioden må avklarast"],
    missing_contribution: ["Påkrevd fagbidrag mangler", "Påkravd fagbidrag manglar"],
  };
  return known[code]?.[language === "nb" ? 0 : 1] ?? code.replaceAll("_", " ");
}
function classificationLabel(language: "nb" | "nn", classification: string) {
  const known: Record<string, [string, string]> = {
    interval_fact: ["Faktum i rapportperioden", "Faktum i rapportperioden"], background_reference: ["Bakgrunn før perioden", "Bakgrunn før perioden"],
    actual_delivery_not_learning_progress: ["Gjennomført leveranse (ikke læringsframgang)", "Gjennomført leveranse (ikkje læringsframgang)"],
    future_plan_not_actual: ["Framtidig plan (ikke gjennomført tiltak)", "Framtidig plan (ikkje gjennomført tiltak)"],
  };
  return known[classification]?.[language === "nb" ? 0 : 1] ?? classification.replaceAll("_", " ");
}
const kinds = ["guardian_email", "annual_ito_evaluation", "local_semester_report", "ordinary_subject_assessment"] as const;
type DocumentRef = { kind: string; id: string; revision: number; link_id?: string; digest?: string };
type TemplateChoice = { template_id: string; revision_id: string; revision: number; content_digest: string; title: string; kind: string; sections: { key: string; label: string; required: boolean; contribution_required: boolean }[]; requirement_version_id: string | null; effective_from: string; effective_until: string; state: "reviewed_current" };
type GuardianChoice = { relationship_id: string; display_name: string; version: number; state: "eligible_proposal" | "unresolved"; disclosure: "not_authorized" };
type StaffChoice = { user_id: string; display_name: string; purpose: "owner" | "contributor"; action: string; state: "eligible"; assignment_purpose: string | null };
type ObligationChoice = { obligation_id: string; label: string; requirement_version_id: string; period_key: string; state: "applicable" | "unresolved"; report_period: { starts_on: string; ends_on: string } | null; unresolved_inputs: string[] };
type SourceChoice = { reference: DocumentRef; label: string; source_type: string; occurred_at: string; classification: "interval_fact" | "background_reference"; state: "current" | "review_required" };
type GoalChoice = { goal_revision_id: string; goal_id: string; title: string; kind: string; applicable_at: string; effective_period: { starts_at: string; ends_at_exclusive: string } };
type ActualChoice = { delivery_revision_id: string; revision: number; label: string; occurred_at: string; state: string; classification: "actual_delivery_not_learning_progress" };
type FutureChoice = { session_revision_id: string; revision: number; title: string; planned_at: string; state: string; classification: "future_plan_not_actual" };
type PickerChoice = GuardianChoice | StaffChoice | TemplateChoice | ObligationChoice | SourceChoice | GoalChoice | ActualChoice | FutureChoice;
type Draft = { kind: string; purpose: string; starts_on: string; ends_on: string; language: "nb" | "nn"; length: string; template_revision_id: string; obligation_id: string; owner_id: string; recipientIds: string[]; sources: DocumentRef[]; background: DocumentRef[]; goals: { goal_revision_id: string; applicable_at: string }[]; actuals: string[]; futurePlans: string[]; discoverEvidence: boolean; discoverObservations: boolean; topics: string[]; sections: { key: string; label: string; text: string; sources: string[]; missingInputs: string[] }[]; handledGaps: Record<string, string>; subject: string; reason: string };
type Recovery = { document_id: string; version: number; revision_id: string; content_digest: string; section_keys: string[]; generated_fields: string[] };
type ModelChoice = { policy_id: string; release_id: string; label: string; model_version: string; reviewed_at: string };
type Proposal = { document_id: string; revision_id: string; expected_version: number; job_id: string; proposal_digest: string; before: { subject: string | null; sections: { key: string; text: string | null; source_keys: string[]; missing_inputs: string[] }[] }; proposed: { subject: string | null; sections: { key: string; text: string; missing_evidence: string[] }[]; missing_evidence: string[] }; source_manifest: { reference?: { kind?: string }; classification?: string }[]; requires_human_review: true };
type ProposalRecord = { id: string; version: number; state: string; attempts: number; created_at: string; updated_at: string; basis_id: string; availability: "current" | "review_required"; reviews: { revision_id: string; outcome: "applied" | "rejected"; selection: { sections: string[]; subject: boolean }; reviewer_id: string; created_at: string }[] };
type InboxItem = { document_id: string; revision_id: string; version: number; kind: string; title: string; sections: { key: string; label: string; required: boolean }[] };
type ContributionWorkspace = { id: string; learner_id: string; version: number; revision_id: string; content_digest: string; assigned_sections: Section[]; sources: Source[]; source_status: { state: string }; contributions: { section_key: string; kind: string; text: string; source_keys: string[] }[]; whole_document_access: string };
export function calendarDateInZone(date: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(date);
  const part = (type: string) => parts.find((value) => value.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}
function zonedLocalToIso(value: string, timeZone: string): string {
  const [day, clock] = value.split("T");
  if (!day || !clock) return "";
  const [year, month, date] = day.split("-").map(Number);
  const [hour, minute] = clock.split(":").map(Number);
  const target = Date.UTC(year, month - 1, date, hour, minute);
  let guess = target;
  for (let attempt = 0; attempt < 3; attempt++) {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(guess));
    const part = (type: string) => Number(parts.find((item) => item.type === type)?.value ?? 0);
    const represented = Date.UTC(part("year"), part("month") - 1, part("day"), part("hour"), part("minute"));
    const correction = target - represented;
    guess += correction;
    if (!correction) break;
  }
  return new Date(guess).toISOString();
}
function newDraft(kind = "local_semester_report", lang: "nb" | "nn" = "nb", today = ""): Draft { return { kind, purpose: kind === "guardian_email" ? "period_update" : "professional_report", starts_on: today ? `${today.slice(0, 4)}-01-01` : "", ends_on: today, language: lang, length: "standard", template_revision_id: "", obligation_id: "", owner_id: "", recipientIds: [], sources: [], background: [], goals: [], actuals: [], futurePlans: [], discoverEvidence: true, discoverObservations: true, topics: [], sections: [{ key: "summary", label: lang === "nb" ? "Oppsummering" : "Samandrag", text: "", sources: [], missingInputs: [] }, { key: "next_steps", label: lang === "nb" ? "Videre oppfølging" : "Vidare oppfølging", text: "", sources: [], missingInputs: [] }], handledGaps: {}, subject: "", reason: "" }; }
function refKey(ref: DocumentRef) { return `${ref.kind}:${ref.id}:${ref.revision}`; }

export default function DocumentWorkspace(props: DocumentWorkspaceProps) {
  return <Scoped key={`${clientKey(props.client)}:${props.schoolId}:${props.learnerId}:${props.currentUser.id}`} {...props} />;
}
function Scoped(props: DocumentWorkspaceProps) {
  const t = labels[props.language];
  const [workspace, setWorkspace] = useState<Workspace>();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [selected, setSelected] = useState<string>();
  const [draft, setDraft] = useState(() => newDraft("local_semester_report", props.language));
  const [editor, setEditor] = useState(() => newDraft("local_semester_report", props.language));
  const [rebuildCoordinate, setRebuildCoordinate] = useState("");
  const [recovery, setRecovery] = useState<{ coordinate: string; value: Recovery }>();
  const [recoveryError, setRecoveryError] = useState("");
  const [inventoryRefresh, setInventoryRefresh] = useState(0);
  const [editorSourcesLoading, setEditorSourcesLoading] = useState(false);
  const [independentFields, setIndependentFields] = useState<string[]>([]);
  const [editorChoices, setEditorChoices] = useState<Record<string, PickerChoice[]>>({});
  const [editorChoicesLoading, setEditorChoicesLoading] = useState(false);
  const [editorChoicesError, setEditorChoicesError] = useState("");
  const [editorChoicesBlocked, setEditorChoicesBlocked] = useState(false);
  const [editorSources, setEditorSources] = useState<SourceChoice[]>([]);
  const [editorSourcesError, setEditorSourcesError] = useState("");
  const [editorTemplateSections, setEditorTemplateSections] = useState<{ key: string; label: string }[]>([]);
  const [editorTemplateError, setEditorTemplateError] = useState("");
  const [editorTemplateLoading, setEditorTemplateLoading] = useState(false);
  const [secureGeneration, setSecureGeneration] = useState(0);
  const recoveryKey = `documents-proposal:${clientKey(props.client)}:${props.schoolId}:${props.learnerId}:${props.currentUser.id}`;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<{ path: string[]; body: Record<string, unknown> } | undefined>(() => {
    try { const saved = JSON.parse(sessionStorage.getItem(`${recoveryKey}:pending`) ?? "null"); return Array.isArray(saved?.path) && saved?.body?.request_key ? saved : undefined; }
    catch { return undefined; }
  });
  const [success, setSuccess] = useState("");
  const [conflict, setConflict] = useState(false);
  const [modelChoices, setModelChoices] = useState<ModelChoice[]>([]);
  const [modelChoice, setModelChoice] = useState("");
  const [modelError, setModelError] = useState("");
  const [proposalJobId, setProposalJobId] = useState("");
  const [proposal, setProposal] = useState<Proposal>();
  const [savedProposals, setSavedProposals] = useState<ProposalRecord[]>([]);
  const [proposalError, setProposalError] = useState("");
  const [proposalLoading, setProposalLoading] = useState(false);
  const [proposalRefresh, setProposalRefresh] = useState(0);
  const [chosenSections, setChosenSections] = useState<string[]>([]);
  const [chooseSubject, setChooseSubject] = useState(false);
  const [inbox, setInbox] = useState<InboxItem[]>([]);
  const [pickerChoices, setPickerChoices] = useState<Record<string, PickerChoice[]>>({});
  const [pickerErrors, setPickerErrors] = useState<Record<string, string>>({});
  const [pickerLoading, setPickerLoading] = useState(false);
  const [schoolToday, setSchoolToday] = useState("");
  const [schoolTimeZone, setSchoolTimeZone] = useState("");
  const [scheduleDraft, setScheduleDraft] = useState({ firstRun: "", endsAt: "", recurrence: "months", recurrenceCount: "1", periodRule: "rolling_days", periodDays: "14" });
  const [scheduleRecipients, setScheduleRecipients] = useState<string[]>([]);
  const active = useRef(true);
  const loadGeneration = useRef(0);
  const load = useCallback(async () => {
    const generation = ++loadGeneration.current;
    setLoading(true); setLoadError("");
    try { const value = await props.client.schoolGet<Workspace>(props.schoolId, ["documents", "learners", props.learnerId, "workspace"], new URLSearchParams({ limit: "100" })); if (active.current && generation === loadGeneration.current) { setWorkspace(value); setSelected((prior) => value.documents.items.some((row) => row.id === prior) ? prior : value.documents.items[0]?.id); } }
    catch (e) { if (active.current && generation === loadGeneration.current) { setLoadError(props.formatError(e)); if (e instanceof ApiError && [401, 403, 404].includes(e.status)) { setWorkspace(undefined); setSelected(undefined); setEditor(newDraft("local_semester_report", props.language)); setDraft(newDraft("local_semester_report", props.language)); setProposal(undefined); setSavedProposals([]); setProposalJobId(""); setPending(undefined); setPickerChoices({}); setScheduleRecipients([]); setSecureGeneration((value) => value + 1); try { sessionStorage.removeItem(`${recoveryKey}:pending`); sessionStorage.removeItem(recoveryKey); } catch { /* Storage is optional; in-memory protected state is already cleared. */ } } } }
    finally { if (active.current && generation === loadGeneration.current) setLoading(false); }
  }, [props.client, props.schoolId, props.learnerId, props.formatError]);
  useEffect(() => { active.current = true; void load(); return () => { active.current = false; }; }, [load]);
  useEffect(() => {
    let valid = true;
    props.client.schools().then((schools) => {
      const school = schools.find((item) => item.id === props.schoolId);
      if (!valid) return;
      const today = school ? calendarDateInZone(new Date(), school.timezone) : "";
      setSchoolToday(today);
      setSchoolTimeZone(school?.timezone ?? "");
      setDraft((draft) => draft.starts_on || draft.ends_on ? draft : newDraft(draft.kind, props.language, today));
    }, () => { if (valid) setLoadError(props.language === "nb" ? "Skolens tidssone kunne ikke hentes." : "Tidssona til skulen kunne ikkje hentast."); });
    return () => { valid = false; };
  }, [props.client, props.schoolId, props.language]);
  useEffect(() => {
    let valid = true;
    props.client.schoolGet<{ items: InboxItem[] }>(props.schoolId, ["documents", "learners", props.learnerId, "contribution-inbox"], new URLSearchParams({ offset: "0", limit: "50" })).then((value) => { if (valid) setInbox(Array.isArray(value.items) ? value.items : []); }, () => { if (valid) setInbox([]); });
    return () => { valid = false; };
  }, [props.client, props.schoolId, props.learnerId]);
  useEffect(() => {
    let valid = true;
    const query = new URLSearchParams({ purpose: draft.kind === "guardian_email" ? "guardian_email_drafting" : "report_drafting", learner_id: props.learnerId });
    allChoices<ModelChoice>(props.client, props.schoolId, ["ai", "choices"], query).then((value) => { if (valid) setModelChoices(value); }, (error) => { if (valid) setModelError(props.formatError(error)); });
    return () => { valid = false; };
  }, [props.client, props.schoolId, props.learnerId, props.formatError, draft.kind]);
  useEffect(() => {
    let valid = true;
    setPickerLoading(true); setPickerErrors({});
    const base = { kind: draft.kind, starts_on: draft.starts_on, ends_on: draft.ends_on };
    const template = (pickerChoices.templates as TemplateChoice[] | undefined)?.find((item) => item.revision_id === draft.template_revision_id);
    const requests: [string, string, Record<string, string>][] = [
      ["owners", "owners", base],
      ["guardians", "guardians", base],
      ["templates", "templates", base],
      ["sources", "sources", { ...base, source_mode: "interval" }],
      ["background", "sources", { ...base, source_mode: "background" }],
    ];
    if (template?.requirement_version_id) requests.push(["obligations", "obligations", { ...base, requirement_version_id: template.requirement_version_id }]);
    if (draft.kind === "annual_ito_evaluation") { requests.push(["goals", "goals", base], ["actuals", "actuals", base]); }
    if (draft.kind === "guardian_email") requests.push(["future_plans", "future_plans", base]);
    Promise.all(requests.map(async ([key, category, params]) => {
      try { const query = new URLSearchParams(params); const values = await allChoices<PickerChoice>(props.client, props.schoolId, ["documents", "learners", props.learnerId, "choices", category], query); if (valid) { setPickerChoices((old) => ({ ...old, [key]: values })); if (key === "owners") setDraft((d) => d.owner_id ? d : ({ ...d, owner_id: (values as StaffChoice[]).find((choice) => choice.purpose === "owner")?.user_id ?? "" })); } }
      catch (error) { if (valid) { setPickerErrors((old) => ({ ...old, [key]: props.formatError(error) })); setPickerChoices((old) => ({ ...old, [key]: [] })); setDraft((d) => key === "sources" ? ({ ...d, sources: [], sections: d.sections.map((s) => ({ ...s, sources: s.sources.filter((source) => !d.sources.some((ref) => refKey(ref) === source)) })) }) : key === "background" ? ({ ...d, background: [], sections: d.sections.map((s) => ({ ...s, sources: s.sources.filter((source) => !d.background.some((ref) => refKey(ref) === source)) })) }) : key === "guardians" ? ({ ...d, recipientIds: [], }) : key === "obligations" ? ({ ...d, obligation_id: "" }) : key === "owners" ? ({ ...d, owner_id: "" }) : key === "actuals" ? ({ ...d, actuals: [] }) : key === "goals" ? ({ ...d, goals: [] }) : key === "future_plans" ? ({ ...d, futurePlans: [] }) : d); } }
    })).finally(() => { if (valid) setPickerLoading(false); });
    return () => { valid = false; };
  }, [props.client, props.schoolId, props.learnerId, props.formatError, draft.kind, draft.starts_on, draft.ends_on, draft.template_revision_id, (pickerChoices.templates as TemplateChoice[] | undefined)?.length]);
  const selectedDoc = workspace?.documents.items.find((row) => row.id === selected);
  const editorCoordinate = selectedDoc ? `${selectedDoc.id}:${selectedDoc.revision.id}:${selectedDoc.revision.source_status}:${!!selectedDoc.revision.source_changes.content_withheld}` : "";
  const rebuilding = !!editorCoordinate && rebuildCoordinate === editorCoordinate;
  const currentRecovery = recovery?.coordinate === editorCoordinate && recovery.value.version === selectedDoc?.version ? recovery.value : undefined;
  const sourceBad = !!selectedDoc && (selectedDoc.revision.source_status !== "current" || !!selectedDoc.revision.source_changes.content_withheld);
  useEffect(() => {
    setRecovery(undefined); setRecoveryError("");
    if (!selectedDoc || !sourceBad) return;
    let valid = true;
    props.client.schoolGet<Recovery>(props.schoolId, ["documents", "cases", selectedDoc.id, "recovery"]).then((value) => {
      if (!valid) return;
      if (value.document_id !== selectedDoc.id || value.revision_id !== selectedDoc.revision.id || value.version !== selectedDoc.version || value.content_digest !== selectedDoc.revision.digest || !Array.isArray(value.section_keys) || !Array.isArray(value.generated_fields)) {
        setRecoveryError(tr(props.language, "Grunnlaget er endret. Last inn dokumentet på nytt før gjenoppretting.", "Grunnlaget er endra. Last inn dokumentet på nytt før gjenoppretting.")); return;
      }
      setRecovery({ coordinate: editorCoordinate, value });
    }, (error) => { if (valid) setRecoveryError(props.formatError(error)); });
    return () => { valid = false; };
  }, [props.client, props.schoolId, editorCoordinate, selectedDoc?.version, inventoryRefresh]);
  useEffect(() => {
    if (!selectedDoc) { setEditorSources([]); return; }
    const period = selectedDoc.revision.snapshot?.manifest.period ?? (selectedDoc.revision.configuration?.starts_on && selectedDoc.revision.configuration.ends_on ? { starts_on: selectedDoc.revision.configuration.starts_on, ends_on: selectedDoc.revision.configuration.ends_on } : undefined);
    if (!period) { setEditorSources([]); setEditorSourcesError(tr(props.language, "Perioden for nytt kildegrunnlag er ikke tilgjengelig.", "Perioden for nytt kjeldegrunnlag er ikkje tilgjengeleg.")); return; }
    let valid = true;
    setEditorSources([]); setEditorSourcesError(""); setEditorTemplateSections([]); setEditorTemplateError("");
    setEditorChoices({}); setEditorChoicesLoading(true); setEditorChoicesError(""); setEditorChoicesBlocked(false);
    const base = { kind: selectedDoc.kind, starts_on: period.starts_on, ends_on: period.ends_on };
    const categories = ["owners", "goals", "actuals", "future_plans", ...(selectedDoc.kind === "guardian_email" ? ["guardians"] : [])];
    Promise.all(categories.map(async (category) => {
      try { const items = await allChoices<PickerChoice>(props.client, props.schoolId, ["documents", "learners", props.learnerId, "choices", category], new URLSearchParams(base)); if (valid) setEditorChoices((old) => ({ ...old, [category]: items })); }
      catch (error) { if (valid) { setEditorChoicesError((prior) => `${prior ? `${prior} · ` : ""}${category}: ${props.formatError(error)}`); if (category === "owners" || (category === "guardians" && selectedDoc.kind === "guardian_email")) setEditorChoicesBlocked(true); } }
    })).finally(() => { if (valid) setEditorChoicesLoading(false); });
    setEditorSourcesLoading(true);
    const query = new URLSearchParams({ ...base, source_mode: "interval" });
    allChoices<SourceChoice>(props.client, props.schoolId, ["documents", "learners", props.learnerId, "choices", "sources"], query).then((items) => { if (valid) { setEditorSources(items.filter((item) => item.state === "current")); setEditorSourcesError(""); } }, (error) => { if (valid) { setEditorSources([]); setEditorSourcesError(props.formatError(error)); } }).finally(() => { if (valid) setEditorSourcesLoading(false); });
    setEditorTemplateLoading(true);
    allChoices<TemplateChoice>(props.client, props.schoolId, ["documents", "learners", props.learnerId, "choices", "templates"], new URLSearchParams(base)).then(async (items) => {
      if (!valid) return;
      const templateId = selectedDoc.revision.configuration?.template_revision_id;
      const matching = items.find((item) => item.revision_id === templateId && item.kind === selectedDoc.kind && item.effective_from <= period.starts_on && period.ends_on <= item.effective_until);
      if (templateId && !matching) { setEditorTemplateSections([]); setEditorTemplateError(tr(props.language, "Den lagrede malen er ikke lenger tilgjengelig. Nytt grunnlag lagres som manuelt arbeidsutkast uten denne malen.", "Den lagra malen er ikkje lenger tilgjengeleg. Nytt grunnlag blir lagra som manuelt arbeidsutkast utan denne malen.")); }
      else { setEditorTemplateSections(matching?.sections.map((section) => ({ key: section.key, label: section.label })) ?? []); setEditorTemplateError(""); }
      if (matching?.requirement_version_id) {
        try { const obligations = await allChoices<ObligationChoice>(props.client, props.schoolId, ["documents", "learners", props.learnerId, "choices", "obligations"], new URLSearchParams({ ...base, requirement_version_id: matching.requirement_version_id })); if (valid) setEditorChoices((old) => ({ ...old, obligations })); }
        catch (error) { if (valid) setEditorTemplateError(props.formatError(error)); }
      }
    }, (error) => { if (valid) { setEditorTemplateSections([]); setEditorTemplateError(selectedDoc.revision.configuration?.template_revision_id ? props.formatError(error) : ""); } }).finally(() => { if (valid) setEditorTemplateLoading(false); });
    return () => { valid = false; };
  }, [props.client, props.schoolId, props.learnerId, props.language, props.formatError, editorCoordinate, inventoryRefresh]);
  useEffect(() => {
    if (!selectedDoc) { setProposalJobId(""); return; }
    try { const saved = JSON.parse(sessionStorage.getItem(recoveryKey) ?? "{}") as Record<string, string>; setProposalJobId(saved[selectedDoc.id] ?? ""); }
    catch { setProposalJobId(""); }
    setProposal(undefined); setProposalError("");
  }, [recoveryKey, selectedDoc?.id]);
  useEffect(() => {
    if (!selectedDoc) { setSavedProposals([]); return; }
    let valid = true;
    allChoices<ProposalRecord>(props.client, props.schoolId, ["documents", "cases", selectedDoc.id, "suggestions"], new URLSearchParams()).then((value) => {
      if (!valid) return;
      const items = value;
      setSavedProposals(items);
      setProposalJobId((current) => {
        if (current && items.some((item) => item.id === current)) return current;
        const saved = items.find((item) => item.availability === "current" && !item.reviews.length);
        if (!saved) return "";
        try { const map = JSON.parse(sessionStorage.getItem(recoveryKey) ?? "{}") as Record<string, string>; sessionStorage.setItem(recoveryKey, JSON.stringify({ ...map, [selectedDoc.id]: saved.id })); } catch { /* Session storage is optional. */ }
        return saved.id;
      });
    }, (e) => { if (valid && !(e instanceof ApiError && e.status === 403)) setProposalError(props.formatError(e)); }).catch((e) => { if (valid) setProposalError(props.formatError(e)); });
    return () => { valid = false; };
  }, [props.client, props.schoolId, selectedDoc?.id, selectedDoc?.version, recoveryKey, props.formatError]);
  useEffect(() => {
    if (!selectedDoc) { setEditor(newDraft("local_semester_report", props.language)); return; }
    const revision = selectedDoc.revision;
    const config = revision.configuration;
    const content = revision.source_status === "current" && !revision.source_changes.content_withheld ? revision.content : null;
    const period = revision.snapshot?.manifest.period;
    const templ = revision.snapshot?.manifest.template?.content;
    const hydrated = newDraft(selectedDoc.kind, config?.language === "nn" ? "nn" : props.language);
    hydrated.owner_id = selectedDoc.owner_id;
    hydrated.purpose = config?.purpose ?? hydrated.purpose;
    hydrated.starts_on = period?.starts_on ?? config?.starts_on ?? hydrated.starts_on;
    hydrated.ends_on = period?.ends_on ?? config?.ends_on ?? hydrated.ends_on;
    hydrated.language = config?.language === "nn" ? "nn" : config?.language === "nb" ? "nb" : props.language;
    hydrated.length = config?.length ?? "standard";
    hydrated.template_revision_id = config?.template_revision_id ?? "";
    hydrated.obligation_id = config?.obligation_id ?? "";
    hydrated.recipientIds = config?.recipient_relationship_ids ?? [];
    hydrated.topics = config?.topics ?? [];
    hydrated.sources = (config?.selection?.references as DocumentRef[] | undefined) ?? [];
    hydrated.background = (config?.selection?.background_references as DocumentRef[] | undefined) ?? [];
    hydrated.goals = (config?.selection?.goals as Draft["goals"] | undefined) ?? [];
    hydrated.actuals = (config?.selection?.actual_revision_ids as string[] | undefined) ?? [];
    hydrated.futurePlans = (config?.selection?.future_plan_revision_ids as string[] | undefined) ?? [];
    hydrated.discoverEvidence = Boolean(config?.selection?.discover_evidence);
    hydrated.discoverObservations = Boolean(config?.selection?.discover_observations);
    hydrated.subject = content?.subject ?? "";
    hydrated.handledGaps = content?.handled_gaps ?? {};
    hydrated.sections = content?.sections.map((s) => ({ key: s.key, label: templ?.sections.find((t) => t.key === s.key)?.label ?? s.key, text: s.text ?? "", sources: s.source_keys, missingInputs: s.missing_inputs ?? [] })) ?? hydrated.sections;
    setEditor(hydrated);
    setRebuildCoordinate(""); setIndependentFields([]);
  }, [editorCoordinate]);
  useEffect(() => {
    const saved = savedProposals.find((item) => item.id === proposalJobId);
    if (!selectedDoc || sourceBad || !proposalJobId || saved?.reviews.length) { setProposal(undefined); setProposalLoading(false); return; }
    let valid = true;
    setProposalLoading(true); setProposalError("");
    props.client.schoolGet<Proposal>(props.schoolId, ["documents", "cases", selectedDoc.id, "suggestions", proposalJobId, "diff"]).then((result) => {
      if (valid) { setProposal(result); setChosenSections([]); setChooseSubject(false); }
    }, (e) => { if (valid) { setProposal(undefined); setProposalError(props.formatError(e)); } }).finally(() => { if (valid) setProposalLoading(false); });
    return () => { valid = false; };
  }, [props.client, props.schoolId, selectedDoc?.id, selectedDoc?.revision_id, selectedDoc?.version, editorCoordinate, proposalJobId, proposalRefresh, savedProposals, props.formatError]);
  async function send(path: string[], body: Record<string, unknown>, successText: string): Promise<unknown> {
    if (busy) return undefined;
    const command = pending ?? { path, body: { request_key: crypto.randomUUID(), ...body } };
    setPending(command); setBusy(true); setError(""); setSuccess("");
    try { sessionStorage.setItem(`${recoveryKey}:pending`, JSON.stringify(command)); } catch { /* Keep the command in component state if storage is unavailable. */ }
    let result: unknown;
    try { result = await props.client.schoolCommand(props.schoolId, ["documents", ...command.path], command.body); if (!active.current) return undefined; setPending(undefined); try { sessionStorage.removeItem(`${recoveryKey}:pending`); } catch { /* Browser storage is optional. */ } setSuccess(successText); await load(); return result; }
    catch (e) { if (!active.current) return undefined; setError(e instanceof ApiError && e.status === 409 ? `${t.reloadConflict} ${props.formatError(e)}` : props.formatError(e)); if (e instanceof ApiError && e.status === 409) { setPending(undefined); try { sessionStorage.removeItem(`${recoveryKey}:pending`); } catch { /* Browser storage is optional. */ } setConflict(true); } else if (e instanceof ApiError && e.status > 0 && e.status < 500) { setPending(undefined); try { sessionStorage.removeItem(`${recoveryKey}:pending`); } catch { /* Browser storage is optional. */ } } else if (command.path.at(-1) === "suggestions") { try { sessionStorage.setItem(`${recoveryKey}:pending`, JSON.stringify(command)); } catch { /* Keep the same command in component state. */ } } }
    finally { if (active.current) setBusy(false); }
  }
  function selectKind(kind: string) { setDraft(newDraft(kind, props.language, schoolToday)); setScheduleRecipients([]); }
  function changePeriod(field: "starts_on" | "ends_on", value: string) {
    setDraft((d) => ({ ...d, [field]: value, recipientIds: [], obligation_id: "", sources: [], background: [], goals: [], actuals: [], futurePlans: [], sections: d.sections.map((s) => ({ ...s, sources: [] })) })); setScheduleRecipients([]);
  }
  function chooseTemplate(templateId: string) {
    const template = (pickerChoices.templates as TemplateChoice[] | undefined)?.find((item) => item.revision_id === templateId);
    if (!template) { setDraft((d) => ({ ...d, template_revision_id: "" })); return; }
    setDraft((d) => ({ ...d, template_revision_id: templateId, obligation_id: "", sources: [], background: [], goals: [], actuals: [], futurePlans: [], sections: template.sections.map((s) => ({ key: s.key, label: s.label, text: "", sources: [], missingInputs: [] })) }));
  }
  async function create(event: FormEvent) {
    event.preventDefault(); if (draft.starts_on > draft.ends_on) { setError(t.rangeError); return; }
    if (draft.kind === "guardian_email" && !draft.recipientIds.length) { setError(t.emailUnavailable); return; }
    if (draft.kind === "annual_ito_evaluation" && !draft.obligation_id) { setError(t.obligationUnavailable); return; }
    const template = (pickerChoices.templates as TemplateChoice[] | undefined)?.find((v) => v.revision_id === draft.template_revision_id && v.kind === draft.kind && v.effective_from <= draft.starts_on && draft.ends_on <= v.effective_until);
    if (draft.template_revision_id && !template) { setError(t.none); return; }
    const content = { subject: draft.subject || null, sections: draft.sections.map((s) => ({ key: s.key, text: s.text.trim() || null, source_keys: s.sources, missing_inputs: s.missingInputs.filter((v) => v.trim()) })), handled_gaps: Object.fromEntries(Object.entries(draft.handledGaps).filter(([, value]) => value.trim())) };
    const references = (items: DocumentRef[]) => items.map(({ kind, id, revision, link_id, digest }) => ({ kind, id, revision, ...(link_id ? { link_id } : {}), ...(digest ? { digest } : {}) }));
    const body = { learner_id: props.learnerId, owner_id: draft.owner_id, kind: draft.kind, purpose: draft.purpose, starts_on: draft.starts_on, ends_on: draft.ends_on, language: draft.language, length: draft.length, topics: draft.topics, recipient_relationship_ids: draft.recipientIds, ...(template ? { template_revision_id: template.revision_id } : {}), ...(draft.obligation_id ? { obligation_id: draft.obligation_id } : {}), selection: { discover_evidence: draft.discoverEvidence, discover_observations: draft.discoverObservations, references: references(draft.sources), background_references: references(draft.background), goals: draft.goals, actual_revision_ids: draft.actuals, future_plan_revision_ids: draft.futurePlans }, content };
    await send(["cases"], body, t.create);
  }
  function editSection(index: number, update: Partial<Draft["sections"][number]>) { setDraft((d) => ({ ...d, sections: d.sections.map((s, i) => i === index ? { ...s, ...update } : s) })); }
  function beginRebuild() {
    if (!selectedDoc || !currentRecovery) return;
    setRebuildCoordinate(editorCoordinate); setIndependentFields([]);
    const owners = editorChoices.owners as StaffChoice[] ?? [];
    const guardians = editorChoices.guardians as GuardianChoice[] ?? [];
    const obligations = editorChoices.obligations as ObligationChoice[] ?? [];
    const sections = editorTemplateSections.length ? editorTemplateSections : currentRecovery.section_keys.map((key) => ({ key, label: key }));
    setEditor((d) => ({ ...d,
      owner_id: owners.some((owner) => owner.user_id === d.owner_id) ? d.owner_id : "",
      recipientIds: d.recipientIds.filter((id) => guardians.some((guardian) => guardian.relationship_id === id && guardian.state === "eligible_proposal")),
      template_revision_id: editorTemplateSections.length ? d.template_revision_id : "",
      obligation_id: obligations.some((obligation) => obligation.obligation_id === d.obligation_id && obligation.state === "applicable") ? d.obligation_id : "",
      subject: "", reason: "", handledGaps: {}, sources: [], background: [], goals: [], actuals: [], futurePlans: [],
      discoverEvidence: false, discoverObservations: false,
      sections: sections.map((section) => ({ ...section, text: "", sources: [], missingInputs: [] })),
    }));
  }
  async function revise(doc: DocumentCase) {
    const content = { subject: editor.subject || null, sections: editor.sections.map((s) => ({ key: s.key, text: s.text.trim() || null, source_keys: s.sources, missing_inputs: s.missingInputs.filter((v) => v.trim()) })), handled_gaps: Object.fromEntries(Object.entries(editor.handledGaps).filter(([, value]) => value.trim())) };
    const configuration = doc.revision.snapshot?.manifest;
    const body = { expected_version: doc.version, ...(independentFields.length ? { sever_generation_fields: independentFields } : {}), reason: editor.reason.trim() || "Menneskelig redigering av dokumentutkast", document: { request_key: crypto.randomUUID(), learner_id: props.learnerId, owner_id: editor.owner_id || doc.owner_id, kind: doc.kind, purpose: doc.revision.configuration?.purpose ?? editor.purpose, starts_on: configuration?.period.starts_on ?? editor.starts_on, ends_on: configuration?.period.ends_on ?? editor.ends_on, language: editor.language, length: editor.length, recipient_relationship_ids: editor.recipientIds, topics: editor.topics, ...(editor.template_revision_id ? { template_revision_id: editor.template_revision_id } : {}), ...(editor.obligation_id ? { obligation_id: editor.obligation_id } : {}), selection: { discover_evidence: editor.discoverEvidence, discover_observations: editor.discoverObservations, references: editor.sources, background_references: editor.background, goals: editor.goals, actual_revision_ids: editor.actuals, future_plan_revision_ids: editor.futurePlans }, content } };
    await send(["cases", doc.id, "revisions"], body, t.newRevision);

  }
  async function transition(doc: DocumentCase, action: "review" | "approve" | "recall") {
    if (action === "approve" && !editor.reason.trim()) { setError(props.language === "nb" ? "Skriv en begrunnelse før godkjenning." : "Skriv ei grunngjeving før godkjenning."); return; }
    const r = doc.revision;
    await send(["cases", doc.id, "review"], { expected_version: doc.version, revision_id: r.id, content_digest: r.digest, action, reason: editor.reason.trim() || (action === "review" ? "Sendt til faglig gjennomgang" : "Godkjenning tilbakekalt") }, action === "review" ? t.submit : action === "approve" ? t.approve : t.recall);
  }
  async function transitionSchedule(schedule: Workspace["schedules"][number], action: "activate" | "pause" | "end") {
    await send(["schedules", schedule.id, "state"], { expected_version: schedule.version, action }, `Planen er ${action === "activate" ? "aktivert" : action === "pause" ? "satt på pause" : "avsluttet"}.`);
  }
  async function createSchedule(event: FormEvent) {
    event.preventDefault();
    const owner = (pickerChoices.owners as StaffChoice[] | undefined)?.find((item) => item.user_id === draft.owner_id);
    if (!schoolTimeZone || !draft.owner_id || !scheduleRecipients.length || !scheduleDraft.firstRun || !scheduleDraft.endsAt) { setError(t.scheduleUnavailable); return; }
    const settings = { learner_id: props.learnerId, owner_id: owner?.user_id ?? draft.owner_id, purpose: "period_update", recipient_relationship_ids: scheduleRecipients, first_run_at: zonedLocalToIso(scheduleDraft.firstRun, schoolTimeZone), ends_at: zonedLocalToIso(scheduleDraft.endsAt, schoolTimeZone), timezone: schoolTimeZone, recurrence: scheduleDraft.recurrence, recurrence_count: Number(scheduleDraft.recurrenceCount), period_rule: scheduleDraft.periodRule, period_days: Number(scheduleDraft.periodDays), language: draft.language, length: draft.length, topics: [], generation_mode: "manual", selection: { discover_evidence: true, discover_observations: true } };
    await send(["schedules"], { settings }, tr(props.language, "Utkastplan opprettet inaktiv. Aktiver planen uttrykkelig når den er kontrollert.", "Utkastplan oppretta inaktiv. Aktiver planen uttrykkeleg når ho er kontrollert."));
  }
  async function requestSuggestion(doc: DocumentCase) {
    const choice = modelChoices[Number(modelChoice)];
    if (!choice || !doc.revision.content || doc.revision.source_status !== "current") return;
    const result = await send(["cases", doc.id, "suggestions"], { expected_version: doc.version, revision_id: doc.revision.id, policy_id: choice.policy_id, release_id: choice.release_id }, props.language === "nb" ? "Lokal forslagjobb er registrert." : "Lokal forslagsjobb er registrert.");
    const id = result && typeof result === "object" && "id" in result ? String(result.id) : "";
    if (id) { setProposalJobId(id); try { const saved = JSON.parse(sessionStorage.getItem(recoveryKey) ?? "{}") as Record<string, string>; sessionStorage.setItem(recoveryKey, JSON.stringify({ ...saved, [doc.id]: id })); } catch { /* Server-side job remains available in the task response. */ } }
  }
  async function reviewSuggestion(doc: DocumentCase, outcome: "applied" | "rejected") {
    if (!proposal || !proposalJobId) return;
    if (outcome === "applied" && !chosenSections.length && !chooseSubject) { setError(props.language === "nb" ? "Velg minst én foreslått seksjon eller emne." : "Vel minst éin føreslått seksjon eller emne."); return; }
    if (!editor.reason.trim()) { setError(props.language === "nb" ? "Skriv en begrunnelse for valget." : "Skriv ei grunngjeving for valet."); return; }
    const result = await send(["cases", doc.id, "suggestion-review"], { expected_version: proposal.expected_version, revision_id: proposal.revision_id, job_id: proposal.job_id, proposal_digest: proposal.proposal_digest, selected_sections: outcome === "applied" ? chosenSections : [], select_subject: outcome === "applied" && chooseSubject, outcome, reason: editor.reason.trim() }, outcome === "applied" ? tr(props.language, "Valgt forslag er lagret i en ny dokumentrevisjon.", "Valt forslag er lagra i ein ny dokumentrevisjon.") : tr(props.language, "Forslaget er forkastet; eksisterende tekst er beholdt.", "Forslaget er forkasta; eksisterande tekst er halden på."));
    if (result !== undefined) { setProposalJobId(""); try { const saved = JSON.parse(sessionStorage.getItem(recoveryKey) ?? "{}") as Record<string, string>; delete saved[doc.id]; sessionStorage.setItem(recoveryKey, JSON.stringify(saved)); } catch { /* Storage is optional; the owner API remains authoritative. */ } }
  }
  function selectSavedProposal(docId: string, id: string) {
    setProposalJobId(id);
    try { const saved = JSON.parse(sessionStorage.getItem(recoveryKey) ?? "{}") as Record<string, string>; sessionStorage.setItem(recoveryKey, JSON.stringify({ ...saved, [docId]: id })); } catch { /* Server list is the durable record. */ }
  }
  const entries = selectedDoc?.revision.snapshot?.manifest.entries ?? [];
  return <section className="documents-workspace" lang={props.language}>
    <h2>{t.heading}</h2>
    {loading && <p role="status">{t.loading}</p>}
    {loadError && <div role="alert"><p>{loadError}</p><button type="button" onClick={() => void load()}>{t.reload}</button></div>}
    {!loading && workspace && <>
      <form onSubmit={(e) => void create(e)} className="documents-create">
        <h3>{t.new}</h3>
        <label>{t.kind}<select value={draft.kind} onChange={(e) => selectKind(e.target.value)}>{kinds.map((kind) => <option value={kind} key={kind}>{kind === "guardian_email" ? t.email : kind === "annual_ito_evaluation" ? t.annual : kind === "local_semester_report" ? t.local : t.subject}</option>)}</select></label>
        <label>{t.purpose}<input required value={draft.purpose} onChange={(e) => setDraft((d) => ({ ...d, purpose: e.target.value }))} /></label>
        <label>{t.from}<input type="date" required value={draft.starts_on} onChange={(e) => changePeriod("starts_on", e.target.value)} /></label>
        <label>{t.to}<input type="date" required value={draft.ends_on} onChange={(e) => changePeriod("ends_on", e.target.value)} /></label>
        <label>{t.languages}<select value={draft.language} onChange={(e) => setDraft((d) => ({ ...d, language: e.target.value as "nb" | "nn" }))}><option value="nb">Bokmål</option><option value="nn">Nynorsk</option></select></label>
        <label>{t.length}<select value={draft.length} onChange={(e) => setDraft((d) => ({ ...d, length: e.target.value }))}><option value="short">Kort</option><option value="standard">{t.standard}</option><option value="detailed">Detaljert</option></select></label>
        {draft.kind !== "guardian_email" && <label>{t.template}<select value={draft.template_revision_id} onChange={(e) => chooseTemplate(e.target.value)}><option value="">{t.manual}</option>{(pickerChoices.templates as TemplateChoice[] ?? []).filter((v) => v.kind === draft.kind).map((v) => <option key={v.revision_id} value={v.revision_id}>{v.title}</option>)}</select></label>}
        {pickerLoading && <p role="status">{tr(props.language, "Henter godkjente valg …", "Hentar godkjende val …")}</p>}
        {pickerErrors.templates && <p role="alert">{tr(props.language, "Malvalg: ", "Malval: ")}{pickerErrors.templates}</p>}
        <label>{tr(props.language, "Ansvarlig fagperson", "Ansvarleg fagperson")}<select value={draft.owner_id} onChange={(e) => setDraft((d) => ({ ...d, owner_id: e.target.value }))}><option value="">{props.currentUser.display_name} ({tr(props.language, "meg", "meg")})</option>{(pickerChoices.owners as StaffChoice[] ?? []).filter((v) => v.user_id !== props.currentUser.id).map((v) => <option key={v.user_id} value={v.user_id}>{v.display_name}</option>)}</select></label>
        {draft.kind === "guardian_email" && <fieldset><legend>{t.email}</legend>{pickerErrors.guardians ? <p role="alert">{pickerErrors.guardians}</p> : null}{!(pickerChoices.guardians as GuardianChoice[] ?? []).some((v) => v.state === "eligible_proposal") && !pickerErrors.guardians && !pickerLoading && <p role="status">{t.emailUnavailable}</p>}{(pickerChoices.guardians as GuardianChoice[] ?? []).filter((v) => v.state === "eligible_proposal").map((guardian) => <label key={guardian.relationship_id}><input type="checkbox" checked={draft.recipientIds.includes(guardian.relationship_id)} onChange={(e) => setDraft((d) => ({ ...d, recipientIds: e.target.checked ? [...d.recipientIds, guardian.relationship_id] : d.recipientIds.filter((id) => id !== guardian.relationship_id) }))} />{guardian.display_name} · {tr(props.language, "forslag kun, deling ikke godkjent", "berre forslag, deling ikkje godkjend")}</label>)}</fieldset>}
        {draft.kind === "annual_ito_evaluation" && <label>{tr(props.language, "Plikt for perioden", "Plikt for perioden")}<select value={draft.obligation_id} onChange={(e) => setDraft((d) => ({ ...d, obligation_id: e.target.value }))}><option value="">{tr(props.language, "Velg vurdert plikt", "Vel vurdert plikt")}</option>{(pickerChoices.obligations as ObligationChoice[] ?? []).filter((v) => v.state === "applicable").map((v) => <option key={v.obligation_id} value={v.obligation_id}>{v.label} · {v.period_key}</option>)}</select></label>}
        {draft.kind === "annual_ito_evaluation" && pickerErrors.obligations && <p role="alert">{pickerErrors.obligations}</p>}
        {draft.kind === "annual_ito_evaluation" && !pickerErrors.obligations && !pickerLoading && !(pickerChoices.obligations as ObligationChoice[] ?? []).some((v) => v.state === "applicable") && <p role="status">{t.obligationUnavailable}</p>}
        {draft.kind === "annual_ito_evaluation" && <fieldset><legend>{tr(props.language, "ITO-mål som gjelder i perioden", "ITO-mål som gjeld i perioden")}</legend>{(pickerChoices.goals as GoalChoice[] ?? []).map((goal) => <label key={goal.goal_revision_id}><input type="checkbox" checked={draft.goals.some((v) => v.goal_revision_id === goal.goal_revision_id)} onChange={(e) => setDraft((d) => ({ ...d, goals: e.target.checked ? [...d.goals, { goal_revision_id: goal.goal_revision_id, applicable_at: goal.applicable_at }] : d.goals.filter((v) => v.goal_revision_id !== goal.goal_revision_id) }))} />{goal.title} · {tr(props.language, "gjelder", "gjeld")} {goal.applicable_at.slice(0, 10)}</label>)}</fieldset>}
        {draft.kind === "annual_ito_evaluation" && <fieldset><legend>{tr(props.language, "Gjennomførte leveranser", "Gjennomførte leveransar")}</legend>{(pickerChoices.actuals as ActualChoice[] ?? []).map((actual) => <label key={actual.delivery_revision_id}><input type="checkbox" checked={draft.actuals.includes(actual.delivery_revision_id)} onChange={(e) => setDraft((d) => ({ ...d, actuals: e.target.checked ? [...d.actuals, actual.delivery_revision_id] : d.actuals.filter((id) => id !== actual.delivery_revision_id) }))} />{actual.label} · {actual.occurred_at.slice(0, 10)} · {classificationLabel(props.language, actual.classification)}</label>)}</fieldset>}
        {draft.kind === "guardian_email" && <fieldset><legend>{tr(props.language, "Framtidige planer, holdt atskilt fra gjennomførte tiltak", "Framtidige planar, haldne skilde frå gjennomførte tiltak")}</legend>{(pickerChoices.future_plans as FutureChoice[] ?? []).map((plan) => <label key={plan.session_revision_id}><input type="checkbox" checked={draft.futurePlans.includes(plan.session_revision_id)} onChange={(e) => setDraft((d) => ({ ...d, futurePlans: e.target.checked ? [...d.futurePlans, plan.session_revision_id] : d.futurePlans.filter((id) => id !== plan.session_revision_id) }))} />{plan.title} · {tr(props.language, "planlagt", "planlagd")} {plan.planned_at.slice(0, 10)}</label>)}</fieldset>}
        {draft.kind !== "guardian_email" && <fieldset><legend>{t.sources}</legend>{(pickerChoices.sources as SourceChoice[] ?? []).filter((v) => v.state === "current").map((source) => { const ref = source.reference; const key = refKey(ref); return <label key={key}><input type="checkbox" checked={draft.sources.some((v) => refKey(v) === key)} onChange={(e) => setDraft((d) => ({ ...d, sources: e.target.checked ? [...d.sources, ref] : d.sources.filter((v) => refKey(v) !== key) }))} />{source.label} · {source.occurred_at.slice(0, 10)}</label>; })}<label><input type="checkbox" checked={draft.discoverEvidence} onChange={(e) => setDraft((d) => ({ ...d, discoverEvidence: e.target.checked }))} />{tr(props.language, "Finn bekreftede evidenskilder i intervallet", "Finn stadfesta kjelder i intervallet")}</label><label><input type="checkbox" checked={draft.discoverObservations} onChange={(e) => setDraft((d) => ({ ...d, discoverObservations: e.target.checked }))} />{tr(props.language, "Finn bekreftede observasjoner i intervallet", "Finn stadfesta observasjonar i intervallet")}</label></fieldset>}
        {draft.kind !== "guardian_email" && <fieldset><legend>{tr(props.language, "Bakgrunnskilder før perioden", "Bakgrunnskjelder før perioden")}</legend>{(pickerChoices.background as SourceChoice[] ?? []).filter((v) => v.state === "current").map((source) => { const ref = source.reference; const key = refKey(ref); return <label key={key}><input type="checkbox" checked={draft.background.some((v) => refKey(v) === key)} onChange={(e) => setDraft((d) => ({ ...d, background: e.target.checked ? [...d.background, ref] : d.background.filter((v) => refKey(v) !== key) }))} />{source.label}</label>; })}</fieldset>}
        <label>{t.title}<input value={draft.subject} onChange={(e) => setDraft((d) => ({ ...d, subject: e.target.value }))} /></label>
        {draft.sections.map((section, index) => <fieldset key={section.key}><legend>{section.label || section.key}</legend><label>{t.text}<textarea rows={4} value={section.text} onChange={(e) => editSection(index, { text: e.target.value })} /></label><details><summary>{t.sourceCited}</summary>{[...draft.sources, ...draft.background].map((ref) => { const key = refKey(ref); return <label key={key}><input type="checkbox" checked={section.sources.includes(key)} onChange={(e) => editSection(index, { sources: e.target.checked ? [...section.sources, key] : section.sources.filter((item) => item !== key) })} />{ref.kind} · versjon {ref.revision}</label>; })}{!draft.sources.length && !draft.background.length && <p>{tr(props.language, "Velg kilder over før du knytter dem til en seksjon.", "Vel kjelder ovanfor før du knyter dei til ein seksjon.")}</p>}</details></fieldset>)}
        <button type="submit" disabled={busy || pickerLoading || !draft.owner_id || !draft.starts_on || !draft.ends_on || (draft.kind === "guardian_email" && !draft.recipientIds.length) || (draft.kind === "annual_ito_evaluation" && !draft.obligation_id)}>{t.create}</button>
      </form>
      <div className="documents-layout">
        <section><h3>{t.list}</h3><button type="button" disabled={loading} onClick={() => void load()}>{t.reload}</button>{workspace.documents.items.length === 0 ? <p>{t.empty}</p> : <ul>{workspace.documents.items.map((doc) => <li key={doc.id}><button type="button" aria-pressed={selected === doc.id} onClick={() => setSelected(doc.id)}>{(doc.revision.source_status === "current" && !doc.revision.source_changes.content_withheld && doc.revision.content?.subject) || (doc.revision.snapshot?.manifest.template?.content?.title ?? doc.kind)} · {doc.revision.number}</button><span>{statusLabel(props.language, doc.state)}</span></li>)}</ul>}</section>
        {selectedDoc && <div><DocumentPanel doc={selectedDoc} draft={editor} setDraft={setEditor} entries={entries} busy={busy} t={t} language={props.language} rebuilding={rebuilding} recovery={currentRecovery} recoveryError={recoveryError} onRefreshChoices={() => { setRebuildCoordinate(""); setInventoryRefresh((value) => value + 1); }} independentFields={independentFields} setIndependentFields={setIndependentFields} editorSourcesLoading={editorSourcesLoading} editorChoices={editorChoices} editorChoicesLoading={editorChoicesLoading} editorChoicesError={editorChoicesError} editorChoicesBlocked={editorChoicesBlocked} editorSources={editorSources} editorSourcesError={editorSourcesError} editorTemplateError={editorTemplateError} editorTemplateLoading={editorTemplateLoading} onBeginRebuild={beginRebuild} sourceBad={sourceBad} onRevise={() => void revise(selectedDoc)} onTransition={(a) => void transition(selectedDoc, a)} /><section className="documents-ai"><h4>{tr(props.language, "Lokal modellassistanse", "Lokal modellassistanse")}</h4>{modelError ? <p role="status">{modelError} · {tr(props.language, "fortsett manuelt.", "hald fram manuelt.")}</p> : modelChoices.length ? <><label>{tr(props.language, "Gjennomgått modell og lokal behandling", "Gjennomgått modell og lokal handsaming")}<select value={modelChoice} onChange={(e) => setModelChoice(e.target.value)}><option value="">{tr(props.language, "Vel oppsett", "Vel oppsett")}</option>{modelChoices.map((choice, index) => <option key={`${choice.policy_id}:${choice.release_id}`} value={index}>{choice.label} · {choice.model_version}</option>)}</select></label><button type="button" disabled={!modelChoice || busy || !selectedDoc.revision.content || selectedDoc.revision.source_status !== "current" || selectedDoc.state === "approved" || selectedDoc.state === "discarded"} onClick={() => void requestSuggestion(selectedDoc)}>{tr(props.language, "Bestill rapportforslag", "Bestill rapportforslag")}</button><p>{tr(props.language, "Forslaget endrer ikke teksten før menneskelig valg. Jobb-ID beholdes for gjenoppretting i denne økten.", "Forslaget endrar ikkje teksten før eit menneske vel. Jobb-ID-en blir teken vare på for gjenoppretting i denne økta.")}</p></> : <p>{tr(props.language, "Ingen godkjente lokale modellvalg er tilgjengelige. Fortsett med manuell redigering.", "Ingen godkjende lokale modellval er tilgjengelege. Hald fram med manuell redigering.")}</p>}
          {savedProposals.length > 0 && <label>{tr(props.language, "Lagrede forslag", "Lagra forslag")}<select aria-label={tr(props.language, "Lagrede forslag", "Lagra forslag")} value={proposalJobId} onChange={(e) => selectSavedProposal(selectedDoc.id, e.target.value)}><option value="">{tr(props.language, "Velg lagret forslag", "Vel lagra forslag")}</option>{savedProposals.map((item) => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString(props.language === "nb" ? "nb-NO" : "nn-NO")} · {item.reviews.length ? `${tr(props.language, "gjennomgått: ", "gjennomgått: ")}${statusLabel(props.language, item.reviews.at(-1)?.outcome ?? "")}` : item.availability === "current" ? statusLabel(props.language, item.state) : tr(props.language, "krever ny kildekontroll", "krev ny kjeldekontroll")}</option>)}</select></label>}
          {proposalJobId && savedProposals.find((item) => item.id === proposalJobId)?.reviews.length ? <p role="status">{tr(props.language, "Dette forslaget er allerede gjennomgått. Historisk utfall og revisjonsnummer vises i lagret historikk; godkjenning gjelder bare den konkrete dokumentrevisjonen.", "Dette forslaget er alt gjennomgått. Historisk utfall og revisjonsnummer står i lagra historikk; godkjenning gjeld berre den konkrete dokumentrevisjonen.")}</p> : null}
          {proposalLoading && <p role="status">{tr(props.language, "Henter valgt forslag …", "Hentar valt forslag …")}</p>}{proposalError && <div role="alert"><p>{proposalError}</p><button type="button" disabled={proposalLoading} onClick={() => setProposalRefresh((v) => v + 1)}>{tr(props.language, "Hent valgt forslag på nytt", "Hent valt forslag på nytt")}</button></div>}
          {proposal && !sourceBad && <div className="documents-proposal"><h4>{tr(props.language, "Ubehandlet forslag · må vurderes av fagperson", "Ubearbeidd forslag · må vurderast av fagperson")}</h4><p>{tr(props.language, "Kildemanifestet kontrolleres på nytt ved lesing. Teksten erstatter ingenting før du velger felt og lagrer vurderingen.", "Kjeldemanifestet blir kontrollert på nytt ved lesing. Teksten erstattar ingenting før du vel felt og lagrar vurderinga.")}</p>{proposal.proposed.subject && <label><input type="checkbox" checked={chooseSubject} onChange={(e) => setChooseSubject(e.target.checked)} /> {tr(props.language, "Foreslått emne: ", "Føreslått emne: ")}<strong>{proposal.proposed.subject}</strong></label>}{proposal.proposed.sections.map((section) => <fieldset key={section.key}><legend>{section.key}</legend><label><input type="checkbox" checked={chosenSections.includes(section.key)} onChange={(e) => setChosenSections((old) => e.target.checked ? [...old, section.key] : old.filter((key) => key !== section.key))} /> {tr(props.language, "Bruk denne seksjonen", "Bruk denne seksjonen")}</label><div className="documents-diff"><section><h5>{tr(props.language, "Gjeldende tekst", "Gjeldande tekst")}</h5><p>{proposal.before.sections.find((v) => v.key === section.key)?.text || "Ingen tekst"}</p></section><section><h5>{tr(props.language, "Foreslått tekst", "Føreslått tekst")}</h5><p>{section.text}</p></section></div>{section.missing_evidence.map((gap) => <p role="status" key={gap}>{tr(props.language, "Manglende grunnlag: ", "Manglande grunnlag: ")}{gap}</p>)}</fieldset>)}{proposal.proposed.missing_evidence.map((gap) => <p role="status" key={gap}>{tr(props.language, "Manglende grunnlag: ", "Manglande grunnlag: ")}{gap}</p>)}<p>{tr(props.language, "Kilder i forslaget: ", "Kjelder i forslaget: ")}{proposal.source_manifest.map((entry) => `${entry.reference?.kind ?? "kilde"} (${entry.classification ?? "uavklart"})`).join(", ") || "Ingen stadfesta kjelder"}</p><div className="documents-actions"><button type="button" disabled={busy} onClick={() => void reviewSuggestion(selectedDoc, "applied")}>{tr(props.language, "Lagre valgte felt som ny revisjon", "Lagre valde felt som ny revisjon")}</button><button type="button" disabled={busy} onClick={() => void reviewSuggestion(selectedDoc, "rejected")}>{tr(props.language, "Forkast forslaget og behold egen tekst", "Forkast forslaget og hald på eigen tekst")}</button></div></div>}
        </section></div>}
      </div>
      <section className="documents-schedules"><h3>{t.schedules}</h3><form onSubmit={(event) => void createSchedule(event)}><fieldset><legend>{tr(props.language, "Ny plan for utkast – separat fra rapportperioden", "Ny plan for utkast – skild frå rapportperioden")}</legend><label>{tr(props.language, "Første kjøring i skolens tidssone", "Første køyring i skulen si tidssone")}<input required type="datetime-local" value={scheduleDraft.firstRun} onChange={(e) => setScheduleDraft((d) => ({ ...d, firstRun: e.target.value }))} /></label><label>{tr(props.language, "Planen slutter", "Planen sluttar")}<input required type="datetime-local" value={scheduleDraft.endsAt} onChange={(e) => setScheduleDraft((d) => ({ ...d, endsAt: e.target.value }))} /></label><label>{tr(props.language, "Gjentakelse", "Gjentaking")}<select value={scheduleDraft.recurrence} onChange={(e) => setScheduleDraft((d) => ({ ...d, recurrence: e.target.value }))}><option value="months">{tr(props.language, "Måneder", "Månader")}</option><option value="days">{tr(props.language, "Dager", "Dagar")}</option></select></label><label>{tr(props.language, `Antall ${scheduleDraft.recurrence === "months" ? "måneder" : "dager"} mellom utkast`, `Tal ${scheduleDraft.recurrence === "months" ? "månader" : "dagar"} mellom utkast`)}<input type="number" min="1" max="365" required value={scheduleDraft.recurrenceCount} onChange={(e) => setScheduleDraft((d) => ({ ...d, recurrenceCount: e.target.value }))} /></label><label>{tr(props.language, "Rapportperiode", "Rapportperiode")}<select value={scheduleDraft.periodRule} onChange={(e) => setScheduleDraft((d) => ({ ...d, periodRule: e.target.value }))}><option value="rolling_days">{tr(props.language, "Rullerende dager", "Rullerande dagar")}</option><option value="previous_month">{tr(props.language, "Forrige kalendermåned", "Førre kalendermånad")}</option></select></label>{scheduleDraft.periodRule === "rolling_days" && <label>{tr(props.language, "Dager i hver rapportperiode", "Dagar i kvar rapportperiode")}<input type="number" min="1" max="366" required value={scheduleDraft.periodDays} onChange={(e) => setScheduleDraft((d) => ({ ...d, periodDays: e.target.value }))} /></label>}<fieldset><legend>{tr(props.language, "Foresatte (planen lager bare utkast)", "Føresette (planen lagar berre utkast)")}</legend>{(pickerChoices.guardians as GuardianChoice[] ?? []).filter((g) => g.state === "eligible_proposal").map((g) => <label key={g.relationship_id}><input type="checkbox" checked={scheduleRecipients.includes(g.relationship_id)} onChange={(e) => setScheduleRecipients((old) => e.target.checked ? [...old, g.relationship_id] : old.filter((id) => id !== g.relationship_id))} />{g.display_name}</label>)}{!(pickerChoices.guardians as GuardianChoice[] ?? []).some((g) => g.state === "eligible_proposal") && !pickerLoading && <p role="status">{t.emailUnavailable}</p>}</fieldset><button type="submit" disabled={busy || pickerLoading || !draft.owner_id || !scheduleDraft.firstRun || !scheduleDraft.endsAt || !scheduleRecipients.length}>{tr(props.language, "Opprett inaktiv plan", "Opprett inaktiv utkastplan")}</button></fieldset></form>{workspace.schedules.length ? <ul>{workspace.schedules.map((s) => <li key={s.id}><strong>{statusLabel(props.language, s.effective_state)}</strong> · {tr(props.language, "neste periode", "neste periode")} {s.next_period.starts_on}–{s.next_period.ends_on} · {tr(props.language, "neste kjøring", "neste køyring")} {s.next_run_at} · {s.runs.length} {t.contributions}{s.runs.map((run, index) => <p key={index}>{statusLabel(props.language, run.status)} · {run.summary.manual_review_required ? tr(props.language, "Krever manuell kontroll", "Krev manuell kontroll") : tr(props.language, "Ingen ekstra kontrollstatus", "Ingen ekstra kontrollstatus")}</p>)}{s.state !== "ended" && <div className="documents-actions"><button type="button" disabled={busy || s.state === "active"} onClick={() => void transitionSchedule(s, "activate")}>{tr(props.language, "Aktiver", "Aktiver")}</button><button type="button" disabled={busy || s.state !== "active"} onClick={() => void transitionSchedule(s, "pause")}>{tr(props.language, "Sett på pause", "Set på pause")}</button><button type="button" disabled={busy} onClick={() => void transitionSchedule(s, "end")}>{tr(props.language, "Avslutt", "Avslutt")}</button></div>}</li>)}</ul> : <p>{tr(props.language, "Ingen utkastplaner er opprettet.", "Ingen utkastplanar er oppretta.")}</p>}</section>
      <p className="documents-disclosure">{t.disclosure} {t.dispatch}</p>
    </>}
    {!!inbox.length && <ContributionInbox key={secureGeneration} client={props.client} schoolId={props.schoolId} items={inbox} formatError={props.formatError} language={props.language} />}
    {pending && !busy && !error && <div role="status"><p>{tr(props.language, "En tidligere lagring har uavklart svar. Gjenta samme kommando med uendret nøkkel for å hente bekreftet resultat.", "Ei tidlegare lagring har uavklart svar. Gjenta den same kommandoen med uendra nøkkel for å hente stadfesta resultat.")}</p><button type="button" onClick={() => void send(pending.path, pending.body, t.save)}>{t.retry}</button></div>}
    {error && <div role="alert"><p>{error}</p>{pending && <button type="button" disabled={busy} onClick={() => void send(pending.path, pending.body, t.save)}>{t.retry}</button>}{conflict && <button type="button" disabled={loading} onClick={() => { void load().then(() => { setConflict(false); setError(""); }); }}>{t.reload}</button>}{!pending && !conflict && <button type="button" onClick={() => setError("")}>{t.reload}</button>}</div>}
    {success && <p role="status">{success}</p>}
  </section>;
}

type T = typeof labels.nb;
function DocumentPanel({ doc, draft, setDraft, entries, busy, t, language, sourceBad, rebuilding, recovery, recoveryError, onRefreshChoices, independentFields, setIndependentFields, editorSourcesLoading, editorChoices, editorChoicesLoading, editorChoicesError, editorChoicesBlocked, editorSources, editorSourcesError, editorTemplateError, editorTemplateLoading, onBeginRebuild, onRevise, onTransition }: { doc: DocumentCase; draft: Draft; setDraft: (update: (d: Draft) => Draft) => void; entries: Source[]; busy: boolean; t: T; language: "nb" | "nn"; sourceBad: boolean; rebuilding: boolean; recovery?: Recovery; recoveryError: string; onRefreshChoices: () => void; independentFields: string[]; setIndependentFields: (fields: string[]) => void; editorSourcesLoading: boolean; editorChoices: Record<string, PickerChoice[]>; editorChoicesLoading: boolean; editorChoicesError: string; editorChoicesBlocked: boolean; editorSources: SourceChoice[]; editorSourcesError: string; editorTemplateError: string; editorTemplateLoading: boolean; onBeginRebuild: () => void; onRevise: () => void; onTransition: (action: "review" | "approve" | "recall") => void }) {
  const revision: Revision = doc.revision;
  const generatedFields = sourceBad ? recovery?.generated_fields ?? [] : Object.keys(revision.lineage ?? {});
  const gapCodes = [...new Set([...(sourceBad ? [] : revision.snapshot?.manifest.gaps ?? []), ...draft.sections.flatMap((section) => section.missingInputs).filter((gap) => gap.trim())])];
  const replacementInvalid = (rebuilding && generatedFields.some((field) => !independentFields.includes(field))) || independentFields.some((field) => {
    const after = field === "subject" ? draft.subject.trim() : draft.sections.find((section) => section.key === field)?.text.trim();
    const before = field === "subject" ? revision.content?.subject : revision.content?.sections.find((section) => section.key === field)?.text;
    return !after || (before !== undefined && after === before);
  });
  return <article className="document-current">
    <h3>{(!sourceBad && doc.revision.content?.subject) || doc.revision.snapshot?.manifest.template?.content?.title || doc.kind} · revisjon {revision.number}</h3>
    <p>{t.status}: {statusLabel(language, doc.state)} · {tr(language, "kildegrunnlag", "kjeldegrunnlag")}: {statusLabel(language, revision.source_status)} · {t.dispatch}</p>
    {sourceBad && <p role="alert">{t.sourceWarn}</p>}
    {revision.approval && <p>{t.contentApproval}: {statusLabel(language, revision.approval.state)}</p>}
    {!!gapCodes.length && (!sourceBad || rebuilding) && <div><h4>{t.gaps}</h4><fieldset><legend>{tr(language, "Menneskelig avklaring av hvert gap", "Menneskeleg avklaring av kvart gap")}</legend>{gapCodes.map((gap) => <label key={gap}>{gapLabel(language, gap)}<textarea aria-label={`${tr(language, "Forklaring for", "Forklaring for")} ${gapLabel(language, gap)}`} rows={2} value={draft.handledGaps[gap] ?? ""} onChange={(e) => setDraft((d) => ({ ...d, handledGaps: { ...d.handledGaps, [gap]: e.target.value } }))} /></label>)}</fieldset></div>}
    {revision.missing_contributions?.length ? <p>{t.contributions}: {revision.missing_contributions.join(", ")}</p> : null}
    {revision.content && !sourceBad ? <div>{revision.content.sections.map((section) => <section key={section.key}><h4>{section.key}</h4><p>{section.text || t.noText}</p><small>{section.source_keys.length ? `${t.sources}: ${section.source_keys.map((key) => entries.find((v) => v.key === key)?.value?.title ?? key).join(", ")}` : tr(language, "Ingen siterte kilder", "Ingen siterte kjelder")}</small></section>)}</div> : null}
    {!!entries.length && !sourceBad && <details><summary>{t.sources} ({entries.length})</summary><ul>{entries.map((entry) => <li key={entry.key}><strong>{String(entry.value.title ?? entry.value.content ?? entry.reference.kind)}</strong> · {entry.reference.kind} · {classificationLabel(language, entry.classification)}</li>)}</ul></details>}
    {((revision.content && !sourceBad) || rebuilding) && <div className="documents-edit"><h4>{rebuilding ? tr(language, "Bygg nytt grunnlag", "Bygg nytt grunnlag") : t.newRevision}</h4><label>{t.title}<input value={draft.subject} onChange={(e) => setDraft((d) => ({ ...d, subject: e.target.value }))} /></label>{draft.sections.map((section, index) => <fieldset key={section.key}><legend>{section.label}</legend><label>{t.text}<textarea rows={4} value={section.text} onChange={(e) => setDraft((d) => ({ ...d, sections: d.sections.map((v, i) => i === index ? { ...v, text: e.target.value } : v) }))} /></label><label>{tr(language, "Uavklart informasjon i seksjonen", "Uavklart informasjon i seksjonen")}<textarea rows={2} value={section.missingInputs.join("\n")} onChange={(e) => setDraft((d) => ({ ...d, sections: d.sections.map((v, i) => i === index ? { ...v, missingInputs: e.target.value.split("\n") } : v) }))} /></label><span>{t.sources}</span>{(rebuilding ? editorSources.map((source) => ({ key: refKey(source.reference), reference: source.reference, classification: "interval_fact", value: { title: source.label, content: source.label } as Record<string, unknown> })) : entries).map((entry) => <label className="document-source-choice" key={entry.key}><input type="checkbox" checked={section.sources.includes(entry.key)} onChange={(e) => setDraft((d) => ({ ...d, sources: rebuilding && e.target.checked && !d.sources.some((source) => refKey(source) === entry.key) ? [...d.sources, entry.reference] : d.sources, sections: d.sections.map((v, i) => i === index ? { ...v, sources: e.target.checked ? [...v.sources, entry.key] : v.sources.filter((k) => k !== entry.key) } : v) }))} />{String(entry.value.title ?? entry.value.content ?? entry.reference.kind)} · {entry.reference.kind} · {classificationLabel(language, entry.classification)}</label>)}</fieldset>)}</div>}
    {!!generatedFields.length && (!sourceBad || rebuilding) && <fieldset><legend>{tr(language, "Selvstendig menneskelig erstatning av AI-felt", "Sjølvstendig menneskeleg erstatning av AI-felt")}</legend><p>{tr(language, "Velg bare felt du har skrevet selv fra det nye grunnlaget. Kopiert eller uendret AI-tekst beholder sin opprinnelse. Feltene du velger må ha ny tekst. Utilgjengelig AI-grunnlag krever at alle berørte felt erstattes før dokumentet blir lesbart.", "Vel berre felt du har skrive sjølv frå det nye grunnlaget. Kopiert eller uendra AI-tekst beheld opphavet sitt. Felta du vel må ha ny tekst. Utilgjengeleg AI-grunnlag krev at alle berørte felt blir erstatta før dokumentet blir leseleg.")}</p>{generatedFields.map((field) => <label key={field}><input type="checkbox" checked={independentFields.includes(field)} onChange={(e) => setIndependentFields(e.target.checked ? [...independentFields, field] : independentFields.filter((key) => key !== field))} />{tr(language, "Jeg har skrevet en selvstendig erstatning for", "Eg har skrive ei sjølvstendig erstatning for")} {field === "subject" ? t.title : field}</label>)}</fieldset>}
    {sourceBad && !rebuilding && <button type="button" disabled={busy || editorSourcesLoading || editorChoicesLoading || editorTemplateLoading} onClick={onRefreshChoices}>{tr(language, "Hent gjeldende valg på nytt", "Hent gjeldande val på nytt")}</button>}
    {recoveryError && <p role="alert">{recoveryError}</p>}{editorChoicesError && sourceBad && <p role="alert">{editorChoicesError}</p>}
    <label>{t.reason}<textarea rows={2} value={draft.reason} onChange={(e) => setDraft((d) => ({ ...d, reason: e.target.value }))} /></label>
    {editorTemplateError && sourceBad && <p role="alert">{editorTemplateError}</p>}{sourceBad && !rebuilding && <button type="button" disabled={busy || !recovery || editorSourcesLoading || editorTemplateLoading || editorChoicesLoading || editorChoicesBlocked || !(revision.snapshot?.manifest.period || (revision.configuration?.starts_on && revision.configuration.ends_on)) || !!editorSourcesError} onClick={onBeginRebuild}>{tr(language, "Kontroller og bygg nytt kildegrunnlag", "Kontroller og bygg nytt kjeldegrunnlag")}</button>}{rebuilding && <fieldset><legend>{tr(language, "Nåværende kilder i rapportperioden", "Gjeldande kjelder i rapportperioden")}</legend>{editorSourcesError && <p role="alert">{editorSourcesError}</p>}{editorSources.map((source) => { const key = refKey(source.reference); return <label key={key}><input type="checkbox" checked={draft.sources.some((ref) => refKey(ref) === key)} onChange={(e) => setDraft((d) => ({ ...d, sources: e.target.checked ? [...d.sources, source.reference] : d.sources.filter((ref) => refKey(ref) !== key), sections: d.sections.map((section) => ({ ...section, sources: e.target.checked ? section.sources : section.sources.filter((sourceKey) => sourceKey !== key) })) }))} />{source.label} · {source.occurred_at.slice(0, 10)}</label>; })}</fieldset>}
    {rebuilding && <RecoveryChoices draft={draft} setDraft={setDraft} choices={editorChoices} language={language} />}
    <div className="documents-actions"><button type="button" disabled={busy || replacementInvalid || (sourceBad && !rebuilding) || (!revision.content && !rebuilding) || (rebuilding && (!recovery || editorSourcesLoading || editorChoicesLoading || editorChoicesBlocked || !!editorSourcesError || !draft.owner_id || (doc.kind === "guardian_email" && !draft.recipientIds.length)))} onClick={onRevise}>{rebuilding ? tr(language, "Lagre ny revisjon med gjeldende kilder", "Lagre ny revisjon med gjeldande kjelder") : t.newRevision}</button><button type="button" disabled={busy || sourceBad || doc.state === "approved" || doc.state === "discarded"} onClick={() => onTransition("review")}>{t.submit}</button>{doc.state === "in_review" && <button type="button" disabled={busy || sourceBad} onClick={() => onTransition("approve")}>{t.approve}</button>}{doc.state === "approved" && <button type="button" disabled={busy} onClick={() => onTransition("recall")}>{t.recall}</button>}</div>
  </article>;
}

function RecoveryChoices({ draft, setDraft, choices, language }: { draft: Draft; setDraft: (update: (d: Draft) => Draft) => void; choices: Record<string, PickerChoice[]>; language: "nb" | "nn" }) {
  return <fieldset><legend>{tr(language, "Gjeldende valg for nytt grunnlag", "Gjeldande val for nytt grunnlag")}</legend>
    <p>{tr(language, "Tidligere kilder, bakgrunn, mål, leveranser og framtidige planer er fjernet fra dette utkastet. Velg grunnlaget på nytt. Et tomt evidensgrunnlag lagres med synlige avklaringsbehov; det dokumenterer ingen framgang.", "Tidlegare kjelder, bakgrunn, mål, leveransar og framtidige planar er fjerna frå dette utkastet. Vel grunnlaget på nytt. Eit tomt evidensgrunnlag blir lagra med synlege avklaringsbehov; det dokumenterer ingen framgang.")}</p>
    <label>{tr(language, "Ansvarlig for nytt grunnlag", "Ansvarleg for nytt grunnlag")}<select value={draft.owner_id} onChange={(e) => setDraft((d) => ({ ...d, owner_id: e.target.value }))}><option value="">{tr(language, "Velg ansvarlig", "Vel ansvarleg")}</option>{(choices.owners as StaffChoice[] ?? []).map((owner) => <option key={owner.user_id} value={owner.user_id}>{owner.display_name}</option>)}</select></label>
    {draft.kind === "guardian_email" && <fieldset><legend>{tr(language, "Foresatte for nytt utkast", "Føresette for nytt utkast")}</legend>{(choices.guardians as GuardianChoice[] ?? []).filter((guardian) => guardian.state === "eligible_proposal").map((guardian) => <label key={guardian.relationship_id}><input type="checkbox" checked={draft.recipientIds.includes(guardian.relationship_id)} onChange={(e) => setDraft((d) => ({ ...d, recipientIds: e.target.checked ? [...d.recipientIds, guardian.relationship_id] : d.recipientIds.filter((id) => id !== guardian.relationship_id) }))} />{guardian.display_name}</label>)}</fieldset>}
    {!!choices.obligations?.length && <label>{tr(language, "Gjeldende rapportplikt", "Gjeldande rapportplikt")}<select value={draft.obligation_id} onChange={(e) => setDraft((d) => ({ ...d, obligation_id: e.target.value }))}><option value="">{tr(language, "Plikten må avklares", "Plikta må avklarast")}</option>{(choices.obligations as ObligationChoice[]).filter((obligation) => obligation.state === "applicable").map((obligation) => <option key={obligation.obligation_id} value={obligation.obligation_id}>{obligation.label}</option>)}</select></label>}
    <fieldset><legend>{tr(language, "Historiske mål i perioden", "Historiske mål i perioden")}</legend>{(choices.goals as GoalChoice[] ?? []).map((goal) => <label key={goal.goal_revision_id}><input type="checkbox" checked={draft.goals.some((value) => value.goal_revision_id === goal.goal_revision_id)} onChange={(e) => setDraft((d) => ({ ...d, goals: e.target.checked ? [...d.goals, { goal_revision_id: goal.goal_revision_id, applicable_at: goal.applicable_at }] : d.goals.filter((value) => value.goal_revision_id !== goal.goal_revision_id) }))} />{goal.title} · {goal.applicable_at.slice(0, 10)}</label>)}</fieldset>
    <fieldset><legend>{tr(language, "Gjennomførte leveranser i perioden", "Gjennomførte leveransar i perioden")}</legend>{(choices.actuals as ActualChoice[] ?? []).map((actual) => <label key={actual.delivery_revision_id}><input type="checkbox" checked={draft.actuals.includes(actual.delivery_revision_id)} onChange={(e) => setDraft((d) => ({ ...d, actuals: e.target.checked ? [...d.actuals, actual.delivery_revision_id] : d.actuals.filter((id) => id !== actual.delivery_revision_id) }))} />{actual.label} · {classificationLabel(language, actual.classification)}</label>)}</fieldset>
    <fieldset><legend>{tr(language, "Framtidige planer etter perioden", "Framtidige planar etter perioden")}</legend>{(choices.future_plans as FutureChoice[] ?? []).map((plan) => <label key={plan.session_revision_id}><input type="checkbox" checked={draft.futurePlans.includes(plan.session_revision_id)} onChange={(e) => setDraft((d) => ({ ...d, futurePlans: e.target.checked ? [...d.futurePlans, plan.session_revision_id] : d.futurePlans.filter((id) => id !== plan.session_revision_id) }))} />{plan.title} · {classificationLabel(language, plan.classification)}</label>)}</fieldset>
  </fieldset>;
}

function ContributionInbox({ client, schoolId, items, formatError, language }: { client: DocumentWorkspaceProps["client"]; schoolId: string; items: InboxItem[]; formatError: DocumentWorkspaceProps["formatError"]; language: "nb" | "nn" }) {
  const [selected, setSelected] = useState<InboxItem>();
  const [workspace, setWorkspace] = useState<ContributionWorkspace>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [citations, setCitations] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{ path: string[]; body: Record<string, unknown> }>();
  const [conflict, setConflict] = useState(false);
  const alive = useRef(true);
  const selectionGeneration = useRef(0);
  const currentDocument = useRef<string | undefined>(undefined);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function open(item: InboxItem) {
    const generation = ++selectionGeneration.current;
    currentDocument.current = item.document_id;
    setSelected(item); setLoading(true); setError(""); setBusy(false); setConflict(false); setWorkspace(undefined); setTexts({}); setCitations({});
    try { const saved = JSON.parse(sessionStorage.getItem(`documents-contribution:${clientKey(client)}:${schoolId}:${item.document_id}`) ?? "null"); setPending(Array.isArray(saved?.path) && saved?.body?.request_key ? saved : undefined); } catch { setPending(undefined); }
    try { const value = await client.schoolGet<ContributionWorkspace>(schoolId, ["documents", "cases", item.document_id, "contribution-workspace"]); if (alive.current && generation === selectionGeneration.current && currentDocument.current === item.document_id) { setWorkspace(value); setTexts(Object.fromEntries(value.assigned_sections.map((section) => [section.key, value.contributions.find((c) => c.section_key === section.key)?.text ?? ""]))); setCitations(Object.fromEntries(value.assigned_sections.map((section) => [section.key, value.contributions.find((c) => c.section_key === section.key)?.source_keys ?? section.source_keys]))); } }
    catch (e) { if (alive.current && generation === selectionGeneration.current && currentDocument.current === item.document_id) setError(formatError(e)); }
    finally { if (alive.current && generation === selectionGeneration.current && currentDocument.current === item.document_id) setLoading(false); }
  }
  async function submit(section: Section) {
    if (!workspace || !selected || !texts[section.key]?.trim() || busy) return;
    const selectedAtSubmit = selected;
    const generation = selectionGeneration.current;
    const isCurrent = () => alive.current && generation === selectionGeneration.current && currentDocument.current === selectedAtSubmit.document_id;
    const command = pending ?? { path: ["documents", "cases", selected.document_id, "contributions"], body: { request_key: crypto.randomUUID(), expected_version: workspace.version, revision_id: workspace.revision_id, section_key: section.key, kind: "submitted", text: texts[section.key], source_keys: citations[section.key] ?? [] } };
    setPending(command); setBusy(true); setError("");
    try { sessionStorage.setItem(`documents-contribution:${clientKey(client)}:${schoolId}:${selected.document_id}`, JSON.stringify(command)); } catch { /* Component state retains retry details. */ }
    try { await client.schoolCommand(schoolId, command.path, command.body); if (isCurrent()) { setPending(undefined); try { sessionStorage.removeItem(`documents-contribution:${clientKey(client)}:${schoolId}:${selectedAtSubmit.document_id}`); } catch { /* Storage is optional. */ } await open(selectedAtSubmit); } }
    catch (e) { if (isCurrent()) { setError(formatError(e)); if (e instanceof ApiError && e.status === 409) { setPending(undefined); try { sessionStorage.removeItem(`documents-contribution:${clientKey(client)}:${schoolId}:${selectedAtSubmit.document_id}`); } catch { /* Storage is optional. */ } setConflict(true); } else if (e instanceof ApiError && e.status > 0 && e.status < 500) { setPending(undefined); try { sessionStorage.removeItem(`documents-contribution:${clientKey(client)}:${schoolId}:${selectedAtSubmit.document_id}`); } catch { /* Storage is optional. */ } } } }
    finally { if (isCurrent()) setBusy(false); }
  }
  return <section className="documents-contributions"><h3>{tr(language, "Mine tildelte bidrag", "Mine tildelte bidrag")}</h3><ul>{items.map((item) => <li key={item.document_id}><button type="button" onClick={() => void open(item)}>{item.title} · {item.sections.map((section) => section.label).join(", ")}</button></li>)}</ul>
    {loading && <p role="status">{tr(language, "Henter tildelte seksjoner …", "Hentar tildelte seksjonar …")}</p>}{error && <div role="alert"><p>{error}</p>{pending && <button type="button" disabled={busy} onClick={() => void submit(workspace?.assigned_sections.find((s) => s.key === pending.body.section_key) ?? ({ key: String(pending.body.section_key) } as Section))}>{tr(language, "Prøv samme bidrag igjen", "Prøv same bidrag på nytt")}</button>}{conflict && selected && <button type="button" disabled={loading} onClick={() => void open(selected)}>{tr(language, "Hent nyeste revisjon og bruk bidraget manuelt på nytt", "Hent nyaste revisjon og bruk bidraget manuelt på nytt")}</button>}</div>}
    {workspace && selected && <div><p>{tr(language, "Du ser bare tildelte seksjoner. Hele dokumentet krever egen lesetillatelse. Kildestatus: ", "Du ser berre tildelte seksjonar. Heile dokumentet krev eiga lesetilgang. Kjeldestatus: ")}{statusLabel(language, workspace.source_status.state)}</p>{workspace.source_status.state === "current" ? workspace.assigned_sections.map((section) => <fieldset key={section.key}><legend>{section.key}</legend><label>{tr(language, "Bidragstekst", "Bidragstekst")}<textarea rows={4} value={texts[section.key] ?? ""} onChange={(e) => setTexts((old) => ({ ...old, [section.key]: e.target.value }))} /></label><div>{workspace.sources.map((source) => <label className="document-source-choice" key={source.key}><input type="checkbox" checked={(citations[section.key] ?? []).includes(source.key)} onChange={(e) => setCitations((old) => ({ ...old, [section.key]: e.target.checked ? [...(old[section.key] ?? []), source.key] : (old[section.key] ?? []).filter((key) => key !== source.key) }))} />{String(source.value.title ?? source.value.content ?? source.reference.kind)} · {source.reference.kind}</label>)}</div><button type="button" disabled={busy || !texts[section.key]?.trim()} onClick={() => void submit(section)}>{tr(language, "Lever bidrag til denne seksjonen", "Lever bidrag til denne seksjonen")}</button></fieldset>) : <p role="alert">{tr(language, "Kildegrunnlaget er endret. Bidragsteksten holdes tilbake fram til ny kontroll.", "Kjeldegrunnlaget er endra. Bidragsteksten blir halden tilbake til ny kontroll.")}</p>}</div>}
  </section>;
}
