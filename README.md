# Libre Tiles

Open-source web Libre Tiles game with AI opponents, live human-vs-human multiplayer, and an eye-candy animated frontend.

**Architecture**: Next.js frontend (provider-diverse free-rival AI + UI) + lightweight Django backend (game logic, validation, admin).

**Standalone repository**: This folder is intended to be published as its **own** GitHub repository. It does **not** depend on the parent `scrabgpt_sk` monorepo — all assets and code live under `libretiles/`. For agent/continuation notes see **[AGENTS.md](AGENTS.md)**.

## Features

- Full Libre Tiles game engine with **twelve playable board languages** — English (Collins 2019, 279,496 words), Slovak, Czech, Polish, German, Portuguese, Icelandic, Italian, Dutch, Danish, Swedish, Afrikaans — each with its own alphabet, tile distribution (100-120 tiles) and word list, Tier-1 strict validation in Django
- Interface localized in **twelve languages** (`en sk cs pl de pt is it nl da sv af`), selectable in Settings and applied across gameplay
- AI opponents via provider-diverse free rivals with tool calling. The canonical direct priority is Groq → Google Gemini → Cloudflare Workers AI → Mistral → IBM watsonx.ai; NVIDIA NIM and OpenRouter remain the compatibility tail
- Live human-vs-human multiplayer with waiting-room matchmaking, realtime board sync, and in-game chat
- AI plays as a tool-calling agent: validates moves, checks words, calculates scores
- Play and Judge share one preference-first fallback queue (at most three distinct pairs, one whole-turn provider-call budget)
- Advanced drag-and-drop with touch/mobile support (@dnd-kit)
- Animated tile drawing, scoring, and game-end effects (Framer Motion, confetti)
- Django Admin for configuration (AI model catalog, games)
- Settings page with the selectable free-rival shortlist from `GET /api/catalog/models/`
- Free-only play: the product does not handle money, app credits, USD balances, token prices, or per-game charges. Play and Judge use the selectable free-rival catalog only. Provider quotas or trial terms are external and may change — they are not Libre Tiles credits or charges. Stripe is rejected for this product direction.
- Responsive design (desktop, tablet, mobile)
- 3-tier word validation: local per-variant word list (Collins 2019 for English), online API (optional), AI judge

## Languages

**Twelve board languages ship playable.** `ls backend/assets/variants/` lists twelve manifests and `game.views.list_variant_summaries()` reports `readiness: "playable"` for all twelve: english, slovak, czech, polish, german, portuguese, icelandic, italian, dutch, danish, swedish, afrikaans. Each carries its own alphabet order, tile distribution and points, and word list. `poetry run python manage.py validate_lexicons` audits every shipped asset:

```
validate_lexicons: 13 asset(s) audited, 0 failed
```

Surviving word counts at this commit: English 279,496 · Afrikaans 148,267 · Icelandic 200,182 · Danish 317,167 · German 709,844 · Swedish 822,919 · Dutch 1,293,086 · Slovak 3,005,250 · Italian 3,128,429 · Polish 3,721,704 · Czech 3,930,497 · Portuguese 4,119,831, plus the Slovak two-tile allowlist at 103.

Every non-English lexicon is reproducible from source: eleven committed scripts under `backend/scripts/` each pin an upstream commit and the SHA-256 of every source file they fetch, pin the host expander (`hunspell 1.7.3`), and fail closed on a mismatch. `--check --check-dir <dir outside backend/assets/>` re-verifies a committed asset instead of rebuilding it. They are host tools: not imported by Django, and they add no Poetry or npm dependency.

**The interface is localized in twelve languages.** `LOCALES` in `frontend/src/lib/i18n/locales.ts` is `en sk cs pl de pt is it nl da sv af`, `translate.ts` wires all twelve `messages.XX.ts` catalogs, and the interface-language picker offers all twelve endonyms. Variant names are translated too, so the variant picker and the human-queue label show a localized exonym in every shipped locale.

What this does **not** claim:

- The eight newest interface catalogs (German, Portuguese, Icelandic, Italian, Dutch, Danish, Swedish, Afrikaans) are machine-authored and have had **no second-opinion review**.
- The test suite pins exact expected wording for four of the twelve locales (`REVIEWED_LOCALES` = `en sk cs pl`) and covers the other eight structurally.
- The Slovak word list is a hunspell expansion of the LibreOffice `sk_SK` dictionary — playable, **not** an SSS-official list.

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
# Prefer ./scripts/libretiles.sh from the repo root: it copies .env.example
# only when backend/.env is missing and generates DJANGO_SECRET_KEY into that
# new file. It never overwrites an existing .env. Do not paste a literal
# example key. If you copy by hand, set DJANGO_SECRET_KEY yourself
# (≥50 characters, ≥5 unique, no django-insecure- prefix).
[ -f .env ] || cp .env.example .env               # copy only if missing
poetry install                                    # install Python dependencies
poetry run python manage.py migrate               # create database tables
poetry run python manage.py seed_models           # seed compatibility + inactive direct rows
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
# Set one or more server-only provider credentials from .env.local.example.
npm install                                       # install JS dependencies
npm run dev                                       # start dev server at :3000
```

Open http://localhost:3000, register, choose a mode, and play. Credentials live only on the Next.js server. Missing or placeholder credentials are rejected before any provider fetch; the UI still boots and fallback can use another configured active row. Provider bases and exact direct model IDs are hardcoded, never supplied by the browser or a base-URL environment variable. There is no `NEXT_PUBLIC_DEFAULT_MODEL`; an empty stored selection resolves to catalog row 1.

### Environment Variables

**Backend** (`backend/.env`):

A pre-existing `.env` overrides new code defaults, is read once at process start, and must be reviewed after any settings change. This is how an old `GAME_WS_TICKET_MAX_AGE_SECONDS` value can silently keep a retired TTL.

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | - | Django secret key (required). `./scripts/libretiles.sh` generates one into a freshly created `backend/.env` and never overwrites an existing file. |
| `DEBUG` | `True` | Debug mode |
| `DB_ENGINE` | `sqlite` | `sqlite` or `postgresql` |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Frontend origin(s) |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis connection used by Django Channels; also the production fallback for the shared throttle cache |
| `DJANGO_THROTTLE_CACHE_URL` | unset | Required only when `DJANGO_DEBUG` is false: `redis://` or `rediss://` URL for the shared DRF throttle cache. If unset, `REDIS_URL` is used; if both are empty, Django refuses to start. Unused for local `DEBUG=true` boot. |
| `DJANGO_NUM_PROXIES` | `0` | Trusted reverse-proxy count for DRF unauthenticated throttle identity. `0` keys buckets on `REMOTE_ADDR`. Set to the real proxy count in a deployment; a mismatch either over-throttles or trusts `X-Forwarded-For`. |
| `GAME_WS_TICKET_MAX_AGE_SECONDS` | `10` | Max age for signed websocket tickets |
| `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` | `false` | Controls only the NIM/OpenRouter compatibility tail: curated bootstrap when false, newest-four OpenRouter plus NIM when true. Active direct rows always remain first. |

**Frontend** (`frontend/.env.local`):
| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Django backend URL (browser) |
| `BACKEND_URL` | `http://localhost:8000` | Django backend URL (Next.js server routes) |
| `NEXT_DEV_ALLOWED_ORIGINS` | unset | Optional extra hosts allowed to load Next.js dev assets |
| `GROQ_API_KEY` | unset | Server-only Groq credential |
| `GEMINI_API_KEY` | unset | Server-only Google Gemini credential |
| `CLOUDFLARE_API_TOKEN` | unset | Server-only Workers AI token |
| `CLOUDFLARE_ACCOUNT_ID` | unset | Server-only 32-hex-character Cloudflare account id |
| `MISTRAL_API_KEY` | unset | Server-only Mistral credential |
| `IBM_CLOUD_API_KEY` | unset | Server-only IBM Cloud IAM credential |
| `IBM_WATSONX_PROJECT_ID` | unset | Server-only watsonx project id |
| `IBM_WATSONX_REGION` | unset | Allowlisted watsonx region: `eu-de`, `eu-gb`, `us-south`, `jp-tok`, or `au-syd` |
| `AION_API_KEY` | unset | Prepared watchlist credential; row remains inactive pending PASS |
| `HF_TOKEN` | unset | Prepared Hugging Face watchlist credential; row remains inactive pending PASS |
| `OPENROUTER_API_KEY` | `your-openrouter-api-key` | Server-only OpenRouter key from https://openrouter.ai/keys |
| `NVIDIA_API_KEY` | `your-nvidia-api-key` | Server-only NVIDIA NIM key from https://build.nvidia.com |

Native IDs only (never `openrouter/google/...`). No provider secret or base URL belongs in a `NEXT_PUBLIC_` variable.

**Prepared direct priority** (exact pairs):

1. `groq` — `openai/gpt-oss-120b`
2. `google-gemini` — `gemini-3.7-flash`
3. `cloudflare-workers-ai` — `@cf/zai-org/glm-4.7-flash`
4. `mistral` — `mistral-small-2603`
5. `ibm-watsonx` — `ibm/granite-4-h-small`

`aion` / `aion-labs/aion-3.0-mini` and `huggingface` / `openai/gpt-oss-120b:groq` are inactive watchlist rows. NVIDIA NIM and OpenRouter remain behind active direct rows as a compatibility tail. Every new direct/watchlist row is created inactive. It becomes selectable only after server credentials are configured, the exact pair returns capability `pass`, and an operator explicitly enables it in Django Admin. Migration and seed code never changes an existing row's Admin `is_active` kill switch.

**Compatibility tail with the dynamic flag off** (`DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false`, the default):

1. `openrouter` — `google/gemma-4-31b-it:free`
2. `nvidia-nim` — `nvidia/nemotron-3-super-120b-a12b`
3. `openrouter` — `nvidia/nemotron-3-super-120b-a12b:free`
4. `openrouter` — `z-ai/glm-5.2:free`
5. `openrouter` — `google/gemma-4-26b-a4b-it:free`

**Flag-on compatibility tail**: the four newest eligible OpenRouter `:free` models plus the seeded NIM tuple last. The flag changes only this tail; it never removes or reorders active direct rows. A valid user preference remains attempt 1 and the remaining attempts preserve canonical order without duplicates.

Django Admin remains catalog authority. Play and Judge share one preference-first queue capped at three distinct pairs. New accounts default to 120 seconds and 50 provider steps. Play reserves at least five steps for each later lane, segments the remaining time, reports actual provider/IAM request counts, and carries only a bounded `retry_after_seconds`. Judge tries up to three sequential lanes (`maxRetries: 0`, 10 seconds per lane, 30 seconds overall) and returns HTTP 503 on exhaustion without inventing an invalid verdict. Collins 2019 on Django remains the persisted-move validator.

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
# Prefer ./scripts/libretiles.sh, which generates DJANGO_SECRET_KEY into a
# fresh backend/.env. A hand copy of .env.example still needs a generated key.
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
  Browser (Next.js)                   Free-rival providers
  ┌─────────────────┐                ┌──────────────────┐
  │ React UI        │                │ Groq / Gemini /  │
  │ @dnd-kit + FM   │◄──────────────►│ Cloudflare /     │
  │ Zustand store   │  /api/ai/move  │ compatibility    │
  │                 │  /api/ai/judge          │
  │ Settings page   │        ▲       │ Mistral / IBM    │ generateText()
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
   - `finishMove` -- confirms continuation after a backend-valid candidate
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
- `GET /api/catalog/models/` -- List active direct rivals in canonical order followed by the flag-selected compatibility tail. Row 1 is `is_flagship` / `recommended`. Exposes `released_at`; no money fields.

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

## Explicit provider capability probe

`npm run probe:provider` is an operator-only live check. It is never imported by boot, catalog, gameplay, or client code and its live Vitest file is skipped by ordinary `npm test` and production builds. It uses the same server-only `getLanguageRuntime(...)` and AI SDK `generateText(...)` path as gameplay, with no fallback and `maxRetries: 0`.

The check forces `validateMove` for `RETAINS` at `(7,4)` through `(7,10)`, returns a random nonce pong from the local tool, then requires the model to continue and call `finishMove({ready:true})`. The first step exposes only named `validateMove`; later steps expose both tools with automatic choice. It stops on finish, three model generations, or the overall timeout.

Configure the relevant provider credential in the server process/current shell without committing it, then run exactly one pair:

```bash
cd frontend
PROVIDER_PROBE_PROVIDER=groq PROVIDER_PROBE_MODEL=openai/gpt-oss-120b npm run probe:provider
PROVIDER_PROBE_PROVIDER=google-gemini PROVIDER_PROBE_MODEL=gemini-3.7-flash npm run probe:provider
PROVIDER_PROBE_PROVIDER=cloudflare-workers-ai PROVIDER_PROBE_MODEL=@cf/zai-org/glm-4.7-flash npm run probe:provider
PROVIDER_PROBE_PROVIDER=mistral PROVIDER_PROBE_MODEL=mistral-small-2603 npm run probe:provider
PROVIDER_PROBE_PROVIDER=ibm-watsonx PROVIDER_PROBE_MODEL=ibm/granite-4-h-small npm run probe:provider
```

The only application output is one compact, sanitized object (Vitest may also print its own test framing):

```json
{"provider":"groq","model":"openai/gpt-oss-120b","status":"pass","latency_ms":1234,"outbound_count":2}
```

Fields never include request/response bodies, headers, tokens, reasoning, raw errors, credentials, or usage. `outbound_count` is the actual bounded HTTP count, including IBM IAM. Status meanings:

| Status | Meaning |
|---|---|
| `pass` | Exact validate pong and model-driven finish continuation succeeded |
| `not_configured` | Missing/placeholder credential or locally invalid/missing pair; no provider fetch |
| `auth_failed` | A real outbound request returned authentication/authorization failure |
| `rate_limited` | Provider returned a quota/rate-limit response |
| `model_unavailable` | Exact model or endpoint is unavailable, including “No endpoints found” |
| `named_tool_unsupported` | Forced named first tool was rejected or answered with prose |
| `tool_continuation_failed` | Validation succeeded but the model did not call `finishMove` |
| `schema_failed` | Tool arguments did not satisfy the exact schema/content |
| `timeout` | The bounded overall probe timed out |
| `unknown` | Sanitized failure did not match a stable known class |

This command makes a real quota-consuming and potentially billable provider call only when manually invoked. Reverify current quota, data-processing, and acceptable-use terms before activation; free-tier terms are external, volatile, and are not product credits or an SLA. Current reference points: [Groq limits](https://console.groq.com/docs/rate-limits) and [tool calling](https://console.groq.com/docs/tool-use/local-tool-calling), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) and [OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai), [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) and [GLM model](https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/), [Mistral Free Mode](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key) and [Chat API](https://docs.mistral.ai/api/endpoint/chat), [IBM IAM](https://cloud.ibm.com/docs/apis/iam-identity-token-api) and [watsonx.ai API](https://cloud.ibm.com/docs/apis/watsonx-ai).

Activation is deliberately manual: a credential plus probe PASS plus explicit Django Admin activation of the exact row. Then complete one live game. The minimum live MVP claim is one provider PASS and one completed game. Do not claim that all five providers work until every exact pair has a current live PASS. Rollback is Admin deactivation of the affected row; never delete the row or game history.

## Operations (catalog refresh)

The documented production schedule is `libretiles-openrouter-catalog-refresh`, daily at 03:17 UTC, invoking `python manage.py sync_openrouter_models` under a non-overlapping platform lock. One scheduled run performs exactly one unauthenticated OpenRouter catalog GET with a 20-second timeout, no retries, no per-model probes, and no NVIDIA/NIM request. The scheduler itself is configured only under separate production authority — this repository documents it and does not install it.

Direct-provider rollout is pair-by-pair: deploy code and migrations with rows inactive → configure one server credential → run the explicit capability probe → activate only the exact PASS row in Django Admin → complete one live game. Roll back by deactivating that row; do not delete catalog rows or game history. The dynamic OpenRouter schedule remains an optional compatibility-tail operation: set the flag false and restart Django to roll that tail back.

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
npm test                                   # Unit/integration suite; live probe skipped
npm run lint                               # ESLint
npx tsc --noEmit                           # TypeScript check
npm run build                              # Production build
```

## Tech Stack

### Backend
- Python 3.11+, Django 5.x, Django REST Framework
- Django Channels + Redis for realtime multiplayer and chat
- JWT auth (djangorestframework-simplejwt)
- PostgreSQL (prod) / SQLite (dev)
- Twelve word lists, one per playable variant, all O(1) frozenset lookup — Collins 2019 for English (~279k words) and a hunspell-expanded list for each of the other eleven

### Frontend
- Next.js 16, React 19, TypeScript
- Tailwind CSS 4, Framer Motion, @dnd-kit/core
- Vercel AI SDK v6 via direct free rivals plus the NIM/OpenRouter compatibility tail (OpenAI-compatible transports and a watsonx IAM adapter)
- Zustand (state management with localStorage persistence)
- canvas-confetti (endgame effects)

## Game Engine

The `gamecore/` package is a pure Python Libre Tiles engine with zero framework dependencies:

- `board.py` -- 15x15 board with premium squares
- `rules.py` -- Move validation (center coverage, line placement, connectivity, gaps)
- `scoring.py` -- Score calculation with premium multipliers and bingo bonus
- `tiles.py` -- Tile bag built from the selected variant's distribution (100-120 tiles depending on the variant)
- `game.py` -- Full game simulation with endgame detection
- `variant_store.py` -- Variant loading (twelve installed manifests; English is the default slug)
- `fastdict.py` -- In-memory dictionary lookup (O(1) via frozenset)

Conceptually aligned with the desktop `scrabgpt` engine; this tree ships its **own** `gamecore/` and dictionary file.

Regular games end when a player empties their rack with an empty bag or after six consecutive scoreless turns, following the [WESPA rule](https://www.wespa.org/features/rulesv1.pdf). Pass and exchange both increment the scoreless counter; a scoring placement resets it. A tied finished game keeps `winner_slot=null` and is serialized and displayed as a draw. The deterministic engine harness runs 20 seeds in the normal backend suite and 100 seeds in the slow acceptance test, with a 200-ply cap, tile conservation, turn order, scoring, and terminal-reason checks.

## Troubleshooting

- **Invalid word but the server “accepted” it** — Distinguish between an **AI overlay candidate** (may show `valid: false`) and a **saved move**. Word validity is always decided by Django (`submit_move` / `validate_move_for_ai`) using `backend/assets/dicts/collins2019.txt`. Regression tests: `tests/test_dictionary_validation.py`.
- **Weak AI play** — Switch among the selectable free rivals, raise timeout / search steps in Settings, and tune `frontend/src/lib/prompts.ts` (see [AGENTS.md](AGENTS.md)). Do not buy a paid catalog tier for this cut.
- **Judge returned 503** — All fallback attempts failed or the catalog was empty. The route does not invent invalid verdicts from malformed output; retry or switch rivals.
- **Provider row is missing from Settings** — Prepared direct/watchlist rows are intentionally inactive. Configure the server credential, obtain an exact-pair capability `pass`, then activate only that row in Django Admin.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and how to submit changes. **[AGENTS.md](AGENTS.md)** is the maintainer/agent handoff doc.

## License

MIT
