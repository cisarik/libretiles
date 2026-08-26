# Libre Tiles -- Architecture

This document describes the technical architecture of the Libre Tiles project. It covers the system design, data flow, AI agent workflow, and deployment topology.

**Repository boundary**: The `libretiles/` tree is self-contained and can be published as a standalone Git repository. It does not import code from other monorepos; the game engine and dictionary assets live under `backend/`.

## System Overview

Libre Tiles is a web application with three runtime components:

1. **Next.js Frontend** (deployed on Vercel) -- UI, AI agent orchestration, model routing
2. **Django Backend** (self-hosted VPS) -- game state, matchmaking, validation, auth, admin, dictionary
3. **Redis** -- Django Channels backing store for websocket rooms and realtime fan-out (human multiplayer only; not required for AI-only local play)

AI turns use **provider-diverse free rivals** selected by `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` (default false). Flag-off returns the five curated bootstrap pairs; flag-on returns the four newest eligible OpenRouter models plus the seeded NIM tuple. Next.js `/api/ai/move` and `/api/ai/judge` dispatch on the Next.js server: OpenRouter at hardcoded `https://openrouter.ai/api/v1` with server-only `OPENROUTER_API_KEY`, and NVIDIA NIM at hardcoded `https://integrate.api.nvidia.com/v1` with server-only `NVIDIA_API_KEY`. No base-URL env vars. Never prefix `openrouter/`. The NIM id has no `:free` suffix and is not the FrameNest Omni/VLM. The UI still boots if either key is missing. There is no `NEXT_PUBLIC_DEFAULT_MODEL`; empty selections resolve to catalog row 1. The Vercel AI SDK is an OpenAI-compatible adapter only; LM Studio and Vercel AI Gateway remain historical rejections, not live routing.

```
┌─────────────────────────────────────────────────────────┐
│                    User's Browser                       │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │         Next.js React Application               │    │
│  │                                                 │    │
│  │  Board (15x15)  TileRack  ScorePanel  Settings  │    │
│  │  @dnd-kit drag  Framer Motion animations        │    │
│  │  Zustand state (token + model persisted)        │    │
│  └────────────┬────────────────────────────────────┘    │
└───────────────│─────────────────────────────────────────┘
                │
                │ REST API (JWT Bearer) + websocket ticket bootstrap
                ▼
┌───────────────────────────────────────┐
│       Next.js Server (Vercel)         │
│                                       │
│  /api/ai/move    -- AI agent route    │   ──────►  OpenRouter
│  /api/ai/judge   -- Word judge route  │            + NVIDIA NIM
│                                       │            (free rivals)
│  /api/models     -- Catalog proxy     │
│                                       │
│  Uses: Vercel AI SDK v6              │
│        generateText() + tool calling  │
└──────────────┬────────────────────────┘
               │
               │ HTTP callbacks (validate-move, validate-words, ai-move)
               ▼
┌──────────────────────────────────────────────┐
│            Django Backend (VPS)              │
│                                              │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │
│  │accounts │ │ catalog  │ │     game     │  │
│  │(JWT)    │ │(models)  │ │state, queue, │  │
│  │         │ │          │ │moves, chat   │  │
│  └─────────┘ └──────────┘ └──────┬───────┘  │
│                                  │           │
│  ┌─────────────────────────────────────────┐ │
│  │           gamecore/ (pure Python)       │ │
│  │  board, rules, scoring, tiles, game     │ │
│  │  variant_store, fastdict (Collins 2019) │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ┌────────────────────────┐                  │
│  │  Django Admin (/admin) │                  │
│  │  - AI model catalog    │                  │
│  │  - Game sessions       │                  │
│  │  - Users               │                  │
│  └────────────────────────┘                  │
│                                              │
│  Database: PostgreSQL (prod) / SQLite (dev)  │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
             ┌────────────────────┐
             │ Redis / Channels   │
             │ game_<public_id>   │
             │ websocket fan-out  │
             └────────────────────┘
```

## AI Agent Workflow

The AI opponent plays using the same tool-calling agent pattern as the desktop `scrabgpt` application. This is the core differentiator -- the AI doesn't just generate text, it uses tools to validate its own moves before committing.

### Sequence Diagram

```
Browser           Next.js /api/ai/move           AI Model              Django Backend
   │                      │                        │                        │
   │ POST (game_id,       │                        │                        │
   │  token, model_id)    │                        │                        │
   │─────────────────────►│                        │                        │
   │                      │                        │                        │
   │                      │ GET /ai-context/       │                        │
   │                      │───────────────────────────────────────────────►│
   │                      │◄──────────────────────────────────────────────│
   │                      │ (board, rack, scores)  │                        │
   │                      │                        │                        │
   │                      │ generateText(prompt,   │                        │
   │                      │  tools, stopWhen)      │                        │
   │                      │───────────────────────►│                        │
   │                      │                        │                        │
   │                      │                        │ tool: validateMove     │
   │                      │                        │  (placements)          │
   │                      │◄───────────────────────│                        │
   │                      │                        │                        │
   │                      │ POST /validate-move/   │                        │
   │                      │───────────────────────────────────────────────►│
   │                      │◄──────────────────────────────────────────────│
   │                      │ (legal, words, score)  │                        │
   │                      │───────────────────────►│                        │
   │                      │                        │                        │
   │                      │                        │ tool: validateWords    │
   │                      │◄───────────────────────│                        │
   │                      │ POST /validate-words/  │                        │
   │                      │───────────────────────────────────────────────►│
   │                      │◄──────────────────────────────────────────────│
   │                      │───────────────────────►│                        │
   │                      │                        │                        │
   │                      │                        │ (repeat for more       │
   │                      │                        │  candidates...)        │
   │                      │                        │                        │
   │                      │◄───────────────────────│                        │
   │                      │ final move JSON        │                        │
   │                      │                        │                        │
   │                      │ POST /ai-move/         │                        │
   │                      │───────────────────────────────────────────────►│
   │                      │◄──────────────────────────────────────────────│
   │                      │                        │                        │
   │◄─────────────────────│                        │                        │
   │ (move result + meta) │                        │                        │
```

### AI Tools

| Tool | Description | Django Endpoint |
|------|-------------|-----------------|
| `validateMove` | Check placement legality, extract words, calculate score | `POST /api/game/{id}/validate-move/` |
| `finishMove` | Signal that a backend-validated placement is ready to finalize | (no Django call; aborts search) |
| `validateWords` | Check words against the Collins 2019 dictionary | `POST /api/game/{id}/validate-words/` |

### AI Prompt Structure

The system prompt (`frontend/src/lib/prompts.ts`) is a non-overridable TypeScript CORE. Database presets are composed around it as an advisory SEARCH_PROFILE block and cannot change action authority:

- **Legality-first anchor search** -- scan anchors, form candidates from held tiles, rank by EV, never brute-force nonsense strings
- **Early validated scoring floor** -- secure one backend-validated legal scoring move first, then climb
- **Budget-bounded diversity** -- explore different families only while the shared step budget remains; no arbitrary candidate quota
- **Backend validation authority** -- Collins Scrabble Words (2019) decides legality; intuition only proposes
- **Blank policy / game phase / anti-blunder / genuine no-move fallback** -- pass or exchange only after `GET /api/game/{id}/ai-playability/` returns `none`
- **Action authority** -- tools only (`validateMove`, then `finishMove`). Free-form JSON cannot choose pass, exchange, or place.

The judge system prompt treats Collins 2019 as the sole validity authority, is conservative on uncertain recall, forbids natural-usage/corpus/idiom overrides, and requires strict JSON `{results:[…]}` with exactly one result per requested word.

Database prompt presets (Initial, Fast Search, Short Hooks, Grandmaster) refresh through reversible hash-gated migrations `0010_refresh_seeded_prompts` then `0011_playable_seeded_prompts` (advisory SEARCH_PROFILE text). Admin-customized rows are never overwritten. Reverse restores prior text only for rows the forward step updated.

The user prompt provides:
- Current rack letters
- Tile point values
- Premium square legend
- Compact board state
- First-move flag

### Model Routing

```
Frontend Settings ──► create game request (`ai_model_model_id`)
                              │
                              ▼
                    Django resolves active `catalog.AIModel`
                              │
                              ▼
                    `GameSession.ai_model` becomes source of truth
                              │
                              ▼
                    `/api/game/{id}/ai-context/` returns locked model id
                              │
                              ▼
                    `/api/ai/move` dispatches the runtime pair (`model_id` preference;
                              │  optional `runtime_model_id` for the current attempt)
                              │
                     requested model + actual response model are stored in `Move.ai_metadata`
```

- **Runtime**: two server-only Next.js keys, `OPENROUTER_API_KEY` and `NVIDIA_API_KEY`. Bases are hardcoded in `frontend/src/lib/openrouter.ts` and `frontend/src/lib/nvidia-nim.ts`. Do not put those keys in backend env.
- **Catalog flag**: `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` in `backend/config/settings.py` (default false). False = `FREE_RIVAL_PAIRS` bootstrap order. True = four newest eligible OpenRouter models plus seeded NIM last. `/api/catalog/models/` serializes that list, exposes `released_at`, and marks only row 1 `is_flagship` / `recommended`.
- **Fallback**: Play and Judge call the same `buildFallbackQueue` (`frontend/src/lib/ai-fallback.ts`), capped at three distinct pairs. A valid explicit preference is attempt 1; remaining attempts follow untouched catalog order. Preference `model_id` is unchanged; Play `runtime_model_id` is the attempt. Per-attempt SSE metadata includes `provider_requests_used`; `turn_provider_requests_used` is the orchestrator sum across attempts including the successful one. `max_steps` is the remaining whole-turn provider-call budget. Collins 2019 on Django remains the persisted-move validator. `GET /api/game/{id}/ai-playability/` is the authoritative witness for whether a legal scoring placement exists before any pass/exchange.
- **Judge**: up to three sequential attempts, AI SDK `maxRetries: 0`, 10 seconds per attempt, 30 seconds overall. HTTP 503 on exhaustion. Malformed output is never synthesized into false invalid verdicts.
- **Store default**: Zustand `selectedModelId` starts empty; pages resolve via `resolveEligibleModelId` in `frontend/src/lib/model-catalog.ts` (valid server preference, then valid stored id, then catalog row 1). There is no `NEXT_PUBLIC_DEFAULT_MODEL`.
- **Catalog seed**: `python manage.py seed_models` writes the five-pair offline shortlist and is required for local boot. It must not flip Admin `is_active` on existing rows.
- **Catalog sync** (optional): `python manage.py sync_openrouter_models` performs one unauthenticated public GET (`https://openrouter.ai/api/v1/models`, 20-second timeout, no retries, no per-model probes, no NVIDIA/NIM request). Empty or >50% cohort drops abort with zero writes unless CLI `--allow-large-drop` is passed (empty still aborts). Sync must not own or disable the NIM row. There is no NIM catalog discovery. An unavailable catalog must not block boot.
- **Kill switch**: Django Admin `is_active` remains catalog authority. Deactivating a row (including NIM) removes it from Settings and fallback queues. Seed and sync never reactivate or deactivate existing rows.
- **Free-only play**: the product does not handle money, app credits, USD balances, token prices, or per-game charges. Play and Judge use the selectable free-rival catalog only. Provider quotas or trial terms are external and may change; they are not Libre Tiles credits or charges. Stripe is rejected for this product direction.

## Word Validation Pipeline

```
Word submitted
      │
      ▼
  Tier 1: Collins 2019
  (frozenset, O(1))
      │
      ├── found ──► VALID
      │
      ├── not found
      │       │
      │       ▼
      │   Tier 2: Online API (optional)
      │       │
      │       ├── found ──► VALID
      │       │
      │       ├── not found / unavailable
      │       │       │
      │       │       ▼
      │       │   Tier 3: AI Judge
      │       │   (/api/ai/judge)
      │       │       │
      │       │       ├── valid ──► VALID
      │       │       └── invalid ─► INVALID
      │       │
      └───────┘
```

Tier 1 covers the shipped Collins 2019 word list and handles nearly all cases. Tier 3 provides a fallback for edge cases using AI language understanding.

## Human Multiplayer Workflow

Human-vs-human multiplayer reuses the same `GameSession`, `PlayerSlot`, `Move`, and `gamecore/` rules as AI games. There is no second game engine and no parallel multiplayer state model.

### Queue and match activation

1. The first authenticated player calls `POST /api/game/queue/join/`.
2. Django either reuses that player's existing waiting session or creates a new `GameSession(status="waiting", game_mode="vs_human")`.
3. The second authenticated player joins the oldest compatible waiting session inside a transaction with row locking.
4. Only after the second player is assigned do backend services initialize the bag, racks, starting draw, and first turn; the session becomes `active` and `started_at` is set.

### Realtime sync

- Each game uses one websocket room: `game_<public_id>`.
- The frontend first requests `POST /api/game/{id}/ws-ticket/`; the backend signs a short-lived ticket tied to the authenticated user and game.
- Websocket consumers authenticate the ticket, verify game membership, join the room, and then only relay events.
- After a move, pass, exchange, resignation, match creation, or chat message, the service layer publishes a room event and each connected consumer re-fetches `get_game_state_for_user(...)` for its own user before sending `game_state`.
- This keeps private racks user-specific while shared board state, scores, moves, and chat remain visible to both players.

## Data Model

### Core entities

- **User** (accounts) -- custom user with preferred AI model
- **AIModel** (catalog) -- provider, model_id, display_name, OpenRouter sync metadata, availability, `released_at`; selectable set is bootstrap pairs or newest-four-plus-NIM depending on `DYNAMIC_FREE_MODEL_CATALOG_ENABLED`
- **GameSession** (game) -- board state JSON, bag, turn tracking, game status
- **PlayerSlot** (game) -- links users (or AI) to game positions with rack + score
- **Move** (game) -- move history with placements, words, score, AI metadata
- **ChatMessage** (game) -- compact persisted in-game chat entries for human sessions

### State persistence

Game state is stored in `GameSession.state_json` as a JSON blob managed by `gamecore/state.py`. The schema tracks:
- Board grid (15x15 array of strings)
- Blank positions
- Premium-used flags
- Player racks (keyed by slot index)
- Tile bag contents
- Scores and move count

## Deployment

### Production

- **Frontend**: Vercel (automatic deploys from `main` branch)
- **Backend**: Self-hosted VPS with Docker Compose (Django + PostgreSQL + Redis)
- **AI**: provider-diverse free rivals (`OPENROUTER_API_KEY` and `NVIDIA_API_KEY` on the Next.js server)

### Local development

- Backend: `poetry run python manage.py runserver` (SQLite); `seed_models` for the offline shortlist; leave `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` false unless enabling newest-first locally
- Frontend: `npm run dev` (server-only `OPENROUTER_API_KEY` and `NVIDIA_API_KEY`; UI boots if either is missing)
- Redis: required for human multiplayer, websocket sync, and chat; not required for AI-only play
- Database: SQLite (zero config) or Docker Compose PostgreSQL

## Catalog operations, rollout, and rollback

Documented production schedule (not installed by this repository; configure only under separate production authority):

- Name: `libretiles-openrouter-catalog-refresh`
- Cadence: daily at 03:17 UTC
- Command: `python manage.py sync_openrouter_models` under a non-overlapping platform lock
- One scheduled run: exactly one unauthenticated OpenRouter catalog GET, 20-second timeout, no retries, no per-model probes, no NVIDIA/NIM request

Rollout order:

1. Deploy backend with `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false`
2. Deploy the dynamic-capable frontend
3. Run migrate / sync evidence
4. Enable the flag and restart Django
5. Configure `libretiles-openrouter-catalog-refresh` only under separate production authority

Rollback:

1. Set `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false` and restart Django. Dynamic rows remain stored but become unselectable; stale frontend preferences repair to a bootstrap row.
2. Pause `libretiles-openrouter-catalog-refresh` and/or deactivate a problematic row in Django Admin. No catalog row is deleted.
3. Roll backend selection to curated-only **before** rolling back the dynamic-capable frontend.

## Security Considerations

- JWT tokens for API auth (short-lived access + refresh tokens)
- AI API keys stored server-side only (Next.js server environment)
- Acting player slot is always derived from the authenticated user on the server; public APIs do not trust client-supplied slot indices
- Game-state responses only include the requesting user's private rack; opponent racks are never exposed through query params or websocket payloads
- Websocket access uses short-lived signed tickets plus membership checks before room join
- CORS configured per environment
- Django Admin behind superuser auth
- No secrets in .env.example or .env.local.example files
- `.gitignore` excludes all env files, databases, and build artifacts

## Handoff Notes (August 2026)

These notes are for the next coding agent continuing AI gameplay work.

### Current AI routing state

- User model selection is persisted locally in Zustand (`selectedModelId`, empty until pages resolve catalog row 1) and synchronized into the active game session via `PATCH /api/game/{id}/ai-model/` before the AI move route generates a turn.
- `maxOutputTokens` is no longer hardcoded in the Next.js route:
  - Django exposes `AI_MOVE_MAX_OUTPUT_TOKENS` and `AI_MOVE_TIMEOUT_SECONDS` via `/api/game/{id}/ai-context/`
  - the AI route clamps and uses the backend-provided output-token budget as the source of truth
  - longer searches also get a less aggressive auto-finalize window to avoid cutting candidate exploration too early
- Play fallback shares one whole-turn provider-call budget; terminal SSE events include `provider_requests_used` per attempt and `turn_provider_requests_used` as the whole-turn sum.
- Move-route terminals also carry `completion_source`, `probe_status`, `repair_attempted`, and `terminal_cause`. The thinking overlay renders those as transient human states inside the attempt-progress surface; they are not written to Zustand persist / localStorage.
- The game header now exposes a lightweight audit trail:
  - requested model (frontend selection)
  - session model (backend game source of truth)
  - response model (actual model reported by the AI provider)
- Relevant files:
  - `frontend/src/app/game/[id]/page.tsx`
  - `frontend/src/app/api/ai/move/route.ts`
  - `frontend/src/lib/ai-fallback.ts`
  - `frontend/src/lib/ai-turn-simulation.test.ts`
  - `backend/game/services.py`
  - `backend/gamecore/legality.py`
  - `backend/gamecore/move_search.py`

### Current model catalog policy

- Selectable models depend on `DYNAMIC_FREE_MODEL_CATALOG_ENABLED`:
  - **Flag off (default, legacy path):** five curated bootstrap `(provider, model_id)` pairs in `FREE_RIVAL_PAIRS` order:
    - `openrouter` — `google/gemma-4-31b-it:free`
    - `nvidia-nim` — `nvidia/nemotron-3-super-120b-a12b`
    - `openrouter` — `nvidia/nemotron-3-super-120b-a12b:free`
    - `openrouter` — `z-ai/glm-5.2:free`
    - `openrouter` — `google/gemma-4-26b-a4b-it:free`
  - **Flag on:** four newest eligible OpenRouter `:free` models (zero prompt/completion pricing, tools, text output, OpenRouter-managed, currently available; `openrouter/free` excluded) plus the seeded NIM tuple last. Missing `released_at` ranks after dated rows; bootstrap `sort_order` then `model_id` break ties.
  - exact `(provider, model_id)` membership after selection, `is_active`, `model_type="language"`, tools, and OpenRouter availability (NIM does not require `openrouter_available`)
- `seed_models` is the boot path. `sync_openrouter_models` is optional, non-blocking, and must not own or disable the NIM row.
- Frontend has no static ID allowlist; `frontend/src/lib/model-catalog.ts` revalidates catalog pairs and fails closed.
- Relevant files:
  - `frontend/src/lib/model-catalog.ts`
  - `backend/catalog/selection.py`
  - `backend/catalog/views.py`
  - `backend/catalog/openrouter_sync.py`
  - `backend/tests/test_dynamic_free_catalog.py`

### Current AI UX guardrails

- The thinking overlay renders ordered fallback-rival pills from store attempt state (`data-attempt-status`, `title=modelId`). Exactly one gold/black ping-pong tile mounts while `isAttemptPingPongActive` is true; it disappears when the index clears or the attempt is marked failed. `pingPongTileMotion` uses `delay: 0` and returns `null` under reduced motion (static tile). Premium Look off uses flat amber; pills remain readable. Transient telemetry copy sits in the same progress surface.
- The move prompt is a TypeScript CORE plus advisory SEARCH_PROFILE:
  - anchor-based search workflow
  - early backend-validated scoring floor
  - diverse alternatives only while the shared step budget remains
  - explicit ban on random string generation / arbitrary candidate quotas
  - absolute Collins 2019 backend authority
  - tools-only action authority (no free-form JSON pass/exchange/place)
- The judge prompt is Collins-2019-only with no natural-usage override and strict one-result-per-word JSON.
- Relevant files:
  - `frontend/src/components/game/AIThinkingOverlay.tsx`
  - `frontend/src/lib/premiumSurface.ts`
  - `frontend/src/lib/prompts.ts`
  - `backend/catalog/migrations/0010_refresh_seeded_prompts.py`
  - `backend/catalog/migrations/0011_playable_seeded_prompts.py`

### Current admin operations surface

- Django admin has an operations dashboard with:
  - global game counts
  - aggregate token usage (non-monetary diagnostics)
  - recent games
  - recent AI turns
  - top models by token usage
- AI models admin includes a dedicated sync page with a button that calls the optional `sync_openrouter_models` management command.
- There is no credit-balance editor, spend total, Stripe/top-up control, or installed billing app. Historical `backend/billing/migrations/` files are an inert tombstone only.
- Relevant files:
  - `backend/game/admin.py`
  - `backend/catalog/admin.py`
  - `backend/accounts/admin.py`

### Current game UI / account surface

- The game header now contains a compact account/actions cluster:
  - `Give up` on the left
  - `Profile`, `Logout`, `Settings`, and `New game` on the right
  - password changes happen in a modal and call `POST /api/auth/change-password/`
- A reusable premium pointer-reactive chrome effect was extracted from settings into shared frontend utilities and is now used by:
  - settings surfaces
  - the game header
  - the rack/footer panel
- The premium look is intentionally optional and persisted in Zustand through `premiumLookEnabled`, so future agents should extend the shared helper instead of cloning effect CSS into new components.
- Relevant files:
  - `frontend/src/lib/premiumSurface.ts`
  - `frontend/src/components/game/ScorePanel.tsx`
  - `frontend/src/components/game/GameControls.tsx`
  - `frontend/src/components/game/ProfileModal.tsx`
  - `frontend/src/app/settings/page.tsx`
  - `frontend/src/hooks/useGameStore.ts`

### Recommended next priorities

1. Replace prompt-only strengthening with stronger search:
   - add anchor enumeration and lane generation before model tool calls
   - rank candidates by board anchor quality, rack leave, and premium access
2. Persist AI move diagnostics:
   - structured reject reasons
   - per-turn candidate summaries
   - explicit fallback/pass reasons in the move history
3. Tighten the first-move and opening game UX:
   - cleaner start-of-game rack transition
   - optional move history strip with model + token usage
