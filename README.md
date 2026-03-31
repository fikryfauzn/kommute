# kom-mute

A minimal KRL arrival board for Jabodetabek commuters. Pick a station, see what's coming next.

## Why this exists

Commuters who ride KRL daily already know how to take a train. They don't need step-by-step navigation or time window pickers. They need one answer: **what's the next train, and where is it going.**

kommute is that answer.

## Features

- **Arrival board** -- next 5 trains at any Jabodetabek station, updating in real time against the schedule
- **Direction grouping** -- at transit hubs like Manggarai, trains are grouped by destination so you don't have to think
- **Cross-station trip lookup** -- "I'm at UI, I want to get to Manggarai" shows which trains get you there and how long it takes
- **LED board aesthetic** -- inspired by station departure boards, not mobile app design trends

## Coverage

83 stations across 5 KRL commuter lines: Bogor, Cikarang, Rangkasbitung, Tangerang, Tanjung Priuk.

---

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Go | Single static binary, zero runtime dependencies, ~2MB memory footprint |
| Database | PostgreSQL | Covering indexes, composable queries, battle-tested |
| Frontend | Vanilla HTML/CSS/JS | One page, one purpose, no framework overhead |
| Reverse proxy | Caddy | Automatic HTTPS via Let's Encrypt |
| Process manager | systemd | Already on the server, auto-restart, log collection |
| Server | DigitalOcean 2GB droplet | Singapore region, Ubuntu 24.04 |

## Project structure

```
kommute/
├── cmd/kommute/main.go          # entry point
├── internal/
│   ├── config/config.go         # env vars
│   ├── db/db.go                 # connection pool
│   ├── db/queries.go            # all SQL
│   ├── handler/arrival.go       # GET /api/stations/:id/arrivals
│   ├── handler/station.go       # GET /api/stations
│   ├── handler/trip.go          # GET /api/trip
│   ├── model/schedule.go        # data structs
│   └── server/server.go         # routes, middleware
├── web/static/                  # frontend (LED board UI)
├── migrations/                  # PostgreSQL schema
├── Makefile                     # build, run, migrate, deploy
└── .env.example
```

## Prerequisites

- Go 1.23+
- PostgreSQL 16+

## Setup

```bash
# clone
git clone https://github.com/youruser/kommute.git
cd kommute

# configure
cp .env.example .env
# edit .env with your database credentials

# create database and run migration
createdb kommute
psql -d kommute -f migrations/001_init_schema.sql

# build and run
make build
make run
```

## Environment variables

```
PORT=8080
DB_DSN=postgres://user:pass@localhost:5432/kommute?sslmode=disable
ENV=development
```

## API

#### `GET /api/stations`
Returns all stations grouped by line.

#### `GET /api/stations/:id/arrivals`
Returns the next 5 trains arriving at the given station.

Query params:
- `group` (optional) -- if `true`, groups arrivals by destination

#### `GET /api/trip?from=UI&to=MRI`
Returns the next 5 trains that travel from one station to another, with travel time.

## Data source

Schedule data is fetched from the KAI partner API and stored locally in PostgreSQL. The app serves from its own database -- it does not call KAI on every request. Data is refreshed weekly via a separate fetch script in the `kommute-fetch/` repository.

## Deployment

```bash
# build for linux
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -ldflags="-s -w" -o bin/kommute ./cmd/kommute

# copy to server
scp bin/kommute lazarus@your-server:/opt/kommute/

# restart
ssh lazarus@your-server "sudo systemctl restart kommute"
```

## License

TBD

---

*kom-mute: because checking the next train should easy.*