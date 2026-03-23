# Libre Tiles

Open-source web Libre Tiles game with AI opponents, live human-vs-human multiplayer, and an eye-candy animated frontend.

**Architecture**: Next.js frontend on Vercel (AI Gateway + beautiful UI) + lightweight Django backend (game logic, validation, admin).

**Standalone repository**: This folder is intended to be published as its **own** GitHub repository. It does **not** depend on the parent `scrabgpt_sk` monorepo — all assets and code live under `libretiles/`. For agent/continuation notes see **[AGENTS.md](AGENTS.md)**.

## Features

- Full Libre Tiles game engine (English variant, Collins 2019 dictionary ~279k words, Tier-1 strict validation in Django)
- AI opponents via Vercel AI Gateway -- choose from OpenAI, Google, Anthropic models
- Live human-vs-human multiplayer with waiting-room matchmaking, realtime board sync, and in-game chat
- AI plays as a tool-calling agent: validates moves, checks words, calculates scores
- Advanced drag-and-drop with touch/mobile support (@dnd-kit)
- Animated tile drawing, scoring, and game-end effects (Framer Motion, confetti)
- Django Admin for all configuration (AI models, pricing, games)
- Settings page with model selector cards
- Per-game credit billing based on AI model cost
- Responsive design (desktop, tablet, mobile)
- 3-tier word validation: local Collins 2019, online API (optional), AI judge

## Quick Start

For AI-only local development you need **two terminals**: one for the Django backend, one for the Next.js frontend. For live human-vs-human multiplayer you also need a running Redis instance for Django Channels.

### Python environment (backend)

Recommended: let **Poetry** create and use a virtualenv under `backend/.venv` (gitignored):

```bash
cd libretiles/backend
python3.12 -m venv .venv          # optional: explicit venv in this directory
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install poetry                # if you don't have Poetry globally
poetry install
```

Alternatively, `poetry install` alone will create a venv according to your Poetry config.

### 1. Backend (Django)

```bash
cd libretiles/backend
cp .env.example .env                             # create env (edit SECRET_KEY)
poetry install                                    # install Python dependencies
poetry run python manage.py migrate               # create database tables
poetry run python manage.py seed_models           # seed AI model catalog
poetry run python manage.py sync_gateway_models   # sync latest Gateway model metadata
poetry run python manage.py createsuperuser       # (optional) admin account
poetry run python manage.py runserver 0.0.0.0:8000
```

Backend runs at http://localhost:8000. Django Admin at http://localhost:8000/admin/.

Redis must be running for websocket matchmaking, realtime sync, and chat. The default local URL is `redis://127.0.0.1:6379/0`.

### 2. Frontend (Next.js)

```bash
cd libretiles/frontend
cp .env.local.example .env.local                  # configure API URL + AI keys
npm install                                       # install JS dependencies
npm run dev                                       # start dev server at :3000
```

Open http://localhost:3000, register, choose a mode, and play.

`sync_gateway_models` fetches the latest public catalog from `https://ai-gateway.vercel.sh/v1/models`, updates technical metadata in `catalog.AIModel`, and keeps newly discovered models inactive by default unless you pass `--activate-new`.

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

**Frontend** (`frontend/.env.local`):
| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Django backend URL |
| `BACKEND_URL` | `http://localhost:8000` | Backend URL (server-side) |
| `OPENAI_API_KEY` | - | OpenAI API key (local dev) |
| `AI_GATEWAY_API_KEY` | - | Vercel AI Gateway key (production) |
| `NEXT_PUBLIC_DEFAULT_MODEL` | `openai/gpt-4o-mini` | Default AI model |

### Docker (optional PostgreSQL + Redis)

```bash
cd libretiles
docker compose up -d
```

Then set `DB_ENGINE=postgresql` in `backend/.env` and re-run `migrate`.

### Startup Scripts (recommended)

```bash
# Start everything in detached dev mode (both backend + frontend):
cd libretiles
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
cd libretiles/backend && cp .env.example .env && poetry install && \
  poetry run python manage.py migrate && \
  poetry run python manage.py seed_models && \
  poetry run python manage.py sync_gateway_models && \
  poetry run python manage.py runserver 0.0.0.0:8000

# Terminal 2 (frontend):
cd libretiles/frontend && cp .env.local.example .env.local && npm install && npm run dev
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for full technical documentation.

```
  Browser (Next.js)                   Vercel AI Gateway
  ┌─────────────────┐                ┌──────────────────┐
  │ React UI        │                │ OpenAI / Google / │
  │ @dnd-kit + FM   │◄──────────────►│ Anthropic models  │
  │ Zustand store   │  /api/ai/move  └──────────────────┘
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
2. AI proposes candidate moves using tools:
   - `validateMove` -- checks placement legality, returns all formed words + scores
   - `validateWords` -- checks words against Collins 2019 (~279k words, O(1) lookup)
3. AI iterates 2-3+ candidates, picks the highest-scoring legal move
4. Move is applied server-side via Django `/api/game/{id}/ai-move/`

The prompt is ported from the desktop app's unified move template with strategic priorities, blank policy, anti-blunder rules, and no-scoring fallback logic.

## Project Structure

```
libretiles/
├── backend/
│   ├── config/          # Django settings, URLs, ASGI
│   ├── gamecore/        # Pure Python Libre Tiles engine (ported from scrabgpt/core)
│   ├── accounts/        # User auth (JWT)
│   ├── catalog/         # AI model catalog (admin-managed + gateway sync)
│   │   └── management/commands/
│   ├── game/            # Game sessions, moves, validation, AI tools
│   ├── billing/         # Credits + transactions (v2)
│   ├── assets/          # Collins 2019 dictionary, premiums.json, variant data
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── app/         # Next.js pages (landing, game, settings, API routes)
│   │   ├── components/  # Board, Tile, TileRack, ScorePanel, GameControls...
│   │   ├── hooks/       # Zustand store (useGameStore)
│   │   └── lib/         # Types, API client, AI gateway, prompts, constants
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
- `GET /api/catalog/models/` -- List active AI models with pricing

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
- `POST /api/ai/move` -- AI move generation (tool-calling agent)
- `POST /api/ai/judge` -- AI word judge (Tier 3 validation)
- `GET /api/models` -- Proxy for Django catalog

## Testing

```bash
# Backend
cd libretiles/backend
poetry run pytest                          # All tests
poetry run pytest tests/test_gamecore.py   # Pure game logic (fast, offline)
poetry run pytest tests/test_dictionary_validation.py  # Collins 2019 / invalid-word regressions
poetry run pytest tests/test_api.py        # Django API tests
poetry run ruff check .                    # Lint
poetry run mypy .                          # Type check

# Frontend
cd libretiles/frontend
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
- Vercel AI SDK v6 (AI Gateway, tool calling, structured output)
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
- **Weak AI play** — Use a stronger catalog model, raise the timeout in settings, and tune prompts in `frontend/src/lib/prompts.ts` (see [AGENTS.md](AGENTS.md)).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and how to submit changes. **[AGENTS.md](AGENTS.md)** is the maintainer/agent handoff doc.

## License

MIT
