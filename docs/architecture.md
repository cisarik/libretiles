# Libre Tiles -- Architecture

This document describes the technical architecture of the Libre Tiles project. It covers the system design, data flow, AI agent workflow, and deployment topology.

**Repository boundary**: The `libretiles/` tree is self-contained and can be published as a standalone Git repository. It does not import code from other monorepos; the game engine and dictionary assets live under `backend/`.

## System Overview

Libre Tiles is a web application with three runtime components:

1. **Next.js Frontend** (deployed on Vercel) -- UI, AI agent orchestration, model routing
2. **Django Backend** (self-hosted VPS) -- game state, matchmaking, validation, auth, admin, dictionary
3. **Redis** -- Django Channels backing store for websocket rooms and realtime fan-out (human multiplayer only; not required for AI-only local play)

AI turns use five curated **provider-diverse free rivals**. Next.js `/api/ai/move` and `/api/ai/judge` dispatch on the Next.js server: OpenRouter at hardcoded `https://openrouter.ai/api/v1` with server-only `OPENROUTER_API_KEY`, and NVIDIA NIM at hardcoded `https://integrate.api.nvidia.com/v1` with server-only `NVIDIA_API_KEY`. No base-URL env vars. Default remains OpenRouter `google/gemma-4-31b-it:free`. Never prefix `openrouter/`. The NIM id has no `:free` suffix and is not the FrameNest Omni/VLM. The UI still boots if either key is missing. The Vercel AI SDK is an OpenAI-compatible adapter only; LM Studio and Vercel AI Gateway remain out of this cut.

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
│  │  - AI models + pricing │                  │
│  │  - Game sessions       │                  │
│  │  - Users + billing     │                  │
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
| `validateWords` | Check words against the Collins 2019 dictionary | `POST /api/game/{id}/validate-words/` |

### AI Prompt Structure

The system prompt (`frontend/src/lib/prompts.ts`) includes:

- **Legality rules** -- what constitutes a valid Libre Tiles move
- **Strategic priorities** -- EV maximization, rack leave, board control
- **Game phase guidance** -- opening, midgame, endgame strategies
- **Blank policy** -- when to spend blanks
- **Anti-blunder rules** -- avoid obviously suboptimal moves
- **Mandatory tool workflow** -- use tools before finalizing
- **Output format** -- strict JSON schema for the response

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
- **Fallback**: one AI turn may try at most three sequential `/api/ai/move` streams. Preference `model_id` is unchanged; `runtime_model_id` is the attempt. Collins 2019 on Django remains the move validator.
- **Store default**: Zustand uses `DEFAULT_FREE_MODEL_ID` from `frontend/src/lib/free-rivals.ts`. Optional `NEXT_PUBLIC_DEFAULT_MODEL` is only a documented fallback for move/judge routes.
- **Catalog seed**: `python manage.py seed_models` writes the five-pair offline shortlist and is required for local boot.
- **Catalog sync** (optional, later): `python manage.py sync_openrouter_models` is an unauthenticated public GET. It must not own or disable the NIM row. There is no NIM catalog discovery. An unavailable catalog must not block boot.
- **Kill switch**: Django Admin remains catalog authority; deactivating the NIM row removes it from Settings and fallback queues.
- **Credits**: these rivals charge zero app credits (`free_rival` / dormant). External NVIDIA trial/quota terms can change and are not app credits.

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
- **AIModel** (catalog) -- provider, model_id, display_name, OpenRouter sync metadata, availability; this cut exposes five curated free-rival pairs
- **GameSession** (game) -- board state JSON, bag, turn tracking, game status
- **PlayerSlot** (game) -- links users (or AI) to game positions with rack + score
- **Move** (game) -- move history with placements, words, score, AI metadata
- **ChatMessage** (game) -- compact persisted in-game chat entries for human sessions
- **CreditBalance / Transaction** (billing) -- dormant per-user credits; this cut charges zero app credits for AI turns

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

- Backend: `poetry run python manage.py runserver` (SQLite); `seed_models` for the offline shortlist
- Frontend: `npm run dev` (server-only `OPENROUTER_API_KEY` and `NVIDIA_API_KEY`; UI boots if either is missing)
- Redis: required for human multiplayer, websocket sync, and chat; not required for AI-only play
- Database: SQLite (zero config) or Docker Compose PostgreSQL

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

## Handoff Notes (March 2026)

These notes are for the next Codex agent continuing AI gameplay and billing work.

### Current AI routing state

- User model selection is persisted locally in Zustand and synchronized into the active game session via `PATCH /api/game/{id}/ai-model/` before the AI move route generates a turn.
- `maxOutputTokens` is no longer hardcoded in the Next.js route:
  - Django exposes `AI_MOVE_MAX_OUTPUT_TOKENS` and `AI_MOVE_TIMEOUT_SECONDS` via `/api/game/{id}/ai-context/`
  - the AI route clamps and uses the backend-provided output-token budget as the source of truth
  - longer searches also get a less aggressive auto-finalize window to avoid cutting candidate exploration too early
- The game header now exposes a lightweight audit trail:
  - requested model (frontend selection)
  - session model (backend game source of truth)
  - response model (actual model reported by the AI provider)
- Relevant files:
  - `frontend/src/app/game/[id]/page.tsx`
  - `frontend/src/app/api/ai/move/route.ts`
  - `backend/game/services.py`

### Current model catalog policy

- Selectable models are the five curated `(provider, model_id)` pairs:
  - `openrouter` — `google/gemma-4-31b-it:free` (default)
  - `nvidia-nim` — `nvidia/nemotron-3-super-120b-a12b`
  - `openrouter` — `nvidia/nemotron-3-super-120b-a12b:free`
  - `openrouter` — `z-ai/glm-5.2:free`
  - `openrouter` — `google/gemma-4-26b-a4b-it:free`
  - shortlist membership, active/available, explicit free pricing, and tools
- `seed_models` is the boot path. `sync_openrouter_models` is optional, non-blocking, and must not own or disable the NIM row.
- Relevant files:
  - `frontend/src/lib/free-rivals.ts`
  - `backend/catalog/selection.py`
  - `backend/catalog/views.py`
  - `backend/tests/test_api.py`

### Current AI UX guardrails

- The live AI overlay now hides invalid nonsense word attempts and surfaces only valid candidates plus reject counts.
- The move prompt was hardened to reduce brute-force dictionary guessing:
  - stronger lexical plausibility filter
  - anchor-based search workflow
  - explicit ban on using tools for random string generation
  - emphasis on short credible hooks before speculative long strings
- Relevant files:
  - `frontend/src/components/game/AIThinkingOverlay.tsx`
  - `frontend/src/lib/prompts.ts`

### Current billing / insufficient funds behavior

- This cut charges **zero app credits** for AI turns. Frontend empty-credit gates are gone.
- Credits UX remains in the product as a dormant USD balance. Stripe top-up is unfinished; do not document a top-up flow.
- Relevant files:
  - `frontend/src/app/api/ai/move/route.ts`
  - `frontend/src/app/game/[id]/page.tsx`
  - `backend/accounts/views.py`

### Current admin operations surface

- Django admin now has a real operations dashboard with:
  - global game counts
  - aggregate token usage
  - AI spend totals
  - recent games
  - recent AI turns
  - top models by spend
- AI models admin now includes a dedicated sync page with a button that calls the optional `sync_openrouter_models` management command.
- User credit can now be edited directly in admin from the user detail page or from the credit balance list.
- Relevant files:
  - `backend/game/admin.py`
  - `backend/catalog/admin.py`
  - `backend/accounts/admin.py`
  - `backend/billing/admin.py`

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
2. Finish the real top-up flow:
   - Stripe / checkout
   - server-side hard credit floor enforcement before charging
   - better transaction history UI
3. Persist AI move diagnostics:
   - structured reject reasons
   - per-turn candidate summaries
   - explicit fallback/pass reasons in the move history
4. Tighten the first-move and opening game UX:
   - cleaner start-of-game rack transition
   - optional move history strip with model + token spend
