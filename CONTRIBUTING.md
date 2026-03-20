# Contributing to Libre Tiles

Thank you for your interest in contributing! This guide covers everything you need to get productive quickly.

## Development Setup

### Prerequisites

- Python 3.11+ with [Poetry](https://python-poetry.org/)
- Node.js 20+ with npm
- Git
- (Optional) Docker + Docker Compose for PostgreSQL/Redis

### First-time setup

```bash
# Clone and enter the project (this repo root is libretiles/)
git clone <repo-url>
cd libretiles

# Backend — optional: dedicated venv in backend/.venv (gitignored)
cd backend
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
cp .env.example .env
poetry install
poetry run python manage.py migrate
poetry run python manage.py seed_models
poetry run python manage.py createsuperuser

# Frontend
cd ../frontend
cp .env.local.example .env.local
# Prefer AI_GATEWAY_API_KEY + AI_GATEWAY_BASE_URL for Vercel AI Gateway (see .env.local.example)
npm install
```

See **[AGENTS.md](AGENTS.md)** for architecture notes, validation rules, and tips for coding agents continuing the project.

### Running locally

```bash
# Terminal 1: Django backend
cd backend && poetry run python manage.py runserver 0.0.0.0:8000

# Terminal 2: Next.js frontend
cd frontend && npm run dev
```

## Code Quality

We enforce code quality with automated tools. Please run these before submitting:

### Backend (Python)

```bash
cd backend
poetry run ruff check .              # Linter
poetry run ruff format --check .     # Formatter
poetry run mypy .                    # Type checker (strict mode)
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
npx tsc --noEmit                     # TypeScript strict check
```

**Style rules:**
- Strict TypeScript (no `any` unless justified)
- Prefer named exports
- Components in PascalCase files

## Project Architecture

```
Backend (Django)           Frontend (Next.js)          AI Models
┌──────────────┐          ┌──────────────────┐       ┌─────────────┐
│ gamecore/    │◄─────────│ /api/ai/move     │──────►│ Vercel AI   │
│ game/        │ validate │ /api/ai/judge    │       │ Gateway     │
│ accounts/    │ + score  │ /api/models      │       │ (or direct) │
│ catalog/     │          │                  │       └─────────────┘
│ billing/     │          │ React UI         │
│ config/      │          │ Zustand store    │
└──────────────┘          └──────────────────┘
```

### Key principles

1. **gamecore/ is pure Python** -- no Django imports, no network calls. It's the game engine.
2. **Django handles state + validation** -- all game logic goes through `game/services.py`.
3. **Next.js API routes handle AI** -- the AI agent runs in Next.js, calls Django for validation.
4. **Admin-first config** -- all models, pricing, settings come from Django Admin.
5. **AI plays with tools** -- the AI model uses tool calling to validate its own moves.

### Where to find things

| Concern | Location |
|---------|----------|
| Game rules (board, scoring, tiles) | `backend/gamecore/` |
| Game state management | `backend/game/services.py` |
| REST API endpoints | `backend/game/views.py` |
| AI model catalog | `backend/catalog/` |
| AI move generation | `frontend/src/app/api/ai/move/route.ts` |
| AI prompts | `frontend/src/lib/prompts.ts` |
| AI gateway config | `frontend/src/lib/ai-gateway.ts` |
| Game UI components | `frontend/src/components/` |
| Client state | `frontend/src/hooks/useGameStore.ts` |

## Making Changes

### Adding a new AI tool

1. Add a Django API endpoint in `backend/game/views.py` + `services.py`
2. Register the URL in `backend/game/urls.py`
3. Add the tool definition in `frontend/src/app/api/ai/move/route.ts`
4. Update the system prompt in `frontend/src/lib/prompts.ts` if needed

### Adding a new AI model provider

1. Add the provider to `PROVIDER_CHOICES` in `backend/catalog/models.py`
2. Add it to `seed_models.py` default list
3. Add provider icon in `frontend/src/app/settings/page.tsx`
4. If the provider isn't OpenAI-compatible, update `frontend/src/lib/ai-gateway.ts`

### Modifying game rules

1. Change logic in `backend/gamecore/` (keep it pure Python)
2. Update `backend/game/services.py` if the service layer is affected
3. Add/update tests in `backend/tests/test_gamecore.py`
4. Update the AI prompt in `frontend/src/lib/prompts.ts`

## Testing

### Backend tests

```bash
# Fast offline tests (gamecore only)
poetry run pytest tests/test_gamecore.py -v

# Full API tests
poetry run pytest tests/test_api.py -v

# All tests
poetry run pytest -v

# With coverage
poetry run pytest --cov=. --cov-report=html
```

### Test categories

- **Gamecore tests** -- pure Python, no network, no DB. Always pass.
- **API tests** -- use Django TestCase, create real DB records.
- **AI tests** -- marked with `@pytest.mark.internet`, require API keys.

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
