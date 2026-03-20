# Agent / contributor guide (Libre Tiles)

This document is for **automated coding agents** and humans who continue development after the repository is published on GitHub. The project is **standalone** — it does not require the parent `scrabgpt_sk` repository.

## What Libre Tiles is

- **Frontend**: Next.js (React), Tailwind, Framer Motion, Zustand, DnD Kit; AI via Vercel AI Gateway (Next.js API routes).
- **Backend**: Django + DRF; pure game logic in `gamecore/` (board, rules, scoring, Collins 2019 dictionary).
- **Separation**: No imports outside `libretiles/`. All assets (dictionary, premiums, variants) live under `backend/assets/`.

## Quick start (local)

1. **Backend** (recommended: Poetry + virtual environment in `backend/.venv`):

   ```bash
   cd backend
   python3.12 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install poetry
   poetry install
   cp .env.example .env
   poetry run python manage.py migrate
   poetry run python manage.py seed_models
   poetry run python manage.py runserver 0.0.0.0:8000
   ```

2. **Frontend**:

   ```bash
   cd frontend
   cp .env.local.example .env.local
   npm install
   npm run dev
   ```

3. Or from the repo root: `./scripts/libretiles.sh` (see [README.md](README.md)).

## Code quality

From `backend/`:

```bash
poetry run ruff check .
poetry run mypy config game gamecore accounts catalog billing
poetry run pytest
```

From `frontend/`:

```bash
npm run lint
npm run build
```

## Key files

| Area | Path |
|------|------|
| Game engine (pure Python) | `backend/gamecore/` |
| API and game state | `backend/game/services.py`, `backend/game/views.py` |
| Collins 2019 dictionary (Tier 1) | `backend/assets/dicts/collins2019.txt` |
| Word validation (lazy load) | `services._get_dictionary()`, `_word_passes_dictionary()` |
| AI stream (SSE) | `frontend/src/app/api/ai/move/route.ts` |
| Agent prompts | `frontend/src/lib/prompts.ts` |
| Game UI | `frontend/src/app/game/[id]/page.tsx` |

## Word validation (important)

- The **source of truth** for whether a word is valid is the **backend** — `submit_move` and `validate_move_for_ai` must always go through `_word_passes_dictionary()` + Collins 2019.
- AI **candidates** in the overlay may show invalid attempts (`valid: false`); the final move is always **re-validated** on the server.
- If someone reports that the “backend accepted” an invalid word: check whether it was an **overlay candidate** vs. a **persisted move**; add a regression test under `backend/tests/`.
- The dictionary is not copied from `scrabgpt_sk` — maintain it only in `libretiles/backend/assets/dicts/`.

## Making the AI stronger

- **Model**: higher tier in Django Admin / catalog (`catalog.AIModel`) + `NEXT_PUBLIC_DEFAULT_MODEL`.
- **Time**: `aiTimeout` in frontend settings (store) and the SSE route.
- **Prompt**: `frontend/src/lib/prompts.ts` — strategy, tools, anti-pass logic; change carefully and test against backend validation.

## Deployment

- Frontend: Vercel (env from `frontend/.env.local.example`).
- Backend: VPS / PaaS with PostgreSQL in production; see `docs/architecture.md` and `README.md`.

## Security

- Never commit `.env`, `backend/.env`, or `frontend/.env.local`.
- Template files `.env.example` / `.env.local.example` are fine to commit.

## Not done yet (typical next steps)

- Human-vs-human multiplayer (API is structured for extension).
- Stripe / billing completion.
- Tier 2 / 3 dictionary (optional API, AI judge) — see PRD and `docs/architecture.md`.
