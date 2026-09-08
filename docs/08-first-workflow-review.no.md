# Første komplette arbeidsflyt – til faglig gjennomgang

Arbeidsversjon 0.2 · 8. september 2026. Dette er en foreslått arbeidsflyt som skal vurderes av domenefagperson, ikke en implementert løsning eller en allerede gjennomført brukertest.

Målet er at pedagogen kan bruke informasjon skolen allerede har til å forberede en konkret økt, gi assistenten nødvendig veiledning og registrere et kort resultat som gjør neste økt enklere å planlegge.

**Første flyt:** relevant informasjon → bekreftet elev- og plangrunnlag → godkjent økt → assistentkort ved behov → faktisk gjennomføring → kort notat til neste økt.

E-post til foresatte er en senere, valgfri arbeidsflyt. Programmet skal kunne generere e-postutkast for et valgt tidsintervall, men den første pilotens nytte skal kunne vurderes uten at foreldrekommunikasjon er bygget.

## Forutsetninger og eksempel

- Skolen har definert tilgang, ansvar og relevante behandlings-/dokumentregler i P1.
- Utvikling og demonstrasjon bruker syntetiske data. Lokal AI-behandling og nødvendige produksjonskontroller må være klare før en AI-pilot med faktiske elevdata.
- I eksemplet har skolen allerede et vedtak og en godkjent IOP. Den første leveransen registrerer og bekrefter dette grunnlaget; generering av ny IOP kommer i P3.
- En lærer/spesialpedagog er faglig ansvarlig. En assistent kan få et avgrenset støtteoppdrag og nødvendig veiledning innenfor den ansvarlige pedagogens opplegg.
- Den fiktive eleven «Demo-elev 001» arbeider med et bekreftet lesemål. Klassen har et felles tema, og skolen har tilgjengelige bildekort. Dette er illustrasjon av produktatferd, ikke en anbefaling om tiltak for en faktisk elev.

For elever uten ITO kan flyten bruke ordinære bekreftede undervisningsmål. En IOP skal ikke være et generelt krav for å bruke øktplanleggingen.

## Forløpet, steg for steg

| Steg | Hva brukeren gjør | Hva programmet gjør | Hva som viser at steget virker |
|---|---|---|---|
| 1. Finn riktig elev | Pedagogen åpner sin elevoversikt og velger eleven | Viser aktiv tilknytning, nødvendig pedagogisk profil og relevante oppgaver | Andre elevers eller beskyttede sakers innhold blir ikke synlig gjennom søk eller lenker |
| 2. Legg inn grunnlaget | Laster opp eksisterende vedtak/IOP og legger inn et relevant notat eller en lagret e-post | Bevarer kilden, oppdager dubletter og foreslår elevkobling og dokumentfelt | Usikker elevkobling blir et avklaringspunkt, ikke et automatisk elevnotat |
| 3. Bekreft innholdet | Kontrollerer mål, rammer, gyldighet og relevante opplysninger ved siden av originalen | Lagrer bekreftede felt med kilde, versjon, avsender og dato | PPT-anbefaling og vedtaksramme er fortsatt atskilt; notatet beholder sitt faktiske opphav |
| 4. Bestill en økt | Velger mål, varighet, tema, arena og tilgjengelig materiell | Viser hvilke kilder som vil brukes og foreslår en konkret aktivitet med støtte og observasjonspunkt | Brukeren ser både begrunnelsen for forslaget og hvilket grunnlag som mangler |
| 5. Gjør økten brukbar | Redigerer aktivitet og støtte, velger tidspunkt manuelt og godkjenner | Bevarer brukerens redigeringer og den eksakte godkjente versjonen | Pedagogen kan gjennomføre planen uten å måtte oversette en generell AI-tekst til praktiske steg |
| 6. Gi assistenten veiledning | Velger støtteoppdrag, kontrollerer assistentkort og tildeler det | Viser mål i enkelt språk, materiell, tre–fem hovedsteg, avtalt forenkling og kontaktperson | Assistenten kan normalt forstå kortet innen fem minutter og får nødvendig veiledning i tillegg |
| 7. Registrer hva som skjedde | Bekrefter faktisk deltakelse, varighet og eventuell endring/avlysning | Skiller planlagt aktivitet, faktisk undervisning og assistentstøtte | En avlyst eller delvis gjennomført økt telles riktig, uten automatisk fullføring fra timeplanen |
| 8. Skriv kort notat | Registrerer en konkret observasjon og eventuelt neste steg | Kobler notatet til riktig elev, mål og gjennomføring med dato og forfatter | Et vanlig notat kan føres raskt og gjenbrukes uten at samme tekst må legges inn flere steder |
| 9. Forbered neste økt | Åpner neste planlegging | Viser den nye observasjonen som grunnlag sammen med aktive mål og øvrig relevant informasjon | Det er lett å videreføre eller justere opplegget; systemet hevder ikke mer mestring enn notatet støtter |

Steg 6 hoppes over når det ikke er et assistentoppdrag. Full automatisk timeplanlegging og gruppeoptimalisering kommer i P5. P2 skal støtte en praktisk manuell plassering av økten med bekreftede deltakere og ressurser.

## Konkret eksempel på innhold

Før økten foreligger et bekreftet notat: «Eleven leste tre av fem øvingsord med bildekort. Trengte støtte for å komme i gang.» Systemet må bevare både avsender og hva som faktisk ble observert.

Pedagogen velger et aktivt mål og 25 minutter. Et øktutkast kan foreslå en kort repetisjon, arbeid med kjent materiell og en avsluttende observasjon. Pedagogen avgjør hvilke ord, støttetrinn og tilpasninger som er faglig riktige før økten godkjennes.

Assistentkortet beskriver bare det konkrete støtteoppdraget: hva som skal ligge klart, hvordan avtalt støtte gis, hvilken forenkling pedagogen har valgt og hvem assistenten kontakter ved spørsmål. Kortet trenger ikke gjengi elevens sakkyndige vurdering eller andre familieopplysninger.

Etter økten registreres 20 faktiske minutter og et kort notat, for eksempel «Eleven startet etter én påminnelse og leste fire av de samme fem ordene med bildekort.» Programmet kan vise dette ved neste planlegging. Det skal ikke omskrive observasjonen til at eleven nå leser selvstendig eller har nådd målet.

## Avvik som må kunne håndteres

| Situasjon | Forventet atferd |
|---|---|
| Dokumentet kan gjelde to elever | Hold det i avgrenset innboks og krev bekreftet kobling før ordinær gjenbruk |
| Et dokument mangler eller er vanskelig å lese | Vis hva som mangler; tilby manuell registrering og faglig avklaring uten å finne på opplysninger |
| Vedtak eller IOP har uavklart gyldighet | Vis behovet for ansvarlig vurdering. Ikke endre eller stans elevens støtte automatisk, og ikke merk uavklarte rammer som bekreftet |
| Eleven har ikke ITO/IOP | Bruk ordinære mål for tilpasset undervisning; ikke krev et kunstig vedtak eller en IOP |
| AI foreslår for vanskelig eller lite egnet aktivitet | Pedagogen kan endre eller avvise forslaget uten å miste tidligere redigeringer |
| AI-tjenesten svarer ikke | Bevar arbeidet og tilby manuell planlegging når resten av systemet er tilgjengelig |
| Assistenten er usikker | Gjør kontaktperson og spørsmål lett tilgjengelig; åpning av kortet betyr ikke at assistenten har forstått oppdraget |
| Økten endres etter at kortet er godkjent | Marker relevant kort som utdatert og krev ny kontroll før det brukes som gjeldende instruksjon |
| Eleven er borte eller økten avlyses | Registrer faktisk årsak og eventuelt oppfølgingsansvar; ikke tell planlagt tid som gjennomført |
| Et notat viser seg å tilhøre feil elev | Rett koblingen, fjern feil operativ tilgang og vis hvilke forslag eller dokumenter som er berørt |
| Lagring får et uklart svar | Avklar om registreringen er lagret før et gjentatt forsøk skaper en ny økt eller et dobbelt notat |
| Vikarens eller assistentens oppdrag utløper | Trekk tilbake tilgang, også ved direkte lenker til et tidligere åpnet kort |

## Hva domenefagpersonen bes vurdere

1. Ligner denne flyten en konkret arbeidsoppgave dere vil spare tid på?
2. Hvilke opplysninger må pedagogen kontrollere før en økt, og hvilke felt er unødvendige?
3. Hva må stå i et øktopplegg for at det er praktisk brukbart ved skolen?
4. Er assistentoppdraget avgrenset riktig, og hvilken veiledning trengs i tillegg til kortet?
5. Er eksemplet på et kort notat tilstrekkelig for neste økt og senere evaluering?
6. Hvilke vesentlige avvik eller Montessori-spesifikke behov mangler?
7. Hva føres allerede i andre systemer og bør gjenbrukes?
8. Hvordan kan vi måle spart tid inkludert kontroll, retting og etterarbeid?

Tilbakemeldinger kan merkes med stegnummer og funksjons-ID, for eksempel «Steg 6 / F13: kortet må også vise hvor materiellet oppbevares». Funksjonskatalogen har et eget spørsmål og konkrete akseptansekriterier per funksjon.

## Senere arbeidsflyt: e-post for en valgt periode

I P4 velger pedagogen elev, formål og fra-/til-dato, for eksempel 1.–20. oktober. Begge dager inngår, og de faktiske datoene vises også når en snarvei brukes. Programmet foreslår relevant innhold og lager et redigerbart emne og en brødtekst med intern kildevisning.

Brukeren gjennomgår teksten, velger mottakerspesifikt innhold og godkjenner før eventuell uttrykkelig utsending gjennom skolens tillatte kanal. Et sent registrert notat, ny periode eller endret tekst krever vurdering av en ny revisjon. En tom periode skal ikke gi oppdiktet fremgang.

Skolen kan velge gjentakelse av utkast, for eksempel hver 14. dag eller månedlig, med egen ansvarlig, periodeavgrensning og mulighet for pause. Gjentakelse er avslått som utgangspunkt og gir aldri forhåndsgodkjenning av fremtidige brev. En fast ukentlig e-post er ikke prioritert.

Se [F20 i funksjonskatalogen](02-feature-catalog.no.md#f20), [ES07 i event storming](03-event-storming.en.md) og [P4 i implementasjonsplanen](05-implementation-plan.en.md).
