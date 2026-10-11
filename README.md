# Kommute

**Less app. More answer.**

Kommute is a responsive KRL Jabodetabek departure board. Find a station, see the next scheduled trains, and get on with your journey.

It is built for commuters who already know the network and need one answer quickly: **when is the next train, and where is it going?**

## Why Kommute?

Transit apps can do a lot. But a timetable check shouldn't require navigating a journey planner, a map, or several menus first.

Kommute follows a narrower principle: **direct by design**. New features are welcome only when they make the departure answer faster to find, easier to understand, or more reliable. More features alone are not the goal.

**Find station → See departures → Done.**

## Features

- **Next five departures:** scheduled destination, line color, countdown, and departure time, updated as time passes.
- **Search and recents:** find a station by name or code and reopen recently viewed stations without an account.
- **Relevant line filtering:** filter services at multi-line stations; marginal station-line associations with fewer than four distinct daily board-visible trains are excluded from the passenger-facing board.
- **Junction directions:** stable **TOWARD** choices based on physical outgoing tracks, not on whichever trains happen to be next. Shown only at Manggarai, Kampung Bandan, Jatinegara, Citayam, Duri, and Tanah Abang.
- **Route-aware destination labels:** distinguish trains via Manggarai and via Pasar Senen where the difference matters.
- **Conditional timetable cues:** **NEXT HH:MM** highlights a meaningful later service when it is not already listed; **LAST TRAIN** identifies a final scheduled service. Expired departures leave the active board.
- **Responsive layouts:** a compact mobile station picker and board; on desktop, a persistent station sidebar, clickable schematic network map, and departure details with remaining train stops.
- **Direct-trip lookup API:** find scheduled trains traveling between two stations. This is implemented in the backend, **not** a separate journey-planning screen.

### One product, two layouts

| Viewport | Experience |
| --- | --- |
| Mobile (below 900px) | Search or select a station → view the departure board. |
| Desktop (900px and above) | Station sidebar remains visible; the main panel shows the network overview or selected station. |
| Wide desktop (1280px and above) | Departure rows can show compact upcoming-stop diagrams and expandable full stop lists. |

The mobile board stays primary; the desktop layout adds space and context without adding another mandatory workflow.

## Coverage and data

The committed timetable snapshot includes:

| Metric | Compiled snapshot |
| --- | ---: |
| Selectable stations | 84 |
| Commuter lines | 5 |
| Trains | 1,129 |
| Complete train-route stops | 18,344 |
| Board-visible station stops | 17,214 |

The five lines are **Bogor, Cikarang, Rangkasbitung, Tangerang, and Tanjung Priok**. Counts reflect the compiled snapshot and may change when it is regenerated.

**Important:** Kommute shows **scheduled** departures, not live train locations, delay predictions, or platform confirmations. Countdown labels such as `NOW` refer to the scheduled departure minute, not a confirmed train arrival. **Actual service may differ.**

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Go (`net/http`, `pgx/v5`) |
| Database | PostgreSQL 16+ |
| Frontend | HTML, CSS, and vanilla JavaScript |
| Data pipeline | Python 3 and `curl`, compiled to JSON and imported with `psql` |
| Timezone | `Asia/Jakarta` |
| Deployment assets | Caddy and systemd example configurations under `deploy/` |

There is no SPA framework, frontend build step, or external API call for every board request. The Go server reads locally imported PostgreSQL schedule data and serves static files.

## Repository structure

```text
kommute/
├── cmd/kommute/             # Go entry point
├── internal/
│   ├── config/              # environment configuration
│   ├── db/                  # PostgreSQL queries, fork logic, cues, train routes
│   ├── model/               # API response types
│   └── server/              # HTTP routes, handlers, middleware
├── migrations/              # schema: 001_init_schema.sql, 002_route_visibility.sql
├── data/kommute.json        # compiled schedule snapshot
├── tools/                   # fetch, compile, normalize, and import scripts
├── web/static/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── deploy/                  # example Caddyfile and systemd unit
├── Makefile
└── .env.example
```

## Run locally

### Requirements

- Go **1.26.1 or newer** (version declared in `go.mod`)
- PostgreSQL **16 or newer**, with `psql` and `createdb` available
- Python 3 (for the importer)
- `curl` (only needed to fetch new upstream schedule data)

### 1. Clone and configure

```bash
git clone https://github.com/fikryfauzn/kommute.git
cd kommute
cp .env.example .env
```

Edit `.env` with the connection details of your **local** PostgreSQL database. A typical development configuration is:

```dotenv
PORT=8080
DB_DSN=postgres://kommute:your-local-password@localhost:5432/kommute?sslmode=disable
ENV=development
TZ=Asia/Jakarta
```

Create a PostgreSQL database and login role that match your `DB_DSN`, if you have not already done so. Keep `.env` private; it is ignored by Git.

### 2. Apply the schema and import the snapshot

From the repository root:

```bash
set -a
source .env
set +a

psql "$DB_DSN" -X -v ON_ERROR_STOP=1 -f migrations/001_init_schema.sql
psql "$DB_DSN" -X -v ON_ERROR_STOP=1 -f migrations/002_route_visibility.sql
python3 tools/import_postgres.py
```

The importer reads the committed `data/kommute.json` by default and loads its validated stations, lines, destination mappings, and complete train routes into PostgreSQL. **The import replaces the existing generated reference/schedule tables.** Apply migrations only once to a newly created database.

### 3. Start Kommute

```bash
go run ./cmd/kommute
```

Open **http://localhost:8080** in your browser. Run from the repository root because static files are served from the relative `web/static` directory.

Alternatively:

```bash
make build
make run
```

For tests:

```bash
go test ./...
# or: make test
```

## Refreshing timetable data

Kommute fetches KCI schedule data **offline during ingestion**, not during every user request.

```bash
# Run from the repository root; requires network access to the KCI endpoints.
python3 tools/fetch_kci.py
python3 tools/fetch_train_routes.py
python3 tools/compile_schedule.py

# Re-import the newly compiled snapshot.
set -a
source .env
set +a
python3 tools/import_postgres.py
```

The pipeline retrieves station boards and complete train routes, validates and normalizes them, and writes `data/kommute.json`. The raw upstream responses under `data/kci/raw/` are intentionally Git-ignored.

When introducing a new source snapshot, verify the data before replacing a deployed database. **No automatic weekly refresh is configured by the application itself.** Scheduling refreshes is a deployment responsibility.

## HTTP API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Health response. |
| `GET /api/stations` | Selectable stations grouped by regular commuter line. |
| `GET /api/stations/{id}/arrivals` | Next five scheduled departures at a station. |
| `GET /api/stations/{id}/arrivals?line=COMMUTER%20LINE%20BOGOR` | Next five departures restricted to one line. |
| `GET /api/stations/{id}/arrivals?group=true` | Upcoming departures grouped by destination. |
| `GET /api/stations/{id}/cues` | Direction definitions and full-day timetable cues. |
| `GET /api/stations/{id}/trains/{train}/route` | Remaining scheduled stops for a train from a selected station. |
| `GET /api/trip?from=UI&to=MRI` | Scheduled direct trains between two stations (API-only feature). |

Times are evaluated for the Jakarta operating day; service after midnight is handled as a continuation of the previous evening's schedule where applicable.

## Deployment status

Kommute was previously hosted on DigitalOcean. The current repository includes example **Caddy** and **systemd** configuration under `deploy/`, but those files **do not indicate that the current version is publicly deployed**.

A production setup needs a PostgreSQL instance populated with a verified timetable, an environment file or equivalent secrets configuration, HTTPS/reverse proxy, and a defined data-refresh process. The server must be started with a working directory that contains `web/static`.

The interface supports local Helvetica Neue font files, but `web/static/font/` is Git-ignored. Do not redistribute proprietary fonts without the appropriate license; use licensed assets or the included system-font fallback in public deployments.

## License

Not yet specified.

---

*Checking the next train should be the easy part.*
