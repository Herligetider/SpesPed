"""Render the editable planning registries as Markdown and validate their references."""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

def read(name):
    return json.loads((DOCS / name).read_text())

sources = read("sources.json")
features = read("features.json")
requirements = read("legal-requirements.json")
source_by_id = {s["id"]: s for s in sources}
feature_by_id = {f["id"]: f for f in features}
assert len(source_by_id) == len(sources)
assert len(feature_by_id) == len(features)
assert len({r["id"] for r in requirements}) == len(requirements)
for r in requirements:
    assert r["featureIds"] and r["sourceIds"], r["id"]
    assert all(f in feature_by_id for f in r["featureIds"]), r["id"]
    assert all(s in source_by_id for s in r["sourceIds"]), r["id"]
    assert r["legalReviewed"] is False

def clean(value):
    return str(value).replace("|", "\\|").replace("\n", " ")

def source_links(ids):
    return "; ".join(f'[{s}: {source_by_id[s]["title"]}]({source_by_id[s]["url"]})' for s in ids)

legal = """# Lovkrav og funksjonsdekning – grunnskolen

Kartlagt 7. september 2026. Arbeidsversjon 0.1. Omfatter offentlige grunnskoler og private montessoriskoler med statstilskudd, 1.–10. trinn. Andre private skoler har en separat betinget profil.

Dette er et kildebelagt produkt- og kravregister, ikke en juridisk godkjenning av en ferdig løsning. Kildedatoen betyr at kilden ble kontrollert i denne kartleggingen; den er ikke en ikrafttredelsesdato. Skolens konkrete kommunale forskrifter, godkjenning, delegering, arkivplan og avtaler er ikke mottatt. Registeret kan derfor ikke betegnes som en uttømmende bekreftelse på alle plikter ved en bestemt skole.

## Slik leses registeret

O = opplæringslova. P = privatskolelova. OF = opplæringsforskrifta. PF = privatskoleforskrifta. F-numrene viser til [funksjonskatalogen](02-feature-catalog.no.md). Hver funksjon har et domene og en implementasjonsfase i [sporbarhetsmatrisen](06-traceability.md).

Alle lovkrav får **delstøtte** fra programmet: dokumentutkast, kildekontroll, oppgaver, frister, tilgang eller integrasjon. Konkrete mekaniske oppgaver kan automatiseres helt. Juridisk myndighet, faglige vurderinger, samtaler, undervisning og fysiske tiltak blir hos mennesker. En ferdig rapport viser ikke alene at en rettighet er oppfylt.

«Dokumentasjon/handling» beskriver hva plikten retter seg mot. Det er ikke et krav om at alt skal skrives i vårt system. Dokumentasjon som allerede finnes i skolens autoritative system, bør gjenbrukes eller refereres. Samtykke til ITO, tillatelse til en bestemt deling og GDPR-behandlingsgrunnlag skal modelleres separat.

## Anvendelse og regelvedlikehold

En nasjonal regel må vurderes mot skoleslag, godkjenning, trinn, fagets avslutningstidspunkt, elevens vedtak, relevant dato og lokal forskrift. Ukjent informasjon gir status **uavklart**, aldri automatisk «ikke relevant». Lagre hjemmel, kildeversjon, vurdert gyldighet, ansvarlig regelredaktør og godkjenningsdato. Forslag fra AI eller endrede nettsider blir en oppgave for regelredaktøren; de endrer ikke gjeldende regelpakke automatisk.

Kravområdene L079–L090 er bevisst markert som områder som trenger mer konkret rettslig eller lokal spesifisering. De inngår i produktomfanget, men er ikke ferdige maskinregler. Alle rader er fortsatt uten juridisk signering.

## Kildekonflikter og endringer som påvirker designet

- Godkjente Montessori-unntak er knyttet til skolens ordning. Vedtak fra 2023 viser eldre forskriftsnumre; nåværende bestemmelse og godkjenning må knyttes sammen.
- Halvårsvurdering uten karakter er ikke automatisk en plikt til en skriftlig halvårsrapport. Ukesoppdatering og ettminuttsnotat er produktvalg.
- Gjeldende lovstruktur bruker O § 3-6 for særskilt språkopplæring. Enkelte veiledninger og henvisninger bruker andre/eldre numre; aktiv lovtekst må styre regelpakken.
- Skolebyttereglene er endret fra august 2026. Eldre veiledning om deling bare med tillatelse beskriver ikke alle nåværende situasjoner.
- Arkivregelverket er endret fra januar 2026. Ingen universell oppbevaringsfrist eller automatisk regel om «Noark for alle» er fastsatt her.
- Den vedtatte nye forvaltningsloven og norsk gjennomføring av KI-reglene må håndteres med eksplisitt ikrafttredelseskontroll. Høringer, planer og pressemeldinger er ikke selv operative lovregler.

"""
groups = defaultdict(list)
for r in requirements:
    groups[r["category"]].append(r)
for group, items in groups.items():
    legal += f"## {group}\n\n"
    legal += "| ID / krav og grunnlag | Hvem og når | Dokumentasjon/handling | Programstøtte | Menneskelig ansvar / status |\n|---|---|---|---|---|\n"
    for r in items:
        fs = "; ".join(f'{f} {feature_by_id[f]["title"]}' for f in r["featureIds"])
        cols = [f'**{r["id"]} {r["title"]}**<br>{r["basis"]}<br>{source_links(r["sourceIds"])}',
                f'{r["applicability"]}<br>Ansvar: {r["owner"]}<br>{r["trigger"]}',
                r["documentation"], fs,
                f'{r["humanResponsibility"]}<br>{r["verification"]}']
        legal += "| " + " | ".join(clean(c) for c in cols) + " |\n"
    legal += "\n"
legal += """## Å lukke kartleggingen for en konkret skole

Skoleeier utpeker ansvarlig for juridisk vurdering og regelvedlikehold. Gå gjennom registeret sammen med skoleledelse, pedagoger, personvern-/arkivfunksjon og vedtaksmyndighet. Hvert krav får anvendelse, kildestøttet frist, dokumentklasse, myndighet, mottakerregel og bevaringsregel. Marker begrunnede unntak, legg til lokale krav og registrer hvem som godkjente tolkningen. En funksjon som avhenger av en uavklart regel, kan brukes som manuelt arbeidsverktøy, men skal ikke vise lovmessig samsvar eller ta avgjørelser på det grunnlaget.

## Frister skal ha riktig betydning

«Årlig» må få en lokal planlagt dato. «Uten ugrunnet opphold» eller «straks» skal ikke oversettes til en vilkårlig standardfrist som gir tillatelse til å vente. GDPR-frister beregnes fra riktig hendelse med lovlige unntak. Klagefrist for enkeltvedtak skal ikke brukes for sluttvurdering, innsyn eller skolemiljøsaker. Obligasjonsmotoren lagrer både lovens tidsregel og skolens tidligere interne påminnelsesdato.
"""
(DOCS / "01-legal-matrix.no.md").write_text(legal)

feature_doc = """# Funksjonskatalog

Alle foreslåtte funksjoner er med. Fase angir rekkefølge, ikke at senere funksjoner er fjernet. Produktmålet og dokumenttypene er beskrevet i [produktgrunnlaget](00-product-brief.no.md). BC-numrene viser til den engelske [domenemodellen](04-domain-model.en.md).

Første versjon av ukesoppdatering går bare til foresatte med relevant informasjonsrett. Elevtilpasset mottak inngår senere. Offentlige rapporter og lovpålagt informasjon til eleven har egne mottakerregler og blir ikke begrenset av dette produktvalget.

"""
for f in features:
    links = [r["id"] for r in requirements if f["id"] in r["featureIds"]]
    feature_doc += f'## {f["id"]} {f["title"]}\n\n{f["description"]}\n\nDomene: {f["context"]}. Første leveranse: {f["phase"]}. Kravkoblinger: {", ".join(links) or "Produktmål; ingen særskilt lovplikt"}.\n\n'
(DOCS / "02-feature-catalog.no.md").write_text(feature_doc.rstrip() + "\n")

trace = """# Traceability: obligations → capabilities → contexts → phases

This is a planning map, not evidence of implemented compliance. P0–P8 are defined in the implementation plan. A feature's first delivery phase does not mean every extension is complete in that phase. Later extensions and their release gates are explicit in that plan.

| Capability | Legal requirement / area IDs | Owning context | First delivery phase |\n|---|---|---|---|\n"""
for f in features:
    ids = ", ".join(r["id"] for r in requirements if f["id"] in r["featureIds"])
    trace += f'| {f["id"]} {f["title"]} | {ids or "Product requirement"} | {f["context"]} | {f["phase"]} |\n'
(DOCS / "06-traceability.md").write_text(trace)

catalog = "# Kilder / Sources\n\nKontrolldato: 7. september 2026. Lovtekst, veiledning, godkjenning, forarbeid og produktmetode er merket separat. Enkelte lovsider var utilgjengelige i fulltekst; tilgjengelige Udir-gjengivelser og primære myndighetskilder er brukt. Forarbeid/statuskilder brukes ikke alene som operative regler. Se lovregisterets avklaringspunkter.\n\n"
catalog += "| ID | Kilde | Type | Kontrollert |\n|---|---|---|---|\n"
for s in sources:
    catalog += f'| {s["id"]} | [{s["title"]}]({s["url"]}) | {s["type"]} | {s["checked"]} |\n'
(DOCS / "07-sources.md").write_text(catalog)
print(f"Rendered 4 Markdown documents; validated {len(requirements)} requirements, {len(features)} features, {len(sources)} sources.")
