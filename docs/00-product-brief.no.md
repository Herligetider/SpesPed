# Spesped – produktgrunnlag

Arbeidsversjon 0.2 · 8. september 2026. Produktutformingen er oppdatert; lovkildenes kontrolldato er fortsatt 7. september. Alle tidligere foreslåtte funksjoner er beholdt. Dette dokumentet beskriver ønsket produkt; ingen funksjon er implementert ennå.

## Formål og vedtatt omfang

Programmet skal redusere samlet arbeid med planlegging, oppfølging, samarbeid og dokumentasjon for lærere og spesialpedagoger. Skoleledelsen skal få bedre oversikt over ansvar og utestående oppfølging. Gevinsten skal måles etter at tid til kontroll, retting og dobbeltføring er trukket fra.

- Offentlige grunnskoler og private montessoriskoler, 1.–10. trinn.
- Første pilot på montessoriskole; ordinære offentlige regler inngår i modellen fra starten.
- E-postutkast per elev for et valgt fra-/til-intervall, med valgfri gjentakelse av utkast. Ingen fast ukerytme eller automatisk utsending som standard. Bare foresatte som mottakere i første versjon; elevrettet variant beholdes senere.
- Lærere og spesialpedagoger bidrar med notater, e-post fra foresatte, planer, kartlegginger, IOP, vedtak, sakkyndighet og andre relevante dokumenter.
- Systemet lager utkast og samler relevant grunnlag. En faglig kvalifisert person gjennomgår innholdet før formell bruk og utsending.
- Ekstern AI-API kan brukes med syntetiske utviklingsdata. I produksjon skal AI-behandlingen kunne kjøres på brukerens egen server, inkludert dokumentlesing, søk og eventuell tale.

Private skoler godkjent etter opplæringslova kapittel 22 er en egen juridisk kategori. De er registrert som en betinget utvidelse, ikke slått sammen med privatskoler med statstilskudd. Videregående opplæring inngår bare som mottakende overgang, ikke som et ferdig kartlagt eget skoleslag.

## Den daglige arbeidsflyten

1. En ansatt legger inn et notat eller en relevant e-post. Systemet foreslår elev, tema og oppfølgingspunkt.
2. Den ansatte kontrollerer uttrekket. Avsenderens opplysning beholder avsender og dato; den blir ikke automatisk skolens konstaterte faktum.
3. Godkjent informasjon kan brukes i elevoversikt, øktplanlegging, møteforberedelse og rapportutkast uten ny inntasting.
4. Spesialpedagogen velger og tilpasser neste økt. Assistenten får et kort, godkjent opplegg med nødvendig informasjon.
5. Etter økten registreres gjennomføring og et kort notat. Planlagt aktivitet teller ikke som gjennomført aktivitet.
6. Ved behov velger pedagogen en periode og ber om et e-postutkast til foresatte. En valgfri utkastplan kan gjenta klargjøringen med valgt intervall. Vurderings- og rapportutkast følger sine egne behov og frister.
7. Ansvarlig person ser tekst, kilder, mangler, mottakere og vedlegg før godkjenning og uttrykkelig utsending.

Første komplette leveranse stopper ved en gjennomført økt med kort notat som kan brukes ved neste planlegging. Foresatt-e-post og ekstern utsending kommer i P4 og er ikke et krav for denne piloten. Se [det konkrete forløpet for faglig gjennomgang](08-first-workflow-review.no.md).

## Prinsipper som reduserer arbeid

- Registrer én gang og gjenbruk med synlig kilde. Be om presisering bare når det har betydning for neste handling.
- Bruk korte skjemaer, forslag til struktur og automatisk lagring. Fri tekst skal fortsatt være mulig.
- Et dokument kan dekke flere oppgaver når innhold, mottakere og tidspunkt passer, men pliktene følges separat.
- Skill pålagte handlinger, pålagt skriftlig dokumentasjon, lokal rutine og frivillig produktfunksjon.
- Varsle ved relevante hendelser og frister; unngå gjentatte påminnelser om uendret status.
- Gi én arbeidsliste per rolle og en samlet oversikt per elev. Begrens arbeidslisten etter faktisk tilgang og ansvar.
- La manuelle arbeidsflyter fungere ved AI-feil. Opptak av samtaler, automatisk innhenting fra e-post og eksterne utsendinger er særskilte funksjoner med tydelig kontroll.

## Viktige regelmessige forskjeller

IOP gjelder elever med individuelt tilrettelagt opplæring, og må bygge på vedtaket. Den årlige skriftlige evalueringen av ITO er et særskilt dokumentasjonskrav. [Udir om IOP](https://www.udir.no/regelverk-og-tilsyn/skole-og-opplaring/veileder-for-tilpasset-opplaring-og-individuell-tilrettelegging/individuell-opplaringsplan-iop/) og [årlig evaluering](https://www.udir.no/regelverk-og-tilsyn/skole-og-opplaring/veileder-for-tilpasset-opplaring-og-individuell-tilrettelegging/arlig-evaluering-av-utbyttet/).

Halvårsvurdering uten karakter kan være muntlig eller skriftlig. Vi skal ikke presentere en lokal skriftlig rapportmal som et generelt nasjonalt lovkrav. [Udir om halvårsvurdering](https://www.udir.no/eksamen-og-prover/vurdering/underveisvurdering/halvarsvurdering/).

Montessoriskolenes godkjente ungdomsordning innebærer vurdering uten karakter på 8.–9. trinn, med unntak for fag som avsluttes, og uten karakter i orden og oppførsel. Fra skoleåret 2025–2026 er standpunkt eneste sluttvurdering i fag. Skolens godkjenning og gjeldende læreplan må registreres. Vedtaket bruker paragrafnummer fra tidligere forskrift; disse skal ikke ukritisk kopieres inn som nåværende hjemler. [Udirs godkjenningsvedtak](https://montessorinorge.no/wp-content/uploads/2025/09/Vedtak-om-godkjenning-av-vurderingsordning-for-montessoriskolenes-ungdomstrinn.pdf).

## Dokumenttyper og riktig kontroll

| Dokument/leveranse | Når og for hvem | Grunnlag | Ansvarlig kontroll | Mottaker/praktisk bruk |
|---|---|---|---|---|
| IOP | Ved ITO; ved relevante endringer | Vedtak, sakkyndighet, elev-/foreldreinnspill, mål | Faglig ansvarlig etter skolens rollefordeling | Arbeidsplan; tilgang/deling vurderes konkret |
| Årlig ITO-evaluering | Årlig for elev med ITO | Faktisk opplæring, gjeldende målversjoner og dokumentert utvikling | Ansvarlig pedagog; ev. leder etter lokal rutine | Elev/foreldre får tilgang; annen deling krever grunnlag |
| Halvårsvurdering | Etter elevens vurderingsordning | Faglig grunnlag og elevinnspill | Faglærer; kontaktlærer for orden/oppførsel etter reglene | Eleven; foresatte etter informasjonsrett |
| Lokal halvårsrapport om ITO | Bare når skoleeier har valgt det | Samme grunnlag, avgrenset periode | Ansvarlig pedagog | Etter lokal rutine og lovlig deling |
| E-postutkast til foresatte | Ved bestilling for valgt periode; valgfri gjentakelse av utkast | Bekreftede relevante opplysninger fra perioden; fremtidige planer merkes separat | Valgt lærer/spesialpedagog og mottakerkontroll | Kun berettigede foresatte i første versjon; eksplisitt utsending via tillatt kanal |
| Møteforberedelse / referat | Ved relevant møte | Innspill, mål, tiltak og avtaler | Møteleder og relevante bidragsytere | Avgrenset deltakerkrets |
| Sakkyndig vurdering | Ved relevant utredning | PPTs arbeid | PPT | Importert autoritativt dokument; programmet erstatter ikke utredningen |
| Enkeltvedtak | Etter aktuell saksprosess | Sakens opplysninger og lovgrunnlag | Kompetent vedtaksmyndighet | Part/representant med klageinformasjon |
| Skolemiljøplan | Ved tiltak i skolemiljøsak | Undersøkelser, elevens syn og tiltak | Ansvarlig skoleleder og fagpersoner | Avgrenset sakskrets |
| Melding etter fysisk inngrep | Etter relevant hendelse | Faktisk hendelse, inngrep og elevens syn | Ansatt/rektor etter rolle | Pålagte mottakere etter hendelsen |
| Bekymringsmelding | Når vilkårene er oppfylt | Konkrete opplysninger og avsenders vurdering | Ansvarlig ansatt; ingen obligatorisk ledergodkjenning | Barnevernet / annen riktig myndighet |
| Overføringspakke | Ved skolebytte | Nødvendige opplysninger med riktig delingsgrunnlag | Ansvarlig skole | Verifisert mottakerskole |
| Innsynssvar | Ved forespørsel | Relevante opplysninger, avledninger og metadata | Innsynsansvarlig | Rett person med nødvendige skjerminger |
| Tilsyns-/statistikkuttrekk | Årets krav eller konkret pålegg | Kontrollerte administrative data | Rektor/skoleeier/administrator | Riktig myndighet eller fagsystem |

Dokumentoversikten er en produktutforming. De konkrete pliktene og kildene finnes i lovregisteret. Ingen mottaker får tilgang til hele elevmappen bare fordi vedkommende mottar ett dokument.

## Målbare pilotkriterier

Produktmål, ikke lovkrav eller målte resultater:

- Median tidsbruk for et vanlig øktnotat er høyst ett minutt.
- En assistent kan forstå et vanlig gjennomføringskort innen fem minutter; må prøves med reelle arbeidsoppgaver og kvalifisert veiledning.
- Første pilot måler samlet tid for øktforberedelse, assistentveiledning og notatføring. E-postutkast og rapporter måles først når de aktuelle funksjonene tas i bruk.
- Rapportarbeid må måles inkludert kontroll av kilder og retting; foreløpig ambisjon er minst 30 % mindre samlet tid i piloten.
- Alle elevspesifikke faktapåstander i testede rapportutkast har kontrollerbar kilde, eller er tydelig markert som manglende/ubegrunnet og krever avklaring.
- Ingen godkjent test tillater utsending av endret innhold uten ny godkjenning, dobbeltutsending ved forsøk på gjentakelse eller opplysninger om feil elev.

## Hva som må avklares med pilotskolen

Skolens navn, kommune(r), godkjenningsvedtak, lokale maler/frister, arkivordning, eksisterende administrative systemer, bemanning, godkjenningsfullmakter, pilotstørrelse og tilgjengelig servermaskinvare. Manglene hindrer ikke denne produkt- og domeneplanen, men de må avklares før en produksjonskonfigurasjon kan hevdes å følge alle skolens konkrete krav.
