# Funksjonskatalog

Arbeidsversjon 0.3 · 21. oktober 2026. Alle 40 funksjonsområder er beholdt og konkretisert for faglig gjennomgang. Denne revisjonen utdyper arbeidsflater, statusendringer, automatikk og håndtering av mangler. Beskrivelsene er produktkrav, ikke en bekreftelse på implementerte funksjoner eller en ny juridisk kontroll. Akseptansekriteriene beskriver observerbar atferd som en leveranse senere skal verifiseres mot.

Første komplette arbeidsflyt prioriterer innsamling → bekreftet elev-/plangrunnlag → undervisningsøkt → assistentkort → faktisk gjennomføring og kort notat. [Arbeidsflyten for faglig gjennomgang](08-first-workflow-review.no.md) viser et konkret eksempel og avvik som må fungere.

F20 støtter e-postutkast til foresatte for et valgt tidsintervall og valgfri gjentakelse av utkast. En fast ukerytme er ikke prioritert eller aktivert som standard. Foreldre-e-post ligger i P4 og er ikke nødvendig for første pilotflyt. Første versjon av denne kommunikasjonen går bare til foresatte med relevant informasjonsrett. Elevtilpasset mottak inngår senere; lovpålagt informasjon til eleven har egne mottakerregler.

Hver funksjon beskriver brukere, inndata, arbeidsflate, arbeidssteg, statusendringer, automatikk og menneskelige valg, håndtering av feil, resultat, regler, akseptansekriterier og et eksempel. Arbeidsflaten beskriver hva brukeren skal se og gjøre; endelig visuell utforming avklares med fagpersonene. Statusbeskrivelsene er faglige begreper, ikke låste tekniske feltnavn. Avhengigheter viser funksjoner som må bidra med relevant grunnstøtte, ikke at alle deres senere utvidelser må være ferdige først. «Første leveranse» avgrenser hva fasen faktisk skal inneholde; hele beskrivelsen dekker også senere utvidelser.

Produktmålet og dokumenttypene finnes i [produktgrunnlaget](00-product-brief.no.md). BC-numrene viser til [domenemodellen](04-domain-model.en.md), og fasene til [implementasjonsplanen](05-implementation-plan.en.md). Generelle krav til tilgang, kilder, menneskelig kontroll og manuell reserve gjelder på tvers av funksjonene.

## Til den som gjør faglig gjennomgang

Les først arbeidsflyten og funksjonene F03–F08, F12–F16, F33 og F39–F40. Vurder om eksemplene ligner hverdagen, hva som mangler, hvilke felt som skaper merarbeid og hva som må endres i akseptansekriteriene. Prøv også å beskrive hva brukeren gjør når grunnlaget mangler eller noe feiler. Spørsmålet på slutten av hver funksjon er et konkret punkt til gjennomgangen, ikke et krav om å avklare alt før dokumentene kan leses.

Forslag til tilbakemelding: funksjons-ID → konkret situasjon → ønsket endring → hvorfor det sparer arbeid eller gir bedre kvalitet → nødvendig i første flyt eller senere. Detaljene gjelder hele funksjonens omfang og skal følges opp i implementasjonsjobbene; de eksisterende akseptansekriteriene er fortsatt eksempler, ikke hele kravlisten.

## Funksjonsoversikt

| ID | Funksjon | Første leveranse |
|---|---|---|
| [F01](#f01) | Skole, brukere og fullmakter | P1 |
| [F02](#f02) | Elevprofil og foresattrelasjoner | P1 |
| [F03](#f03) | Felles innboks for elevinformasjon | P2 |
| [F04](#f04) | Uttrekk med kildekontroll | P2 |
| [F05](#f05) | Elevtidslinje og retting | P2 |
| [F06](#f06) | Kravregister og årshjul | P1 |
| [F07](#f07) | Henvisning, sakkyndighet og vedtak | P2 |
| [F08](#f08) | IOP med mål og versjoner | P2 |
| [F09](#f09) | Læreplan og klassens planer | P3 |
| [F10](#f10) | Bibliotek for egne opplegg og materiell | P3 |
| [F11](#f11) | Kartlegging og målinger | P4 |
| [F12](#f12) | Planlegg neste undervisningsøkt | P2 |
| [F13](#f13) | Assistentkort og veiledning | P2 |
| [F14](#f14) | Automatisk timeplan og gruppeforslag | P5 |
| [F15](#f15) | Gjennomførte timer og avvik | P2 |
| [F16](#f16) | Rask øktlogg og diktering | P2 |
| [F17](#f17) | Fremgang og neste steg | P4 |
| [F18](#f18) | Lovpålagte elevdokumenter og rapporter | P4 |
| [F19](#f19) | Underveis-, halvårs- og sluttvurdering | P4 |
| [F20](#f20) | E-postutkast til foresatte for valgt tidsintervall | P4 |
| [F21](#f21) | Gjennomgang, godkjenning og sikker utsending | P4 |
| [F22](#f22) | Møter, samarbeid og individuell plan | P4 |
| [F23](#f23) | Fravær og oppfølging | P5 |
| [F24](#f24) | Skolemiljø og aktivitetsplan | P6 |
| [F25](#f25) | Bekymring, barnevern og akutt oppfølging | P6 |
| [F26](#f26) | Fysiske inngrep og forebygging | P6 |
| [F27](#f27) | Personvern, tilgang og innsyn | P1 |
| [F28](#f28) | Dokumentforvaltning og arkiv | P1 |
| [F29](#f29) | Ledelsesoversikt og internkontroll | P6 |
| [F30](#f30) | Offentlig rapportering og administrasjon | P7 |
| [F31](#f31) | Tilgjengelighet og språk | P1 |
| [F32](#f32) | Integrasjoner og datautveksling | P7 |
| [F33](#f33) | AI med utskiftbar modell og kvalitetskontroll | P2 |
| [F34](#f34) | Drift, sikkerhet og beredskap | P1 |
| [F35](#f35) | Skoleår, overganger og skolebytte | P7 |
| [F36](#f36) | Ressurser og arbeidsbelastning | P5 |
| [F37](#f37) | Betingede leder- og driftsplikter | P7 |
| [F38](#f38) | Varsler, fritak, klager og partsrettigheter | P4 |
| [F39](#f39) | Tilbakemelding og kontroll av forslag | P2 |
| [F40](#f40) | Målbar avlastning | P2 |

<a id="f01"></a>

## F01 Skole, brukere og fullmakter

Skoleslag, godkjenning, trinn, skoleår, ansatte, kompetanse, elevtilknytning og tidsavgrenset stedfortreder. Skill rolle fra myndighet i en bestemt sak.

**Brukere:** Skoleadministrator, Rektor eller delegert leder.

**Når brukes den:** Ved oppstart, ansettelse, rollebytte eller vikariat.

### Inndata

- Skoleslag, eier, godkjenning, trinn og skoleår.
- Ansatte, kvalifikasjonsreferanser, elev-/sakstilknytning og fullmaktenes gyldighet.

### Arbeidsflate og handlinger

- Skoleoppsettet viser skoleslag, trinn, skoleår og om regelprofilen er avklart. Ansattlisten viser aktive oppdrag, fullmakter og utløpsdatoer; leder kan åpne én person og se den samlede tilgangen.
- Ved «Tildel oppdrag» velges konkrete elever eller saker, handlinger og gyldighetsperiode. Før lagring vises hvem og hvilket innhold tildelingen gjelder. Tilbakekalling krever ikke sletting av historikken.

### Slik fungerer det

1. Administrator oppretter skolen og velger en regelprofil som må bekreftes av ansvarlig person.
2. Leder knytter ansatte til grupper, elever eller saker og velger hvilke handlinger hver tilknytning tillater.
3. Et vikariat får start og slutt. Systemet viser virkningen før endringen lagres og trekker tilgangen tilbake når perioden utløper.

### Status og overganger

Tildelinger vises som kommende, aktive, utløpte eller tilbakekalte. En konto kan være aktiv selv om den ikke har et gyldig elevoppdrag. Uavklart godkjenningsmyndighet vises separat.

### Automatikk og menneskelige valg

Programmet beregner gyldighet og varsler om kommende utløp. Leder avgjør oppdrag, kvalifikasjoner og fullmakter; en ny stillingstittel gir ikke automatisk tilgang til alle elever.

### Når noe mangler eller feiler

Ved manglende myndighet vises ansvarlig avklaringsvei. Dersom en samtidig endring har påvirket oppdraget, må leder kontrollere den nye oversikten før sin endring lagres.

### Resultat

- Oversikt over bemanning, aktive tilganger, signeringsmyndighet og kommende utløp.

### Regler og avvik

- Rolle, tilgang til innhold og myndighet til å godkjenne er separate tildelinger.
- En teknisk administrator får ikke automatisk lesetilgang til elevdokumenter.

### Akseptansekriterier

- Et utløpt vikariat gir avslag ved åpning av både elevside, direkte dokumentlenke og bakgrunnsjobb.
- En lærer uten fullmakt kan bidra til et dokument, men kan ikke utføre den reserverte godkjenningshandlingen.

**Eksempel:** En vikar får tilgang til tre elever mandag–fredag og mister denne tilgangen lørdag uten manuell opprydding.

**Avhengigheter:** Ingen særskilte funksjonsavhengigheter.

**Første leveranse og utvidelser:** P1: grunnoppsett og manuelle tildelinger. F32 kobler senere til identitets- og personalsystemer.

**Til faglig gjennomgang:** Hvem tildeler tilgang og godkjenningsmyndighet ved pilotskolen?

Domene: BC01. Første leveranse: P1. Kravkoblinger: L013, L014, L036, L057, L058, L074, L081, L089, L090.

<a id="f02"></a>

## F02 Elevprofil og foresattrelasjoner

Styrker, interesser, språk, kommunikasjon og støtte som virker. Foreldreansvar, bosted, representasjon, begrensninger og informasjonsrett registreres med kilde og gyldighet.

**Brukere:** Kontaktlærer, Spesialpedagog, Autorisert administrasjon.

**Når brukes den:** Ved innskriving, forberedelse til undervisning eller endret familiesituasjon.

### Inndata

- Elevidentitet, innskriving, gruppe og kontaktopplysninger.
- Bekreftede styrker, interesser, språk og støttestrategier; kildebelagte foresattrelasjoner og begrensninger.

### Arbeidsflate og handlinger

- Elevsiden har en kort oversikt over styrker, interesser, kommunikasjon og støtte som virker, samt aktive mål og neste oppgave. Hver opplysning kan åpnes med kilde, dato og hvem som har bekreftet den.
- En egen fane viser foresattrelasjoner med gyldighet, kontaktmåte og uavklarte begrensninger for autoriserte ansatte. «Foreslå retting» lar lærer sende inn en endring uten å overskrive bekreftet informasjon.

### Slik fungerer det

1. Elevsiden viser først en kort pedagogisk oversikt og aktuelle oppgaver som brukeren har tilgang til.
2. Ansatte kan foreslå endringer i det pedagogiske innholdet med kilde og dato; ansvarlig person bekrefter vesentlige opplysninger.
3. Foresattrelasjoner forvaltes separat. Brukeren ser hvem som kan kontaktes, hvilke forhold som må avklares og gyldigheten til grunnlaget.

### Status og overganger

Profilopplysninger er foreslåtte, bekreftede, bestridte eller erstattede. Historiske verdier beholdes med dato, mens den korte oversikten viser gjeldende informasjon og synlige avklaringsbehov.

### Automatikk og menneskelige valg

Programmet samler allerede bekreftede opplysninger og fremhever motstrid. Fagperson avgjør hvilke støttestrategier som fortsatt gjelder; autorisert person avklarer foresattrelasjoner.

### Når noe mangler eller feiler

Ukjent familieforhold blir et avklaringspunkt. Elevens undervisningsplanlegging kan fortsette innenfor bekreftet tilgang, mens utlevering til en uavklart mottaker avventer kontroll.

### Resultat

- Oppdatert elevoversikt og mottakergrunnlag som andre funksjoner kan bruke.

### Regler og avvik

- Elevprofilen viser kilde og siste vurdering, og beholder motstridende opplysninger som uavklarte.
- Adresse, bosted og foreldreansvar er ikke alene en generell tillatelse til all utlevering.

### Akseptansekriterier

- En assistent ser nødvendig støtteinformasjon for sitt oppdrag, uten automatisk tilgang til sakkyndig vurdering eller familiesak.
- Endret foresattrelasjon blir tilgjengelig for ny mottakerkontroll før neste utsending.

**Eksempel:** Før en økt ser pedagogen at eleven foretrekker visuell støtte, hvem som bekreftet dette og når det sist ble vurdert.

**Avhengigheter:** [F01](#f01).

**Første leveranse og utvidelser:** P1: identitet, relasjoner og kort manuelt profilinnhold. Kildebasert sammensatt oversikt utvides i P2–P4.

**Til faglig gjennomgang:** Hvilke fem–ti opplysninger trenger personalet faktisk å se før en økt?

Domene: BC01. Første leveranse: P1. Kravkoblinger: L001, L003, L048, L070, L071, L072, L080.

<a id="f03"></a>

## F03 Felles innboks for elevinformasjon

Notater, e-post fra foresatte, vedlegg, PDF, Word, skannede dokumenter, rapporter og timeplaner. Først manuell import; senere godkjente e-post- og systemkoblinger. Ingen generell innhøsting av alle ansattes e-poster.

**Brukere:** Lærer, Spesialpedagog, Autorisert saksbehandler.

**Når brukes den:** Når et notat, en e-post eller et dokument skal knyttes til elevoppfølging.

### Inndata

- Fritekst, PDF, Word, skannede dokumenter, lagrede e-poster og vedlegg.
- Avsender, mottakstid, opprinnelig dato og foreslått elev dersom kjent.

### Arbeidsflate og handlinger

- Innboksen viser filnavn, kildetype, avsender, mottakstid, foreslått elev og behandlingstilstand. Brukeren kan opprette et notat, laste opp filer eller importere en lagret e-post med vedlegg.
- Ved åpning vises original og foreslått elevkobling. Brukeren kan dele relevant tekst i elevspesifikke utdrag, velge dokumenttype og sende materialet til kontroll uten å gjøre hele originalen synlig for elevteamet.

### Slik fungerer det

1. Brukeren skriver et notat eller laster opp en fil til en innboks med status mottatt, under behandling, må avklares eller ferdig.
2. Systemet kontrollerer filtype, skadelig innhold og mulige dubletter før dokumentlesing.
3. Brukeren vurderer elevkobling og avgrenser nødvendig innhold før materialet blir tilgjengelig i elevens ordinære arbeidsflate.

### Status og overganger

Hvert importelement viser mottatt, filkontroll pågår, karantene, klart for uttrekk, må avklares eller behandlet. En ferdig opplasting er ikke det samme som en bekreftet elevopplysning.

### Automatikk og menneskelige valg

Filkontroll og dublettsøk starter ved import. Systemet kan foreslå elevkobling, men en ansatt bekrefter tilordning og nødvendig innhold før ordinær gjenbruk.

### Når noe mangler eller feiler

Uleselig, passordbeskyttet eller ikke støttet fil får en konkret feilmelding og mulighet for ny kopi eller separat manuelt notat med kildehenvisning. Karanteneinnhold brukes ikke til forslag.

### Resultat

- Et bevart kildedokument, importstatus og en oppgave for kontroll i F04.

### Regler og avvik

- Filer med usikker elevkobling blir i en begrenset innboks; navnelikhet gir ikke automatisk tilgang.
- Automatisk e-postinnhenting aktiveres bare for avtalte kilder og filtre via F32.

### Akseptansekriterier

- Samme importerte e-post med samme kildeidentitet oppretter ikke to identiske oppfølgingspunkter.
- En e-post som omtaler søsken kan deles i kontrollerte utdrag uten å eksponere hele originalen for begge elevenes team.

**Eksempel:** En lærer laster opp en foresatt-e-post og får spørsmål om hvilken av to elever med samme fornavn opplysningen gjelder.

**Avhengigheter:** [F01](#f01), [F02](#f02), [F27](#f27), [F28](#f28).

**Første leveranse og utvidelser:** P2: notater og manuell fil-/e-postimport. Løpende koblinger og større importjobber kommer i P7.

**Til faglig gjennomgang:** Hvilke dokumenttyper og innkanaler står for mest dobbeltarbeid i dag?

Domene: BC02. Første leveranse: P2. Kravkoblinger: L012, L045, L049, L064.

<a id="f04"></a>

## F04 Uttrekk med kildekontroll

Dokumentlesing og OCR foreslår elevkobling, datoer, mål og tiltak. Bevar avsender, opprinnelig tekst, sidereferanse og hva som er påstand, observasjon eller vurdering. Feiltolkninger og dubletter håndteres.

**Brukere:** Lærer, Spesialpedagog, Dokumentansvarlig.

**Når brukes den:** Et nytt dokument er akseptert i innboksen, eller en tidligere tolking må rettes.

### Inndata

- Original dokumentversjon med tekst eller skannede sider.
- Forslag til elev, dokumenttype, datoer, mål, tiltak og oppfølgingspunkter.

### Arbeidsflate og handlinger

- Kontrollflaten viser original side eller tekstutdrag til venstre og foreslåtte felt til høyre. Feltet viser verdi, enhet, type opplysning og kilde; valg er «Godta», «Rett» og «Forkast».
- Brukeren kan filtrere på ubekreftede og motstridende felt og hoppe fra et felt til riktig kildeutsnitt. Opplysninger som ikke kan bekreftes får en avklaringsmerknad og ansvarlig.

### Slik fungerer det

1. Systemet viser originalen ved siden av foreslåtte felt og lar brukeren hoppe til relevant side eller tekstutdrag.
2. Brukeren godtar, retter eller forkaster hvert viktig uttrekk; uklar tekst merkes for manuell avklaring.
3. Bekreftede felt blir gjenbrukbare opplysninger med kobling til original, avsender og dokumentversjon.

### Status og overganger

Et felt går fra forslag til bekreftet, rettet eller forkastet; dokumentet kan være delvis gjennomgått. Uavklarte felt skal fortsatt være synlige når de øvrige brukes videre.

### Automatikk og menneskelige valg

OCR og AI foreslår struktur og kildekoblinger. Den ansatte kontrollerer faktainnhold, datoer, omfang og elevtilordning; teknisk lesesikkerhet erstatter ikke denne kontrollen.

### Når noe mangler eller feiler

Når kildeutsnitt mangler eller teksten er utydelig, kan feltet stå åpent eller fylles manuelt med synlig kilde og forbehold. Nytt uttrekk erstatter ikke tidligere bekreftede verdier uten gjennomgang.

### Resultat

- Bekreftet strukturert informasjon og en liste over åpne tolkningsspørsmål.

### Regler og avvik

- Et foreldresitat, en ansattobservasjon og en faglig vurdering beholder hver sin type og opphav.
- Innhold i importerte dokumenter behandles som data og kan ikke instruere programmet til å endre tilgang eller sende informasjon.

### Akseptansekriterier

- Feillesing av et timeantall kan rettes før det inngår i planlegging eller rapport.
- En bekreftet påstand kan åpnes med riktig kildeversjon og sidereferanse; manglende lesetilgang gir ikke innsyn via forhåndsvisning.

**Eksempel:** OCR foreslår 80 timer, men originalen viser 30. Pedagogen retter tallet og bekrefter hvilken vedtaksbestemmelse det tilhører.

**Avhengigheter:** [F03](#f03), [F33](#f33).

**Første leveranse og utvidelser:** P2: grunnleggende uttrekk og kontroll. Mer spesialiserte dokumentfelt legges til sammen med de aktuelle fagmodulene.

**Til faglig gjennomgang:** Hvilke felt må alltid kontrolleres manuelt, og hvilke kan presenteres som mindre kritiske forslag?

Domene: BC02. Første leveranse: P2. Kravkoblinger: L012, L045, L046.

<a id="f05"></a>

## F05 Elevtidslinje og retting

Søk i relevant, autorisert informasjon. Hendelsesdato og registreringsdato holdes adskilt. Innspill kan bestrides; nyere informasjon kan erstatte operative oppsummeringer med sporbar historikk.

**Brukere:** Elevens lærerteam, Spesialpedagog, Autorisert saksbehandler.

**Når brukes den:** Når noen trenger oversikt over et forløp, søker etter en opplysning eller oppdager feil.

### Inndata

- Bekreftede opplysninger og kildelenker.
- Hendelsesdato, registreringsdato, emne, måltilknytning og eventuell uenighet.

### Arbeidsflate og handlinger

- Tidslinjen har periodevalg og filtre for mål, tema, kilde og dokumenttype. Hvert element viser hendelsesdato, registreringsdato, avsender og opplysningstype, slik at en sen registrering kan forstås riktig.
- Detaljvisningen har «Åpne kilde», «Foreslå retting» og oversikt over hvor opplysningen er brukt. En retting forhåndsviser hvilke utkast, økter og delte dokumenter som trenger oppfølging.

### Slik fungerer det

1. Brukeren filtrerer tidslinjen etter periode, tema, mål, kilde eller dokumenttype.
2. Et element kan åpnes for kontekst, kildelesing og oversikt over planer eller rapporter som har brukt det.
3. Ved retting registreres begrunnelse og ny versjon. Systemet viser berørte utkast og sender allerede delte dokumenter til en egen oppfølgingsvurdering.

### Status og overganger

Opplysninger vises som gjeldende, bestridte, korrigerte eller erstattede. Berørte utkast merkes for ny gjennomgang; tidligere delte versjoner beholder sin faktiske delingshistorikk.

### Automatikk og menneskelige valg

Programmet filtrerer, finner avledninger og markerer følger av en retting. Ansvarlig bestemmer ny formulering og eventuell korrigerende kommunikasjon.

### Når noe mangler eller feiler

Ved feil elevtilordning fjernes den operative tilgangen fra feil elevs arbeidsflate. Rettelsen får en ansvarlig oppfølgingsoppgave dersom tidligere delte dokumenter eller andre systemer kan være berørt.

### Resultat

- Søkbar tidslinje, rettingshistorikk og oversikt over berørte avledninger.

### Regler og avvik

- Registreringsdato skal ikke erstatte tidspunktet noe faktisk hendte.
- Retting av feil elevkobling må også fjerne feil tilgang fra søk, oppsummeringer og andre operative avledninger.

### Akseptansekriterier

- Et notat skrevet i oktober om en hendelse i september kan finnes på begge relevante datoer med tydelig merking.
- En feil elevkobling gjør berørte utkast utdaterte og gir ingen fortsatt kildetilgang gjennom gamle lenker.

**Eksempel:** Læreren finner alle bekreftede observasjoner om leseflyt siden forrige målrevisjon, med motstridende observasjoner synlige.

**Avhengigheter:** [F03](#f03), [F04](#f04), [F27](#f27).

**Første leveranse og utvidelser:** P2: filtrering, kildesøk og retting. Konsekvensoversikten utvides når nye dokumenttyper innføres.

**Til faglig gjennomgang:** Hvilke filtre og rettingssituasjoner er viktigst i en vanlig skoleuke?

Domene: BC02. Første leveranse: P2. Kravkoblinger: L016, L051.

<a id="f06"></a>

## F06 Kravregister og årshjul

Versjonerte lovkrav, forskrifter, godkjenningsvedtak, lokale rutiner og produktvalg. Beregn hvilke krav som gjelder hvem og når; vis kilde, ansvar, dokumentbehov og uavklarte forhold.

**Brukere:** Rektor, Skoleeier, Regelansvarlig, Ansatte med oppfølgingsansvar.

**Når brukes den:** Ved skolestart, relevante hendelser eller godkjent endring i et regelgrunnlag.

### Inndata

- Kravregister, skoleprofil, lokale rutiner, dokumentmaler og godkjente tidsregler.
- Elev-/saksforhold som avgjør om et krav gjelder.

### Arbeidsflate og handlinger

- Arbeidslisten kan vises som kalender eller tabell med oppgave, elev/sak der tilgang finnes, ansvarlig, tidsregel, lokal påminnelse og status. Lovkrav, lokal rutine og frivillig oppgave er tydelig merket.
- Regelredaktøren åpner et kravkort med kildeversjon, anvendelsesvilkår og godkjenning. Før aktivering av en endring vises berørte oppgaver og hva som vil endres.

### Slik fungerer det

1. Regelansvarlig vurderer hvilke regler og lokale rutiner som gjelder skolen, med kilde og gyldighet.
2. Systemet oppretter konkrete oppgaver med ansvarlig, tidsregel og eventuell lokal påminnelsesdato.
3. Ansatte ser sin arbeidsliste, legger til utført handling eller dokumentasjon og sender uavklarte spørsmål til rett ansvarlig.

### Status og overganger

Regler har utkast, til vurdering, godkjent og erstattet versjon. Oppgaver viser blant annet uavklart anvendelse, åpen, under arbeid, til kontroll og avsluttet med dokumentert handling.

### Automatikk og menneskelige valg

Godkjente regler kan opprette oppgaver og påminnelser fra registrerte hendelser. Regelansvarlig avgjør anvendelse og tidsgrunnlag; den ansvarlige bekrefter at handlingen faktisk er utført.

### Når noe mangler eller feiler

Ukjent skoleprofil eller manglende utløserdato gir en avklaringsoppgave. Programmet skal vise hva som mangler fremfor å produsere en tilsynelatende presis frist.

### Resultat

- Årshjul, rollebasert arbeidsliste og spor fra oppgave til gjeldende grunnlag.

### Regler og avvik

- Lovkrav, veiledning, lokal rutine og valgfri produktfunksjon merkes forskjellig.
- Manglende anvendelsesgrunnlag gir uavklart status; opplastet dokument lukker ikke automatisk den underliggende plikten.

### Akseptansekriterier

- En lokal rapportfrist kan endres uten å omskrive lovens tidsregel eller historiske oppgaver.
- En regelendring viser hvilke åpne oppgaver som berøres før en autorisert person aktiverer endringen.

**Eksempel:** Rektor ser at en årlig evaluering mangler ansvarlig pedagog, mens en frivillig e-postrutine vises som skolens eget valg.

**Avhengigheter:** [F01](#f01).

**Første leveranse og utvidelser:** P1: manuelt godkjente regelprofiler og oppgaver. Omfattende endringsanalyse og ledelsesoversikt utvides i P6–P7.

**Til faglig gjennomgang:** Hvilke lokale frister og rutiner skal være med, og hvem vedlikeholder dem?

Domene: BC03. Første leveranse: P1. Kravkoblinger: L023, L030, L045, L053, L056, L066, L074, L076, L084, L087, L088, L089, L090.

<a id="f07"></a>

## F07 Henvisning, sakkyndighet og vedtak

Samle henvisningsgrunnlag, nødvendig samtykke/tillatelse og PPT-dokumentasjon. Registrer innhold, omfang, organisering, kompetanse, gyldighet og vedtaksmyndighet. Hold ITO, assistanse og fysisk tilrettelegging atskilt.

**Brukere:** Spesialpedagog, Rektor, Autorisert saksbehandler.

**Når brukes den:** Ved nytt støttebehov, henvisning, sakkyndig vurdering eller vedtak.

### Inndata

- Tidligere tiltak og utbytte, relevant samtykke, PPT-dokumenter og vedtaksoriginal.
- Myndighet, gyldighetsperiode, fag, omfang, organisering og kompetansekrav.

### Arbeidsflate og handlinger

- Saksoversikten samler henvisning, sakkyndig vurdering, vedtak og avklaringer i et datert forløp. Et sammenligningsbilde viser PPTs anbefalinger ved siden av vedtakets bestemmelser.
- Ved registrering bekreftes kategori, fag, omfang med enhet og periode, organisering, kompetansekrav og vedtaksmyndighet. Brukeren kan åpne bestemmelsens kilde direkte fra hvert felt.

### Slik fungerer det

1. Brukeren oppretter en sak eller registrerer dokumenter i en eksisterende sak.
2. Systemet skiller anbefalinger i sakkyndig vurdering fra rettigheter og vilkår i vedtaket; brukeren bekrefter nøkkelfeltene.
3. Ansvarlig kan følge henvisning, ventende avklaringer, mottatt vedtak og behov for ny vurdering fra én saksoversikt.

### Status og overganger

Saksforløpet viser forberedelse, henvisning sendt, venter på grunnlag, vedtak mottatt og oppfølging. Dokumentenes bekreftelse og gyldighet vises separat fra sakens fremdrift.

### Automatikk og menneskelige valg

Programmet foreslår uttrekk, sammenstiller forskjeller og oppretter avklaringspunkter. Ansvarlig bekrefter grunnlaget, og vedtaksmyndigheten treffer avgjørelsen.

### Når noe mangler eller feiler

Manglende vedtak, uklare enheter eller motstridende datoer markeres konkret. En manuell økt kan forberedes med synlige forbehold, uten at uavklart omfang registreres som en bekreftet rettighet.

### Resultat

- Bekreftet vedtaksgrunnlag, anbefalingsoversikt og saksoppgaver som IOP og timeplan kan bruke.

### Regler og avvik

- ITO, personlig assistanse og fysisk tilrettelegging registreres som forskjellige kategorier.
- Ufullstendig eller utløpt dokumentgrunnlag utløser avklaring; systemet endrer ikke elevens tilbud automatisk.

### Akseptansekriterier

- Et avvik mellom PPTs anbefalte omfang og vedtaket vises tydelig og blandes ikke til ett tall.
- Planlegging kan spore hvert registrert omfang til riktig bestemmelse, enhet og periode.

**Eksempel:** Et vedtak gir både ITO og assistanse. Pedagogen bekrefter to separate rammer før de brukes i øktplanlegging.

**Avhengigheter:** [F02](#f02), [F04](#f04), [F06](#f06).

**Første leveranse og utvidelser:** P2: import og bekreftelse av eksisterende vedtak/sakkyndighet. P3: full henvisnings- og saksflyt; P4: klager via F38.

**Til faglig gjennomgang:** Hvilke vedtaksformuleringer og enheter bruker kommunene som pilotskolen samarbeider med?

Domene: BC04. Første leveranse: P2. Kravkoblinger: L003, L009, L010, L011, L012, L013, L015, L019, L029, L040, L041, L043, L060, L062, L070, L071, L072, L073, L075, L090.

<a id="f08"></a>

## F08 IOP med mål og versjoner

Generer og rediger IOP-utkast innenfor vedtaket. Koble mål, delmål, tiltak, arena, ansvar og evaluering. Dokumenter elev- og foreldreinnspill; kontroller endringer ved nye vedtak.

**Brukere:** Ansvarlig spesialpedagog, Faglærer, Elev-/foresattinnspill registrert av ansatte.

**Når brukes den:** Ved eksisterende IOP som skal brukes, opprettelse av ny plan eller relevant endring.

### Inndata

- Aktuelt vedtak, sakkyndige anbefalinger, læreplan og bekreftet elevgrunnlag.
- Eksisterende IOP, delmål, tiltak, ansvar, organisering og vurderingsmåte.

### Arbeidsflate og handlinger

- IOP-redigeringen viser mål, delmål, tiltak, arena, ansvar og evalueringsmåte, med gjeldende vedtak tilgjengelig ved siden av. Elev- og foresattinnspill kan knyttes til den delen de gjelder.
- Hvert mål har en stabil identitet og daterte versjoner. «Sammenlign versjoner» viser hvilke mål som er endret, videreført eller avsluttet, og hvilke kommende økter som kan påvirkes.

### Slik fungerer det

1. Brukeren registrerer en eksisterende IOP eller ber om et nytt utkast og kontrollerer koblingen til vedtaket.
2. Mål og tiltak redigeres med forventet handling, arena, støtte og hvordan utvikling skal observeres; elev- og foresattinnspill tas med.
3. Ansvarlig gjennomgår og aktiverer en datert revisjon. Endringer som krever nytt vedtak blir en avklaringsoppgave.

### Status og overganger

Planen har utkast, til faglig gjennomgang, godkjent gjeldende versjon og historiske versjoner. Et endret mål i utkast endrer ikke målet som tidligere undervisning ble dokumentert mot.

### Automatikk og menneskelige valg

Programmet kan foreslå målformuleringer og struktur fra bekreftet grunnlag og kontrollere manglende felt. Faglig ansvarlig velger innhold, vurderer medvirkning og godkjenner planen.

### Når noe mangler eller feiler

Nytt eller endret vedtak oppretter en revisjonsoppgave med synlig forskjell. Systemet overskriver ikke gjeldende IOP eller flytter historiske observasjoner til nye mål uten eksplisitt vurdering.

### Resultat

- Aktiv IOP-revisjon med mål som kan brukes i økter, kartlegging og evaluering.

### Regler og avvik

- Sakkyndig vurdering alene gir ikke grunnlag for å utvide eller redusere vedtakets rammer.
- Historiske økter og vurderinger beholder koblingen til målversjonen som gjaldt da.

### Akseptansekriterier

- En ny målrevisjon endrer ikke teksten i tidligere års dokumentasjon.
- Et forslag utenfor bekreftet vedtaksramme kan ikke aktiveres som om det allerede var godkjent.

**Eksempel:** Et bredt lesemål deles i observerbare delmål; neste økt bruker det aktive delmålet og viser hvor det kommer fra.

**Avhengigheter:** [F07](#f07), [F04](#f04).

**Første leveranse og utvidelser:** P2: registrer og bekreft eksisterende godkjent IOP og mål. P3: generering, bidrag, revisjon og aktivering av nye planer.

**Til faglig gjennomgang:** Hvordan formulerer dere mål som er nyttige i økten og samtidig egner seg for evaluering?

Domene: BC05. Første leveranse: P2. Kravkoblinger: L001, L011, L015, L016, L019, L021.

<a id="f09"></a>

## F09 Læreplan og klassens planer

Skolens godkjente læreplan, fag- og timefordeling, halvårsplaner og ukeplaner. Koble tema til elevmål; varsle om endringer og ta hensyn til Montessori og aldersblanding.

**Brukere:** Kontaktlærer, Faglærer, Spesialpedagog.

**Når brukes den:** Ved planlegging av skoleår, tema eller endring i klassens plan.

### Inndata

- Skolens godkjente læreplan og vurderingsordning.
- Klasse-/gruppeplaner med tema, periode, læringsmål og planlagte aktiviteter.

### Arbeidsflate og handlinger

- Klasseplanen viser tema, periode, læreplanreferanser, aktiviteter og materiell i en periodeoversikt. Brukeren kan importere en eksisterende halvårsplan og kontrollere feltene før publisering.
- Fra elevens planlegging vises aktuelle klassetemaer sammen med egne mål. Pedagogen velger hva eleven skal delta i, hva som tilpasses og hvilke koblinger som ikke er relevante.

### Slik fungerer det

1. Læreren importerer eller skriver en plan og bekrefter perioder og målreferanser.
2. Spesialpedagogen ser aktuelle klassetemaer sammen med elevens mål og velger meningsfulle koblinger.
3. Når en plan publiseres i ny versjon, vises berørte kommende økter slik at ansvarlig kan beholde eller endre dem.

### Status og overganger

Klasseplanen har utkast, publisert og erstattet versjon. En berørt økt viser hvilken versjon den bygger på og om en senere planendring trenger vurdering.

### Automatikk og menneskelige valg

Programmet foreslår koblinger mellom tema og elevmål og finner berørte økter ved endring. Pedagogen avgjør faglig relevans og tilpasning.

### Når noe mangler eller feiler

En ustrukturert import kan lagres som kilde mens perioder legges inn manuelt. Manglende klasseplan skal ikke hindre planlegging ut fra bekreftede elevmål.

### Resultat

- Versjonert klasseplan og eksplisitte koblinger mellom klassens tema og elevens arbeid.

### Regler og avvik

- Felles tema skal ikke automatisk gjøre elevens mål eller vanskelighetsgrad identisk med klassens.
- Aldersblandede grupper og lengre Montessori-arbeidsperioder må støttes uten krav om én plan per enkelttrinn.

### Akseptansekriterier

- Flytting av et tema oppdaterer forslag til fremtidige økter uten å endre gjennomførte økter.
- En elev kan arbeide med samme tema som klassen og ha egne konkrete mål og materiell.

**Eksempel:** Klassen arbeider med verdensdeler; eleven trener lesing og begreper med tilpassede kort fra samme tema.

**Avhengigheter:** [F01](#f01), [F06](#f06).

**Første leveranse og utvidelser:** P3: planregister og koblinger. P2 kan bruke manuelt bekreftet tema i en enkeltøkt uten full importfunksjon.

**Til faglig gjennomgang:** Hvordan er halvårsplaner og aldersblandede temaer strukturert hos dere?

Domene: BC06. Første leveranse: P3. Kravkoblinger: L004, L006, L015, L021, L044, L071, L073.

<a id="f10"></a>

## F10 Bibliotek for egne opplegg og materiell

Import, søk, gjenbruk og deling av pedagogens opplegg med rettigheter, alder, ferdigheter og tidsbruk. Oversikt over materiell, plassering, antall og dokumenterte Montessori-presentasjoner.

**Brukere:** Lærer, Spesialpedagog, Materiellansvarlig.

**Når brukes den:** Når et eget opplegg skal lagres, finnes igjen, tilpasses eller deles.

### Inndata

- Egne dokumenter, presentasjoner og praktiske opplegg.
- Mål, forkunnskaper, varighet, materiell, plassering, antall og bruksrettigheter.

### Arbeidsflate og handlinger

- Biblioteket kan filtreres etter fag, målområde, nivå, varighet, gruppestørrelse og materiell. Ressurskortet viser original, opphav, bruksrett, forberedelser og tidligere registrerte erfaringer.
- «Bruk i økt» lager en tilpasning knyttet til originalversjonen. For fysisk materiell vises plassering og tilgjengelighet; pedagogen kan velge et alternativ som allerede finnes ved skolen.

### Slik fungerer det

1. Brukeren legger inn opplegget og bekrefter forslag til beskrivende merker.
2. Ved øktplanlegging søkes det etter passende egne ressurser; pedagogen ser originalen og hvorfor den kan passe.
3. En tilpasning lagres som egen versjon eller variant, med kobling til originalen og registrert erfaring etter bruk.

### Status og overganger

Ressurser vises som private utkast, tilgjengelige for avtalt team eller trukket fra videre bruk. Varianter beholder koblingen til originalen og overskriver ikke andres opplegg.

### Automatikk og menneskelige valg

Programmet foreslår merking og relevante ressurser fra det avgrensede biblioteket. Pedagogen bekrefter egnethet og tilpasning; eier eller ansvarlig avklarer bruksrett.

### Når noe mangler eller feiler

Manglende materiell eller uklar delingsrett vises før opplegget tas i bruk. Brukeren kan velge en annen ressurs eller lage et eget opplegg; systemet antar ikke at alt kan kopieres.

### Resultat

- Søkbart ressursbibliotek og materielloversikt med gjenbrukbare opplegg.

### Regler og avvik

- Skolens egne opplegg skal kunne foretrekkes som kilde før nye aktiviteter foreslås.
- Bruksrettigheter styrer deling, kopiering og AI-bruk; fysisk antall kobles til reservasjoner i F14.

### Akseptansekriterier

- En privat ressurs blir ikke søkbar for hele skolen før eieren har valgt en tillatt deling.
- En tilpasset Montessori-presentasjon beholder spor til original og synlige endringer.

**Eksempel:** Pedagogen finner et tidligere brukt perlemateriellopplegg, tilpasser varighet og reserverer det nødvendige materiellet.

**Avhengigheter:** [F01](#f01), [F03](#f03).

**Første leveranse og utvidelser:** P3: bibliotek, varianter og materiellregister. P5: tilgjengelighet i timeplanlegging.

**Til faglig gjennomgang:** Hvilke merker og beskrivelser gjør egne opplegg raske å finne igjen?

Domene: BC06. Første leveranse: P3. Kravkoblinger: L004, L010, L069, L072, L083, L086.

<a id="f11"></a>

## F11 Kartlegging og målinger

Registrer instrument, versjon, resultater og gjennomføringsbetingelser. Hold standardiserte prøver atskilt fra observasjoner; bruk faglig godkjente intervaller, lisensvilkår og gyldige fritak.

**Brukere:** Kvalifisert kartlegger, Lærer, Spesialpedagog.

**Når brukes den:** Ved planlagt kartlegging, nytt oppfølgingsbehov eller foreslått ny måling.

### Inndata

- Instrument, versjon, bruksrett, aktuelle mål og faglig intervallveiledning.
- Dato, råresultat, skala, tilpasninger og gjennomføringsbetingelser.

### Arbeidsflate og handlinger

- Kartleggingskortet viser instrument, versjon, formål, skala, instruksjon, lisens og relevante tidligere gjennomføringer. Registreringsbildet skiller råresultat, betingelser og faglig tolkning.
- Tidslinjen kan vise gjentatte målinger med merknader om støtte, språk og andre endrede betingelser. Et forslag om neste kartlegging viser kilde og hvorfor tidspunktet foreslås.

### Slik fungerer det

1. Pedagogen velger kartlegging og ser forkunnskaper, lisensbegrensninger og eventuelle tidligere resultater.
2. Resultatet registreres med instrumentets skala og forhold som kan påvirke tolkingen; ansvarlig bekrefter registreringen.
3. Systemet foreslår oppfølging og eventuelt tidspunkt for ny kartlegging med synlig kilde og begrunnelse. Pedagogen velger videre bruk.

### Status og overganger

En gjennomføring er planlagt, påbegynt, registrert eller faglig vurdert; avbrutt og ikke sammenlignbar er synlige utfall. En påminnelse om ny måling kan godtas, flyttes eller avvises med begrunnelse.

### Automatikk og menneskelige valg

Programmet kan validere format og skala og foreslå oppfølging ut fra godkjente instrumentopplysninger. Fagperson gjennomfører, tolker og velger hva resultatet betyr for undervisningen.

### Når noe mangler eller feiler

Feil skala eller manglende instrumentversjon må avklares før sammenstilling. Usammenlignbare resultater vises hver for seg; manglende målinger erstattes ikke med beregnede elevresultater.

### Resultat

- Kontrollerte kartleggingsresultater, sammenlignbar historikk og avtalt oppfølging.

### Regler og avvik

- AI skal ikke finne på testintervaller, normer eller diagnoser.
- Ulike instrumenter, versjoner og tilpasninger vises separat når direkte sammenligning ikke er begrunnet.

### Akseptansekriterier

- En verdi utenfor instrumentets skala blir avvist eller må avklares før bekreftelse.
- Et forslag til ny prøve uten godkjent intervallgrunnlag merkes som et åpent faglig spørsmål.

**Eksempel:** En leseprøve med ekstra støtte markeres med gjennomføringsbetingelsene før pedagogen vurderer utvikling siden sist.

**Avhengigheter:** [F02](#f02), [F04](#f04), [F06](#f06).

**Første leveranse og utvidelser:** P4: instrumentregister, resultatføring og faglig vurderte påminnelser. Automatisk resultatimport krever F32.

**Til faglig gjennomgang:** Hvilke kartlegginger brukes, og finnes det dokumenterte intervaller og regler for gjenbruk?

Domene: BC09. Første leveranse: P4. Kravkoblinger: L007, L008, L030, L041, L073, L086.

<a id="f12"></a>

## F12 Planlegg neste undervisningsøkt

Bruk aktive mål, siste gjennomføring, klassens tema og tilgjengelige ressurser. Mål, materiell, konkrete trinn, støtte, tilpasninger og observasjonspunkt. Faglig gjennomgang før bruk.

**Brukere:** Spesialpedagog, Lærer.

**Når brukes den:** Når pedagogen skal forberede neste økt eller tilpasse et eksisterende opplegg.

### Inndata

- Aktive mål og rammer, siste relevante notat, bekreftede støttestrategier og klassens tema.
- Tilgjengelig tid, arena, deltakere, materiell og pedagogens egne ressurser.

### Arbeidsflate og handlinger

- Planleggingsbildet starter med elev, mål, varighet, tema, arena og materiell. Et grunnlagspanel viser valgte IOP-mål, støttestrategier, siste relevante observasjoner og eventuelle mangler.
- Økten redigeres som forberedelse, steg med tidsanslag, støtte, avtalt forenkling og observasjonspunkt. «Lag nytt forslag» viser endringene før pedagogen velger hva som skal erstatte egen tekst.

### Slik fungerer det

1. Pedagogen velger elev, mål og øktlengde; systemet viser hvilket grunnlag det vil bruke.
2. Et utkast beskriver mål, forberedelse, materiell, konkrete steg, støtte, alternativ ved vansker og hva som skal observeres.
3. Pedagogen endrer eller avviser forslag, kontrollerer at det passer eleven og godkjenner økten for gjennomføring.

### Status og overganger

Økten er utkast, til gjennomgang, godkjent for gjennomføring eller trenger ny kontroll etter endring. Planlagt tidspunkt og faktisk gjennomføring har egne statuser.

### Automatikk og menneskelige valg

Programmet foreslår et konkret opplegg fra valgt grunnlag og egne ressurser. Pedagogen avgjør om aktivitet, støtte, tempo og observasjonspunkt passer eleven og godkjenner versjonen.

### Når noe mangler eller feiler

Når AI ikke svarer, kan pedagogen bruke samme felter manuelt og beholde lagret arbeid. Manglende kilder og uavklart plangrunnlag blir synlige, uten oppdiktet innhold eller automatisk stans i elevens støtte.

### Resultat

- Et praktisk øktopplegg med kilder, ansvarlig og tydelig godkjent versjon.

### Regler og avvik

- Manglende eller motstridende grunnlag vises; systemet dikter ikke opp hva eleven mestrer.
- Øktforslaget kan ikke endre vedtak eller aktiv IOP. Nye aktiviteter merkes som forslag, ikke som dokumentert tidligere erfaring.
- For elever uten ITO brukes et bekreftet ordinært undervisningsmål; IOP er ikke et generelt inngangskrav for øktplanlegging.

### Akseptansekriterier

- Ved regenerering beholdes pedagogens tidligere versjon og redigeringer til brukeren velger å erstatte dem.
- En økt kan planlegges manuelt når AI er utilgjengelig, med samme mål- og godkjenningskontroll.

**Eksempel:** Pedagogen velger 25 minutter og et aktivt lesemål. Utkastet bruker klassens tema og et kjent opplegg, med en enklere variant ved behov.

**Avhengigheter:** [F02](#f02), [F04](#f04), [F07](#f07), [F08](#f08), [F33](#f33).

**Første leveranse og utvidelser:** P2: én elev og én økt med bekreftet eksisterende grunnlag og manuelt tema/materiell. P3: fullt bibliotek og klasseplan; P5: timeplan/grupper.

**Til faglig gjennomgang:** Hvilke deler av et øktopplegg må alltid være med for at det kan brukes uten ekstra planlegging?

Domene: BC07. Første leveranse: P2. Kravkoblinger: L004, L006, L008, L010, L041, L043, L044, L070.

<a id="f13"></a>

## F13 Assistentkort og veiledning

Gjennomføringskort som kan forstås på omtrent fem minutter. Materiell, tre–fem trinn, hvordan støtte, avtalt forenkling og kontaktperson; korte tilbakemeldinger. Krev nødvendig opplæring i tillegg.

**Brukere:** Assistent, Ansvarlig lærer eller spesialpedagog.

**Når brukes den:** Når en assistent får et avgrenset oppdrag knyttet til en godkjent økt.

### Inndata

- Godkjent økt, avtalt assistentrolle, nødvendig elevstøtte og kontaktperson.
- Materiell, plassering, praktiske steg og avtalte forenklinger.

### Arbeidsflate og handlinger

- Assistenten åpner dagens tildelte kort med sted, tidspunkt, materiellplassering, mål i enkelt språk og tre–fem trinn. Avtalt forenkling, når hjelp skal hentes og kontaktperson vises uten ekstra søk.
- Kortet har «Still spørsmål» og en kort etterregistrering av hva som ble gjort og hva som var vanskelig. Pedagogen kan se spørsmål og gi oppdatert veiledning til det konkrete oppdraget.

### Slik fungerer det

1. Systemet lager et kort fra den godkjente økten med mål i enkelt språk, materiell og tre–fem hovedsteg.
2. Ansvarlig pedagog kontrollerer kortet og tildeler det til assistenten for en bestemt økt/periode.
3. Assistenten åpner kortet, kan stille et spørsmål og etterpå gi en kort tilbakemelding om hva som ble gjort og hvor hjelp trengs.

### Status og overganger

Kortet vises som utkast, godkjent, tildelt eller utdatert. Åpnet kort viser bare tilgangshendelsen; det regnes ikke som dokumentert forståelse eller utført oppdrag.

### Automatikk og menneskelige valg

Programmet kan forkorte en godkjent økt til et praktisk kort. Pedagogen kontrollerer at nødvendig støtte og kontaktvei er med; assistenten bekrefter faktisk gjennomføring separat.

### Når noe mangler eller feiler

Når økten endres, markeres kortet for ny kontroll. Hvis assistenten er usikker eller tildelingen mangler, vises ansvarlig kontakt og avklaringsbehov fremfor tilgang til hele elevmappen.

### Resultat

- Kort gjennomføringsveiledning og tilbakemelding til den faglig ansvarlige.

### Regler og avvik

- Kortet skal normalt kunne forstås på omtrent fem minutter, og må prøves med faktiske assistenter.
- Kortet gir ikke selvstendig undervisningsansvar og erstatter ikke nødvendig opplæring eller veiledning.

### Akseptansekriterier

- Assistenten får bare innhold som trengs for det tildelte oppdraget, uten lenker som åpner hele elevmappen.
- En relevant endring i økten merker kortet som utdatert og krever ny pedagogisk kontroll.

**Eksempel:** Assistenten ser hvilket materiell som skal hentes, hvordan støtte skal gis, hva som kan forenkles og hvem som kontaktes ved spørsmål.

**Avhengigheter:** [F01](#f01), [F12](#f12), [F27](#f27).

**Første leveranse og utvidelser:** P2: enkelt kort og kort tilbakemelding. P3: flere maler og veiledningsoppfølging.

**Til faglig gjennomgang:** Hva må stå på kortet for at en assistent med liten forberedelsestid kan gjennomføre oppdraget trygt og forståelig?

Domene: BC07. Første leveranse: P2. Kravkoblinger: L009, L014, L072, L076, L080.

<a id="f14"></a>

## F14 Automatisk timeplan og gruppeforslag

Faste krav, pedagogiske preferanser, kompetanse, elevbehov, inkludering, rom og materiell. Forklar gruppeforslag; lås økter; vis uløselige konflikter og omplanlegg ved fravær.

**Brukere:** Spesialpedagog, Timeplanansvarlig, Rektor.

**Når brukes den:** Ved ny planperiode, endret bemanning eller behov for omplanlegging.

### Inndata

- Klasse- og elevplaner, vedtaksrammer, kompetanse, tilgjengelighet, rom og materiell.
- Pedagogisk vurderte gruppevalg, faste begrensninger, ønskede tidspunkter og låste økter.

### Arbeidsflate og handlinger

- Timeplanen viser elever, ansatte, rom og materiell i en ukevisning. Planleggeren registrerer tilgjengelighet, vedtaksrammer, skjermede klasseperioder og krav som ikke kan brytes, adskilt fra ønsker.
- Forslag kan sammenlignes med forklaring på gruppesammensetning, reisetid, ressurskonflikter og udekkede behov. Manuelle flyttinger og låste økter tas med ved ny beregning.

### Slik fungerer det

1. Planleggeren registrerer hva som er ufravikelig, og hva som er en preferanse.
2. Systemet foreslår gjennomførbare plasseringer og grupper med forklaring på valg, ressursbruk og eventuelle udekkede behov.
3. Planleggeren sammenligner alternativer, låser gode økter og publiserer etter pedagogisk kontroll; senere endringer vises som en konkret differanse.

### Status og overganger

Planversjoner er forslag, til kontroll, publisert eller erstattet. Publisering viser en endringsliste til berørte ansatte; en uløst konflikt beholdes som konkret avvik.

### Automatikk og menneskelige valg

Programmet søker etter plasseringer innenfor bekreftede rammer. Pedagogen vurderer om elever kan arbeide sammen, og planansvarlig godkjenner den samlede planen.

### Når noe mangler eller feiler

Når ingen fullstendig plan finnes, vises hvilke krav som kolliderer og mulige valg for ansvarlig. Programmet skal ikke skjule underdekning eller gjøre harde krav til preferanser for å vise en ferdig plan.

### Resultat

- Godkjent timeplan, gruppeoppsett og forklarte konflikter/kapasitetsmangler.

### Regler og avvik

- Faste rettighets- eller kompetansekrav kan ikke automatisk nedgraderes for å få planen til å gå opp.
- Gruppeforslag trenger faglig vurdering og må ta hensyn til inkludering, elevbehov og Montessori-arbeidsperioder.

### Akseptansekriterier

- Et uløselig forslag oppgir hvilke konkrete begrensninger som kolliderer i stedet for å publisere en ugyldig plan.
- Samme ansatt eller samme eksemplar av materiell kan ikke dobbeltreserveres ved samtidig publisering.

**Eksempel:** To elever kan jobbe med samme tema, men bare én trenger individuell økt. Systemet viser hvorfor de ikke kan grupperes i den aktuelle timen.

**Avhengigheter:** [F07](#f07), [F09](#f09), [F10](#f10), [F12](#f12), [F36](#f36).

**Første leveranse og utvidelser:** P5: automatiske forslag og omplanlegging. Manuell plassering av enkeltøkter finnes fra P2.

**Til faglig gjennomgang:** Hvilke timeplanbegrensninger er absolutte, og hvilke kan pedagogen velge å fravike?

Domene: BC08. Første leveranse: P5. Kravkoblinger: L004, L005, L008, L014, L018, L075, L082.

<a id="f15"></a>

## F15 Gjennomførte timer og avvik

Registrer per elev faktisk deltakelse, varighet, støtteform, bemanning og årsak til bortfall. Sammenstill med vedtak uten å likestille assistentminutter med undervisning eller automatisk fordele gruppetid feil.

**Brukere:** Lærer, Spesialpedagog, Assistent innenfor oppdraget.

**Når brukes den:** Etter en økt, avlysning eller retting av tidligere registrert gjennomføring.

### Inndata

- Planlagt økt som valgfritt utgangspunkt.
- Faktisk deltakelse, varighet, støtteform, bemanning og årsak til avvik.

### Arbeidsflate og handlinger

- Etterregistreringen åpnes fra økten med planlagte deltakere, tid og støtte som forslag. Brukeren bekrefter faktisk start/slutt eller varighet, hvem som deltok og hvilken støtte som ble gitt.
- Ved delvis gjennomføring eller avlysning registreres årsak og eventuell oppfølgingsansvarlig. Oversikten sammenstiller planlagt og faktisk støtte per elev og kategori, med kilde til vedtaksrammen.

### Slik fungerer det

1. Brukeren bekrefter hvem som deltok og registrerer faktisk tid og aktivitet; planlagte verdier vises bare som forslag.
2. Ved avvik velges relevant årsak, for eksempel elevfravær, manglende bemanning eller endret opplegg, med oppfølgingsansvar ved behov.
3. Systemet viser sammenstilling av planlagt og gjennomført støtte etter registrerte kategorier og vedtaksrammer.

### Status og overganger

En økt viser ikke registrert, gjennomført, delvis gjennomført eller avlyst. En korrigert registrering beholder tidligere verdier og begrunnelse; oppfølgingsoppgaven har egen status.

### Automatikk og menneskelige valg

Programmet kan foreslå kjente felt og summere bekreftede registreringer. Den som fulgte økten bekrefter hva som faktisk skjedde; en passert kalenderavtale gir ingen automatisk gjennomføring.

### Når noe mangler eller feiler

Ufullstendig registrering vises som manglende dokumentasjon. Ved uklart lagringssvar kontrolleres eksisterende registrering før nytt forsøk, slik at samme gjennomføring ikke telles to ganger.

### Resultat

- Etterprøvbar gjennomføringslogg og oversikt over bortfall som må vurderes.

### Regler og avvik

- Assistentstøtte og ITO-tid summeres ikke som samme ytelse.
- Elevtid og ansattressurs telles separat; gruppetid fordeles etter faktisk deltakelse og relevante vedtaksregler.

### Akseptansekriterier

- En publisert timeplan oppretter ingen gjennomførte minutter før noen har registrert faktisk gjennomføring.
- En gruppeøkt på 30 minutter med to deltakende elever kan vise 30 minutter per elev og 30 minutter ansattressurs uten dobbel ressursbelastning.

**Eksempel:** En planlagt økt på 30 minutter blir 20 minutter for én elev. Bare den faktiske deltakelsen inngår i senere evaluering.

**Avhengigheter:** [F07](#f07), [F12](#f12).

**Første leveranse og utvidelser:** P2: faktisk gjennomføring og avvik per økt. P3: vedtakssammenstilling; P5: samlet timeplan- og ressursavstemming.

**Til faglig gjennomgang:** Hvordan registreres gruppetid og bortfall i dag, og hva trenger ledelsen for å følge opp?

Domene: BC07. Første leveranse: P2. Kravkoblinger: L009, L010, L011, L017, L018, L063.

<a id="f16"></a>

## F16 Rask øktlogg og diktering

Strukturert kortnotat på cirka ett minutt, med valgfri fritekst. Senere diktering med kontroll av transkripsjon, uttrykkelig opptaksvalg og begrenset lagring av lyd.

**Brukere:** Lærer, Spesialpedagog, Assistent med avgrenset oppdrag.

**Når brukes den:** Etter undervisning eller en relevant observasjon i skolehverdagen.

### Inndata

- Valgt elev/økt, tidspunkt og eventuelt mål.
- Kort observasjon, grad/type støtte og valgfritt forslag til neste steg.

### Arbeidsflate og handlinger

- Kortloggen viser riktig elev, økt, dato og mål ferdig valgt når den åpnes fra en økt. Feltene er konkret observasjon, støtte som ble gitt og eventuelt neste steg; ekstra felter vises ved behov.
- Brukeren kan åpne kilde og redigere eget notatutkast. Ved senere diktering vises transkripsjonen til kontroll før lagring, med synlig informasjon om behandling og håndtering av lyd.

### Slik fungerer det

1. Brukeren åpner en kort logg fra økten eller elevsiden; kjente felt fylles som synlige forslag.
2. Brukeren skriver et kort notat eller senere dikterer og kontrollerer transkripsjonen.
3. Notatet lagres én gang og kan gjenbrukes i tidslinje, neste økt, vurdering og rapport med opprinnelig avsender.

### Status og overganger

Et notat er utkast, lagret eller korrigert; diktert tekst er ubekreftet inntil brukeren har kontrollert den. Faglig tolkning merkes separat fra den konkrete observasjonen.

### Automatikk og menneskelige valg

Programmet gjenbruker øktens kontekst og kan foreslå struktur eller transkribere. Forfatteren bekrefter innholdet; teksten skal ikke utvides med mestring eller hendelser som ikke er oppgitt.

### Når noe mangler eller feiler

Brukeren kan skrive manuelt hvis talegjenkjenning feiler. Ved lagringsfeil vises at notatet ikke er bekreftet lagret, og innholdet beholdes i den åpne redigeringen så lenge tilgang og økt er gyldig.

### Resultat

- Et kort datert notat med mål-/øktkobling og tydelig opphav.

### Regler og avvik

- Observasjon og tolkning holdes gjenkjennelig fra hverandre; fritekst er mulig uten et omfattende obligatorisk skjema.
- Diktering gjelder et uttrykkelig valgt notatopptak; det innebærer ikke kontinuerlig opptak av barn eller klasserom.

### Akseptansekriterier

- En vanlig logg kan gjennomføres i brukertest med median tidsbruk høyst ett minutt uten tap av nødvendig informasjon.
- En ikke godkjent transkripsjon brukes ikke som bekreftet elevopplysning i genererte dokumenter.

**Eksempel:** Pedagogen skriver «leste tre ord selv med bildekort» og velger det aktuelle målet; opplysningen er tilgjengelig ved neste økt.

**Avhengigheter:** [F02](#f02), [F05](#f05).

**Første leveranse og utvidelser:** P2: kort tekstlogg og gjenbruk. P7: diktering etter lokal tale-, tilgangs- og lagringsavklaring.

**Til faglig gjennomgang:** Hvilke to–fire felt er nyttige nok til at personalet faktisk vil fylle dem ut?

Domene: BC07. Første leveranse: P2. Kravkoblinger: L006, L007, L020.

<a id="f17"></a>

## F17 Fremgang og neste steg

Vis utvikling per mål og hvilke observasjoner den bygger på. Manglende belegg skal være synlig; foreslå justering med faglig begrunnelse og hensyn til dagsform og kontekst.

**Brukere:** Spesialpedagog, Faglærer.

**Når brukes den:** Ved måloppfølging, planendring eller forberedelse til evaluering.

### Inndata

- Målversjoner, relevante observasjoner, kartlegginger og gjennomførte tiltak.
- Tidligere faglige vurderinger og gjennomføringsbetingelser.

### Arbeidsflate og handlinger

- Målvisningen kombinerer gjeldende målversjon, observasjoner, faktisk støtte og sammenlignbare kartlegginger for valgt periode. Brukeren kan åpne hvert støttepunkt og se variasjon eller manglende grunnlag.
- Vurderingsbildet har forslag til oppsummering og valg for videreføring, tilpasning eller mer kartlegging. Pedagogen skriver sin vurdering og knytter neste tiltak til et mål eller en oppgave.

### Slik fungerer det

1. Pedagogen velger et mål og en periode og får en oversikt over støttepunkter, variasjon og manglende belegg.
2. Systemet foreslår en forsiktig oppsummering og mulige neste steg med kildehenvisninger.
3. Pedagogen bekrefter sin vurdering og velger videreføring, tilpasning eller behov for mer informasjon.

### Status og overganger

En utviklingsvurdering er utkast, til gjennomgang eller bekreftet av fagperson. Nytt grunnlag kan markere behov for ny vurdering uten å overskrive den historiske vurderingen.

### Automatikk og menneskelige valg

Programmet sammenstiller dokumenterte observasjoner og foreslår formuleringer med kilder. Fagpersonen avgjør måloppnåelse og videre tiltak; få observasjoner gir ikke automatisk en sikker trend.

### Når noe mangler eller feiler

Ved motstridende observasjoner vises begge med kontekst. Dersom mål eller målebetingelser er endret, markeres bruddet i sammenligningen og pedagogen kan velge en kortere, sammenlignbar periode.

### Resultat

- Datert faglig vurdering per mål og valgte neste steg.

### Regler og avvik

- Planlagt aktivitet og høy registreringsfrekvens er ikke i seg selv læringsfremgang.
- Dagsform, støtte og ulike målemetoder skal være synlige; ingen automatisk samlet elevskår.

### Akseptansekriterier

- Når det mangler observasjoner, vises utilstrekkelig grunnlag fremfor en påstand om stagnasjon eller mestring.
- Endring i testmetode gjør sammenligningsbegrensningen synlig i graf og tekst.

**Eksempel:** Flere notater viser mestring med støtte, men bare ett uten. Pedagogen kan ikke få dette presentert som stabil selvstendig mestring.

**Avhengigheter:** [F08](#f08), [F11](#f11), [F15](#f15), [F16](#f16).

**Første leveranse og utvidelser:** P4: målvisning, sammenstilling og godkjent utviklingsvurdering.

**Til faglig gjennomgang:** Hva regner dere som tilstrekkelig belegg for å videreføre eller endre et mål?

Domene: BC09. Første leveranse: P4. Kravkoblinger: L007, L008, L016, L017, L020, L067.

<a id="f18"></a>

## F18 Lovpålagte elevdokumenter og rapporter

Rapporttyper og maler styres av gjeldende krav. Generer blant annet årlig ITO-evaluering fra relevant dokumentasjon; kontroller innhold, perioder, kilder, mangler og nødvendige faglige godkjenninger.

**Brukere:** Spesialpedagog, Faglærer, Ansvarlig leder.

**Når brukes den:** Når en relevant rapportplikt skal oppfylles eller en godkjent lokal rapport bestilles.

### Inndata

- Dokumenttype, gjeldende regel/mal, elev, periode og ansvarlig.
- Vedtak, historiske IOP-mål, gjennomført opplæring, kartlegginger og faglige vurderinger.

### Arbeidsflate og handlinger

- Rapportarbeidsflaten viser dokumenttype, periode, gjeldende mal, ansvarlig og manglende bidrag. Teksten redigeres seksjonsvis med kilder og målversjoner tilgjengelig ved siden av.
- Lærer og spesialpedagog kan tildeles avgrensede deler, kommentere og levere inn bidrag. Godkjenningsvisningen viser hele dokumentet, endringer og uløste felt før det går til mottakerkontroll.

### Slik fungerer det

1. Brukeren åpner rapportoppgaven og ser hvilke innholdskrav, kilder og bidrag som mangler.
2. Systemet lager et redigerbart utkast med kildehenvisninger for faktapåstander og tydelige avklaringsfelt.
3. Bidragsytere kontrollerer sine deler; ansvarlig godkjenner riktig dokumentversjon og sender den videre til mottakerkontroll i F21.

### Status og overganger

Dokumentet er utkast, venter på bidrag, til kontroll, godkjent eller erstattet. Utsending og arkivering vises som egne forløp; godkjent tekst betyr ikke at mottaker har fått den.

### Automatikk og menneskelige valg

Programmet kan hente bekreftet grunnlag og generere malbasert tekst. Ansvarlig fagperson vurderer konklusjonene, kontrollerer at innholdet dekker formålet og godkjenner riktig versjon.

### Når noe mangler eller feiler

Manglende dokumentgrunnlag blir konkrete avklaringsfelt, ikke automatisk positive formuleringer. Ved ukjent eller ikke godkjent mal kan et manuelt arbeidsutkast lages uten merking som ferdig lovpålagt rapport.

### Resultat

- Gjennomgått rapport, kildemanifest og dokumentasjon av faglig godkjenning.

### Regler og avvik

- Årlig ITO-evaluering, lokal halvårsrapport og ordinær vurdering bruker hver sin type og anvendelsesregel.
- En rapport beskriver faktisk gjennomføring og utbytte; systemet oppfinner ikke manglende aktiviteter eller resultater.

### Akseptansekriterier

- En rapport over en periode med to IOP-revisjoner viser hvilket målgrunnlag som gjaldt når.
- Manglende obligatoriske opplysninger blir avklart eller håndtert av ansvarlig før dokumentet kan ferdigstilles etter den aktuelle malen.

**Eksempel:** Den årlige evalueringen henter øktlogger og målutvikling og synliggjør bortfalt undervisning som pedagogen må kommentere.

**Avhengigheter:** [F06](#f06), [F08](#f08), [F15](#f15), [F17](#f17), [F27](#f27).

**Første leveranse og utvidelser:** P4: de første godkjente elevrapportmalene og bidragsflyten; flere lokale maler legges til etter behov.

**Til faglig gjennomgang:** Hvilke rapportmaler skal støttes først, og hvem gjennomgår og godkjenner hver type?

Domene: BC10. Første leveranse: P4. Kravkoblinger: L017, L022, L035, L060, L069, L089.

<a id="f19"></a>

## F19 Underveis-, halvårs- og sluttvurdering

Samle lærernes innspill og elevens egenvurdering. Lag utkast til veiledende vurdering og møtegrunnlag. Faglærer fastsetter karakterer; Montessori-regler, fritak og fag som avsluttes tidlig styres særskilt.

**Brukere:** Faglærer, Kontaktlærer, Spesialpedagog som bidragsyter.

**Når brukes den:** Ved løpende vurdering, halvårsvurdering eller sluttvurdering.

### Inndata

- Gjeldende læreplan/vurderingsordning, fagets avslutning, eventuelle fritak og relevant IOP.
- Lærerens faglige grunnlag, elevens egenvurdering og relevante dokumenterte observasjoner.

### Arbeidsflate og handlinger

- Vurderingsbildet tilpasses fag, trinn, periode og skolens bekreftede vurderingsordning. Det viser kompetansegrunnlag, elevinnspill og innspill fra andre ansatte med tydelig opphav.
- Læreren kan redigere formuleringer om kompetanse og videre arbeid og registrere sin egen vurdering. Eventuell karakter har et separat felt med riktig myndighet, og formidlingsmåte registreres for seg.

### Slik fungerer det

1. Læreren velger vurderingstype og får riktige felt for trinn, fag og skolens ordning.
2. Systemet samler innspill og foreslår formuleringer om kompetanse og videre arbeid som læreren kan redigere.
3. Faglærer fastsetter vurdering og eventuell karakter; faktisk formidling eller registrering i autoritativt system dokumenteres separat.

### Status og overganger

Vurderingen viser under arbeid, trenger grunnlag og fastsatt. Formidlet til eleven, delt med berettigede foresatte og overført til skolens hovedsystem er separate hendelser.

### Automatikk og menneskelige valg

Programmet foreslår struktur og tekst basert på dokumentert grunnlag. Læreren fastsetter vurdering og eventuell karakter; systemet produserer ikke karakterer fra IOP-mål, fravær eller AI-forslag.

### Når noe mangler eller feiler

Uavklart Montessori-ordning eller manglende vurderingsgrunnlag gir avklaring. Programmet skal ikke velge en generell karakterordning for å fylle tomme felter eller likestille IOP-evaluering med fagvurdering.

### Resultat

- Gjennomgått vurderingsinnspill, eventuell lærerfastsatt karakter og status for formidling.

### Regler og avvik

- IOP-mål kan ikke ukritisk erstatte karaktergrunnlaget i fag.
- Montessori-unntak, fritak og tidlig avsluttede fag følger registrert ordning, ikke en generell aldersregel.

### Akseptansekriterier

- Samme trinn ved offentlig skole og godkjent Montessori-ordning kan få forskjellige relevante vurderingsfelt.
- AI foreslår ingen karakter og ferdigstiller ikke en vurdering på vegne av faglærer.

**Eksempel:** Kontaktlæreren samler faglærernes halvårsinnspill og ser hvilke som fortsatt mangler før samtalen.

**Avhengigheter:** [F06](#f06), [F09](#f09), [F17](#f17).

**Første leveranse og utvidelser:** P4: vurderingsinnspill, manuell karakterfastsetting der relevant og formidlingsstatus. F32 støtter senere overføring.

**Til faglig gjennomgang:** Hvilke deler føres i eksisterende skolesystem, og hvor kan dette programmet spare arbeid uten dobbeltføring?

Domene: BC09. Første leveranse: P4. Kravkoblinger: L020, L021, L022, L023, L024, L025, L027, L028, L029, L031, L032, L041, L060.

<a id="f20"></a>

## F20 E-postutkast til foresatte for valgt tidsintervall

Generer redigerbare e-poster per elev basert på et valgt fra-/til-intervall. Ansvarlig velger formål, innhold, språk og mottakere. Valgfri gjentakelse kan klargjøre nye utkast; ingen fast ukerytme eller automatisk utsending. Foreldrekommunikasjon er en senere funksjon og styrer ikke første komplette arbeidsflyt.

**Brukere:** Kontaktlærer, Spesialpedagog, Annen autorisert pedagog.

**Når brukes den:** Når en pedagog ønsker en foresatt-e-post, eller en uttrykkelig aktivert utkastplan når neste tidspunkt.

### Inndata

- Én elev, fra-/til-dato, formål, relevante temaer/mål, språk, ønsket lengde og foreslåtte mottakere.
- Bekreftede opplysninger fra perioden, nødvendige bakgrunnsreferanser og eventuelle separat merkede fremtidige planer.
- Valgfritt: utkastfrekvens, periodeavgrensning, første tidspunkt, ansvarlig og sluttdato for gjentakelse.

### Arbeidsflate og handlinger

- «Lag e-post» åpner elev, formål, fra-/til-dato, temaer, språk og ønsket lengde. Datovelgeren viser den faktiske perioden også ved snarveier som siste 14 dager; ingen ukentlig rutine er forhåndsvalgt.
- Gjennomgangen viser emne og redigerbar brødtekst sammen med inkluderte observasjoner, mangler og overlapp med tidligere delte perioder. En separat oversikt lar brukeren aktivere, pause eller avslutte gjentatte utkast og se neste tidspunkt.

### Slik fungerer det

1. Brukeren åpner «Lag e-post», velger datoer direkte eller en snarvei som siste 14 dager, forrige måned eller siden forrige sendte periode. Beregnede datoer vises alltid før generering.
2. Systemet viser hvilke opplysninger som inngår, hvilke som mangler og eventuell overlapp med tidligere delte perioder. Brukeren kan avgrense temaer og velge relevant innhold.
3. Systemet lager emne og brødtekst med arbeid, konkrete observasjoner, relevante avtaler og eventuelle neste steg. Kildene vises i en intern gjennomgangsflate.
4. Pedagogen redigerer, kontrollerer faktapåstander og velger mottakerspesifikt innhold. F21 håndterer godkjenning og eventuell utsending gjennom skolens tillatte kanal.
5. Hvis gjentakelse ønskes, aktiverer brukeren en egen utkastplan, for eksempel hver 14. dag eller månedlig. Nye utkast går til ansvarlig for gjennomgang; planen kan pauses, endres og avsluttes.

### Status og overganger

Et brev er utkast, til gjennomgang, godkjent eller forkastet. Utkastplanen er inaktiv, aktiv, pauset eller avsluttet; sendestatus kommer fra F21 og kan ikke utledes av at et utkast er generert.

### Automatikk og menneskelige valg

Programmet kan lage emne og tekst for valgt periode og klargjøre nye utkast ved uttrykkelig valgt intervall. Pedagogen kontrollerer innhold og mottakere for hvert brev og velger eventuell utsending separat.

### Når noe mangler eller feiler

Tom periode viser «Ingen bekreftede observasjoner i valgt periode» og valg om ny periode eller manuelt brev. Manglende ansvarlig eller genereringsfeil gir oppfølging; forsinkede kjøringer lager ikke en bunke brev automatisk.

### Resultat

- Et datert e-postutkast med emne, brødtekst, valgt periode, kilder, ansvarlig og status.
- Ved valgfri gjentakelse: oversikt over neste utkasttidspunkt, neste periode og tidligere kjøringer.

### Regler og avvik

- Oppsummeringsperiode og utkastfrekvens er forskjellige valg. Manuell bestilling er utgangspunktet, uten automatisk aktivert ukentlig rutine.
- Begge valgte kalenderdatoer inngår i perioden i skolens tidssone, og fra-dato kan ikke være etter til-dato. Hendelsesdato avgjør periodeplassering; opprettelsestidspunktet fryser hvilket kjent materiale utkastet bygget på.
- Et sent registrert notat om en hendelse i perioden vises som nytt grunnlag for revisjon. Det endrer aldri et godkjent eller sendt brev i det stille.
- Perioder med overlapp er tillatt med synlig varsel. «Siden sist» krever valgt mottaker og formål og bruker forrige bekreftet sendte periode for denne kombinasjonen, ikke et forkastet, mislykket eller uavklart utkast. Brukeren får avklare hull og rettelser.
- Manglende grunnlag gir et synlig avklaringsbehov eller mulighet for manuelt brev. Fremtidige planer merkes som planer og blandes ikke inn som gjennomførte aktiviteter.
- Bare berettigede foresatte er mottakere i første versjon. Sensitive sakstyper og opplysninger om andre elever tas ikke automatisk med; godkjenning gjelder én konkret versjon, aldri fremtidige brev.
- Utkastplaner uten aktiv ansvarlig pauses for omfordeling. Ved forsinket kjøring vises én oppsummering av manglende perioder til ansvarlig fremfor automatisk masseoppretting av brev.

### Akseptansekriterier

- Datoene 1.–15. oktober gir et utkast med relevant kjent grunnlag fra hele begge grensedagene, og datoene vises i gjennomgangen.
- En valgfri plan hver 14. dag oppretter høyst ett utkast per planversjon, elev og periode ved gjentatt jobbkjøring; den sender ingen e-post.
- Et utkast uten observasjoner påstår ikke at eleven har hatt fremgang. Brukeren kan avbryte eller skrive et manuelt brev med annet bekreftet formål.
- Et relevant sent registrert notat som tas inn i teksten, en endret periode eller en redigert oversettelse krever en ny dokumentrevisjon og ny relevant godkjenning.
- En ugyldig eller uavklart foresattrelasjon blokkerer utlevering også når mottakeren stod i en tidligere e-post.
- Fra-dato etter til-dato avvises. «Siden sist» uten et bekreftet tidligere sendingsgrunnlag ber brukeren velge datoer og antar ikke en periode.

**Eksempel:** Læreren velger 1.–20. oktober for å oppsummere et avsluttet tema. Senere velger hun en månedlig utkastplan for samme elev. Ingen av valgene innebærer automatisk utsending.

**Avhengigheter:** [F02](#f02), [F05](#f05), [F16](#f16), [F21](#f21), [F33](#f33).

**Første leveranse og utvidelser:** P4: manuelle perioder, e-postutkast og valgfri styrt gjentakelse. Full e-postkobling og portalutvidelser kommer i P7. F20 er ikke et akseptansekrav for P2-piloten.

**Til faglig gjennomgang:** Hvilke formål, perioder og innholdstyper gjør en foresatt-e-post nyttig, og trenger skolen gjentatte utkast i det hele tatt?

Domene: BC10. Første leveranse: P4. Kravkoblinger: L002, L026, L048.

<a id="f21"></a>

## F21 Gjennomgang, godkjenning og sikker utsending

Godkjenn eksakt innhold, vedlegg, mottakere og kanal. Endringer gjør godkjenning ugyldig. Støtt eksplisitt utsending, kvittering, feil, usikkert leveringsutfall, rettelser og sikker foresattportal.

**Brukere:** Faglig godkjenner, Autorisert avsender, Foresatt eller annen berettiget mottaker.

**Når brukes den:** Når et dokument eller e-postutkast skal ferdigstilles, deles eller korrigeres etter deling.

### Inndata

- Eksakt dokumentrevisjon, emne, brødtekst, vedlegg og eventuell språkvariant.
- Mottakergrunnlag, formål, valgt kanal og godkjenningsfullmakter.

### Arbeidsflate og handlinger

- Godkjenningsbildet viser eksakt dokumentversjon, kilder, språkvariant og vedlegg. Avsenderen får en egen forhåndsvisning for hver mottaker med kanal og hva vedkommende faktisk får tilgang til.
- Utsendingsoversikten viser tidspunkt, ansvarlig avsender og transportutfall. Ved avvik kan avsender undersøke kvittering, rette mottakergrunnlag eller klargjøre en korrigert versjon.

### Slik fungerer det

1. Faglig ansvarlig ser teksten sammen med kilder, endringer og mangler og godkjenner den konkrete versjonen.
2. Avsender velger mottaker og ser en forhåndsvisning av akkurat det vedkommende vil motta, inkludert vedlegg.
3. Systemet kontrollerer gjeldende mottakerrett og kanal før eksplisitt utsending og følger resultatet til bekreftet transportutfall eller avklaringsbehov.
4. Ved feil velges retting, ny versjon eller videre oppfølging; tidligere utsending beholdes som eget faktisk hendelsesforløp.

### Status og overganger

Innholdsgodkjenning, tillatelse til deling og transportutfall vises hver for seg. Transport kan være i kø, under sending, bekreftet akseptert, feilet eller uavklart; akseptert transport betyr ikke lest.

### Automatikk og menneskelige valg

Programmet kan kontrollere versjon, gjeldende rettigheter og kanal og utføre en uttrykkelig bestilt utsending. Godkjenner vurderer innhold, og autorisert avsender beslutter utleveringen.

### Når noe mangler eller feiler

Endret tekst eller vedlegg krever ny relevant godkjenning. Ved uavklart sendingsutfall avstemmes med transporttjenesten før nytt forsøk; eksport eller kopiering til e-postklient merkes ikke automatisk sendt.

### Resultat

- Godkjent dokument, mottakerspesifikk utleveringspakke og sporbar utsendingsstatus.

### Regler og avvik

- Redigering av godkjent innhold eller vedlegg krever ny innholdsgodkjenning; ny mottaker eller kanal krever ny utleveringskontroll.
- Vanlig e-post brukes bare når skolens godkjente kanal- og innholdspolicy tillater det. Ellers kan e-posten varsle om innhold via sikker kanal.
- Ferdig utkast, eksportert fil, akseptert transport og lest innhold er forskjellige statuser. Personlige/akutte meldeplikter følger egne løp i F25.

### Akseptansekriterier

- En foresatt som mister relevant tilgang mens en melding står i kø, kan ikke motta pakken uten ny avklaring.
- Ved ukjent leveringsutfall avstemmes leverandørreferansen før eventuell ny innsending, slik at timeout ikke gir blind dobbeltutsending.
- Kopiering til ekstern e-postklient registreres som klargjort/eksportert, og vises ikke som bekreftet sendt uten eget grunnlag.

**Eksempel:** To foresatte får hver sin vurderte innholdspakke; interne kildenotater og andre foresattes adresser følger ikke automatisk med.

**Avhengigheter:** [F01](#f01), [F02](#f02), [F27](#f27), [F28](#f28).

**Første leveranse og utvidelser:** P4: felles dokumentgodkjenning, mottakerkontroll, kontrollert eksport og første sikre utsendingsadapter. P7: full portal og flere kanaler.

**Til faglig gjennomgang:** Hvilke dokumenter skal hvem godkjenne, og hvilke utsendingskanaler er allerede godkjent ved skolen?

Domene: BC11. Første leveranse: P4. Kravkoblinger: L002, L003, L017, L026, L027, L032, L033, L038, L047, L048, L049, L060, L061, L063, L069.

<a id="f22"></a>

## F22 Møter, samarbeid og individuell plan

Møteforberedelse, innspill, referatutkast, ansvar, oppgaver og frister. Samarbeid med PPT og andre tjenester etter relevant grunnlag. Individuell plan etter velferdslovgivning holdes atskilt fra IOP.

**Brukere:** Kontaktlærer, Spesialpedagog, Møteleder, Koordinator.

**Når brukes den:** Ved planlagt samtale, samarbeidsmøte eller koordinert oppfølging.

### Inndata

- Møtetype, deltakere, formål, relevant elevgrunnlag og tidligere avtaler.
- Innspill fra elev, foresatte og tjenester med avklart delingsgrunnlag.

### Arbeidsflate og handlinger

- Møtekortet viser formål, deltakere, agenda, relevant grunnlag og åpne avtaler. Referatet har egne felt for elevens syn, faglige innspill, beslutninger og tiltak med ansvarlig og dato.
- Møtelederen kan gi deltakere avgrensede bidragsoppgaver og lage en mottakertilpasset referatversjon. En individuell plan fra andre tjenester lenkes som egen plantype, tydelig atskilt fra IOP.

### Slik fungerer det

1. Møteleder velger formål og deltakere og får forslag til agenda, utestående oppgaver og relevant grunnlag.
2. Under eller etter møtet registreres konkrete avtaler, elevens syn, ansvarlige og frister; referatutkast kan genereres fra notater.
3. Møteleder bekrefter referatet og fordeler oppfølging; deltakere får avgrenset informasjon etter sin rolle.

### Status og overganger

Møtet er planlagt, gjennomført eller avlyst; referatet er utkast eller bekreftet. Hvert tiltak følges separat som åpent, under arbeid eller utført med registrert resultat.

### Automatikk og menneskelige valg

Programmet kan foreslå agenda fra åpne oppgaver og skrive referatutkast fra registrerte notater. Møteleder bekrefter hva som ble avtalt og hvem som får hvilke opplysninger.

### Når noe mangler eller feiler

Uenighet beholdes med avsender fremfor å omskrives til enighet. En deltaker uten avklart delingsgrunnlag får ikke hele elevgrunnlaget som følge av å være invitert til møtet.

### Resultat

- Møteagenda, gjennomgått referat og oppgaver med eier og oppfølgingsdato.

### Regler og avvik

- Deltakelse i ett møte gir ikke automatisk tilgang til hele elevsaken.
- Individuell plan på tvers av velferdstjenester er en egen plantype og skal ikke forveksles med IOP.

### Akseptansekriterier

- Et gjennomført møte kan registreres uten at systemet krever et unødvendig omfattende referat.
- En oppgave forsvinner ikke ved neste møte; den viser utført handling eller fortsatt åpent ansvar.

**Eksempel:** Før en foreldresamtale får kontaktlæreren siste måloppfølging og åpne avtaler, og kan registrere tre nye tiltak med ansvarlig.

**Avhengigheter:** [F02](#f02), [F05](#f05), [F06](#f06).

**Første leveranse og utvidelser:** P4: møteforberedelse, referat og oppgaver. P7: kalenderkobling og selektiv ekstern samhandling.

**Til faglig gjennomgang:** Hvilke møteformer trenger egne maler, og hva er et tilstrekkelig kort referat?

Domene: BC12. Første leveranse: P4. Kravkoblinger: L001, L002, L007, L012, L022, L024, L025, L026, L033, L035, L040, L042, L043, L062, L076, L078, L080.

<a id="f23"></a>

## F23 Fravær og oppfølging

Hent eller før fravær, registrer kontakt og tiltak, foreslå oppfølging og gjør ansvar synlig. Skill elevfravær fra avlyst undervisning og fra manglende lærerressurs.

**Brukere:** Kontaktlærer, Spesialpedagog, Fraværsansvarlig.

**Når brukes den:** Ved nytt fravær, gjentatte fraværsmønstre eller behov for oppfølging.

### Inndata

- Fraværsregistrering fra autoritativt system eller manuell føring med kilde.
- Berørte timer, kontaktforsøk, nødvendige årsaksopplysninger og avtalte tiltak.

### Arbeidsflate og handlinger

- Fraværsoversikten viser registrert elevfravær ved siden av planlagte økter og faktisk gjennomføring. Brukeren kan åpne perioder for å skille elevens fravær fra avlyst tilbud eller manglende registrering.
- Oppfølgingskortet samler kontakt, elev-/foresattinnspill, tiltak, ansvarlig og avtalt evaluering. Neste oppfølging vises i den ansvarliges arbeidsliste.

### Slik fungerer det

1. Systemet viser fravær sammen med planlagt og faktisk undervisning uten å slå kategoriene sammen.
2. Ansvarlig vurderer situasjonen og registrerer kontakt, elev-/foresattinnspill og oppfølging.
3. Ved avtalt oppfølgingsdato vises hva som er gjort, hva som mangler og om tiltak må endres.

### Status og overganger

Et fravær kan være registrert, avklart eller korrigert; oppfølgingen har egen status. En avsluttet oppfølgingsoppgave betyr ikke at elevens fraværsutfordring er løst.

### Automatikk og menneskelige valg

Programmet avstemmer registreringer og fremhever mønstre etter skolens avklarte regler. Ansvarlig vurderer årsaker og tiltak; systemet stiller ingen diagnose eller automatisk risikoklassifisering.

### Når noe mangler eller feiler

Motstrid mellom import og manuell føring vises med begge kilder. Identiske importhendelser skal ikke doble fraværet, og manglende import skal vises som ukjent fremfor null fravær.

### Resultat

- Fraværsoversikt og oppfølgingsforløp med tydelig ansvar.

### Regler og avvik

- Elevfravær, avlyst økt og manglende lærerressurs er ulike hendelser med forskjellige oppfølgingsbehov.
- Systemet kan varsle om registrerte mønstre, men skal ikke utlede diagnose eller årsak fra fravær alene.

### Akseptansekriterier

- Samme fraværsregistrering importert flere ganger gir én gjeldende oppføring med kildeversjoner.
- En avlyst spesialpedagogisk økt registreres ikke som elevfravær når eleven var på skolen.

**Eksempel:** Læreren ser at eleven ofte mister samme aktivitet, undersøker årsaken og avtaler et konkret tiltak med ny oppfølgingsdato.

**Avhengigheter:** [F02](#f02), [F06](#f06), [F15](#f15), [F22](#f22).

**Første leveranse og utvidelser:** P5: registrering, avstemming og oppfølging. Løpende synkronisering med fraværssystem inngår i P7.

**Til faglig gjennomgang:** Hvor føres fravær i dag, og hvilke situasjoner utløser faktisk oppfølging hos dere?

Domene: BC12. Første leveranse: P5. Kravkoblinger: L031, L033, L043.

<a id="f24"></a>

## F24 Skolemiljø og aktivitetsplan

Egen begrenset sak med varsel, undersøkelser, elevens syn, tiltak, ansvar og evaluering. Dokumenter faktisk handling; rute saker om ansatte til korrekt mottaker.

**Brukere:** Alle ansatte som melder fra, Ansvarlig skoleleder, Tildelte saksmedarbeidere.

**Når brukes den:** Når skolen får kjennskap til et mulig utrygt skolemiljø eller følger opp tiltak.

### Inndata

- Bekymring, tidspunkt, berørte personer og faktisk varsling.
- Undersøkelser, elevens syn, problemforståelse, tiltak, ansvarlige og evalueringsdatoer.

### Arbeidsflate og handlinger

- Et separat saksrom viser mottatt bekymring, ansvarlig, elevens opplevelse, undersøkelser og aktivitetsplan. Skjermet innhold inngår ikke i den vanlige elevtidslinjen for ansatte uten sakstilgang.
- Aktivitetsplanen redigeres med problem som skal løses, tiltak, ansvar, tid og evaluering. Ansvarlig registrerer utførte handlinger og elevens opplevelse ved oppfølging direkte på planen.

### Slik fungerer det

1. Ansatt registrerer bekymringen i en egen begrenset sak og ser riktig varslingsvei.
2. Ansvarlig følger undersøkelser og lager en konkret aktivitetsplan med tiltak og ansvar.
3. Utførte handlinger registreres separat fra planen; ved evaluering vurderes elevens situasjon og behov for videre tiltak.

### Status og overganger

Saken viser mottatt, varslet, under undersøkelse, tiltak pågår og til evaluering. Avslutning krever ansvarlig vurdering; en ferdig plan lukker ikke saken automatisk.

### Automatikk og menneskelige valg

Programmet støtter struktur, varsling og oppfølging etter avklart regelprofil. Ansatte utfører nødvendige handlinger, undersøker og vurderer om tiltakene hjelper.

### Når noe mangler eller feiler

Hvis vanlig varslingsvei ikke er egnet, skal godkjent alternativ være synlig. Manglende felter eller dokumentgenerering må ikke hindre faktisk varsling; handling utenfor programmet kan registreres etterpå.

### Resultat

- Beskyttet saksforløp, aktivitetsplan og dokumentasjon av faktisk oppfølging.

### Regler og avvik

- Saker som gjelder ansatte eller leder må kunne gå til riktig overordnet uten å bli synlige for den saken gjelder.
- Tilgang til undervisningsnotater gir ikke automatisk tilgang til skolemiljøsaken eller omvendt.

### Akseptansekriterier

- Opprettelse av en plan setter ikke tiltakene til gjennomført.
- En sak om nærmeste leder følger konfigurert alternativ mottakervei og stopper ikke i vedkommendes godkjenningskø.

**Eksempel:** En lærer registrerer elevens opplevelse; rektor fordeler undersøkelser og følger opp om de avtalte tiltakene faktisk virker.

**Avhengigheter:** [F01](#f01), [F06](#f06), [F27](#f27), [F28](#f28).

**Første leveranse og utvidelser:** P6: eget saksrom, varslingsvei, aktivitetsplan og evaluering.

**Til faglig gjennomgang:** Hvordan varsles og fordeles slike saker i dag, inkludert saker som gjelder ansatte eller ledelsen?

Domene: BC13. Første leveranse: P6. Kravkoblinger: L001, L034, L035, L036, L037, L077, L079.

<a id="f25"></a>

## F25 Bekymring, barnevern og akutt oppfølging

Beskyttet dokumentasjon, ansvarlig avsenders vurdering, riktige kontaktpunkter og registrering av melding/handling. Akutte og personlige plikter skal ikke forsinkes av AI eller krav om rektorgodkjenning.

**Brukere:** Ansatt med bekymring eller personlig meldeplikt, Autorisert støtteperson.

**Når brukes den:** Ved alvorlig bekymring, vurdering av meldeplikt eller behov for akutt handling.

### Inndata

- Konkrete observasjoner/opplysninger, kilde og tidspunkt.
- Ansvarlig persons vurdering, kontaktpunkt og faktisk handling eller melding.

### Arbeidsflate og handlinger

- Handlingsbildet viser skolens avklarte kontaktveier og hvem den ansatte kan kontakte. Et beskyttet skjema skiller egne observasjoner, opplysninger fra andre, usikkerhet og faktisk utført kontakt.
- Den ansvarlige kan samle nødvendig grunnlag og lage et utkast til melding med mottaker og formål. Foresatte og det ordinære elevteamet legges ikke automatisk til som mottakere.

### Slik fungerer det

1. Brukeren får tydelig tilgang til relevante kontaktveier og kan handle uten å vente på dokumentgenerering.
2. Nødvendig faktagrunnlag registreres i en beskyttet sak; eventuelt utkast gjennomgås av den ansvarlige avsenderen.
3. Faktisk melding og kontakt registreres med mottaker og tidspunkt, og videre oppfølging gis til rett ansvarlig.

### Status og overganger

Registrert bekymring, forberedt melding, faktisk kontakt eller sending og videre oppfølging er separate statuser. En lagret tekst skal aldri fremstå som en allerede levert melding.

### Automatikk og menneskelige valg

Programmet kan ordne dokumentert informasjon og minne om oppfølging. Den ansvarlige vurderer og handler innenfor sin plikt; AI avgjør ikke om et barn er utsatt eller om melding skal sendes.

### Når noe mangler eller feiler

Ved hast eller utilgjengelig system brukes etablerte kontaktveier, og faktisk handling dokumenteres når det er mulig. Normal dokumentgodkjenning skal ikke bli en ventekø for nødvendig personlig handling.

### Resultat

- Avgrenset bekymringsgrunnlag, meldings-/handlingsspor og oppfølgingsoppgaver.

### Regler og avvik

- AI avgjør ikke om det foreligger omsorgssvikt eller en personlig meldeplikt.
- Akutte og personlige plikter krever ikke ordinær rektorgodkjenning i programmet. Foresatte kopieres ikke automatisk.

### Akseptansekriterier

- Brukeren kan registrere en allerede utført akutt handling etterpå uten at systemet krever et forhåndsgodkjent utkast.
- En vanlig e-postoppsummering i F20 henter ikke automatisk inn bekymringssakens innhold.

**Eksempel:** En ansatt kontakter riktig tjeneste og dokumenterer deretter hva som ble formidlet og hvilke oppfølgingshandlinger som er avtalt.

**Avhengigheter:** [F01](#f01), [F06](#f06), [F27](#f27), [F28](#f28).

**Første leveranse og utvidelser:** P6: beskyttet dokumentasjon og handlingsspor med egne ruter. Nødvendig manuell handling er alltid mulig uten systemet.

**Til faglig gjennomgang:** Hvilke støtte- og kontaktveier skal være tilgjengelige uten å forsinke den ansvarlige ansattes handling?

Domene: BC13. Første leveranse: P6. Kravkoblinger: L034, L036, L038, L039, L047.

<a id="f26"></a>

## F26 Fysiske inngrep og forebygging

Egen hendelsesregistrering med beskrivelse, inngrep, elevens syn og faktisk varsling. Gjentatte/alvorlige hendelser følges opp i riktig organisatorisk løp.

**Brukere:** Involvert ansatt, Rektor, Ansvarlig oppfølger.

**Når brukes den:** Etter et fysisk inngrep eller ved gjennomgang av forebyggende tiltak.

### Inndata

- Tid, sted, hendelsesforløp, hva som ble gjort og hvem som var involvert.
- Elevens egen beskrivelse, faktisk varsling og relevante oppfølgingspunkter.

### Arbeidsflate og handlinger

- Hendelsesskjemaet viser tidspunkt, sted, involverte roller, situasjonen før og under hendelsen, varighet og det som faktisk ble gjort. Elevens syn og observerte følger registreres som egne opplysninger.
- Ansvarlig ser nødvendige varslings- og dokumentasjonsoppgaver etter skolens avklarte regler og kan knytte forebyggende oppfølging til hendelsen. Gjentakelser kan gjennomgås innenfor sakstilgangen.

### Slik fungerer det

1. Ansatt fyller ut et eget hendelsesskjema med faktiske forhold fremfor en generell øktlogg.
2. Systemet viser manglende nødvendige felt og varslingsoppgaver etter skolens godkjente regelprofil.
3. Ansvarlig gjennomgår hendelsen og følger opp forebygging og eventuelle gjentakelser med avgrenset tilgang.

### Status og overganger

Hendelsen er registrert, under kontroll eller korrigert. Varsling, informasjon og forebyggende tiltak har egne utførelsesstatuser; ferdig hendelsesskjema avslutter ikke disse.

### Automatikk og menneskelige valg

Programmet kan strukturere beskrivelsen og vise manglende dokumentasjon. Ansvarlige vurderer hendelsen og videre tiltak; løsningen gir ikke automatiske konklusjoner om lovlighet eller instrukser for inngrep.

### Når noe mangler eller feiler

Motstridende beskrivelser beholdes med opphav. Etterregistrering viser både hendelsestid og registreringstid, og en manglende kvittering behandles som uavklart varsling.

### Resultat

- Hendelsesregistrering, varslingsspor og avtalte forebyggende tiltak.

### Regler og avvik

- Registrert varslingsbehov og faktisk varsling er separate statuser.
- Programmet gir ikke AI-genererte instruksjoner for fysisk maktbruk og avgjør ikke automatisk om et inngrep var lovlig.

### Akseptansekriterier

- Manglende elevperspektiv vises som et punkt for ansvarlig oppfølging, med mulighet til å beskrive hvorfor det ikke foreligger ennå.
- Gjentatte hendelser kan vises for rett ansvarlig uten å eksponere sakstekst i ordinære elevoppsummeringer.

**Eksempel:** Etter en hendelse registreres faktisk varsling og elevens forklaring, mens et nytt forebyggende tiltak får ansvarlig og oppfølgingstid.

**Avhengigheter:** [F01](#f01), [F06](#f06), [F27](#f27), [F28](#f28).

**Første leveranse og utvidelser:** P6: eget hendelsesskjema, varsling og forebyggende oppfølging.

**Til faglig gjennomgang:** Hvilke lokale skjemaer, varslingsveier og oppfølgingsrutiner skal funksjonen støtte?

Domene: BC13. Første leveranse: P6. Kravkoblinger: L037.

<a id="f27"></a>

## F27 Personvern, tilgang og innsyn

Formålsstyrt tilgang per skole, elev og sak; sikker innlogging og revisjonsspor. Innsyn, retting, begrensning og informasjon til registrerte. Administratortilgang gir ikke automatisk rett til elevinnhold.

**Brukere:** Ansatte innenfor oppdrag, Personvern-/innsynsansvarlig, Autorisert driftspersonell.

**Når brukes den:** Ved enhver tilgang eller deling, og når en registrert ber om innsyn, retting eller annen håndtering.

### Inndata

- Skole-, elev- og sakstilknytning, formål, gjeldende rettigheter og dataklassifisering.
- Forespørsel, identitets-/representasjonsgrunnlag, omfang og relevant tidsregel.

### Arbeidsflate og handlinger

- Personvernarbeidslisten viser innsyns- og rettingshenvendelser med identitetsavklaring, omfang, ansvarlig og tidsgrunnlag. Saksbehandleren kan samle relevante dokumenter og avledninger innenfor sin fullmakt.
- Før utlevering vises en pakke med hva som tas med, skjermes eller krever vurdering, samt begrunnelser. Tilgangshistorikk og berørte rettinger kan undersøkes uten generell adgang til alle elevtekster.

### Slik fungerer det

1. Tilgang kontrolleres ved åpning, søk, generering, eksport og utsending; avslag viser en praktisk avklaringsvei uten å røpe skjermet innhold.
2. Innsynsansvarlig registrerer en forespørsel, avklarer identitet og omfang og får en samlet oversikt over relevante opplysninger og avledninger.
3. Ansvarlig vurderer skjerming, retting eller andre tiltak og registrerer svar og utførelse med sporbar begrunnelse.

### Status og overganger

En henvendelse viser mottatt, identitet eller omfang uavklart, under behandling, klart til kontroll og besvart. Beslutning og faktisk utførelse av retting eller annen handling registreres separat.

### Automatikk og menneskelige valg

Programmet kan finne relevante data, følge opp tidsregler og håndheve tildelt tilgang. Ansvarlig vurderer identitet, andres opplysninger, rettslig grunnlag og hvilken respons som skal gis.

### Når noe mangler eller feiler

Ved uklar representasjon eller tredjepartsopplysninger avgrenses pakken og spørsmålet sendes til ansvarlig. Et avslått oppslag skal ikke røpe innhold eller bekrefte skjermede saksdetaljer.

### Resultat

- Formålsavgrenset tilgang, innsynspakke og spor etter rettighetshåndtering.

### Regler og avvik

- Tekniske logger skal vise hvem som gjorde hva uten å kopiere all sensitiv dokumenttekst.
- Sletting, bevaring og innsyn er ulike vurderinger; en forespørsel gir ikke automatisk fri tilgang eller sletting av alt.

### Akseptansekriterier

- Bytte av elev-ID i en lenke, eksport eller AI-forespørsel gir ikke tilgang til en annen elev.
- En innsynspakke inneholder ikke skjermede opplysninger om andre personer bare fordi de finnes i samme e-posttråd.

**Eksempel:** Ved et innsynskrav finner ansvarlig både originalnotater og relevante genererte oppsummeringer, og vurderer innholdet før utlevering.

**Avhengigheter:** [F01](#f01).

**Første leveranse og utvidelser:** P1: tilgang, revisjonsspor og mottak av forespørsler. Utvidet sammenstilling og gjennomføring følger datatypene i P2–P7.

**Til faglig gjennomgang:** Hvem behandler innsyn og tilgangsavvik, og hvordan godkjennes unntak eller stedfortredertilgang?

Domene: BC14. Første leveranse: P1. Kravkoblinger: L045, L046, L047, L048, L049, L050, L051, L053, L054, L056, L057, L058, L059, L061, L065, L085, L087.

<a id="f28"></a>

## F28 Dokumentforvaltning og arkiv

Dokumentklasser, bevarings-/sletteplan, rettslig sperre, arkivoverføring og kvittering. Slett operative avledninger når grunnlaget krever det. Ingen generell sletting ved skoleårets slutt.

**Brukere:** Dokument-/arkivansvarlig, Saksansvarlig, Autorisert drift.

**Når brukes den:** Når dokument opprettes, ferdigstilles, skal arkiveres eller når en godkjent disponeringsregel utløses.

### Inndata

- Dokumenttype, eier, kildeversjon, saksreferanse og bevarings-/sletteregel.
- Eventuell rettslig sperre, avhengige kopier og kvittering fra autoritativt arkiv.

### Arbeidsflate og handlinger

- Dokumentkortet viser klasse, ansvarlig system, versjon, bevaringsregel og eventuelle sperrer. Arkivoversikten skiller dokumenter klare til overføring fra dokumenter som mangler metadata eller kvittering.
- Før disponering vises nøyaktig hvilke originaler, versjoner og avledninger som omfattes. Ansvarlig kan kontrollere sperrer og registrere godkjent handling; resultatet følges opp per del.

### Slik fungerer det

1. Dokumentet klassifiseres og får en livssyklus; uavklart regel sendes til ansvarlig.
2. Ferdige dokumenter kan overføres til riktig arkiv med metadata og status for mottak.
3. Ved sletting eller annen disponering kontrolleres sperrer, nødvendige avledninger og faktisk resultat; feil blir synlige oppgaver.

### Status og overganger

Arbeidsutkast, ferdig dokument, venter på arkiv, bekreftet mottatt og disponert er ulike statuser. En bevaringssperre har egen gyldighet og begrunnelse.

### Automatikk og menneskelige valg

Programmet anvender godkjente regler, forbereder metadata og utfører avklarte overføringer. Ansvarlig fastsetter dokumentklasse og bevaringsgrunnlag og håndterer unntak.

### Når noe mangler eller feiler

Ukjent regel eller aktiv sperre hindrer automatisk sletting. Manglende arkivkvittering gir avklaringsoppgave, og en delvis mislykket sletting skal ikke vises som fullført.

### Resultat

- Dokumentoversikt med versjoner, bevaringsgrunnlag, sperrer og arkiv-/disponeringsstatus.

### Regler og avvik

- Skoleårsslutt er ikke en generell slettekommando; regelen må passe dokumenttypen og skolen.
- Operative søkeindekser og genererte avledninger må følge vurdert disponering, også etter gjenoppretting fra sikkerhetskopi.

### Akseptansekriterier

- Et arkivkall uten bekreftet mottak merkes ikke som vellykket arkivert.
- En aktiv rettslig sperre stanser berørt sletting og oppgir ansvarlig avklaringsvei.

**Eksempel:** En ferdig årsrapport overføres med riktig metadata, mens arbeidskopier får en separat vurdert livssyklus.

**Avhengigheter:** [F01](#f01), [F06](#f06).

**Første leveranse og utvidelser:** P1: klassifisering, grunnregler og sperrer. P4: rapportlivssyklus; P7: full arkivkobling og kontrollert overføring.

**Til faglig gjennomgang:** Hvilket system er formelt arkiv, og hvilke dokumentklasser og bevaringsregler skal gjelde?

Domene: BC14. Første leveranse: P1. Kravkoblinger: L050, L051, L052, L058, L064, L065.

<a id="f29"></a>

## F29 Ledelsesoversikt og internkontroll

Oppgaver, ansvar, avvik, risiko og oppfølgingsstatus. Vis manglende opplysninger særskilt; et ferdig dokument betyr ikke at elevens rett er oppfylt. Styret og skoleeier får riktig aggregert informasjon.

**Brukere:** Rektor, Skoleeier eller styre, Ansvarlige oppfølgere.

**Når brukes den:** Ved daglig prioritering, internkontroll eller ledelsens gjennomgang.

### Inndata

- Oppgaver, frister, faktiske avvik og utførte oppfølgingshandlinger.
- Aggregerte ressurs- og dokumentasjonsdata med relevant tilgangsgrunnlag.

### Arbeidsflate og handlinger

- Ledelsesbildet viser oppgaver uten eier, frister, avvik og dokumenterte mangler i leveransen. Filtre gjelder periode, organisatorisk område og type avvik; skjermede elevdetaljer krever egen tilgang.
- Leder kan åpne et avvik, tildele tiltak og avtale kontroll av resultat. Sammendraget skal gjøre det mulig å følge ansvar og kapasitet uten å lese alle underliggende elevdokumenter.

### Slik fungerer det

1. Leder ser hva som mangler ansvarlig, nærmer seg frist eller har dokumentert avvik.
2. En sak kan åpnes innenfor fullmakten; leder fordeler tiltak og følger opp utførelse.
3. Ved gjennomgang vurderes om tiltaket løste forholdet; status og begrunnelse oppdateres separat fra dokumentferdigstilling.

### Status og overganger

Avvik viser meldt, vurdert, tiltak besluttet, under oppfølging og effekt vurdert. Lukking begrunnes av ansvarlig; et opplastet dokument alene lukker ikke avviket.

### Automatikk og menneskelige valg

Programmet sammenstiller registrert status og fremhever manglende oppfølging. Leder prioriterer tiltak og vurderer om forholdet faktisk er rettet.

### Når noe mangler eller feiler

Manglende data eller uavklarte regler vises som slike, fremfor grønn samsvarsstatus. Små grupper og skjermede saker begrenses slik at aggregater ikke gir indirekte innsyn.

### Resultat

- Prioritert ledelsesoversikt, avviksforløp og dokumentasjon av internkontroll.

### Regler og avvik

- Ingen data skal vises som grønn status når de nødvendige opplysningene er ukjente.
- Elev- og personalopplysninger aggregeres for eier/styre når detaljinnsyn ikke er nødvendig eller tillatt.

### Akseptansekriterier

- En ferdig rapport lukker ikke automatisk et registrert avvik om manglende undervisning.
- En visning for styret røper ikke identifiserbar sakstekst gjennom små grupper eller filtrering uten særskilt vurdering.

**Eksempel:** Rektor ser at flere planlagte tiltak mangler bemanning, fordeler ansvar og følger den faktiske korrigeringen.

**Avhengigheter:** [F06](#f06), [F15](#f15), [F27](#f27).

**Første leveranse og utvidelser:** P6: ledelsesoversikt og avvikshåndtering. P7: flere organisatoriske rapportområder.

**Til faglig gjennomgang:** Hvilke få indikatorer hjelper ledelsen å handle, og hvilke ville bare skape mer rapportering?

Domene: BC03. Første leveranse: P6. Kravkoblinger: L018, L034, L037, L056, L057, L059, L066, L067, L068, L070, L078, L079, L084, L089.

<a id="f30"></a>

## F30 Offentlig rapportering og administrasjon

Forbered kontrollerte uttrekk til GSI, elevdata, tilsyn og relevante tilskudds-/refusjonsprosesser. Avstem mot skoleadministrative kilder; menneskelig attestasjon og integrasjon etter tilgjengelige grensesnitt.

**Brukere:** Skoleadministrator, Rektor, Skoleeier.

**Når brukes den:** Ved pålagt innrapportering, tilsyn eller relevant tilskudds-/refusjonsprosess.

### Inndata

- Gjeldende rapportspesifikasjon og periode.
- Kontrollerte data fra elev-, bemannings-, vedtaks- og andre autoritative systemer.

### Arbeidsflate og handlinger

- Rapportveiviseren viser aktuell rapporttype, periode, spesifikasjonsversjon og hvilke data programmet kan bidra med. Felt kan åpnes for definisjon, kilde og avstemming mot skolens hovedsystem.
- Kontrollbildet viser manglende felt og avvik før ansvarlig attesterer. En eksport får format, tidspunkt, ansvarlig og dokumentert innleveringsmåte; kvittering knyttes til den konkrete versjonen.

### Slik fungerer det

1. Ansvarlig velger rapporttype og ser definisjon, kilder og hvilke felt programmet kan bidra med.
2. Systemet beregner eller sammenstiller et uttrekk og viser avstemmingsforskjeller og mangler.
3. Ansvarlig attesterer innholdet og eksporterer eller sender via avtalt grensesnitt; innleveringskvittering registreres der den finnes.

### Status og overganger

Uttrekket er under sammenstilling, trenger avstemming, attestert, eksportert eller bekreftet innlevert. En eksportfil betyr ikke at rapporten er sendt til myndigheten.

### Automatikk og menneskelige valg

Programmet beregner og sammenstiller bare felter med avklart definisjon og grunnlag. Ansvarlig avstemmer, attesterer og leverer; tall med ukjent betydning skal ikke fylles automatisk.

### Når noe mangler eller feiler

Hvis mottakerskjema eller definisjon er endret, må den nye spesifikasjonen avklares. Der API mangler, støttes kontrollert eksport og registrering av faktisk manuell innlevering.

### Resultat

- Kontrollert uttrekk, avstemmingsoversikt og faktisk innleveringsstatus.

### Regler og avvik

- Definisjoner og rapportversjoner må gjelde riktig periode; manglende data skal ikke automatisk bli null.
- Et klargjort uttrekk er ikke bevis på at det er levert til myndigheten.

### Akseptansekriterier

- Tall kan spores til kildene og beregningsdefinisjonen som ble brukt i akkurat denne rapportversjonen.
- Uenighet med skoleadministrativt system vises før attestasjon og overskrives ikke i det stille.

**Eksempel:** Administrator forbereder et GSI-grunnlag og får synlige avvik mot elevregisteret som må avklares før innlevering.

**Avhengigheter:** [F06](#f06), [F28](#f28), [F29](#f29), [F32](#f32).

**Første leveranse og utvidelser:** P7: prioriterte uttrekk etter bekreftede spesifikasjoner; manuell innlevering er mulig når det ikke finnes egnet API.

**Til faglig gjennomgang:** Hvilke offentlige uttrekk krever mest manuelt arbeid, og hvilke systemer eier tallene?

Domene: BC03. Første leveranse: P7. Kravkoblinger: L013, L028, L030, L031, L067, L068, L083, L084.

<a id="f31"></a>

## F31 Tilgjengelighet og språk

Tastatur, skjermleser, god lesbarhet, tilgjengelige dokumenter og støtte for bokmål/nynorsk. Oversettelsesutkast og tolkeoppfølging når nødvendig; faglig og språklig kontroll av viktig innhold.

**Brukere:** Alle ansatte, Foresatte som mottakere, Innholdsansvarlige.

**Når brukes den:** I alle skjermbilder, dokumenter og kommunikasjonssituasjoner.

### Inndata

- Brukerens språkvalg og behov for tilgjengelig presentasjon.
- Originaltekst, dokumentstruktur og eventuelle språk-/tolkebehov for mottakeren.

### Arbeidsflate og handlinger

- Alle sentrale skjermbilder har tydelige feltetiketter, synlig tastaturfokus, forståelige feil og tilbakemelding ved lagring. Innhold kan forstørres og brukes på smal skjerm uten at nødvendige handlinger forsvinner.
- Brukeren velger bokmål eller nynorsk i arbeidsflaten. Dokumentets språk og eventuell oversettelse velges separat; original og språkvariant kan sammenlignes ved gjennomgang.

### Slik fungerer det

1. Brukeren skal kunne fullføre sentrale oppgaver med tastatur og hjelpemidler uten å måtte bruke en alternativ mindreverdig arbeidsflyt.
2. Innhold vises med klare felt, lesbare feilbeskjeder og tilgjengelige dokumentmaler.
3. Ved oversettelse opprettes en egen språkvariant; en kompetent person kontrollerer viktig innhold før bruk eller deling.

### Status og overganger

En språkvariant er utkast, til språkkontroll eller godkjent for en bestemt innholdsversjon. Når originalen endres, vises at oversettelsen trenger ny kontroll.

### Automatikk og menneskelige valg

Programmet følger brukerens språkvalg og kan foreslå oversettelse der tjenesten er tilgjengelig. Kompetent person kontrollerer viktig innhold før deling; en oversatt tekst arver ikke automatisk godkjenning.

### Når noe mangler eller feiler

Feil beskriver hvilket felt som trenger retting, uten at utfylt innhold går tapt. Manglende oversettelse vises tydelig med tilgang til originalen, fremfor en språkvariant som ser ferdig ut.

### Resultat

- Tilgjengelige arbeidsflater og dokumenter, språkvarianter og eventuell tolkeoppfølging.

### Regler og avvik

- Bokmål/nynorsk og språkvalg må gjelde både redigering, feilbeskjeder og relevante eksportmaler.
- En oversettelse arver ikke automatisk godkjenning fra originalen, og AI-oversettelse erstatter ikke nødvendig kvalifisert kommunikasjon.

### Akseptansekriterier

- En bruker kan registrere notat, gjennomgå kilde og godkjenne en økt med bare tastatur.
- Mottakerens dokument har logisk leserekkefølge og tydelig struktur ved skjermleserprøving.

**Eksempel:** En lærer bruker nynorsk i arbeidsflaten og kontrollerer en oversatt foresatt-e-post side om side med originalen.

**Avhengigheter:** [F01](#f01).

**Første leveranse og utvidelser:** P1: tilgjengelig grunnflate og språkstruktur. Hver fase må verifisere nye skjermbilder og dokumenttyper; flere språk følger konkrete behov.

**Til faglig gjennomgang:** Hvilke språk og hjelpemidler må inngå i pilotens faktiske brukertester?

Domene: BC01. Første leveranse: P1. Kravkoblinger: L069, L071, L085.

<a id="f32"></a>

## F32 Integrasjoner og datautveksling

Feide/annen identitet, skoleadministrasjon, LMS, e-post, kalender, dokumentarkiv og sikker post. Avtaler, tillatelser, minimalt datatilfang, dublettkontroll og manuell import/eksport som reserve.

**Brukere:** Skoleadministrator, Integrasjonsansvarlig, Ansatte som bruker import/eksport.

**Når brukes den:** Ved oppsett av en systemkobling, synkronisering eller kontrollert manuell utveksling.

### Inndata

- Avtalt system, skole, datatyper, tilgangsomfang og hvilken kilde som er autoritativ.
- Eksterne identifikatorer, filformat/API-versjon, siste synkroniseringspunkt og feilstatus.

### Arbeidsflate og handlinger

- Integrasjonsoversikten viser tilkoblet system, avtalte datatyper, rettigheter, sist vellykkede kjøring og ansvarlig. Administrator kan teste en avgrenset forbindelse, pause den eller trekke tilgangen tilbake.
- Importgjennomgangen viser ekstern identitet, foreslått intern kobling og konkrete endringer. Konflikter og delvis feil får en arbeidsliste der ansvarlig velger hva som skal behandles på nytt.

### Slik fungerer det

1. Administrator aktiverer bare godkjente datatyper og kontrollerer kobling mellom eksterne og interne identiteter.
2. Import kjøres med forhåndsvisning der det er nødvendig; endringer avstemmes og konflikter sendes til ansvarlig.
3. Systemet viser siste vellykkede overføring, feil og mulig manuell reserve, og kan pauses eller frakobles.

### Status og overganger

En kobling er ikke konfigurert, klar, aktiv, pauset eller trenger handling. Hver overføring har egen status, og fravær av nye data skilles fra mislykket import.

### Automatikk og menneskelige valg

Programmet utveksler kun aktiverte datatyper, gjenkjenner gjentatte hendelser og følger opp transportutfall. Administrator avklarer kilder, identiteter og hvilket system som eier en opplysning.

### Når noe mangler eller feiler

Uklart identitetstreff eller motstridende endring settes til kontroll. Ved bortfall vises sist vellykkede synkronisering og avtalt manuell reserve; programmet lager ikke dubletter ved hvert nytt forsøk.

### Resultat

- Avstemt datautveksling med dokumentert eierskap, status og sporbar kobling.

### Regler og avvik

- En kobling gir ikke ansatte eller bakgrunnsjobber større myndighet enn den godkjente behandlingen tillater.
- E-posttilgang må avgrenses til avtalte mapper/kilder; generelle innbokser skal ikke ukritisk importeres.

### Akseptansekriterier

- Gjennomkjøring av samme import oppretter ikke nye kopier av samme elev, melding eller vedtak.
- Frakobling stanser nye overføringer og viser hvem som håndterer gjenværende data og ventende jobber.

**Eksempel:** Elevregisteret oppdaterer gruppetilknytning, mens programmet varsler om en uklar foresattkobling i stedet for å gjette.

**Avhengigheter:** [F01](#f01), [F27](#f27), [F28](#f28), [F34](#f34).

**Første leveranse og utvidelser:** P7: prioriterte identitets-, skole-, e-post-, kalender- og arkivkoblinger. Tidlige faser bruker smale adaptere og kontrollert manuell import.

**Til faglig gjennomgang:** Hvilke eksisterende systemer skal kobles først, og hvilke data skal aldri ha to redigerbare hovedkilder?

Domene: BC16. Første leveranse: P7. Kravkoblinger: L054, L055, L068, L085, L086.

<a id="f33"></a>

## F33 AI med utskiftbar modell og kvalitetskontroll

Serverstyrt gateway for generering, søk, OCR og tale. API i utvikling med syntetiske data, egen server i produksjon. Kilder, modellversjon, evalueringer, kostnadsgrenser og ingen stille ekstern reserve.

**Brukere:** Lærer og spesialpedagog som bestiller forslag, Modell-/driftsansvarlig.

**Når brukes den:** Når en bruker bestiller dokumentlesing, øktforslag, rapporttekst eller annen godkjent AI-operasjon.

### Inndata

- Et avgrenset formål og bare autoriserte kilder som trengs for oppgaven.
- Modell-/promptversjon, behandlingsmiljø, kvalitetskrav og ressursgrenser.

### Arbeidsflate og handlinger

- I den aktuelle arbeidsflyten vises hvilket grunnlag som brukes, at generering pågår og hvilket forslag som er klart til kontroll. Fagpersonen kan åpne kildene og se mangler uten å håndtere modellinnstillinger.
- En separat administrasjonsflate viser godkjent modell, støttede oppgaver, behandlingssted og evalueringer. Ny modell prøves på faste syntetiske eksempler og sammenlignes med gjeldende versjon før aktivering.

### Slik fungerer det

1. Systemet bygger et avgrenset kildegrunnlag etter tilgangskontroll og viser status for genereringen.
2. Modellen returnerer et forslag med kildekoblinger og synlige mangler; resultatet går til menneskelig gjennomgang.
3. Modellansvarlig kan prøve og godkjenne en ny modellversjon mot faste syntetiske eksempler før den aktiveres.

### Status og overganger

En forespørsel er i kø, under behandling, ferdig som ubekreftet forslag, avbrutt eller feilet. Modellversjoner har egne tilstander for utprøving, vurdering, aktiv bruk og tilbaketrekking.

### Automatikk og menneskelige valg

AI kan foreslå tekst, uttrekk, taleutskrift og relevante kilder innenfor godkjent formål. Mennesker bekrefter fakta og faglige vurderinger. Produksjonsbehandling skjer på egen server; eksternt utviklings-API bruker kun syntetiske data.

### Når noe mangler eller feiler

Ved timeout eller utilgjengelig modell beholdes siste lagrede utkast og manuell arbeidsflyt er tilgjengelig der den passer. Systemet bytter aldri stille til en ekstern modell, heller ikke for OCR, tale eller embeddings.

### Resultat

- Gjennomgåelige forslag, sporbar modellkjøring og kvalitets-/driftsstatus.

### Regler og avvik

- Ekstern API brukes i utvikling med syntetiske data. All AI i produksjon skal bruke egen godkjent server, også AI-basert OCR, embeddings og tale når aktivert.
- Ingen stille ekstern reserve, automatisk diagnose, karakterfastsetting eller endring av vedtak. Kildeinstruksjoner skal ikke overstyre systemets regler.

### Akseptansekriterier

- Samme brukerflyt kan bruke en utviklingsadapter og en lokal adapter uten at elev-/planbegrepene endres.
- Ved lokal modellfeil forblir produksjonsdata lokale, og brukeren kan fortsette med manuell redigering.
- Forslag uten støtte for faktapåstander viser manglende grunnlag og blir ikke presentert som bekreftet informasjon.

**Eksempel:** En modelloppgradering prøves mot de samme norske økt- og rapporteksemplene før driftsansvarlig velger å aktivere den.

**Avhengigheter:** [F27](#f27), [F34](#f34).

**Første leveranse og utvidelser:** P2: øktforslag via utviklingsadapter og manuell reserve. P4: dokumentutkast. Lokal produksjonsbehandling må være klar før AI-pilot med virkelige elevdata.

**Til faglig gjennomgang:** Hvilke konkrete feil ville gjøre et AI-forslag ubrukelig, og hvilken kvalitet må en lokal modell oppnå?

Domene: BC15. Første leveranse: P2. Kravkoblinger: L046, L052, L053, L054, L055, L060, L086, L087.

<a id="f34"></a>

## F34 Drift, sikkerhet og beredskap

Kryptering, nøkkelstyring, sikkerhetskopier, prøvd gjenoppretting, overvåking uten elevtekst, oppdateringer og hendelseshåndtering. Manuelle arbeidsflyter skal fungere ved AI-feil.

**Brukere:** Driftsansvarlig, Sikkerhetsansvarlig, Skoleledelse.

**Når brukes den:** Ved daglig drift, oppdatering, feil eller gjenoppretting.

### Inndata

- Godkjent driftsoppsett, nøkkel-/tilgangsforvaltning og avtalte gjenopprettingsmål.
- Teknisk status, sikkerhetskopier, hendelser og ansvarlige kontaktpunkter.

### Arbeidsflate og handlinger

- Driftsbildet viser tilgjengelighet, køer, feiltyper, sikkerhetskopier og tidspunkt for siste prøvde gjenoppretting. Vanlige driftslogger inneholder tekniske referanser fremfor elevtekst.
- Driftsansvarlig kan følge en hendelse, se hvilke tjenester som er berørt og dokumentere tiltak og gjenoppretting. Rutiner for oppdatering og reservearbeid knyttes til faktisk testresultat.

### Slik fungerer det

1. Driftsansvarlig ser tjenestestatus, køer og feil uten at elevtekst kopieres til generelle driftslogger.
2. Sikkerhetskopier og oppdateringer følges opp etter avtalt rutine, med praktisk prøving av gjenoppretting.
3. Ved hendelse avgrenses tilgang og berørte operasjoner; ansvarlig følger teknisk retting og nødvendig organisatorisk håndtering.

### Status og overganger

Tjenester vises som tilgjengelige, redusert eller utilgjengelige. En sikkerhetskopi er opprettet eller feilet, mens verifisert gjenoppretting registreres separat.

### Automatikk og menneskelige valg

Programmet overvåker teknisk tilstand og kjører avtalte sikkerhetskopier. Driftsansvarlig vurderer hendelser, godkjenner relevante endringer og bekrefter at gjenoppretting er prøvd.

### Når noe mangler eller feiler

Ved bortfall får brukeren vite hvilke handlinger som er utilgjengelige og om lagring er bekreftet. Arbeid som ikke er registrert i systemet må avstemmes ved gjenoppretting; ingen skjult påstand om offline-lagring.

### Resultat

- Overvåket tjeneste, dokumentert gjenoppretting og håndterte drifts-/sikkerhetshendelser.

### Regler og avvik

- AI-feil skal ikke blokkere all manuell planlegging og notatføring når resten av tjenesten fungerer.
- Gjenoppretting må også ta hensyn til etterfølgende tilgangsendringer, rettelser og disposisjonsbeslutninger.

### Akseptansekriterier

- En prøvd gjenoppretting kan vise at dokumenter, nøkler, rettigheter og nødvendige disposisjonsoppgaver henger sammen.
- Meldingskøens status viser ukjent leveringsutfall fremfor å sende alt på nytt etter omstart.

**Eksempel:** Ved modellstans kan læreren fortsatt åpne det sist godkjente assistentkortet og registrere gjennomføringen.

**Avhengigheter:** [F01](#f01).

**Første leveranse og utvidelser:** P1: sikker grunnplattform og prøvd reservekopi. Driftskrav utvides per fase; P8 fullfører produksjonsverifisering.

**Til faglig gjennomgang:** Hvem eier drift og beredskap, og hvor lenge kan skolen tåle at hver sentral funksjon er utilgjengelig?

Domene: BC15. Første leveranse: P1. Kravkoblinger: L052, L054, L055, L058, L059, L087.

<a id="f35"></a>

## F35 Skoleår, overganger og skolebytte

Oppdater tilknytning, rettigheter, planer og krav ved nytt år/trinn/skole. Selektiv overføringspakke med konkret delingsgrunnlag, nødvendig innhold, mottakerkontroll og kvittering.

**Brukere:** Skoleadministrator, Kontaktlærer, Spesialpedagog, Overføringsansvarlig.

**Når brukes den:** Ved nytt skoleår, trinn-/gruppeskifte eller overgang til en annen skole.

### Inndata

- Nye tilknytninger, datoer, aktive planer og relevante overføringsbehov.
- Mottakerskole, konkret delingsgrunnlag, nødvendig innhold og eventuelle begrensninger.

### Arbeidsflate og handlinger

- Overgangsveiviseren viser elever, nye grupper, aktive planer, åpne oppgaver og tilganger som utløper. Ansvarlig får en forhåndsvisning før endringer for nytt skoleår tas i bruk.
- Ved skolebytte bygges en separat pakke med valgte opplysninger, formål, mottaker og vurdert delingsgrunnlag. Brukeren kan se nøyaktig hvilke dokumentversjoner som følger med.

### Slik fungerer det

1. Års-/overgangsveiviseren viser hvilke tilganger, planer og oppgaver som må videreføres eller avklares.
2. Ansvarlig velger nødvendige opplysninger til en separat overføringspakke og kontrollerer grunnlag og mottaker.
3. Faktisk overføring og mottak registreres; historiske tilknytninger beholdes etter riktig dokumentregel.

### Status og overganger

En overgang er planlagt, under kontroll eller gjennomført; overføringspakken har egne godkjennings- og mottaksstatuser. Gamle skoletilknytninger blir historiske med riktige datoer.

### Automatikk og menneskelige valg

Programmet finner elementer som må videreføres eller avklares og forbereder en selektiv pakke. Ansvarlig bestemmer nye oppdrag, nødvendig innhold og hvem som kan motta det.

### Når noe mangler eller feiler

Åpne saker og uavklart delingsgrunnlag blir konkrete punkter til ansvarlig. Et skolebytte kopierer ikke automatisk hele elevmappen eller gir den nye skolen tilgang til skjermede saker.

### Resultat

- Oppdaterte tilknytninger, overgangsoppgaver og kontrollert overføringspakke.

### Regler og avvik

- Skolebytte gir ikke automatisk ny skole tilgang til hele elevmappen.
- Nytt skoleår nullstiller ikke utestående oppfølging eller sletter historiske vedtak og mål.

### Akseptansekriterier

- Gammel lærertilknytning utløper som planlagt uten å endre tidligere forfatter- og godkjenningsspor.
- Overføringspakken viser hvilke opplysninger som deles på hvilket grunnlag, og kan ikke regnes som mottatt uten relevant bekreftelse.

**Eksempel:** Ved overgang til ungdomstrinnet videreføres nødvendige støtteoppgaver mens tilgang og deling vurderes særskilt for mottakerskolen.

**Avhengigheter:** [F01](#f01), [F06](#f06), [F21](#f21), [F28](#f28).

**Første leveranse og utvidelser:** P7: årsveiviser og selektive skoleoverføringer. Grunnleggende datert tilknytning finnes i P1.

**Til faglig gjennomgang:** Hvilken informasjon trenger mottakerskolen faktisk, og hvem godkjenner hver type overføring?

Domene: BC14. Første leveranse: P7. Kravkoblinger: L019, L042, L047, L061, L064.

<a id="f36"></a>

## F36 Ressurser og arbeidsbelastning

Kompetanse, tilgjengelighet, planleggingstid, veiledning, pauser og faktiske ressursbehov. Foreslå avlastning og synliggjør kapasitetsmangel; støtt gjeldende arbeidsavtaler og lokale arbeidstidsregler.

**Brukere:** Rektor, Spesialpedagog, Timeplanansvarlig.

**Når brukes den:** Ved ressursplanlegging, kapasitetsmangel eller endret bemanning.

### Inndata

- Tilgjengelig arbeidstid, kvalifikasjoner, oppdrag, forberedelse, veiledning og pauser.
- Undervisningsbehov, lokalt avklarte arbeidstidsregler og ressursreservasjoner.

### Arbeidsflate og handlinger

- Kapasitetsbildet viser tilgjengelig tid og kompetanse sammen med undervisning, forberedelse, veiledning, møter og forflytning. Planlagt ressursbruk og registrert faktisk tidsbruk holdes atskilt.
- Leder kan sammenligne alternative fordelinger og se hvilke oppgaver eller elevbehov som blir udekket. Et valgt scenario kan brukes som grunnlag for timeplanforslag uten å publiseres automatisk.

### Slik fungerer det

1. Leder registrerer tilgjengelig kapasitet og nødvendig tid rundt undervisningen.
2. Systemet sammenstiller oppdrag og behov med kapasitet og viser konkret underdekning.
3. Leder prøver alternative fordelinger som kan brukes av F14, og følger opp forhold som krever bemanning eller endret organisering.

### Status og overganger

Scenarioer er utkast, sammenligningsalternativer eller besluttet plan. Underdekning beholdes som synlig forhold med ansvarlig oppfølging.

### Automatikk og menneskelige valg

Programmet summerer behov, tid og tilgjengelighet og viser konflikter. Leder avgjør bemanning og organisering; beregningene fastsetter ikke automatisk hvem som skal miste støtte.

### Når noe mangler eller feiler

Ukjent kapasitet merkes som ukjent, ikke ledig tid. Samtidig arbeid med en elevgruppe skal telle riktig for den ansattes kalender og skilles fra registrert støtte til hver elev.

### Resultat

- Ressursoversikt og forklarte kapasitetsbehov, inkludert forberedelse og veiledning.

### Regler og avvik

- Planleggingstid og veiledning skal ikke behandles som ubegrensede gratisressurser.
- Funksjonen støtter planlegging og avlastning; den skal ikke gi skjult individuell prestasjonsrangering.

### Akseptansekriterier

- Et oppdrag med 30 minutters økt og avtalt forberedelse belaster begge delene av kapasiteten.
- Manglende kvalifisert bemanning vises som et udekket behov, ikke som en automatisk tildeling til en ukvalifisert erstatter.

**Eksempel:** Leder ser at assistentoppfølging krever veiledningstid hos pedagogen før en ny gruppe kan settes inn i planen.

**Avhengigheter:** [F01](#f01), [F07](#f07).

**Første leveranse og utvidelser:** P5: kapasitet, kompetanse og belastning koblet til timeplan. Eventuell HR-import kommer via F32.

**Til faglig gjennomgang:** Hvilken tid rundt elevøktene mangler i dagens ressursoversikter?

Domene: BC08. Første leveranse: P5. Kravkoblinger: L005, L014, L081, L082, L083.

<a id="f37"></a>

## F37 Betingede leder- og driftsplikter

Krav- og oppfølgingsmoduler for opptak, skyss, SFO, helse/miljø, forsikring, bemanning, anskaffelser og økonomi der de gjelder. Integrer med fagsystemer og behold ansvar hos rett funksjon.

**Brukere:** Rektor, Skoleeier eller styre, Utpekt administrativ ansvarlig.

**Når brukes den:** Når et betinget leder-/driftsområde gjelder skolen eller en konkret sak.

### Inndata

- Bekreftet anvendelse av relevante områder: opptak, skyss, SFO, fysisk miljø, bemanning, forsikring, anskaffelser og økonomi.
- Ansvar, kildesystem, dokumentkrav, hendelser og lokale rutiner.

### Arbeidsflate og handlinger

- Skoleledelsen ser en oversikt over betingede områder og om ansvar, regelprofil og hovedsystem er avklart. Bare aktiverte områder får operative oppgaver og relevante skjemaer.
- Hver oppgave viser konkret handling, dokumentasjonsbehov og lenke til riktig fagsystem der arbeidet skjer eksternt. Brukeren kan registrere referanse og utført handling uten å kopiere unødvendige elev- eller personalopplysninger.

### Slik fungerer det

1. Leder aktiverer et konkret område først når ansvar og anvendelige regler er avklart.
2. Hver oppgave får formål, eier, fristgrunnlag og lenke til riktig fagsystem eller nødvendig dokumentasjon.
3. Ansvarlig registrerer gjennomført oppfølging; ledelsen ser uavklarte forhold og avvik uten å samle unødvendige detaljdata i elevsystemet.

### Status og overganger

Et område er uavklart, vurdert ikke relevant med begrunnelse eller aktivert. Oppgaver har egne statuser for utførelse og kontroll; en aktivering betyr ikke at området er ferdig dekket.

### Automatikk og menneskelige valg

Programmet oppretter og følger opp oppgaver fra godkjent oppsett. Skoleleder avklarer anvendelse, ansvar og systemgrense; innholdet i en ekstern fagprosess overtas ikke automatisk.

### Når noe mangler eller feiler

Ved manglende ansvarlig eller ukjent regelgrunnlag vises avklaringsbehov. Dersom en ekstern oppgave bare er lenket, må faktisk gjennomføring dokumenteres før den vises som utført.

### Resultat

- Avgrensede administrative arbeidslister og koblinger til etablerte fagsystemer.

### Regler og avvik

- Dette er flere betingede delområder; de skal ikke presenteres som en ferdig universell samsvarsmodul.
- Lønn, regnskap, helsebehandling og teknisk byggdrift forblir hos ansvarlige funksjoner med mindre en konkret integrasjon er avtalt.

### Akseptansekriterier

- Et område uten avklart regel eller eier vises som uavklart og kan ikke erklæres oppfylt automatisk.
- Et kontrollpunkt kan referere til et autoritativt eksternt system uten å kopiere hele saksmappen.

**Eksempel:** Et skyssbehov gir en oppgave til rett administrativ rolle med nødvendige elevopplysninger og kontakt til vedtaksprosessen.

**Avhengigheter:** [F06](#f06), [F29](#f29), [F32](#f32).

**Første leveranse og utvidelser:** P7: hvert godkjent delområde leveres separat med egen brukerflyt eller avtalt ekstern systemgrense.

**Til faglig gjennomgang:** Hvilke av disse områdene skal programmet støtte direkte, og hvilke trenger bare en oppfølgingslenke?

Domene: BC03. Første leveranse: P7. Kravkoblinger: L066, L074, L075, L076, L077, L078, L079, L080, L081, L082, L083, L084, L085, L089.

<a id="f38"></a>

## F38 Varsler, fritak, klager og partsrettigheter

Riktig myndighet, saksgrunnlag, høring, begrunnelse, underretning, frist og klagepakke. Skill klage på vedtak, gjennomføring og sluttvurdering; tidsberegning er regelstyrt.

**Brukere:** Autorisert saksbehandler, Rektor, Faglærer ved relevant vurderingssak.

**Når brukes den:** Ved varselbehov, søknad om fritak, klage eller annen partsrettighet.

### Inndata

- Sakstype, relevant beslutning/vurdering, tidspunkt for underretning og partsforhold.
- Faktagrunnlag, aktuelt regelgrunnlag og ansvarlig myndighet.

### Arbeidsflate og handlinger

- Saksveiviseren starter med varsel, fritak, klage eller annen definert sakstype. Den viser riktige parter, beslutningsmyndighet, nødvendig grunnlag og fristens utløser for akkurat den prosessen.
- Saksbehandleren kan samle vedlegg, registrere partens innspill, forberede begrunnelse og se en mottakertilpasset pakke. Oversending og underretning får egne registreringer.

### Slik fungerer det

1. Brukeren velger riktig sakstype og får en sjekkliste for denne prosessen.
2. Systemet sammenstiller grunnlag og forslag til begrunnelse eller klagepakke, og viser hvilke frister som er beregnet fra hvilke hendelser.
3. Ansvarlig gjennomgår, treffer beslutning innenfor sin myndighet eller oversender til rett instans, og registrerer faktisk underretning og videre status.

### Status og overganger

Saken viser mottatt, under avklaring, under behandling, avgjort eller oversendt og avsluttet. Partens tilgang og faktisk underretning følger egne, daterte vurderinger.

### Automatikk og menneskelige valg

Programmet foreslår struktur og beregner tidsregler fra bekreftede hendelser og riktig sakstype. Ansvarlig vurderer innhold, beslutning og eventuell videre oversending.

### Når noe mangler eller feiler

Ukjent mottaksdato eller klagetype stopper en påstått sikker fristberegning. Programmet ber om avklaring og bruker ikke en generell klagefrist for alle prosesser.

### Resultat

- Saksspesifikt varsel, vedtaks-/klagegrunnlag og sporbar prosess.

### Regler og avvik

- Klage på enkeltvedtak, gjennomføring og sluttvurdering deler ikke automatisk frist eller avgjørelsesmyndighet.
- Et registrert fritak må angi hva det gjelder; fritak fra vurdering er ikke automatisk fritak fra opplæring.

### Akseptansekriterier

- Endret underretningsdato viser behov for ny fristvurdering og omskriver ikke tidligere dokumentasjon i det stille.
- En bruker uten vedtaksmyndighet kan klargjøre saken, men kan ikke registrere et eget vedtak som gyldig myndighetsavgjørelse.

**Eksempel:** En klage på gjennomføringen knyttes til dokumentert bortfall og riktig prosess, uten å bli behandlet som en karakterklage.

**Avhengigheter:** [F06](#f06), [F07](#f07), [F21](#f21), [F28](#f28).

**Første leveranse og utvidelser:** P4: prioriterte varsel-, fritaks- og klagetyper med eksplisitte regelprofiler.

**Til faglig gjennomgang:** Hvilke sakstyper håndterer skolen selv, og hvilke skal alltid videre til kommunen eller annen instans?

Domene: BC04. Første leveranse: P4. Kravkoblinger: L003, L024, L027, L028, L029, L030, L032, L044, L062, L063, L065, L073, L074, L077, L088.

<a id="f39"></a>

## F39 Tilbakemelding og kontroll av forslag

Pedagogen kan godta, endre, avvise og begrunne forslag. Oppdateringer av elevgrunnlaget viser berørte planer og rapporter; brukeren velger hva som skal endres.

**Brukere:** Alle pedagoger som vurderer forslag, Faglig ansvarlig.

**Når brukes den:** Når et forslag skal vurderes, eller kildemateriale endres etter at det er brukt.

### Inndata

- Forslag, kildeversjoner, tidligere redigeringer og brukerens begrunnelse.
- Endringer i vedtak, mål, opplysninger eller ressursgrunnlag som kan påvirke eksisterende innhold.

### Arbeidsflate og handlinger

- Forslaget har tydelige valg for å bruke, redigere eller forkaste innhold, med kildevisning tilgjengelig. Kort tilbakemelding er valgfri med mindre en konkret faglig kontroll krever begrunnelse.
- Ved ny generering vises forskjeller fra brukerens gjeldende tekst. Brukeren velger hvilke endringer som skal tas inn; egne formuleringer skal ikke forsvinne ved et nytt modellforslag.

### Slik fungerer det

1. Brukeren kan godta, redigere eller forkaste forslaget og eventuelt gi en kort begrunnelse.
2. Ved ny generering vises forskjeller og hvilke egne endringer som vil bli berørt før brukeren velger versjon.
3. Når en kilde rettes, viser systemet berørte økter, kort og dokumentutkast; ansvarlig velger nødvendig revisjon eller oppfølging av allerede delte dokumenter.

### Status og overganger

Forslag viser ubekreftet, gjennomgått, delvis brukt eller forkastet. Når en kilde endres, kan det avledede dokumentet få status trenger ny kontroll uten at det gamle forslaget slettes.

### Automatikk og menneskelige valg

Programmet sammenligner versjoner og identifiserer berørte kilder. Pedagogen avgjør om forslaget er egnet og hvilke rettinger som er nødvendige; en positiv tilbakemelding er ikke en generell godkjenning av fremtidige forslag.

### Når noe mangler eller feiler

En svak eller manglende kilde kan fjernes fra grunnlaget, og brukeren kan fortsette manuelt. Dersom teksten allerede er delt, opprettes oppfølging fremfor at den historiske versjonen endres i det stille.

### Resultat

- Sporbar pedagogisk beslutning og kontrollert oppdatering av avhengig innhold.

### Regler og avvik

- Avvisning av et AI-forslag endrer ikke de underliggende elevopplysningene.
- Godkjenning gjelder en eksakt versjon; en ny modellkjøring kan ikke stille erstatte godkjent innhold.

### Akseptansekriterier

- Pedagogens manuelt endrede støtteinstruksjon beholdes til vedkommende uttrykkelig velger en annen versjon.
- Retting av feil elevkobling gjør berørte operative forslag utilgjengelige eller utdaterte og viser nødvendig videre oppfølging.

**Eksempel:** Pedagogen avviser en for vanskelig aktivitet og beholder sitt eget alternativ; neste generering overskriver det ikke automatisk.

**Avhengigheter:** [F04](#f04), [F05](#f05), [F33](#f33).

**Første leveranse og utvidelser:** P2: kontroll av øktforslag og kilder. P3–P4: samme mønster utvides til IOP, rapporter og e-post.

**Til faglig gjennomgang:** Hvilke endringer skal kreve ny godkjenning, og hvordan bør konsekvenser vises uten å skape varslingsstøy?

Domene: BC07. Første leveranse: P2. Kravkoblinger: L016, L051.

<a id="f40"></a>

## F40 Målbar avlastning

Mål samlet arbeidstid inkludert kontroll, retting og dobbeltføring. Evaluer assistentkort og rapportkvalitet. Bruk aggregert innsikt og frivillige studier, uten rangering av ansatte eller elever.

**Brukere:** Produktansvarlig, Skoleledelse, Frivillige pilotdeltakere.

**Når brukes den:** Ved etablering av pilot, evaluering av en arbeidsflyt eller vesentlig endring i funksjonen.

### Inndata

- Baseline for dagens arbeidsmåte og avtalte målepunkter.
- Samlet oppgavetid, kontroll/korreksjon, dobbeltføring og deltakernes vurdering av nytte.

### Arbeidsflate og handlinger

- Pilotoppsettet definerer oppgavetype og hvordan tid og kvalitet skal sammenlignes før og etter innføring. Deltakere kan registrere forberedelse, kontroll, retting og etterarbeid i samme måling.
- Resultatbildet viser sammenlignbare oppgaver, samlet tidsbruk og kvalitative erfaringer på egnet aggregert nivå. Funksjoner kan vurderes ut fra om de faktisk sparer arbeid og gir brukbart resultat.

### Slik fungerer det

1. Piloten velger konkrete oppgaver, for eksempel forberedelse av økt og kort notatføring.
2. Samme type oppgave måles før og med programmet, inkludert etterarbeid og kvalitetskontroll.
3. Resultater sammenstilles på egnet aggregert nivå og brukes til å forbedre eller utsette funksjoner som ikke avlaster.

### Status og overganger

En måling er planlagt, baseline registrert, prøve gjennomført eller evaluert. Manglende eller ikke sammenlignbare målinger vises som utilstrekkelig grunnlag.

### Automatikk og menneskelige valg

Programmet kan sammenstille frivillig registrerte målinger og beregne forskjeller. Pilotansvarlig vurderer sammenlignbarhet og kvalitet og velger hva som skal forbedres eller utsettes.

### Når noe mangler eller feiler

Få deltakere eller ulik oppgavetyngde skal ikke bli sikre gevinstpåstander eller rangering av ansatte. Første pilot vurderes på undervisningsflyten; e-postmålinger innføres først når den funksjonen tas i bruk.

### Resultat

- Etterprøvbar vurdering av spart arbeid og konkrete forbedringsbehov.

### Regler og avvik

- Lav genereringstid er ikke det samme som spart arbeid; retting, lesing og feiloppfølging skal med.
- Målingen skal ikke skape skjult overvåking, ekstra elevdatafangst eller rangering av ansatte.

### Akseptansekriterier

- En funksjon som sparer fem minutter skriving, men krever ti minutter ekstra kontroll, vises som økt samlet tidsbruk.
- P2 kan evalueres på øktforberedelse, assistentforståelse og notatføring uten at foreldre-e-post er implementert.

**Eksempel:** Piloten sammenligner en vanlig øktforberedelse med og uten programmet og spør assistenten hva som fortsatt var uklart i kortet.

**Avhengigheter:** [F01](#f01).

**Første leveranse og utvidelser:** P2: baseline og praktisk evaluering av første undervisningsflyt. Senere faser måler rapport- og kommunikasjonsarbeid når disse tas i bruk.

**Til faglig gjennomgang:** Hvilke oppgaver bruker dere mest tid på, og hva er en meningsfull reduksjon uten tap av kvalitet?

Domene: BC03. Første leveranse: P2. Kravkoblinger: L067, L082.
