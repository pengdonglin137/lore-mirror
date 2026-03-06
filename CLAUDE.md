# lore-mirror

Local mirror of lore.kernel.org kernel mailing list archives.

## Project Structure

```
/vol_8t/lore/
├── config.yaml              # Inbox list (~200 inboxes, most commented out) + settings
├── start.sh                 # Launch script: ./start.sh (dev) or ./start.sh --build (prod)
├── Dockerfile               # Multi-stage build (Node + Python)
├── docker-compose.yml       # web + sync services
├── repos/                   # Git mirror repos: repos/{inbox}/git/{epoch}.git
├── db/                      # Per-inbox SQLite+FTS5 databases: db/{inbox}.db
├── scripts/
│   ├── mirror.py            # Download git repos (epoch discovery, parallel clone)
│   ├── import_mail.py       # Import emails from git into SQLite (incremental)
│   ├── database.py          # SQLite schema definition (per-inbox, no shared DB)
│   ├── sync.py              # Daily sync: git fetch + incremental import (CLI/cron only)
│   └── healthcheck.py       # Verify & repair git repos and databases
├── .mcp.json                # MCP server config for Claude Code auto-discovery
├── server/
│   ├── app.py               # FastAPI backend (auto-discovers inbox DBs in db/)
│   └── mcp_server.py        # MCP server (wraps REST API via httpx, stdio transport)
└── frontend/                # Vue 3 + Vite SPA
    ├── src/views/           # Home, Inbox, Message, Thread, Search
    ├── src/components/      # ThreadNode (recursive)
    ├── src/api.js           # API client
    └── src/router.js        # Vue Router config
```

## Tech Stack

- **Backend**: Python 3, FastAPI, SQLite3 + FTS5
- **Frontend**: Vue 3, Vite, vue-router
- **Data**: public-inbox git repos → SQLite (each inbox = separate .db file)
- **No external DB server needed** — SQLite is embedded

## Key Architecture Decisions

- **Per-inbox databases**: Each inbox has its own `db/{name}.db` file. No shared/central database. The backend iterates over all .db files for cross-inbox operations (search, message lookup).
- **MCP server**: `server/mcp_server.py` wraps the REST API with 7 tools for AI access. Spawned by Claude Code via `.mcp.json` (stdio transport). Requires REST API running on `:8000`. Tool names prefixed with `lore_` to avoid collisions.
- **Sync is CLI-only**: No web-triggered sync (security). Use `scripts/sync.py` via cron. Frontend only shows read-only sync status from `sync_status/` directory (per-inbox files).
- **Per-inbox locking**: `fcntl.flock` on `sync_status/{inbox}.lock` prevents concurrent writes to the same inbox DB. Different inboxes can sync in parallel.
- **Graceful shutdown**: SIGTERM/SIGINT sets a flag; import loop finishes current commit, saves progress, then exits.
- **Data flow**: `git clone --mirror` → `git show <commit>:m` extracts raw email → Python `email` lib parses → INSERT into SQLite. File `d` in a commit means deletion.
- **FTS5 triggers**: Search index auto-updated via SQLite triggers on INSERT/UPDATE/DELETE.
- **Search prefix syntax**: lore-compatible prefixes (s: f: b: d: t: c: a: m: bs: tc:) parsed in `parse_search_query()` in server/app.py, translated to FTS5 column filters + SQL WHERE clauses.
- **Date handling**: `fix_date()` in import_mail.py corrects Y2K bugs (01xx→20xx), rejects future/pre-1990 dates, falls back to git committer date. Backend ORDER BY also filters anomalous dates.
- **Portable paths**: config.yaml uses relative paths by default, resolved via `scripts/config_utils.py`.

## Common Commands

```bash
# Download repos for a new inbox
python3 scripts/mirror.py --inbox <name>

# Import emails into database
python3 scripts/import_mail.py --inbox <name>

# Sync (fetch + import new emails)
python3 scripts/sync.py

# Health check
python3 scripts/healthcheck.py --repair

# API tests (requires running server)
python3 scripts/test_api.py
python3 scripts/test_api.py --url http://remote:8000

# Start web server (bare metal)
./start.sh              # dev: frontend :3000 + backend :8000
./start.sh --build      # prod: backend :8000 serves built SPA

# Docker deployment
docker compose up -d                    # start web + sync
docker compose run --rm sync python3 scripts/mirror.py --inbox <name>
docker compose run --rm sync python3 scripts/import_mail.py --inbox <name>
```

## Environment Notes

- User `pengdl` has no sudo access on dev machine
- inotify limit is 65536 — Vite uses polling mode (`usePolling: true`)
- PostgreSQL 14 is installed but inaccessible — using SQLite instead
- Docker supported: `Dockerfile` (multi-stage) + `docker-compose.yml` (web + sync)

## Data Scale

- lkml: 19 epochs, ~5.9M emails, 20GB git repos, ~140GB estimated DB (with raw_email)
- Import speed: ~80 commits/s
- Full lkml import: ~20 hours

## Keeping Docs in Sync

When updating any of these, also update the others:
- **API changes** (`server/app.py`) → update `docs/API.md` + `docs/skills/lore-mirror/SKILL.md`
- **Search syntax changes** → update `docs/API.md` + `docs/skills/lore-mirror/SKILL.md` + frontend help (`App.vue`, `Search.vue`)
- **New features/commands** → update `docs/plans/2026-03-05-lore-mirror-design.md` (usage section)
- **Inbox descriptions** (`config.yaml`) → descriptions are served via API, skill references them

The installed skill at `~/.claude/skills/lore-mirror/SKILL.md` is a copy of `docs/skills/lore-mirror/SKILL.md`.

### Pre-commit: Sync skills from ~/.claude/skills

**Before every commit**, check if `~/.claude/skills/kernel-dev/SKILL.md` has diverged from `docs/skills/kernel-dev/SKILL.md`. If so, copy it into the repo and include in the same commit:
```bash
diff ~/.claude/skills/kernel-dev/SKILL.md docs/skills/kernel-dev/SKILL.md
# If different → cp ~/.claude/skills/kernel-dev/SKILL.md docs/skills/kernel-dev/SKILL.md
```
Do the same for `lore-mirror/SKILL.md`. Skills may be updated during other conversations and must be synced back to the repo.

## Conventions

- All scripts run from project root: `cd /vol_8t/lore && python3 scripts/xxx.py`
- Config always at `config.yaml` in project root
- Scripts use `PROJECT_ROOT = Path(__file__).resolve().parent.parent`
