# Kjør SpesPed på egen Mac

`localhost` viser alltid til maskinen der nettleseren kjører. En server startet
på Mac mini-en blir derfor ikke tilgjengelig på MacBook Air-ens `localhost`.
Kjør kommandoene nedenfor i Terminal på maskinen du vil bruke nettleseren på.

Dette er en utviklingsversjon med syntetiske data. Flere funksjoner og
arbeidsflyter er fortsatt under utvikling; merge til `main` betyr ikke at
programmet er produksjonsklart. Databaser, passord, `.env`, `var/` og installerte
avhengigheter følger ikke med Git.

## Hent kode og avhengigheter

Du trenger Git, `uv`, Python 3.12 og Node.js 22.12 eller nyere med npm.
`uv` kan installere den nødvendige Python-versjonen.

Har du allerede repositoryet lokalt, kjør fra prosjektmappen:

```sh
git fetch origin
git switch main
git pull --ff-only origin main
```

Hvis Git melder om lokale endringer eller avvikende historikk, behold arbeidet
og avklar det før du fortsetter. For en ny arbeidskopi:

```sh
git clone https://github.com/Herligetider/SpesPed.git
cd SpesPed
```

Installer de låste avhengighetene fra prosjektroten:

```sh
uv python install 3.12
uv sync --project backend --locked
npm --prefix web ci
```

## Førstegangsoppsett

Følgende lager en privat `.env` for lokal SQLite-utvikling. Den stopper hvis
filen allerede finnes, slik at eksisterende innstillinger ikke overskrives.
Rotens `.env.example` er et separat produksjonseksempel.

```sh
uv run --project backend python - <<'PY'
import os
import secrets

configuration = '\n'.join([
    'SPESPED_ENVIRONMENT=development',
    'SPESPED_DATABASE_URL=sqlite:///./spesped-dev.db',
    'SPESPED_SECRET_KEY=' + secrets.token_urlsafe(48),
    'SPESPED_ALLOWED_ORIGINS=["http://127.0.0.1:5173","http://localhost:5173"]',
    'SPESPED_COOKIE_SECURE=false',
    'SPESPED_AI_PROVIDERS=[]',
]) + '\n'
descriptor = os.open('.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, 'w') as output:
    output.write(configuration)
print('Lokal .env opprettet. Ingen hemmeligheter er skrevet til terminalen.')
PY

uv run --project backend spesped migrate
```

Opprett demokontoer bare én gang, i den nye, tomme utviklingsdatabasen.
Du blir bedt om et selvvalgt passord på minst 12 tegn. Passordet vises ikke i
terminalen og lagres ikke i Git:

```sh
uv run --project backend python - <<'PY'
import getpass
import os
import sys
from spesped.cli import main

os.environ['SPESPED_DEMO_PASSWORD'] = getpass.getpass('Velg demopassord (minst 12 tegn): ')
sys.argv = ['spesped', 'demo', '--confirm-synthetic', '--password-env', 'SPESPED_DEMO_PASSWORD']
main()
PY
```

Legg deretter til tilganger for å prøve de faglige arbeidsflatene:

```sh
uv run --project backend spesped demo-access --confirm-synthetic
```

Logg inn som `demo.leader@example.invalid` med passordet du nettopp valgte.
Standarddemoen oppretter to skoler, tre syntetiske elever og kontoer med ulike
tilganger. `demo-access` gir skolelederkontoen eksplisitte testtilganger til
støtteprofil, planer, undervisning og dokumentarbeid for **Syntetisk elev A og B**,
samt dokumentinnboksen. Den klargjør også syntetiske pedagogiske støttesaker
med egen sakstilgang. Den inneholder ikke ferdige undervisningsforløp.
Assistent-, foresatt- og driftskontoene beholder sine begrensede roller.

Skolelederrollen alene gir fortsatt ikke automatisk tilgang. Kommandoen er
et tillegg til standarddemoen, krever utviklingsmiljø og endrer ikke de vanlige
tilgangsreglene. Den oppretter ikke AI-oppsett, foresattrettigheter eller
godkjenning for utsending. [Backend-veiledningen](../backend/README.md) beskriver
de ordinære tilgangskontraktene.

### Hvis du allerede har startet demoen og får «Du har ikke tilgang»

Stopp backend med Ctrl+C. Fra prosjektroten, i samme terminal og med samme
databaseinnstillinger som backend, kjør:

```sh
git pull --ff-only origin main
uv run --project backend spesped demo-access --confirm-synthetic
```

Start backend igjen som beskrevet nedenfor, og logg inn på nytt som
`demo.leader@example.invalid`. Passord og eksisterende data beholdes. Kommandoen
kan kjøres flere ganger uten å duplisere tilganger; den gjenåpner ikke eksplisitt
tilbakekalte tilganger. Ikke kjør den opprinnelige `demo`-importen på nytt.

Hvis du senere oppretter en ny pedagogisk støttesak for A eller B som
demolederen, kjør `demo-access --confirm-synthetic` på nytt for å gi eksplisitt
tilgang til den nye saken. Opprettelse alene gir ikke sakstilgang. Kommandoen
krever at standarddemoens opprinnelige skoler, kontoer, elever og tilknytninger
fortsatt kan gjenkjennes; den avviser endret eller ufullstendig grunnoppsett.

## Start programmet

Terminal 1, fra prosjektroten:

```sh
uv run --project backend uvicorn spesped.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend/spesped
```

Terminal 2, fra den samme prosjektroten:

```sh
npm --prefix web run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

La begge terminalene være åpne. Gå til <http://127.0.0.1:5173/> i nettleseren
på samme Mac. Frontend sender API-kall videre til serveren på port 8000.
Du trenger ingen AI-nøkkel for innlogging og manuelle arbeidsflater. AI,
filskanning og eksterne forbindelser krever separat oppsett.

## Kontroller tilkoblingen

```sh
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:5173/api/v1/health
```

Begge skal svare `{"status":"ok"}`. Hvis port 8000 eller 5173 er opptatt,
identifiser prosessen med `lsof -nP -iTCP:8000 -iTCP:5173 -sTCP:LISTEN` før du
stanser noe. Ved feil etter en senere oppdatering, stopp serverne, kjør
avhengighetsinstallasjonen og migreringen på nytt, og start begge serverne igjen.
Ikke kjør demoimporten på nytt i en database som allerede har data.
