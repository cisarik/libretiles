# Libre Tiles -- Architecture

This document describes the technical architecture of the Libre Tiles project. It covers the system design, data flow, AI agent workflow, and deployment topology.

**Repository boundary**: The `libretiles/` tree is self-contained and can be published as a standalone Git repository. It does not import code from other monorepos; the game engine and dictionary assets live under `backend/`.

## System Overview

Libre Tiles is a web application with three runtime components:

1. **Next.js Frontend** (deployed on Vercel) -- UI, AI agent orchestration, model routing
2. **Django Backend** (self-hosted VPS) -- game state, matchmaking, validation, auth, admin, dictionary
3. **Redis** -- Django Channels backing store for websocket rooms and realtime fan-out (human multiplayer only; not required for AI-only local play)

AI turns use **provider-diverse free rivals** in canonical direct priority: Groq → Google Gemini → Cloudflare Workers AI → Mistral → IBM watsonx.ai. Aion and Hugging Face are prepared inactive watchlist runtimes. NVIDIA NIM and OpenRouter form the compatibility tail; `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` changes only whether that tail is the curated bootstrap cohort or newest-four OpenRouter cohort plus NIM. Every provider base and exact direct model id is hardcoded server-side. Credentials are server-only and no base-URL or secret is exposed through `NEXT_PUBLIC_` variables. The UI still boots when a credential is missing, and there is no `NEXT_PUBLIC_DEFAULT_MODEL`; empty selections resolve to the first active catalog row.

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
│  /api/ai/move    -- AI agent route    │   ──────►  Groq / Gemini /
│  /api/ai/judge   -- Word judge route  │            Cloudflare / Mistral /
│                                       │            IBM + NIM/OpenRouter tail
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
   │                      │                        │ tool: finishMove       │
   │                      │◄───────────────────────│                        │
   │                      │ (after valid result)   │                        │
   │                      │                        │                        │
   │                      │                        │ (or validate another   │
   │                      │                        │  candidate...)         │
   │                      │                        │                        │
   │                      │◄───────────────────────│                        │
   │                      │ tool-confirmed finish  │                        │
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

- **Runtime registry**: browser-safe metadata contains provider/model pairs and labels only. Server runtime construction validates the pair again, reads credentials, and uses hardcoded endpoints. Groq `openai/gpt-oss-120b` (`GROQ_API_KEY`), Google `gemini-3.7-flash` (`GEMINI_API_KEY`), Cloudflare `@cf/zai-org/glm-4.7-flash` (`CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`), and Mistral `mistral-small-2603` (`MISTRAL_API_KEY`) use the OpenAI-compatible adapter. IBM `ibm/granite-4-h-small` uses `IBM_CLOUD_API_KEY`, `IBM_WATSONX_PROJECT_ID`, and an allowlisted `IBM_WATSONX_REGION` through the dedicated IAM/chat adapter. Aion/HF are inactive watchlist descriptors. NIM/OpenRouter remain compatible exact/structural runtimes.
- **IBM accounting**: IAM and inference fetches share the same bounded request tracker. IAM tokens are cache-isolated by credential, singleflight-refreshed, limited to one hour, refreshed 60 seconds early, and refreshed once after an inference 401. Raw token, header, request, and response data is not retained.
- **Catalog activation**: direct/watchlist seed and migration rows are created with `is_active=false`. Credentials do not activate a row. An operator first runs the exact capability probe and then explicitly enables a PASS row in Django Admin. Seed/migration never flips an existing Admin kill switch. Active direct rows precede the compatibility tail in their fixed canonical order.
- **Catalog flag**: `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` in `backend/config/settings.py` (default false) affects only the compatibility tail. False uses `FREE_RIVAL_PAIRS`; true uses four newest eligible OpenRouter rows plus NIM. `/api/catalog/models/` marks only the first active row `is_flagship` / `recommended`.
- **Fallback**: Play and Judge call the same `buildFallbackQueue`, capped at five distinct pairs. A valid explicit preference is attempt 1; remaining attempts preserve canonical order. New settings default to 120 seconds and 50 provider steps. Per-attempt time is segmented from the remaining deadline; at least five steps are reserved for every later lane. Failed lanes charge at least five steps, while actual HTTP requests (including IBM IAM) are summed in `turn_provider_requests_used`. Only bounded numeric usage and `retry_after_seconds` cross the telemetry boundary. Collins 2019 on Django remains the persisted-move validator, and unchanged-turn reconciliation is required before retry.
- **Judge**: up to five sequential attempts, AI SDK `maxRetries: 0`, 10 seconds per attempt, 50 seconds overall. HTTP 503 on exhaustion. Malformed output is never synthesized into false invalid verdicts.
- **Store default**: Zustand `selectedModelId` starts empty; pages resolve via `resolveEligibleModelId` in `frontend/src/lib/model-catalog.ts` (valid server preference, then valid stored id, then catalog row 1). There is no `NEXT_PUBLIC_DEFAULT_MODEL`.
- **Catalog seed**: `python manage.py seed_models` writes the active compatibility shortlist plus prepared inactive direct/watchlist rows. It must not flip Admin `is_active` on existing rows.
- **Catalog sync** (optional): `python manage.py sync_openrouter_models` performs one unauthenticated public GET (`https://openrouter.ai/api/v1/models`, 20-second timeout, no retries, no per-model probes, no NVIDIA/NIM request). Empty or >50% cohort drops abort with zero writes unless CLI `--allow-large-drop` is passed (empty still aborts). Sync must not own or disable the NIM row. There is no NIM catalog discovery. An unavailable catalog must not block boot.
- **Kill switch**: Django Admin `is_active` remains catalog authority. Deactivating a row (including NIM) removes it from Settings and fallback queues. Seed and sync never reactivate or deactivate existing rows.
- **Free-only play**: the product does not handle money, app credits, USD balances, token prices, or per-game charges. Play and Judge use the selectable free-rival catalog only. Provider quotas or trial terms are external and may change; they are not Libre Tiles credits or charges. Stripe is rejected for this product direction.

### Explicit capability probe boundary

`frontend/src/lib/provider-capability.ts` is a server-only, operator-invoked acceptance boundary. It is not imported by client, boot, catalog, game, Move, or Judge paths. Its live Vitest file is conditional on the package-script sentinel, so `npm test`, build, and normal runtime activity cannot make a provider call. The ordinary unit tests inject synthetic runtime/generation behavior only.

The state machine is intentionally production-equivalent:

1. Resolve one exact pair through the existing registry; OpenRouter requires an explicit structural `:free` id and no model is silently substituted.
2. Construct it with the async production `getLanguageRuntime` factory.
3. Generate a random nonce and call AI SDK `generateText` with `maxRetries: 0` and one overall AbortSignal timeout.
4. Step zero exposes only named `validateMove`. Its strict schema and execution both require `(7,4,R)…(7,10,S)` for `RETAINS`; the local result is only `{valid:true, nonce}`.
5. Later steps expose `validateMove` and `finishMove` with automatic choice. A PASS requires the model itself to call `finishMove({ready:true})` after the pong. Stop immediately on finish or after three model-generation steps.
6. Return only `provider`, `model`, `status`, bounded `latency_ms`, and actual bounded `outbound_count` (including IBM IAM). Never serialize raw errors, bodies, headers, credentials, usage, or reasoning.

With the selected provider credential already present in the server process/current shell, invoke exactly one pair:

```bash
cd frontend
PROVIDER_PROBE_PROVIDER=groq PROVIDER_PROBE_MODEL=openai/gpt-oss-120b npm run probe:provider
PROVIDER_PROBE_PROVIDER=google-gemini PROVIDER_PROBE_MODEL=gemini-3.7-flash npm run probe:provider
PROVIDER_PROBE_PROVIDER=cloudflare-workers-ai PROVIDER_PROBE_MODEL=@cf/zai-org/glm-4.7-flash npm run probe:provider
PROVIDER_PROBE_PROVIDER=mistral PROVIDER_PROBE_MODEL=mistral-small-2603 npm run probe:provider
PROVIDER_PROBE_PROVIDER=ibm-watsonx PROVIDER_PROBE_MODEL=ibm/granite-4-h-small npm run probe:provider
```

Expected application output shape:

```json
{"provider":"groq","model":"openai/gpt-oss-120b","status":"pass","latency_ms":1234,"outbound_count":2}
```

Statuses are exact: `pass`, `not_configured` (local/missing configuration, zero fetch), `auth_failed` (outbound 401/403), `rate_limited`, `model_unavailable`, `named_tool_unsupported`, `tool_continuation_failed`, `schema_failed`, `timeout`, and `unknown`. Any non-PASS fails the live test, preventing activation.

The command is manual because it makes real quota-consuming and potentially billable calls. At activation time, reverify provider quota and data terms against [Groq](https://console.groq.com/docs/rate-limits), [Gemini](https://ai.google.dev/gemini-api/docs/pricing), [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/platform/pricing/), [Mistral Free Mode](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key), and [IBM watsonx.ai](https://cloud.ibm.com/docs/apis/watsonx-ai). External free tiers are volatile and are neither Libre Tiles credits nor an SLA.

Rollout is one pair at a time: deploy inactive row → configure server credential → probe exact pair → activate in Django Admin only on PASS → complete one live game. Minimum live MVP evidence is one PASS provider plus one completed game. “Five functional providers” requires current PASS evidence for all five. Rollback deactivates the exact row and preserves both the row and game history.

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
- **AIModel** (catalog) -- provider, model_id, display name, activation state, OpenRouter sync metadata where applicable, and `released_at`; selectable rows are active direct pairs followed by the flag-selected compatibility tail
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

Endgame state also tracks `consecutive_scoreless_turns`. Pass and exchange increment it; a scoring placement resets it. A normal rack-empty/empty-bag finish is unchanged, and the alternate [WESPA](https://www.wespa.org/features/rulesv1.pdf) terminal occurs at exactly six consecutive scoreless turns. `pass_streak` describes real consecutive passes only and does not decide the game. Tied final scores retain `winner_slot=null` and round-trip through the Django API and history UI as `draw`, not `abandoned`.

The complete-game harness drives the real board, bag, Collins prefix search, legality, scoring, exchange/pass, and final rack adjustments. The normal suite covers 20 deterministic bag seeds and the `slow` acceptance covers 100, both capped at 200 plies. Each ply checks all 100 tiles (including blanks), acting slot, score recomputation, non-repeated full position, and one legal terminal reason. The AI prompt never receives the hidden opponent rack; public context is limited to board/rack-owner information and public counts/history.

## Deployment

### Production

- **Frontend**: Vercel (automatic deploys from `main` branch)
- **Backend**: Self-hosted VPS with Docker Compose (Django + PostgreSQL + Redis)
- **AI**: provider-diverse free rivals with all credentials on the Next.js server; no provider secret or base URL is client-visible

### Local development

- Backend: `poetry run python manage.py runserver` (SQLite); `seed_models` for compatibility plus inactive prepared rows; leave `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` false unless changing only the compatibility tail locally
- Frontend: `npm run dev` (one or more server-only provider credentials; UI boots when they are absent)
- Redis: required for human multiplayer, websocket sync, and chat; not required for AI-only play
- Database: SQLite (zero config) or Docker Compose PostgreSQL

## Catalog operations, rollout, and rollback

Direct-provider activation is separate from the optional OpenRouter refresh:

1. Deploy code/migrations; new direct/watchlist rows remain inactive.
2. Configure one provider's server credentials and reverify current quota/data terms.
3. Run the exact opt-in capability probe without fallback.
4. On PASS, activate only that exact row in Django Admin.
5. Complete one live game; deactivate the row to roll it back. Never delete the row or game history.

Documented production schedule (not installed by this repository; configure only under separate production authority):

- Name: `libretiles-openrouter-catalog-refresh`
- Cadence: daily at 03:17 UTC
- Command: `python manage.py sync_openrouter_models` under a non-overlapping platform lock
- One scheduled run: exactly one unauthenticated OpenRouter catalog GET, 20-second timeout, no retries, no per-model probes, no NVIDIA/NIM request

Optional dynamic compatibility-tail rollout:

1. Deploy backend with `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false`
2. Deploy the dynamic-capable frontend
3. Run migrate / sync evidence
4. Enable the flag and restart Django
5. Configure `libretiles-openrouter-catalog-refresh` only under separate production authority

Rollback:

1. Set `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false` and restart Django. Dynamic rows remain stored but become unselectable; stale frontend preferences repair to a bootstrap row.
2. Pause `libretiles-openrouter-catalog-refresh` and/or deactivate a problematic row in Django Admin. No catalog row is deleted.
3. Roll backend selection to curated-only **before** rolling back the dynamic-capable frontend.

One provider PASS plus one completed live game is sufficient for a live MVP. A claim that all five direct providers work requires current live PASS evidence for all five; this repository's synthetic tests do not make that claim.

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

- Selectable models begin with active exact direct rows in fixed order: Groq `openai/gpt-oss-120b`, Gemini `gemini-3.7-flash`, Cloudflare `@cf/zai-org/glm-4.7-flash`, Mistral `mistral-small-2603`, IBM `ibm/granite-4-h-small`. Prepared direct and Aion/HF watchlist rows default inactive; only credential + PASS + explicit Admin activation makes a row selectable.
- The compatibility tail depends on `DYNAMIC_FREE_MODEL_CATALOG_ENABLED`:
  - **Flag off (default compatibility tail):** the five curated `(provider, model_id)` pairs in `FREE_RIVAL_PAIRS` order, after any active direct rows:
    - `openrouter` — `google/gemma-4-31b-it:free`
    - `nvidia-nim` — `nvidia/nemotron-3-super-120b-a12b`
    - `openrouter` — `nvidia/nemotron-3-super-120b-a12b:free`
    - `openrouter` — `z-ai/glm-5.2:free`
    - `openrouter` — `google/gemma-4-26b-a4b-it:free`
  - **Flag on compatibility tail:** four newest eligible OpenRouter `:free` models (zero prompt/completion pricing, tools, text output, OpenRouter-managed, currently available; `openrouter/free` excluded) plus the seeded NIM tuple last, still after active direct rows. Missing `released_at` ranks after dated rows; bootstrap `sort_order` then `model_id` break ties.
  - exact `(provider, model_id)` membership after selection, `is_active`, `model_type="language"`, tools, and OpenRouter availability (NIM does not require `openrouter_available`)
- `seed_models` is the boot path. `sync_openrouter_models` is optional, non-blocking, and must not own or disable the NIM row.
- Frontend uses an exact client-safe allowlist for direct/watchlist/NIM pairs and structural validation only for OpenRouter `:free` ids; `frontend/src/lib/model-catalog.ts` additionally requires membership in the live active Django catalog and fails closed.
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
