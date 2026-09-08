# Spesped

Prosjektgrunnlag for et program som skal redusere arbeidstrykket for lærere, spesialpedagoger og skoleledelse gjennom gjenbruk av elevinformasjon, planlegging, oppfølging og dokumentutkast med faglig gjennomgang.

Omfanget dekker offentlige grunnskoler og private montessoriskoler med statstilskudd, 1.–10. trinn. E-postutkast til foresatte kan lages for valgte tidsintervaller; eventuell gjentakelse er valgfri og sender ikke automatisk. Første komplette arbeidsflyt prioriterer undervisningsforberedelse og kort øktlogg. Alle 40 foreslåtte funksjonsområder er beholdt.

Arbeidsversjon 0.2, oppdatert 8. september 2026. Lovkildene ble kontrollert 7. september; denne revisjonen utdyper produktet og leveranserekkefølgen. Dette er planleggingsdokumenter; programmet er ikke implementert.

## Leserekkefølge

| Dokument | Innhold | Språk |
|---|---|---|
| [Produktgrunnlag](docs/00-product-brief.no.md) | Formål, arbeidsflyt, dokumenttyper og pilotmål | Norsk |
| [Lovkrav og funksjonsdekning](docs/01-legal-matrix.no.md) | 90 krav/regelområder, kilder, ansvar, tidspunkt, dokumentasjon og funksjonskobling | Norsk |
| [Funksjonskatalog](docs/02-feature-catalog.no.md) | 40 detaljerte spesifikasjoner med arbeidssteg, regler, eksempler og akseptansekriterier | Norsk |
| [Første arbeidsflyt til faglig gjennomgang](docs/08-first-workflow-review.no.md) | Elevgrunnlag → økt → assistentkort → gjennomføring og notat | Norsk |
| [Event storming](docs/03-event-storming.en.md) | 12 arbeidsflyter med hendelser, kommandoer, aktører, policyer og uavklarte spørsmål | English |
| [Domain model](docs/04-domain-model.en.md) | 16 foreslåtte kontekster, begreper, aggregater, entiteter, verdiobjekter og regler | English |
| [Implementation plan](docs/05-implementation-plan.en.md) | Arkitektur, P0–P8, leveranser, avhengigheter og akseptansekriterier | English |
| [Traceability](docs/06-traceability.md) | Lovkrav → funksjon → kontekst → fase | English |
| [Kilder / Sources](docs/07-sources.md) | 71 kilder, merket med kildetype og kontrolldato | Norsk/English |

## Status og videre validering

Lovregisteret er et bredt nasjonalt kartleggingsgrunnlag. Det er ikke en uttømmende juridisk godkjenning av alle plikter ved en bestemt skole. Særlig L079–L090 krever mer konkret regel-/anvendelsesavklaring. Lokale forskrifter, skolens godkjenning, delegering, bevaringsplan og systemavtaler må knyttes til registeret før det brukes som operative samsvarsregler.

Domenemodellen er en første modellering basert på kravene. Den er ikke presentert som et gjennomført og validert verksted med lærere, skoleledelse, PPT og foresatte. Uavklarte spørsmål er beholdt i dokumentene og inngår i P0.

## Redigerbare registre

- `docs/legal-requirements.json`: lovkrav/områder med funksjons- og kildehenvisninger.
- `docs/features.json`: full funksjonsspesifikasjon med brukere, inndata, arbeidssteg, resultat, regler, akseptansekriterier, eksempel, avhengigheter, fase og spørsmål til faglig gjennomgang.
- `docs/sources.json`: kilderegister.

Generer de avledede Markdown-tabellene og kontroller ID-henvisningene med:

```sh
python3 scripts/render_planning_docs.py
```

Genereringen endrer bare dokumentasjon og verifiserer struktur/henvisninger. Den verifiserer ikke juridisk korrekthet eller om programfunksjoner er implementert.
