# Agent / contributor guide (Libre Tiles)

This document is for **automated coding agents** and humans who continue development after the repository is published on GitHub. The project is **standalone** — it does not require the parent `scrabgpt_sk` repository.

## What Libre Tiles is

- **Frontend**: Next.js (React), Tailwind, Framer Motion, Zustand, DnD Kit; AI via provider-diverse free rivals on Next.js API routes. Nine providers are shipped: `openrouter`, `nvidia-nim`, `groq`, `google-gemini`, `cloudflare-workers-ai`, `mistral`, `ibm-watsonx`, `aion`, `huggingface`. Dispatch is `frontend/src/lib/openai-compatible.ts` plus `frontend/src/lib/ibm-watsonx.ts`.
- **Backend**: Django + DRF; pure game logic in `gamecore/` (board, rules, scoring, Collins 2019 dictionary).
- **Realtime**: Django Channels + Redis for human-vs-human matchmaking, websocket sync, and chat.
- **Separation**: No imports outside `libretiles/`. All assets (dictionary, premiums, variants) live under `backend/assets/`.

## Quick start (local)

AI-only local play needs two terminals (Django + Next.js). Redis is required only for human-vs-human websockets, not for AI-only boot.

1. **Backend** (recommended: Poetry + virtual environment in `backend/.venv`):

   ```bash
   cd backend
   python3.12 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install poetry
   poetry install
   # Prefer ./scripts/libretiles.sh from the repo root: it copies .env.example
   # only when backend/.env is absent and generates DJANGO_SECRET_KEY into that
   # new file. A pre-existing .env is never overwritten. Do not copy a literal
   # example key. If you create .env by hand, set DJANGO_SECRET_KEY yourself
   # (≥50 characters, ≥5 unique, no django-insecure- prefix).
   [ -f .env ] || cp .env.example .env
   poetry run python manage.py migrate
   poetry run python manage.py seed_models
   poetry run python manage.py runserver 0.0.0.0:8000
   ```

   `seed_models` loads the offline five-pair bootstrap shortlist (four OpenRouter rows plus one NVIDIA NIM row). Do not require `sync_openrouter_models` to start; that optional public catalog fetch is later and non-blocking. It must not own or disable the NIM row. There is no NIM catalog discovery.

   Selection is gated by `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` (default `false` in `backend/config/settings.py`). `false` returns only those curated bootstrap pairs. `true` returns the four newest eligible OpenRouter models plus the seeded NIM tuple. Leave the flag false for local boot unless a later task explicitly enables it.

2. **Frontend**:

   ```bash
   cd frontend
   [ -f .env.local ] || cp .env.local.example .env.local
   # Set server-only OPENROUTER_API_KEY and/or NVIDIA_API_KEY (see frontend/.env.local.example).
   npm install
   npm run dev
   ```

   Both keys live on the Next.js server. The UI still boots if either is missing or a placeholder; AI turns fail only when neither credential is usable. There is no `NEXT_PUBLIC_DEFAULT_MODEL`; pages resolve an empty Zustand `selectedModelId` against catalog row 1.

3. Or from the repo root: `./scripts/libretiles.sh` (see [README.md](README.md)). Scripts copy env examples only when the target file is absent, and generate `DJANGO_SECRET_KEY` into a freshly created `backend/.env`. A pre-existing `.env` overrides new code defaults, is read once at process start, and must be reviewed after any settings change.

## Code quality

From `backend/`:

```bash
poetry run ruff check .
poetry run mypy config game gamecore accounts catalog
poetry run pytest
```

From `frontend/`:

```bash
npm run typecheck
npm run lint
npm run build
```

## Key files

| Area | Path |
|------|------|
| Game engine (pure Python) | `backend/gamecore/` |
| API and game state | `backend/game/services.py`, `backend/game/views.py` |
| Multiplayer websocket/auth | `backend/game/consumers.py`, `backend/game/routing.py` |
| Collins 2019 dictionary (Tier 1) | `backend/assets/dicts/collins2019.txt` |
| Slovak lexicon (hunspell-sk expansion; playable, not SSS-official) + SSS 100 variant | `backend/assets/dicts/slovak.txt`, `backend/assets/variants/slovak.json` |
| Word validation (lazy load) | `services._get_dictionary()`, `_word_passes_dictionary()` |
| AI stream (SSE) | `frontend/src/app/api/ai/move/route.ts` |
| OpenRouter client | `frontend/src/lib/openrouter.ts` |
| NVIDIA NIM client | `frontend/src/lib/nvidia-nim.ts` |
| Provider registry (nine provider constants) | `frontend/src/lib/provider-registry.ts` |
| OpenAI-compatible runtime constructor | `frontend/src/lib/openai-compatible.ts` |
| IBM watsonx runtime | `frontend/src/lib/ibm-watsonx.ts` |
| Runtime dispatch | `frontend/src/lib/ai-runtimes.ts` |
| Catalog pair resolution | `frontend/src/lib/model-catalog.ts` |
| Shared Play/Judge fallback queue | `frontend/src/lib/ai-fallback.ts` |
| SSE terminal + `provider_requests_used` | `frontend/src/lib/ai-move-stream.ts` |
| Authoritative AI legality / playability | `backend/gamecore/legality.py` |
| Bounded witness search | `backend/gamecore/move_search.py` |
| 300-turn causal simulation | `frontend/src/lib/ai-turn-simulation.test.ts` |
| Catalog seed | `backend/catalog/management/commands/seed_models.py` |
| Optional catalog sync | `backend/catalog/management/commands/sync_openrouter_models.py` |
| Catalog selection (flag + ranking) | `backend/catalog/selection.py` |
| Seeded-prompt hash-gated refresh | `backend/catalog/migrations/0010_refresh_seeded_prompts.py` |
| Agent prompts | `frontend/src/lib/prompts.ts` |
| Game UI | `frontend/src/app/game/[id]/page.tsx` |
| Fallback attempt pills | `frontend/src/components/game/AIThinkingOverlay.tsx` |
| Header / game chrome | `frontend/src/components/game/ScorePanel.tsx`, `frontend/src/components/game/GameControls.tsx` |
| Shared premium UI effect + ping-pong motion | `frontend/src/lib/premiumSurface.ts` |
| Lexicon build scripts (pinned upstream) | `backend/scripts/build_slovak_lexicon.py`, `backend/scripts/build_czech_lexicon.py`, `backend/scripts/build_polish_lexicon.py` |
| Lexicon provenance in manifests | `backend/assets/variants/*.json` → `lexicon_provenance` |
| Lexicon asset validation | `backend/gamecore/lexicon_health.py`, `manage.py validate_lexicons` |

Every non-English lexicon is reproducible from a pinned upstream commit by its committed script: each pins the upstream commit and the SHA-256 of every source file it fetches, pins the host expander (`hunspell 1.7.3`) and fails closed on a mismatch, and writes the lexicon plus its `.LICENSE`. Adding `--check --check-dir <dir outside backend/assets/>` re-verifies a committed asset instead of rebuilding it: the reproduction goes into that directory, both digests are printed per artifact, the exit code is non-zero on any mismatch, and the run refuses outright if its working directory resolves inside `backend/assets/`. The scripts are host tools — not imported by Django, and they add no Poetry or npm dependency.

## Current product state (August 2026)

- Human-vs-human multiplayer is live:
  - queue join/cancel
  - waiting-room flow
  - websocket realtime sync
  - in-game chat
  - server-derived acting slot only; client slot trust removed
- Profile UX is now available directly from the game header:
  - `Profile` modal
  - password change flow via `POST /api/auth/change-password/`
  - `Logout` shortcut in the same header cluster
- The frontend now has a reusable premium surface system:
  - shared pointer-reactive gold/black chrome in `frontend/src/lib/premiumSurface.ts`
  - used by settings plus the game header/footer
  - controlled by the persisted `premiumLookEnabled` store flag
- Libre Tiles is a **free-only** product: it does not handle money, app credits, USD balances, token prices, or per-game charges. Play and Judge share one preference-first fallback queue over the selectable free-rival catalog (flag-off: five curated bootstrap pairs; flag-on: four newest eligible OpenRouter models plus the seeded NIM tuple). Provider quotas or trial terms are external and may change; they are not Libre Tiles credits or charges. Stripe is rejected for this product direction.
- Authoritative playability: `GET /api/game/{id}/ai-playability/` returns `found|none|indeterminate` plus an optional witness. AI pass/exchange are rejected with 409 `legal_scoring_move_exists` | `playability_unknown` | `exchange_required` when a legal scoring placement exists or playability is unknown. Bounded sanitized `ai_metadata` is stored on every AI terminal.
- Tool-only move pipeline: `/api/ai/move` gives free-form model text no authority over pass/exchange/place. The first step is forced `validateMove`; `finishMove({ready:true})` may run only after a backend-valid candidate. A 2-step repair reserve stays inside the same granted `max_steps`. `completion_source` is one of `provider_candidate` | `backend_ranked_candidate` | `repair_candidate` | `backend_witness_rescue` | `genuine_no_move_exchange` | `genuine_no_move_pass`.
- Seeded SEARCH_PROFILE prompts: migration `0011_playable_seeded_prompts` hash-gates the four seed rows (Initial, Fast Search, Short Hooks, Grandmaster) into advisory SEARCH_PROFILE blocks around the TypeScript CORE. Admin-customized rows are never overwritten.
- Transient turn telemetry: overlay attempt-progress may show `completion_source`, `probe_status`, `repair_attempted`, and `terminal_cause` as human states such as "backend found a legal rescue; repairing", "genuine dead rack — exchanging", or "providers exhausted". These fields are not persisted to localStorage.

## Word validation (important)

- The **source of truth** for whether a word is valid is the **backend** — `submit_move` and `validate_move_for_ai` must always go through `_word_passes_dictionary()` + Collins 2019.
- AI **candidates** in the overlay may show invalid attempts (`valid: false`); the final move is always **re-validated** on the server.
- If someone reports that the “backend accepted” an invalid word: check whether it was an **overlay candidate** vs. a **persisted move**; add a regression test under `backend/tests/`.
- The dictionary is not copied from `scrabgpt_sk` — maintain it only in `libretiles/backend/assets/dicts/`.
- The AI judge (`/api/ai/judge`) is Collins-2019-conservative Tier 3 assistance only. It never overrides a persisted Django verdict. Exhaustion is HTTP 503; the route must not synthesize false `invalid` results from malformed output.

## Making the AI stronger

- **Catalog**: `GET /api/catalog/models/` returns `get_selectable_models()` in canonical order and marks only row 1 `is_flagship` / `recommended`. Native IDs only (never `openrouter/google/...`). The NIM id has no `:free` suffix and is not the FrameNest Omni/VLM.
  - `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false` (default, flag-off legacy path): the five curated bootstrap pairs from `backend/catalog/selection.py` `FREE_RIVAL_PAIRS` — OpenRouter `google/gemma-4-31b-it:free`, NVIDIA NIM `nvidia/nemotron-3-super-120b-a12b`, OpenRouter `nvidia/nemotron-3-super-120b-a12b:free`, `z-ai/glm-5.2:free`, `google/gemma-4-26b-a4b-it:free`.
  - Flag on: the four newest eligible OpenRouter `:free` models (zero prompt and completion pricing, tools, text output, OpenRouter-managed and currently available) plus the fixed seeded NIM tuple last. Missing `released_at` ranks after dated rows; bootstrap `sort_order` then `model_id` break ties.
  - Django Admin `is_active` is the durable kill switch. Neither `seed_models` nor `sync_openrouter_models` may reactivate or deactivate an existing row. Do not buy a paid catalog tier for this cut.
- **Preference**: a valid explicit preference is attempt 1; remaining attempts follow untouched catalog order. New users and empty Zustand `selectedModelId` receive catalog row 1. Returning valid preferences stay; stale ids are repaired against the live catalog. There is no `NEXT_PUBLIC_DEFAULT_MODEL`.
- **Fallback**: Play and Judge call the same `buildFallbackQueue` in `frontend/src/lib/ai-fallback.ts`, capped at three distinct pairs. Preference `model_id` is unchanged; `runtime_model_id` is the Play attempt. Play retries only retryable provider failures after unchanged-turn reconciliation. Per-attempt SSE metadata includes `provider_requests_used`; the orchestrator sums `turn_provider_requests_used` across attempts including the finally-successful one. `max_steps` is the remaining whole-turn provider-call budget shared across attempts (not a fresh budget per stream).
- **Judge**: up to three sequential attempts, AI SDK `maxRetries: 0`, 10 seconds per attempt, 30 seconds overall. HTTP 503 on exhaustion. Never invent false invalid verdicts.
- **Presentation**: `AIThinkingOverlay` shows ordered provider/model pills bound to attempt lifecycle (`data-attempt-status`). Exactly one gold/black ping-pong tile mounts on the active attempt (`pingPongTileMotion` delay is always `0`). Reduced motion yields a static tile. With Premium Look off, pills stay readable via flat amber chrome. Transient telemetry copy renders inside that same progress surface and is cleared with the turn.
- **Time / search**: `aiTimeout` and `aiMaxSteps` in the Zustand store / Settings, consumed by the SSE move route. A no-provider-progress deadline (default 20 seconds, overridable as `no_provider_progress_deadline` on the move request, never exceeding the attempt timeout or `REPAIR_MIN_REMAINING_SECONDS` headroom) aborts a silent model and commits an already-valid ranked candidate. If the model has produced a backend-valid candidate, or no ranked candidate is available, the deadline does not fire and the existing auto-finalize / hard-timeout / playability path is unchanged.
- **Prompt**: `frontend/src/lib/prompts.ts` — non-overridable TypeScript CORE plus an advisory SEARCH_PROFILE from the selected DB preset. Legality-first anchor search, early backend-validated scoring floor, budget-bounded diversity, Collins-2019-only judge authority, no natural-usage override. Free-form JSON does not choose pass/exchange/place. Change carefully and test against backend validation plus `frontend/src/lib/ai-turn-simulation.test.ts`.
- **Seeded-prompt migration**: `0010_refresh_seeded_prompts` then `0011_playable_seeded_prompts` are reversible and SHA-256 hash-gated. They refresh only unmodified seed rows (Initial, Fast Search, Short Hooks, Grandmaster). Admin-customized rows are never overwritten.
- Hardcoded bases: OpenRouter `https://openrouter.ai/api/v1`; NVIDIA NIM `https://integrate.api.nvidia.com/v1`. No base-URL env vars.

## Operations and rollout

Documented production schedule (configure only under separate production authority — this repository does not install it):

- Name: `libretiles-openrouter-catalog-refresh`
- Cadence: daily at 03:17 UTC
- Command: `python manage.py sync_openrouter_models` under a non-overlapping platform lock
- One scheduled run performs exactly **one** unauthenticated OpenRouter catalog GET (`https://openrouter.ai/api/v1/models`) with a 20-second timeout, no retries, no per-model probes, and no NVIDIA/NIM request
- Empty or >50% cohort drops abort with zero writes unless an operator passes CLI-only `--allow-large-drop` (empty still aborts)

Rollout order:

1. Deploy backend with `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false`
2. Deploy the dynamic-capable frontend
3. Run migrate / sync evidence
4. Enable the flag and restart Django
5. Configure `libretiles-openrouter-catalog-refresh` only under separate production authority

Rollback:

1. Set `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false` and restart Django (immediate product rollback; stored dynamic rows become unselectable; stale frontend preferences repair to a bootstrap row)
2. Pause `libretiles-openrouter-catalog-refresh` and/or deactivate rows in Django Admin (operational kill switches; catalog rows are not deleted)
3. Roll backend selection back to curated-only **before** rolling back the dynamic-capable frontend

## Deployment

- Frontend: Vercel (env from `frontend/.env.local.example`).
- Backend: VPS / PaaS with PostgreSQL in production; see [docs/architecture.md](docs/architecture.md) and [README.md](README.md).

## Security

- Never commit `.env`, `backend/.env`, or `frontend/.env.local`.
- Template files `.env.example` / `.env.local.example` are fine to commit.
- A pre-existing `.env` overrides new code defaults, is read once at process start, and must be reviewed after any settings change. New variables such as `DJANGO_THROTTLE_CACHE_URL` inherit that hazard.

## Not done yet (typical next steps)

- LM Studio, Vercel AI Gateway, and push/deploy are out of this cut (historical rejection / removal, not unfinished AI routing). Stripe is rejected, not unfinished work.
- Slovak assets now ship; Settings/engine/prompt wiring is later slices of `slovak-playable-variant`; live Slovak play is not enabled until those slices land.
- Configuring `libretiles-openrouter-catalog-refresh` on a host is separate production authority, not this cut.
- Tier 2 dictionary (optional API) — see PRD and `docs/architecture.md`.
- Stronger AI search / candidate generation beyond prompt-only improvements.


<!-- BEGIN MANAGED AP INTEGRATION -->
## Analytic Programming

This project uses Analytic Programming through the pinned Git submodule at `.ap/`.
The exact AP version is the commit recorded by this repository's `.ap` gitlink.

Required reading:
- All participants read `.ap/AP.md`.
- Orchestrators also read `.ap/AP_ORCHESTRATOR.md`.
- Workers also read `.ap/AP_WORKER.md`.
- Prompt structures are in `.ap/PROMPT_CONTRACTS.md`.

Project-specific rules outside this managed block remain authoritative within
their scope. Task authority comes only from the current authoritative
Orchestrator prompt.

Treat `.ap/` as read-only during ordinary project work. Protocol updates require
a separate explicit AP update task.
<!-- END MANAGED AP INTEGRATION -->
