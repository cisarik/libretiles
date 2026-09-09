# Contributing to Libre Tiles

Thank you for your interest in contributing! This guide covers everything you need to get productive quickly.

## Development Setup

### Prerequisites

- Python 3.12 recommended with [Poetry](https://python-poetry.org/) 2.3.2 or newer. The backend manifest permits Python >=3.11,<3.14; the documented VPS setup uses 3.12.
- Node.js 24 recommended with npm; the documented tooling also supports Node 20.19+ or 22.12+.
- Git
- (Optional) Docker + Docker Compose for PostgreSQL/Redis

### First-time setup

The recommended local supervisor in [README.md](README.md#local-development) generates the key when creating a new backend environment file. The manual setup below requires you to set it before migrations.

```bash
# Clone and enter the project (this repo root is libretiles/)
git clone <repo-url>
cd libretiles

# Backend — optional: dedicated venv in backend/.venv (gitignored)
cd backend
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
[ -f .env ] || cp .env.example .env
# Before continuing, privately set DJANGO_SECRET_KEY in .env:
# at least 50 characters, at least 5 unique, no django-insecure- prefix.
# The example is empty; preserve an existing valid key.
poetry install
poetry run python manage.py migrate
poetry run python manage.py seed_models
poetry run python manage.py createsuperuser

# Frontend
cd ../frontend
[ -f .env.local ] || cp .env.local.example .env.local
# For the seeded compatibility catalog, set server-only OPENROUTER_API_KEY and/or NVIDIA_API_KEY.
# Other integrations need their documented credentials and explicit catalog activation.
npm install
```

See **[AGENTS.md](AGENTS.md)** for architecture notes, validation rules, and tips for coding agents continuing the project.

### Running locally

AI-only play is two terminals. Redis is required only for human-vs-human websockets.

```bash
# Terminal 1 (from repository root): Django backend
cd backend && poetry run python manage.py runserver 127.0.0.1:8000

# Terminal 2 (from repository root): Next.js frontend
cd frontend && npm run dev
```

### Production deployment

Production uses Next.js standalone and Daphne/Django under systemd behind nginx on a self-hosted VPS, with PostgreSQL and Redis. Follow the [VPS deployment guide](docs/vps_deployment_guide.md) for production setup; the commands above start development servers.

## Code Quality

We enforce code quality with automated tools. Please run these before submitting:

### Backend (Python)

```bash
cd backend
poetry run ruff check .              # Linter
poetry run ruff format --check .     # Formatter
poetry run mypy config game gamecore accounts catalog    # Type checker (strict mode)
poetry run pytest                    # Tests
```

**Style rules:**
- Ruff line length: 100 characters
- mypy strict mode enabled
- Explicit typing for public interfaces and async functions
- Keep `gamecore/` pure (no Django, no network, no UI dependencies)

### Frontend (TypeScript)

```bash
cd frontend
npm run lint                         # ESLint
npm run typecheck                    # TypeScript strict check
```

**Style rules:**
- Strict TypeScript (no `any` unless justified)
- Prefer named exports
- Components in PascalCase files

## Project Architecture

This repository is self-contained. Next.js serves the UI and orchestrates external AI calls; Django owns game state and authoritative validation; Django Channels and Redis provide human multiplayer. See [the architecture guide](docs/architecture.md) for data flows and [the VPS guide](docs/vps_deployment_guide.md) for production topology.

### Key principles

1. **gamecore/ is pure Python** -- no Django imports, no network calls. It's the game engine.
2. **Django handles state + validation** -- all game logic goes through `game/services.py`.
3. **Next.js API routes handle AI** -- the AI agent runs in Next.js, calls Django for validation.
4. **Admin-first catalog** -- `seed_models` creates the compatibility bootstrap rows and inactive prepared direct/watchlist rows without changing existing activation. Eligible active direct rows precede the compatibility tail. `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` changes only that tail: curated bootstrap pairs when false, up to four newest eligible OpenRouter rows plus eligible seeded NIM when true. Activation and fallback ordering use the reviewed Django Admin workflow; `is_active` remains the kill switch.
5. **AI plays with tools** -- the AI model proposes moves through tools and Django validates them. Play and Judge share one preference-first fallback queue capped at three distinct pairs.
6. **Free-only play** -- the product does not handle money. Historical `backend/billing/migrations/` files are an inert, uninstalled tombstone, not a live Django app or a credits feature.

### Where to find things

| Concern | Location |
|---------|----------|
| Game rules (board, scoring, tiles) | `backend/gamecore/` |
| Game state management | `backend/game/services.py` |
| REST API endpoints | `backend/game/views.py` |
| AI model catalog | `backend/catalog/` |
| AI move generation | `frontend/src/app/api/ai/move/route.ts` |
| AI prompts | `frontend/src/lib/prompts.ts` |
| OpenRouter client | `frontend/src/lib/openrouter.ts` |
| NVIDIA NIM client | `frontend/src/lib/nvidia-nim.ts` |
| Runtime dispatch | `frontend/src/lib/ai-runtimes.ts` |
| Catalog pair resolution | `frontend/src/lib/model-catalog.ts` |
| Per-turn fallback (Play + Judge) | `frontend/src/lib/ai-fallback.ts` |
| Catalog selection / flag | `backend/catalog/selection.py` |
| Game UI components | `frontend/src/components/` |
| Client state | `frontend/src/hooks/useGameStore.ts` |

## Making Changes

### Adding a new AI tool

1. Add a Django API endpoint in `backend/game/views.py` + `services.py`
2. Register the URL in `backend/game/urls.py`
3. Add the tool definition in `frontend/src/app/api/ai/move/route.ts`
4. Update the system prompt in `frontend/src/lib/prompts.ts` if needed

### Changing the free-rival shortlist

Eligible active direct rows precede the NIM/OpenRouter compatibility tail. With `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false`, that tail uses the curated `FREE_RIVAL_PAIRS`; with the flag enabled, it uses up to four newest eligible OpenRouter models plus eligible seeded NIM. The reviewed Admin workflow controls activation and applicable ordering. Stripe is rejected for this product direction. LM Studio and Vercel AI Gateway remain historical rejections, not live routing.

Membership and selection live in `backend/catalog/selection.py` and `seed_models.py`. Frontend runtime validation uses exact registry pairs for direct/watchlist/NIM integrations and structural `:free` validation for OpenRouter, together with live Django catalog membership. Use native IDs; the NIM id has no `:free` suffix. See [provider activation and catalog operations](docs/architecture.md#catalog-operations-rollout-and-rollback). Configuring the documented `libretiles-openrouter-catalog-refresh` host schedule requires separate production authority.

### Modifying game rules

1. Change logic in `backend/gamecore/` (keep it pure Python)
2. Update `backend/game/services.py` if the service layer is affected
3. Add/update tests in `backend/tests/test_gamecore.py`
4. Update the AI prompt in `frontend/src/lib/prompts.ts`

## Testing

### Backend tests

Run these commands from `backend/`.

```bash
# Fast offline tests (gamecore only)
poetry run pytest tests/test_gamecore.py -v

# Full API tests
poetry run pytest tests/test_api.py -v

# All tests
poetry run pytest -v
```

### Test categories

- **Gamecore tests** -- pure Python, no network, no DB; cover rules, scoring, and dictionary regressions.
- **API tests** -- use Django TestCase, create real DB records.
- **Live provider probes** -- explicit operator checks, separate from ordinary tests; see [the capability-probe guide](docs/architecture.md#explicit-capability-probe-boundary).

## Submitting Changes

1. Fork the repo and create a feature branch from `main`
2. Make your changes with tests
3. Run lint + type check + tests (see Code Quality above)
4. Write a clear commit message (imperative, concise)
5. Open a PR with:
   - Summary of what changed and why
   - Test evidence (pytest output or screenshots)
   - Note any env variable or DB migration changes
   - Screenshots for UI changes

## Environment Variables

See `backend/.env.example` and `frontend/.env.local.example` for all available variables with descriptions. Never commit `.env` or `.env.local` files.

## Questions?

Open a GitHub Issue or Discussion. We're happy to help!
