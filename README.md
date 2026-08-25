# Libre Tiles

Open-source web Libre Tiles game with AI opponents, live human-vs-human multiplayer, and an eye-candy animated frontend.

**Architecture**: Next.js frontend (provider-diverse free-rival AI + UI) + lightweight Django backend (game logic, validation, admin).

**Standalone repository**: This folder is intended to be published as its **own** GitHub repository. It does **not** depend on the parent `scrabgpt_sk` monorepo — all assets and code live under `libretiles/`. For agent/continuation notes see **[AGENTS.md](AGENTS.md)**.

## Features

- Full Libre Tiles game engine (English variant, Collins 2019 dictionary ~279k words, Tier-1 strict validation in Django)
- AI opponents via provider-diverse free rivals with tool calling (OpenRouter + NVIDIA NIM). Flag-off (default) uses five curated bootstrap pairs; flag-on uses the four newest eligible OpenRouter models plus the seeded NIM tuple
- Live human-vs-human multiplayer with waiting-room matchmaking, realtime board sync, and in-game chat
- AI plays as a tool-calling agent: validates moves, checks words, calculates scores
- Play and Judge share one preference-first fallback queue (at most three distinct pairs, one whole-turn provider-call budget)
- Advanced drag-and-drop with touch/mobile support (@dnd-kit)
- Animated tile drawing, scoring, and game-end effects (Framer Motion, confetti)
- Django Admin for configuration (AI model catalog, games)
- Settings page with the selectable free-rival shortlist from `GET /api/catalog/models/`
- Free-only play: the product does not handle money, app credits, USD balances, token prices, or per-game charges. Play and Judge use the selectable free-rival catalog only. Provider quotas or trial terms are external and may change — they are not Libre Tiles credits or charges. Stripe is rejected for this product direction.
- Responsive design (desktop, tablet, mobile)
- 3-tier word validation: local Collins 2019, online API (optional), AI judge

## Quick Start

For AI-only local development you need **two terminals**: one for the Django backend, one for the Next.js frontend. Redis is **not** required for AI-only play. For live human-vs-human multiplayer you also need a running Redis instance for Django Channels.

### Python environment (backend)

Recommended: let **Poetry** create and use a virtualenv under `backend/.venv` (gitignored):

```bash
cd backend
python3.12 -m venv .venv          # optional: explicit venv in this directory
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install poetry                # if you don't have Poetry globally
poetry install
```

Alternatively, `poetry install` alone will create a venv according to your Poetry config.

### 1. Backend (Django)

```bash
cd backend
[ -f .env ] || cp .env.example .env               # copy only if missing
poetry install                                    # install Python dependencies
poetry run python manage.py migrate               # create database tables
poetry run python manage.py seed_models           # seed the five-pair offline shortlist
poetry run python manage.py createsuperuser       # (optional) admin account
poetry run python manage.py runserver 0.0.0.0:8000
```

Backend runs at http://localhost:8000. Django Admin at http://localhost:8000/admin/.

Do **not** require `sync_openrouter_models` to start. That optional command later fetches the public OpenRouter catalog (`GET https://openrouter.ai/api/v1/models`, unauthenticated, 20-second timeout, no retries). It must not own or disable the NIM row. There is no NIM catalog discovery. An unavailable catalog must not block boot. Leave `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` false unless a later task enables newest-first selection.

Redis is required only for websocket matchmaking, realtime sync, and chat. The default local URL is `redis://127.0.0.1:6379/0`.

### 2. Frontend (Next.js)

```bash
cd frontend
[ -f .env.local ] || cp .env.local.example .env.local
# Set server-only OPENROUTER_API_KEY and/or NVIDIA_API_KEY.
npm install                                       # install JS dependencies
npm run dev                                       # start dev server at :3000
```

Open http://localhost:3000, register, choose a mode, and play. Both keys live on the Next.js server. The UI still boots if either is missing or a placeholder; AI turns fail only when neither credential is usable. Bases are hardcoded: OpenRouter `https://openrouter.ai/api/v1` and NVIDIA NIM `https://integrate.api.nvidia.com/v1`; do not add base-URL env vars. There is no `NEXT_PUBLIC_DEFAULT_MODEL`; an empty stored selection resolves to catalog row 1.

### Environment Variables

**Backend** (`backend/.env`):
| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | - | Django secret key (required) |
| `DEBUG` | `True` | Debug mode |
| `DB_ENGINE` | `sqlite` | `sqlite` or `postgresql` |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Frontend origin(s) |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis connection used by Django Channels |
| `GAME_WS_TICKET_MAX_AGE_SECONDS` | `60` | Max age for signed websocket tickets |
| `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` | `false` | `false` = curated bootstrap pairs only; `true` = four newest eligible OpenRouter models plus seeded NIM. Must match `backend/config/settings.py`. |

**Frontend** (`frontend/.env.local`):
| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Django backend URL (browser) |
| `BACKEND_URL` | `http://localhost:8000` | Django backend URL (Next.js server routes) |
| `NEXT_DEV_ALLOWED_ORIGINS` | unset | Optional extra hosts allowed to load Next.js dev assets |
| `OPENROUTER_API_KEY` | `your-openrouter-api-key` | Server-only OpenRouter key from https://openrouter.ai/keys |
| `NVIDIA_API_KEY` | `your-nvidia-api-key` | Server-only NVIDIA NIM key from https://build.nvidia.com |

Native IDs only (never `openrouter/google/...`). The NIM id has no `:free` suffix and is not the FrameNest Omni/VLM.

**Flag-off legacy path** (`DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false`, the default): five curated bootstrap pairs. Catalog row 1 is OpenRouter Gemma:

1. `openrouter` — `google/gemma-4-31b-it:free`
2. `nvidia-nim` — `nvidia/nemotron-3-super-120b-a12b`
3. `openrouter` — `nvidia/nemotron-3-super-120b-a12b:free`
4. `openrouter` — `z-ai/glm-5.2:free`
5. `openrouter` — `google/gemma-4-26b-a4b-it:free`

**Flag-on**: the four newest eligible OpenRouter `:free` models plus the seeded NIM tuple last. A valid user preference remains attempt 1; remaining attempts follow untouched catalog order. New users receive catalog row 1 (newest when the flag is on).

Django Admin remains catalog authority; `is_active` (including deactivating the NIM row) is the operational kill switch. Play and Judge share one preference-first fallback queue capped at three distinct pairs. Play reports `provider_requests_used` in terminal SSE metadata and treats `max_steps` as the remaining whole-turn provider-call budget. Judge tries up to three sequential attempts (`maxRetries: 0`, 10 s each, 30 s overall) and returns HTTP 503 on exhaustion without synthesizing false invalid verdicts. Collins 2019 on Django remains the persisted-move validator. Stripe is rejected for this product direction. LM Studio, Vercel AI Gateway, Slovak dictionary, and push/deploy remain out of this cut.

### Docker (optional PostgreSQL + Redis)

```bash
cd libretiles
docker compose up -d
```

Then set `DB_ENGINE=postgresql` in `backend/.env` and re-run `migrate`.

### Startup Scripts (recommended)

```bash
# Start everything in detached dev mode (both backend + frontend):
./scripts/libretiles.sh

# Check status / logs / restart / stop:
./scripts/libretiles.sh status
./scripts/libretiles.sh logs
./scripts/libretiles.sh restart
./scripts/libretiles.sh stop

# Shortcut for restart:
./scripts/reload.sh

# Or run services separately in foreground:
./scripts/start-backend.sh   # Terminal 1
./scripts/start-frontend.sh  # Terminal 2
```

`libretiles.sh` keeps PID and log files under `./.dev/`, adopts already-running Libre Tiles dev processes on ports `8000` and `3000`, and prevents accidental double-starts that leave ports busy.

The scripts handle `.env` creation, dependency installation, migrations, and model seeding automatically.

### One-liner (SQLite dev mode)

```bash
# Terminal 1 (backend):
cd backend && [ -f .env ] || cp .env.example .env && poetry install && \
  poetry run python manage.py migrate && \
  poetry run python manage.py seed_models && \
  poetry run python manage.py runserver 0.0.0.0:8000

# Terminal 2 (frontend):
cd frontend && [ -f .env.local ] || cp .env.local.example .env.local && npm install && npm run dev
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for full technical documentation.

```
  Browser (Next.js)                   OpenRouter / NVIDIA NIM
  ┌─────────────────┐                ┌──────────────────┐
  │ React UI        │                │ Free rivals      │
  │ @dnd-kit + FM   │◄──────────────►│ newest-first /   │
  │ Zustand store   │  /api/ai/move  │ bootstrap pairs  │
  │                 │  /api/ai/judge          │
  │ Settings page   │        ▲                │ generateText()
  └────────┬────────┘        │                │ + tool calling
           │                 │                │
           │ REST API        │    Next.js API Routes
           │ (JWT auth)      │    ┌───────────────────┐
           ▼                 └────│ /api/ai/move      │
  ┌─────────────────┐            │ /api/ai/judge     │
  │ Django Backend   │◄───────────│ /api/models       │
  │                 │  callbacks  └───────────────────┘
  │ gamecore/       │
  │ game services   │  validate-move, validate-words
  │ Collins 2019    │  ai-context, ai-move
  │ admin panel     │
  └─────────────────┘
```

## AI Agent Tool Workflow

The AI opponent plays as a tool-calling agent (mirroring the desktop `scrabgpt` approach):

1. AI receives board state, rack, scores, tile values, premium legend
2. AI searches from board anchors and proposes candidate moves using tools:
   - `validateMove` -- checks placement legality, returns all formed words + scores
   - `validateWords` -- checks words against Collins 2019 (~279k words, O(1) lookup)
3. AI secures an early backend-validated scoring floor, then explores diverse families only while the shared step budget remains
4. Move is applied server-side via Django `/api/game/{id}/ai-move/` and re-validated against Collins 2019

The move prompt (`frontend/src/lib/prompts.ts`) is legality-first: anchor search, early validated scoring floor, budget-bounded diversity, absolute backend authority, and strict JSON. The judge prompt is Collins-2019-only with no natural-usage override.

During a turn the thinking overlay shows ordered rival pills bound to the attempt lifecycle, with a purely visual gold/black ping-pong tile on the active attempt (zero artificial delay, reduced-motion safe, readable without Premium Look).

## Project Structure

```
libretiles/
├── backend/
│   ├── config/          # Django settings, URLs, ASGI
│   ├── gamecore/        # Pure Python Libre Tiles engine (ported from scrabgpt/core)
│   ├── accounts/        # User auth (JWT)
│   ├── catalog/         # AI model catalog (seed_models + optional OpenRouter sync; NIM is Admin-seeded)
│   │   └── management/commands/
│   ├── game/            # Game sessions, moves, validation, AI tools
│   ├── billing/         # inert migration tombstone only; not a live Django app
│   ├── assets/          # Collins 2019 dictionary, premiums.json, variant data
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── app/         # Next.js pages (landing, game, settings, API routes)
│   │   ├── components/  # Board, Tile, TileRack, ScorePanel, GameControls...
│   │   ├── hooks/       # Zustand store (useGameStore)
│   │   └── lib/         # Types, API client, OpenRouter, NIM, model-catalog, prompts, constants
│   └── package.json
├── docs/                # Technical architecture docs
├── docker-compose.yml
├── AGENTS.md            # Handoff guide for coding agents / maintainers
├── libretiles_PRD.md    # Product Requirements Document
├── CONTRIBUTING.md      # Contributor guide
└── README.md
```

## API Endpoints

### Auth
- `POST /api/auth/register/` -- Create account
- `POST /api/auth/login/` -- Get JWT tokens
- `POST /api/auth/refresh/` -- Refresh access token
- `GET /api/auth/me/` -- Current user profile
- `POST /api/auth/change-password/` -- Change password for the authenticated user

### Catalog
- `GET /api/catalog/models/` -- List selectable free rivals in canonical order (flag-off bootstrap pairs, or flag-on newest-four-plus-NIM). Row 1 is `is_flagship` / `recommended`. Exposes `released_at`; no money fields.

### Game
- `POST /api/game/create/` -- Start new AI game
- `POST /api/game/queue/join/` -- Join or create the global human waiting room
- `POST /api/game/queue/cancel/` -- Cancel an unmatched waiting game
- `GET /api/game/{id}/` -- Get game state + only the requesting player's private rack
- `POST /api/game/{id}/ws-ticket/` -- Mint a short-lived signed websocket ticket
- `POST /api/game/{id}/move/` -- Submit tile placement as the authenticated user
- `POST /api/game/{id}/exchange/` -- Exchange tiles as the authenticated user
- `POST /api/game/{id}/pass/` -- Pass turn as the authenticated user
- `POST /api/game/{id}/give-up/` -- Resign the game

### AI Tool Endpoints (called by Next.js API routes)
- `GET /api/game/{id}/ai-context/` -- Compact board state for AI prompt
- `POST /api/game/{id}/validate-move/` -- Validate placement legality + score
- `POST /api/game/{id}/validate-words/` -- Check words in Collins 2019 dictionary
- `POST /api/game/{id}/ai-pass/` -- Apply an AI pass on the server
- `POST /api/game/{id}/ai-exchange/` -- Apply an AI exchange on the server
- `POST /api/game/{id}/ai-move/` -- Apply AI-proposed move (re-validates server-side)

### Frontend API Routes (Next.js)
- `POST /api/ai/move` -- AI move generation (tool-calling agent; sequential fallback)
- `POST /api/ai/judge` -- AI word judge (Tier 3; same queue, up to three attempts, HTTP 503 on exhaustion)
- `GET /api/models` -- Proxy for Django catalog

## Operations (catalog refresh)

The documented production schedule is `libretiles-openrouter-catalog-refresh`, daily at 03:17 UTC, invoking `python manage.py sync_openrouter_models` under a non-overlapping platform lock. One scheduled run performs exactly one unauthenticated OpenRouter catalog GET with a 20-second timeout, no retries, no per-model probes, and no NVIDIA/NIM request. The scheduler itself is configured only under separate production authority — this repository documents it and does not install it.

Rollout: deploy backend with the dynamic flag false → deploy the dynamic-capable frontend → run migrate/sync evidence → enable `DYNAMIC_FREE_MODEL_CATALOG_ENABLED`. Rollback: set the flag false and restart Django; pause the schedule and/or deactivate rows in Admin; roll backend selection back to curated-only before rolling back the dynamic-capable frontend.

## Testing

```bash
# Backend
cd backend
poetry run pytest                          # All tests
poetry run pytest tests/test_gamecore.py   # Pure game logic (fast, offline)
poetry run pytest tests/test_dictionary_validation.py  # Collins 2019 / invalid-word regressions
poetry run pytest tests/test_api.py        # Django API tests
poetry run ruff check .                    # Lint
poetry run mypy .                          # Type check

# Frontend
cd frontend
npm run lint                               # ESLint
npx tsc --noEmit                           # TypeScript check
```

## Tech Stack

### Backend
- Python 3.11+, Django 5.x, Django REST Framework
- Django Channels + Redis for realtime multiplayer and chat
- JWT auth (djangorestframework-simplejwt)
- PostgreSQL (prod) / SQLite (dev)
- Collins 2019 English dictionary (~279k words, O(1) frozenset lookup)

### Frontend
- Next.js 16, React 19, TypeScript
- Tailwind CSS 4, Framer Motion, @dnd-kit/core
- Vercel AI SDK v6 via OpenRouter and NVIDIA NIM (OpenAI-compatible adapter, tool calling)
- Zustand (state management with localStorage persistence)
- canvas-confetti (endgame effects)

## Game Engine

The `gamecore/` package is a pure Python Libre Tiles engine with zero framework dependencies:

- `board.py` -- 15x15 board with premium squares
- `rules.py` -- Move validation (center coverage, line placement, connectivity, gaps)
- `scoring.py` -- Score calculation with premium multipliers and bingo bonus
- `tiles.py` -- Tile bag with English distribution (100 tiles)
- `game.py` -- Full game simulation with endgame detection
- `variant_store.py` -- Variant loading (English by default)
- `fastdict.py` -- In-memory dictionary lookup (O(1) via frozenset)

Conceptually aligned with the desktop `scrabgpt` engine; this tree ships its **own** `gamecore/` and dictionary file.

## Troubleshooting

- **Invalid word but the server “accepted” it** — Distinguish between an **AI overlay candidate** (may show `valid: false`) and a **saved move**. Word validity is always decided by Django (`submit_move` / `validate_move_for_ai`) using `backend/assets/dicts/collins2019.txt`. Regression tests: `tests/test_dictionary_validation.py`.
- **Weak AI play** — Switch among the selectable free rivals, raise timeout / search steps in Settings, and tune `frontend/src/lib/prompts.ts` (see [AGENTS.md](AGENTS.md)). Do not buy a paid catalog tier for this cut.
- **Judge returned 503** — All fallback attempts failed or the catalog was empty. The route does not invent invalid verdicts from malformed output; retry or switch rivals.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and how to submit changes. **[AGENTS.md](AGENTS.md)** is the maintainer/agent handoff doc.

## License

MIT
