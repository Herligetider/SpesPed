import { useCallback, useEffect, useRef, useState } from "react";
import type { GuardianPortalProps, GuardianGrant, GuardianPayload } from "./types";
import "./guardian.css";

const copy = {
  nb: { heading: "Brev fra skolen", intro: "Her finner du sikre brev som skolen har delt med deg.", loading: "Henter brev …", error: "Brevene kunne ikke hentes.", empty: "Du har ingen tilgjengelige brev nå.", reload: "Oppdater", older: "Eldre brev", newer: "Nyere brev", open: "Åpne brev", opened: "Brevet er åpnet for denne økten.", opening: "Åpner …", unavailable: "Dette brevet er ikke lenger tilgjengelig. Innhold og vedlegg er fjernet.", generic: "Innholdet kunne ikke vises. Prøv å oppdatere listen.", expired: "Økten eller tilgangen er utløpt. Logg inn på nytt for å fortsette.", date: "Mottatt", expires: "Tilgjengelig til", attachment: "Vedlegg", download: "Last ned", ack: "Bekreft lest", ackDone: "Du har bekreftet at brevet er lest.", ackError: "Bekreftelsen kunne ikke lagres. Prøv igjen.", retry: "Prøv samme handling igjen", stale: "Brevet er endret eller tilgangen er trukket tilbake. Oppdater listen før du åpner det igjen.", close: "Lukk brev", status: "Status", revoked: "Tilgang trukket tilbake", active: "Tilgjengelig", noSubject: "Melding fra skolen", downloadError: "Vedlegget kunne ikke lastes ned. Det kan være utilgjengelig.", size: "bytes" },
  nn: { heading: "Brev frå skulen", intro: "Her finn du sikre brev som skulen har delt med deg.", loading: "Hentar brev …", error: "Breva kunne ikkje hentast.", empty: "Du har ingen tilgjengelege brev no.", reload: "Oppdater", older: "Eldre brev", newer: "Nyare brev", open: "Opne brev", opened: "Brevet er opna for denne økta.", opening: "Opnar …", unavailable: "Dette brevet er ikkje lenger tilgjengeleg. Innhald og vedlegg er fjerna.", generic: "Innhaldet kunne ikkje visast. Prøv å oppdatere lista.", expired: "Økta eller tilgangen er utløpt. Logg inn på nytt for å halde fram.", date: "Motteke", expires: "Tilgjengeleg til", attachment: "Vedlegg", download: "Last ned", ack: "Stadfest lese", ackDone: "Du har stadfesta at brevet er lese.", ackError: "Stadfestinga kunne ikkje lagrast. Prøv igjen.", retry: "Prøv same handling igjen", stale: "Brevet er endra eller tilgangen er trekt tilbake. Oppdater lista før du opnar det igjen.", close: "Lukk brev", status: "Status", revoked: "Tilgang trekt tilbake", active: "Tilgjengeleg", noSubject: "Melding frå skulen", downloadError: "Vedlegget kunne ikkje lastast ned. Det kan vere utilgjengeleg.", size: "byte" },
};
const PAGE_SIZE = 20;
let nextRequest = 1;
function requestKey() { return `guardian-${Date.now()}-${nextRequest++}`; }
const clients = new WeakMap<object, number>();
let nextClient = 1;
function clientKey(client: object) { let key = clients.get(client); if (!key) { key = nextClient++; clients.set(client, key); } return key; }
function isWithheld(error: unknown) { return typeof error === "object" && error !== null && "status" in error && [403, 404, 409, 410].includes(Number((error as { status: unknown }).status)); }
function dateLabel(value: string, timezone: string, language: "nb" | "nn") {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  const locales = language === "nn" ? ["nn-NO", "nb-NO"] : ["nb-NO"];
  const supported = Intl.DateTimeFormat.supportedLocalesOf(locales);
  const preferred = supported.length ? supported : ["nb-NO"];
  return new Intl.DateTimeFormat(preferred, { dateStyle: "long", timeStyle: "short", timeZone: timezone }).format(date);
}
function safeName(value: string) {
  const leaf = value.replace(/\\/g, "/").split("/").pop() ?? "vedlegg";
  const safe = leaf.replace(/[\u0000-\u001f\u007f]/g, "").replace(/[^\p{L}\p{N} ._()-]/gu, "_").trim().replace(/^\.+/, "").slice(0, 160);
  return safe || "vedlegg";
}
export default function GuardianPortal(props: GuardianPortalProps) {
  return <Scoped key={`${clientKey(props.client)}:${props.schoolId}:${props.currentUser.id}`} {...props} />;
}
function Scoped(props: GuardianPortalProps) {
  const t = copy[props.language];
  const [grants, setGrants] = useState<GuardianGrant[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [selected, setSelected] = useState<GuardianGrant | null>(null);
  const [payload, setPayload] = useState<GuardianPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [message, setMessage] = useState("");
  const [readConfirmed, setReadConfirmed] = useState(false);
  const [pending, setPending] = useState<{ kind: "open" | "read"; id: string; body: { expected_version: number; request_key: string } } | null>(null);
  const active = useRef(true);
  const scopeVersion = useRef(0);
  const operationVersion = useRef(0);
  const listVersion = useRef(0);
  const grantRef = useRef<GuardianGrant[]>([]);
  const selectedRef = useRef<GuardianGrant | null>(null);
  const pendingGrantRef = useRef<string | null>(null);
  const listRef = useRef<() => Promise<void>>(() => Promise.resolve());
  const clearPayload = useCallback(() => {
    scopeVersion.current++;
    operationVersion.current++;
    selectedRef.current = null;
    pendingGrantRef.current = null;
    setPayload(null); setReadConfirmed(false); setSelected(null); setMessage(""); setPending(null); setBusy(false);
  }, []);

  const load = useCallback(async (pageOffset = offset) => {
    const ticket = ++listVersion.current;
    setLoading(true); setLoadError("");
    try {
      const query = new URLSearchParams({ offset: String(pageOffset), limit: String(PAGE_SIZE) });
      const result = await props.client.schoolGet<{ items: GuardianGrant[]; total: number }>(props.schoolId, ["communication", "portal", "grants"], query);
      if (!active.current || ticket !== listVersion.current) return;
      const rows = Array.isArray(result.items) ? result.items : [];
      grantRef.current = rows; setGrants(rows); setTotal(result.total); setOffset(pageOffset);
      if (pageOffset === offset && (selectedRef.current || pendingGrantRef.current)) {
        const trackedId = selectedRef.current?.id ?? pendingGrantRef.current;
        const refreshed = rows.find((grant) => grant.id === trackedId);
        if (!refreshed) clearPayload();
        else if (selectedRef.current) { selectedRef.current = refreshed; setSelected(refreshed); }
      }
    } catch (error) {
      if (!active.current || ticket !== listVersion.current) return;
      if (isWithheld(error)) { clearPayload(); setGrants([]); setTotal(0); setLoadError(Number((error as { status?: number }).status) === 401 ? t.expired : t.unavailable); }
      else setLoadError(props.formatError(error) || t.error);
    } finally { if (active.current && ticket === listVersion.current) setLoading(false); }
  }, [props.client, props.schoolId, props.formatError, offset, clearPayload, t.error, t.expired]);
  listRef.current = load;

  useEffect(() => {
    active.current = true;
    void listRef.current();
    const onFocus = () => { if (active.current) void listRef.current(); };
    window.addEventListener("focus", onFocus);
    return () => { active.current = false; listVersion.current++; window.removeEventListener("focus", onFocus); clearPayload(); };
  }, [clearPayload]);

  useEffect(() => {
    if (!selected) return;
    const expiresAt = new Date(selected.expires_at).getTime();
    if (!Number.isFinite(expiresAt)) return;
    const expire = () => { clearPayload(); setActionError(t.unavailable); void listRef.current(); };
    let timer = 0;
    const schedule = () => {
      const delay = expiresAt - Date.now();
      if (delay <= 0) expire();
      else timer = window.setTimeout(schedule, Math.min(delay, 2_147_000_000));
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, [selected, clearPayload, t.unavailable]);

  const runOpen = async (grant: GuardianGrant, retry = false) => {
    const body = retry && pending?.kind === "open" && pending.id === grant.id ? pending.body : { expected_version: grant.version, request_key: requestKey() };
    clearPayload();
    pendingGrantRef.current = grant.id;
    setPending({ kind: "open", id: grant.id, body }); setBusy(true); setActionError("");
    const currentScope = scopeVersion.current;
    const currentOperation = ++operationVersion.current;
    try {
      const opened = await props.client.schoolCommand<GuardianGrant>(props.schoolId, ["communication", "portal", "grants", grant.id, "open"], body);
      if (!active.current || currentScope !== scopeVersion.current) return;
      const fresh = await props.client.schoolGet<GuardianPayload>(props.schoolId, ["communication", "portal", "grants", grant.id, "payload"]);
      if (!active.current || currentScope !== scopeVersion.current) return;
      pendingGrantRef.current = null;
      selectedRef.current = opened; setSelected(opened); setPayload(fresh); setMessage(t.opened); setPending(null);
      grantRef.current = grantRef.current.map((item) => item.id === opened.id ? opened : item); setGrants(grantRef.current);
    } catch (error) {
      if (!active.current || currentScope !== scopeVersion.current) return;
      if (isWithheld(error)) { clearPayload(); setActionError(t.unavailable); setPending(null); void listRef.current(); }
      else if (error && typeof error === "object" && "status" in error && Number((error as { status: unknown }).status) === 401) { clearPayload(); setActionError(t.expired); setPending(null); setGrants([]); }
      else setActionError(props.formatError(error) || t.generic);
    } finally { if (active.current && currentOperation === operationVersion.current) setBusy(false); }
  };
  const runRead = async (retry = false) => {
    if (!selected) return;
    const body = retry && pending?.kind === "read" && pending.id === selected.id ? pending.body : { expected_version: selected.version, request_key: requestKey() };
    setPending({ kind: "read", id: selected.id, body }); setBusy(true); setActionError("");
    const currentScope = scopeVersion.current;
    const currentOperation = ++operationVersion.current;
    try {
      const updated = await props.client.schoolCommand<GuardianGrant>(props.schoolId, ["communication", "portal", "grants", selected.id, "read-receipt"], body);
      if (!active.current || currentScope !== scopeVersion.current) return;
      selectedRef.current = updated; setSelected(updated); setReadConfirmed(true); setMessage(t.ackDone); setPending(null);
      grantRef.current = grantRef.current.map((item) => item.id === updated.id ? updated : item); setGrants(grantRef.current);
    } catch (error) {
      if (!active.current || currentScope !== scopeVersion.current) return;
      if (isWithheld(error)) { clearPayload(); setActionError(t.unavailable); setPending(null); void listRef.current(); }
      else if (error && typeof error === "object" && "status" in error && Number((error as { status: unknown }).status) === 401) { clearPayload(); setActionError(t.expired); setPending(null); }
      else setActionError(props.formatError(error) || t.ackError);
    } finally { if (active.current && currentOperation === operationVersion.current) setBusy(false); }
  };
  const download = async (attachment: GuardianPayload["attachments"][number]) => {
    if (!selected || !payload) return;
    setActionError(""); setBusy(true); const currentScope = scopeVersion.current; const currentOperation = ++operationVersion.current;
    try {
      const blob = await props.client.schoolBlob(props.schoolId, ["communication", "portal", "grants", selected.id, "attachments", attachment.id]);
      if (!active.current || currentScope !== scopeVersion.current) return;
      const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = safeName(attachment.filename); anchor.rel = "noopener"; document.body.append(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (error) {
      if (!active.current || currentScope !== scopeVersion.current) return;
      if (isWithheld(error)) { clearPayload(); setActionError(t.unavailable); void listRef.current(); }
      else if (error && typeof error === "object" && "status" in error && Number((error as { status: unknown }).status) === 401) { clearPayload(); setActionError(t.expired); setGrants([]); }
      else setActionError(props.formatError(error) || t.downloadError);
    } finally { if (active.current && currentOperation === operationVersion.current) setBusy(false); }
  };
  const close = () => { clearPayload(); setPending(null); setActionError(""); };

  return <section className="guardian-portal" aria-labelledby="guardian-heading">
    <header><h1 id="guardian-heading">{t.heading}</h1><p>{t.intro}</p></header>
    <div className="guardian-toolbar"><button type="button" onClick={() => void load(offset)} disabled={loading}>{t.reload}</button></div>
    {loading && <p role="status" aria-live="polite">{t.loading}</p>}
    {loadError && <p className="guardian-error" role="alert">{loadError}</p>}
    {!loading && !loadError && grants.length === 0 && <p role="status">{t.empty}</p>}
    {grants.length > 0 && <ul className="guardian-list" aria-label={t.heading}>{grants.map((grant) => <li key={grant.id}>
      <div><strong>{t.noSubject}</strong><p>{t.date}: <time dateTime={grant.created_at}>{dateLabel(grant.created_at, props.timezone, props.language)}</time></p><p>{t.expires}: <time dateTime={grant.expires_at}>{dateLabel(grant.expires_at, props.timezone, props.language)}</time></p><p>{t.status}: {grant.state === "active" ? t.active : t.revoked}</p></div>
      <button type="button" onClick={() => void runOpen(grant)} disabled={busy || grant.state !== "active"}>{busy && pending?.kind === "open" && pending.id === grant.id ? t.opening : t.open}</button>
    </li>)}</ul>}
    {total > PAGE_SIZE && <nav className="guardian-pagination" aria-label={props.language === "nb" ? "Sidenavigasjon" : "Sidenavigasjon"}><button type="button" onClick={() => void load(Math.max(0, offset - PAGE_SIZE))} disabled={loading || offset === 0}>{t.newer}</button><span>{offset + 1}–{Math.min(offset + grants.length, total)} / {total}</span><button type="button" onClick={() => void load(offset + PAGE_SIZE)} disabled={loading || offset + grants.length >= total}>{t.older}</button></nav>}
    {actionError && <p role="alert" className="guardian-error">{actionError}{pending && <button type="button" onClick={() => pending.kind === "open" ? void runOpen(grants.find((item) => item.id === pending.id) ?? { id: pending.id, version: pending.body.expected_version, state: "active", created_at: "", expires_at: "" }, true) : void runRead(true)} disabled={busy}>{t.retry}</button>}</p>}
    {selected && payload && <section className="guardian-letter" aria-labelledby="guardian-letter-heading">
      <div className="guardian-letter-heading"><h2 id="guardian-letter-heading">{payload.subject || t.noSubject}</h2><button type="button" onClick={close}>{t.close}</button></div>
      <div className="guardian-letter-body">{payload.body}</div>
      {payload.attachments.length > 0 && <section aria-label={t.attachment}><h3>{t.attachment}</h3><ul>{payload.attachments.map((attachment) => <li key={attachment.id}><span>{safeName(attachment.filename)} ({attachment.size_bytes} {t.size})</span><button type="button" onClick={() => void download(attachment)} disabled={busy}>{t.download}</button></li>)}</ul></section>}
      <div className="guardian-receipt"><button type="button" onClick={() => void runRead()} disabled={busy || readConfirmed}>{readConfirmed ? t.ackDone : t.ack}</button><span role="status" aria-live="polite">{message}</span></div>
    </section>}
  </section>;
}
