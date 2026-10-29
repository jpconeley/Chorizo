# LASO

A marketplace and analytics terminal for biotech assets. Owners list therapies at any stage of
development and ask for funding. Investors, both institutional and retail, screen assets, see how
often comparable programs succeed at each stage, and contact owners.

Revenue is subscriptions: free to browse, paid plans for analytics, deal flow, data export and
listing. See [docs/architecture.md](docs/architecture.md) for the system design and plan details.

The product is called LASO. The code, commands (`chorizo ...`), database and repository still
use the earlier working name, Chorizo.

## Layout

```
backend/    Python: database models, migrations, REST API, data ingestion, analytics
web/        Next.js: the terminal-style web app
docs/       Architecture and product notes
```

## Run locally

The easiest way needs only [Docker Desktop](https://www.docker.com/products/docker-desktop) (works
on Windows, Mac and Linux):

```bash
docker compose up -d --build
```

Then open http://localhost:3000. The API is on http://localhost:8000 (docs at `/docs`). The first
run takes a few minutes to build. Run `docker compose up -d --build` again after pulling new code,
and `docker compose down` to stop.

### Without Docker for the app

For day-to-day development with hot reload, you need Docker (for Postgres), [uv](https://docs.astral.sh/uv/) and [pnpm](https://pnpm.io/):

```bash
make setup                         # install dependencies
make db                            # start Postgres
cp backend/.env.example backend/.env
make migrate seed                  # create tables, load benchmarks and demo data
make api                           # API on http://localhost:8000 (docs at /docs)
make web                           # web app on http://localhost:3000 (in a second terminal)
```

The terminal opens at an entry gate. Locally (`CHORIZO_OPEN_GATE=1`, set in
`docker-compose.yml`) any user ID and password get in, as the institutional demo user. Never set
it in production. Real logins also work: the demo users are `free@`, `pro@`, `institutional@`
and `sponsor@chorizo-demo.example.com`, all with the password `chorizo-demo-pass`, each holding
the plan in its name.

## Data jobs

Load real data from ClinicalTrials.gov: import every phased drug trial, group them into drug
programs, then compute success rates and per-drug estimates. With the Docker setup:

```bash
docker compose exec api chorizo refresh-data --max-pages 5   # quick test: first 5,000 studies
docker compose exec api chorizo refresh-data                 # full import, roughly 30–60 minutes
```

`refresh-data` also imports FDA approval dates from Drugs@FDA. To rebuild programs and success
rates without re-importing every trial (after an update to the analytics), run:

```bash
docker compose exec api chorizo refresh-analytics
```

Without Docker, run the same commands with `uv run chorizo ...` in `backend/`. The steps also run
separately: `ingest-ctgov`, `ingest-fda`, `build-programs`, `compute-benchmarks` and
`refresh-estimates`.

## Tests

```bash
make test
```

## Disclaimer

LASO shows historical base rates and owner-provided information. It is not investment advice
and does not offer securities. Taking investment through the platform needs a registered funding
portal or broker-dealer; see the roadmap in the architecture doc.
