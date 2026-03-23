# Libre Tiles -- Architecture

This document describes the technical architecture of the Libre Tiles project. It covers the system design, data flow, AI agent workflow, and deployment topology.

**Repository boundary**: The `libretiles/` tree is self-contained and can be published as a standalone Git repository. It does not import code from other monorepos; the game engine and dictionary assets live under `backend/`.

## System Overview

Libre Tiles is a web application with three runtime components:

1. **Next.js Frontend** (deployed on Vercel) -- UI, AI agent orchestration, model routing
2. **Django Backend** (self-hosted VPS) -- game state, matchmaking, validation, auth, admin, dictionary
3. **Redis** -- Django Channels backing store for websocket rooms and realtime fan-out

The AI models are accessed through the **Vercel AI Gateway**, which provides a unified OpenAI-compatible API for multiple providers (OpenAI, Google, Anthropic, etc.).

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
│  /api/ai/move    -- AI agent route    │   ──────►  Vercel AI Gateway
│  /api/ai/judge   -- Word judge route  │            (or direct OpenAI)
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

- **Legality rules** -- what constitutes a valid Scrabble move
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
                    `/api/ai/move` calls `getModel(session.ai_model_id)`
                              │
                     requested model + actual response model are stored in `Move.ai_metadata`
```

- **Production** (Vercel): `AI_GATEWAY_API_KEY` + `AI_GATEWAY_BASE_URL` are set. Model IDs use `provider/model` format. All requests go through the Vercel AI Gateway.
- **Local dev**: Falls back to direct provider SDK. The `provider/` prefix is stripped from model IDs.
- **Catalog sync**: `python manage.py sync_gateway_models` fetches the latest public Vercel AI Gateway catalog from `https://ai-gateway.vercel.sh/v1/models`, updates technical metadata on `catalog.AIModel`, and marks missing models unavailable.

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
- **AIModel** (catalog) -- provider, model_id, display_name, cost, quality_tier, gateway metadata, availability sync
- **GameSession** (game) -- board state JSON, bag, turn tracking, game status
- **PlayerSlot** (game) -- links users (or AI) to game positions with rack + score
- **Move** (game) -- move history with placements, words, score, AI metadata
- **ChatMessage** (game) -- compact persisted in-game chat entries for human sessions
- **CreditBalance / Transaction** (billing) -- per-user credits for AI games

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
- **AI**: Vercel AI Gateway (single API key for all providers)

### Local development

- Backend: `poetry run python manage.py runserver` (SQLite)
- Frontend: `npm run dev` (with direct OPENAI_API_KEY)
- Redis: required for human multiplayer, websocket sync, and chat
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

- Selectable models are now intentionally conservative:
  - only `is_active=True` language models are selectable by default
  - synced gateway models are preferred over unsynced entries
  - tool-capable models are preferred over non-tool models
  - `openai/gpt-5.4` remains explicitly pinnable even if it falls outside the active top-10
- Relevant files:
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

- Before AI generation, the Next.js AI route now checks the authenticated user's backend credit balance.
- If user credit is empty, the route emits a structured SSE error and the game shows a friendly blocker modal instead of raw console noise.
- Provider-side "insufficient funds" errors from the upstream AI service are also normalized into a user-friendly modal.
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
- AI models admin now includes a dedicated sync page with a button that calls the `sync_gateway_models` management command.
- User credit can now be edited directly in admin from the user detail page or from the credit balance list.
- Relevant files:
  - `backend/game/admin.py`
  - `backend/catalog/admin.py`
  - `backend/accounts/admin.py`
  - `backend/billing/admin.py`

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
