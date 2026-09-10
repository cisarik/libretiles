# Libre Tiles

Open-source web Libre Tiles game with AI opponents, live human-vs-human multiplayer, and an eye-candy animated frontend.

**Standalone repository**: all game code, dictionaries, and assets live in this repository — there is no parent monorepo. For agent/continuation notes see **[AGENTS.md](AGENTS.md)**.

## Features

- **Twelve playable board languages** — English (Collins 2019), Slovak, Czech, Polish, German, Portuguese, Icelandic, Italian, Dutch, Danish, Swedish, Afrikaans — each with its own alphabet, tile distribution, and word list
- **Interface localized in twelve languages** (`en sk cs pl de pt is it nl da sv af`), selectable in Settings
- **AI opponents via provider-diverse free rivals** — Play and Judge share one preference-first fallback queue (at most three distinct pairs, one whole-turn provider-call budget)
- **Live human-vs-human multiplayer** — waiting-room matchmaking, realtime board sync, and in-game chat
- **Server-authoritative validation** — every persisted placement is decided by Django's `WordAuthority` over the selected variant's physical tiles; the AI judge is advisory
- **Responsive, animated interaction** — drag-and-drop with touch support, animated tile drawing, and endgame effects; free-only play with no money, credits, or token prices

## Languages

**Twelve board languages ship playable.** `ls backend/assets/variants/` lists twelve manifests and `game.views.list_variant_summaries()` reports `readiness: "playable"` for all twelve. English uses Collins Scrabble Words 2019 (279,496 words); every other variant carries its own alphabet, tile distribution, and word list, and `poetry run python manage.py validate_lexicons` audits all thirteen assets.

Every non-English lexicon is reproducible from source: eleven committed scripts under `backend/scripts/` each pin an upstream commit and the SHA-256 of every source file they fetch, pin the host expander (`hunspell 1.7.3`), and fail closed on a mismatch.

What this does **not** claim: the eight newest interface catalogs (German, Portuguese, Icelandic, Italian, Dutch, Danish, Swedish, Afrikaans) are machine-authored with no second-opinion review, and the Slovak word list is a hunspell expansion of the LibreOffice `sk_SK` dictionary — playable, not an SSS-official list.

Details, word counts, and provenance: [libretiles_PRD.md](libretiles_PRD.md) and [AGENTS.md](AGENTS.md).

## Quick Start

### Local development

Use Python 3.12, Poetry 2.3.2 or newer, and Node.js 24 with npm.
See [CONTRIBUTING.md](CONTRIBUTING.md#prerequisites) for compatibility details.
Run commands from this repository's root unless stated otherwise.

SQLite is the local default. AI-only local play needs Django and Next.js;
human multiplayer also needs Redis for matchmaking, websocket sync, and chat.

**Recommended — start both development services:**

```bash
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
./scripts/libretiles.sh
```

The supervisor installs dependencies, runs migrations and model seeding, and
starts both services. It creates environment files only when absent and generates
`DJANGO_SECRET_KEY` into a new `backend/.env`. Existing environment files are preserved.

Open http://localhost:3000. The Django development API is at
http://127.0.0.1:8000; its local admin is at http://127.0.0.1:8000/admin/.

For external AI opponents, configure `OPENROUTER_API_KEY` and/or `NVIDIA_API_KEY`
in `frontend/.env.local` for the seeded compatibility catalog, then restart.
Other provider integrations require configured server credentials and explicit
catalog activation; see [provider activation](docs/architecture.md#explicit-capability-probe-boundary).
The UI can boot without provider credentials.

```bash
./scripts/libretiles.sh status
./scripts/libretiles.sh logs
./scripts/libretiles.sh restart
./scripts/libretiles.sh stop
```

<details>
<summary>Manual setup and two-terminal development</summary>

Use this as an alternative to the supervisor. Stop supervisor-managed services first
if they are already running.

**Terminal 1 — backend, first setup:**

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
poetry install
[ -f .env ] || cp .env.example .env
```

Before continuing, set a privately generated `DJANGO_SECRET_KEY` in `backend/.env`:
at least 50 characters, at least five unique characters, and no `django-insecure-`
prefix. The example deliberately leaves it empty. Retain an existing valid key.

```bash
poetry run python manage.py migrate
poetry run python manage.py seed_models
poetry run python manage.py runserver 127.0.0.1:8000
```

**Terminal 2 — frontend, starting from the repository root:**

```bash
cd frontend
[ -f .env.local ] || cp .env.local.example .env.local
# Configure server-only provider credentials here if using external AI opponents.
npm install
npm run dev
```

For local Django Admin access, optionally run `poetry run python manage.py createsuperuser`
from `backend/`.

**Subsequent manual starts — each terminal starts at the repository root:**

```bash
# Terminal 1
cd backend && poetry run python manage.py runserver 127.0.0.1:8000
```

```bash
# Terminal 2
cd frontend && npm run dev
```

</details>

Full configuration is documented in [backend/.env.example](backend/.env.example)
and [frontend/.env.local.example](frontend/.env.local.example).
Keep provider credentials server-only; never put them in `NEXT_PUBLIC_` variables
or commit environment files. Review existing backend settings after changes and
restart the affected service.

Keep `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false` for the default local setup.
`seed_models` works offline; public catalog synchronization is optional.
For local human multiplayer, the default Redis URL is `redis://127.0.0.1:6379/0`.

`DJANGO_THROTTLE_CACHE_URL`: Unused for local `DJANGO_DEBUG=true` boot.
Production requires shared Redis throttling, with `REDIS_URL` as the fallback.

### Production (VPS)

Production uses the root Docker Compose topology on a self-hosted VPS. Nginx is
the only host-published service. Next.js standalone runs on
`127.0.0.1:3000` in nginx's shared network namespace; Daphne uses a
group-restricted Unix socket. Nginx's PID-1 master is the sole container-root
exception: UID 0 with shared GID 10001 and exactly `NET_BIND_SERVICE`, `SETGID`,
and `SETUID`. The latter two exist solely so nginx can drop request workers to
`10002:10001`; those workers retain zero effective capabilities. PostgreSQL and
Redis remain capability-free on private networks. File-backed secret sources
use root ownership, dedicated reader GID 10004, and mode `0440` in a private
host directory; only a service with both GID 10004 and an explicit per-secret
mount can read one.

Follow the [VPS deployment guide](docs/vps_deployment_guide.md) for prerequisites,
environment settings, rendered templates, deployment, verification, and recovery.
It also explains Certbot bootstrap/renewal, file-mounted secrets, backup/restore,
paired nginx/frontend recreation, the private Django Admin listener, and the
Next-to-Django callback at `127.0.0.1:8001`. Production uses
`DJANGO_DEBUG=false`.

The development supervisor and commands above are for local development.
Production host changes and the optional catalog-refresh schedule require separate
operator authority.

## Architecture

- **Frontend (Next.js)** serves the UI and orchestrates external AI calls through server-only API routes; provider credentials never reach the browser.
- **Backend (Django + DRF)** owns game state, authentication, and authoritative validation: persisted placements are decided by `WordAuthority` over the selected variant's physical tiles (`backend/gamecore/word_authority.py`). The AI judge is advisory and never overrides a persisted verdict.
- **Realtime (Django Channels + Redis)** provides human-vs-human matchmaking, websocket synchronization, and chat.

Deeper reading: [AI agent workflow](docs/architecture.md#ai-agent-workflow), [provider capability probe boundary](docs/architecture.md#explicit-capability-probe-boundary), [catalog operations, rollout, and rollback](docs/architecture.md#catalog-operations-rollout-and-rollback), and the REST route definitions in [backend/game/urls.py](backend/game/urls.py) and [backend/accounts/urls.py](backend/accounts/urls.py).

## Project Structure

- `backend/gamecore/` — pure Python game engine: board, rules, scoring, tiles, variants
- `backend/game/` — game sessions, moves, validation, AI tool endpoints
- `backend/catalog/` — AI model catalog (`seed_models` + optional OpenRouter sync)
- `backend/assets/` — Collins 2019 dictionary, premiums, variant manifests
- `frontend/src/` — Next.js app: game UI, Zustand store, AI runtime dispatch, API routes
- `docs/` — technical architecture and VPS deployment guides

## Testing

Backend, from `backend/`:

```bash
poetry run pytest                                        # All tests
poetry run pytest tests/test_gamecore.py                 # Pure game logic (fast, offline)
poetry run ruff check .                                  # Lint
poetry run mypy config game gamecore accounts catalog    # Type check
```

Frontend, from `frontend/`:

```bash
npm test                                   # Unit/integration suite; live probe skipped
npm run lint                               # ESLint
npm run typecheck                          # TypeScript check
```

## Tech Stack

| Layer | Technologies |
|---|---|
| Backend | Python 3.12 (recommended), Django 5.x, Django REST Framework, JWT auth |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, Framer Motion, @dnd-kit |
| AI | Vercel AI SDK v6 via direct free rivals plus the NIM/OpenRouter compatibility tail |
| Realtime & storage | Redis (Channels, throttle cache), PostgreSQL (prod) / SQLite (dev) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and how to submit changes. **[AGENTS.md](AGENTS.md)** is the maintainer/agent handoff doc.

## License

MIT
