# Libre Tiles — Product Requirements Document

Updated: September 9, 2026

## 1. Product in One Sentence

Libre Tiles is an open-source web-based Libre Tiles game playable in twelve board languages with a twelve-locale interface, an eye-candy animated frontend, AI opponents via provider-diverse free rivals, live human-vs-human multiplayer, and a lightweight Django backend with full admin control.

## 2. Product Goals

1. Deliver a visually stunning, native-feeling Libre Tiles experience in the browser (desktop + mobile).
2. Let users choose a free rival from the selectable catalog. Eligible active direct rows precede a compatibility tail; the dynamic flag selects the curated bootstrap cohort or up to four newest eligible OpenRouter rows plus eligible seeded NIM. The product does not handle money; play and Judge share one preference-first fallback queue. Provider quotas or trial terms are external and may change — they are not Libre Tiles credits or charges. Stripe is rejected for this product direction.
3. Provide Django Admin control over catalog configuration through the reviewed activation and ordering workflow. In production, public `/admin` serves the Next.js staff console; Django contrib admin is private, as documented in the [VPS guide](docs/vps_deployment_guide.md#private-django-admin). Catalog Admin does not manage token or per-game prices.
4. Support live human-vs-human multiplayer with queue matchmaking, websocket synchronization, and in-game chat.
5. Maintain open-source quality: tests, documentation, clean architecture, GitHub-ready.

## 3. Target Users

- Casual Libre Tiles players who want a beautiful web game they can play on any device.
- AI enthusiasts who want to test their skills against different language models.
- Administrators who manage the game platform via Django Admin.

## 4. Architecture Overview

- **Frontend**: Next.js 16 (React 19, TypeScript, Tailwind CSS 4, Framer Motion, @dnd-kit), deployed as a standalone server on a **self-hosted VPS** behind nginx.
- **AI**: Next.js API routes use Vercel AI SDK for nine external provider integrations: `openrouter`, `nvidia-nim`, `groq`, `google-gemini`, `cloudflare-workers-ai`, `mistral`, `ibm-watsonx`, `aion`, and `huggingface`. Dispatch uses dedicated OpenRouter, NIM and watsonx runtimes plus a shared OpenAI-compatible constructor. Credentials are server-only. Prepared direct/watchlist rows default inactive; the dynamic catalog flag affects only the compatibility tail. Provider endpoints are hardcoded; no Vercel AI Gateway, LM Studio, or provider base-URL environment variables. There is no `NEXT_PUBLIC_DEFAULT_MODEL`.
- **Deployment**: one Docker Compose project on the self-hosted VPS. Nginx alone publishes host ports; Next standalone retains `127.0.0.1:3000` in nginx's network namespace, while Daphne serves a group-restricted Unix socket. Django owns game state, validation, authentication, and admin.
- **Database**: PostgreSQL (production), SQLite (dev).
- **Production secrets**: host file sources are root-owned, group-owned by dedicated reader GID 10004, and mode `0440` inside a root-owned mode-`0700` directory. Only intended consumers receive GID 10004, and explicit per-service mounts preserve least-scope visibility.
- **Realtime**: Django Channels + Redis for human matchmaking, websocket synchronization, and chat. Redis also backs shared production throttling.
- **Game Engine**: Pure Python `gamecore/` package ported from scrabgpt/core/ (zero UI dependencies).

## 5. Functional Requirements

### FR-01: Game Core (Twelve Playable Variants)
- Standard 15x15 board with premium squares (TW, DW, TL, DL).
- Twelve playable board languages, one manifest each under `backend/assets/variants/`: english, slovak, czech, polish, german, portuguese, icelandic, italian, dutch, danish, swedish, afrikaans. `game.views.list_variant_summaries()` reports `readiness: "playable"` for all twelve.
- Per-variant alphabet order, tile distribution and tile points (100-120 tiles depending on the variant), and word list. English uses Collins Scrabble Words 2019 with 279,496 words; `manage.py validate_lexicons` audits thirteen assets with zero failures.
- Every non-English lexicon is reproducible from a pinned upstream commit by one of eleven committed scripts under `backend/scripts/`, each pinning the SHA-256 of every source file it fetches plus the host expander `hunspell 1.7.3`, and failing closed on a mismatch.
- Full move validation: placement rules, word formation, scoring with premiums, bingo (+50).
- Tile exchange, pass, endgame detection, and final scoring.
- Status: **Implemented** (gamecore/, backend/assets/variants/).

### FR-02: User Authentication
- Register with username/email/password.
- JWT-based auth for API access from frontend.
- User profile with preferred AI model selection.
- Status: **Implemented** (accounts/).

### FR-03: Game Session Management
- Create AI games or join/cancel the human matchmaking queue; human games start when a second player is matched.
- Full game state persistence in database (board, racks, bag, scores, moves).
- Move history with audit trail.
- Starting draw animation data (which tiles drawn, who goes first).
- Status: **Implemented** (game/).

### FR-04: AI Opponent via Provider-Diverse Free Rivals
- Django Admin controls model activation and applicable ordering through its reviewed workflow. Eligible active direct rows precede the compatibility tail. `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false` selects that tail from the five curated bootstrap pairs; true selects up to four newest eligible OpenRouter models plus eligible seeded NIM. Only catalog row 1 is flagship/recommended. Seed and sync preserve existing `is_active` decisions.
- Frontend fetches available models from /api/catalog/models/. External runtime pairs must pass frontend registry validation and live Django catalog membership checks (`frontend/src/lib/model-catalog.ts`).
- User selects preferred rival in Settings (`model_id` preference). A valid preference is attempt 1; remaining attempts follow untouched catalog order. New users receive catalog row 1. Play and Judge share `buildFallbackQueue`, capped at three distinct pairs.
- AI move generation through Next.js API route (/api/ai/move) using Vercel AI SDK against the selected provider runtime. Terminal SSE metadata includes `provider_requests_used`; `max_steps` is the remaining whole-turn provider-call budget.
- External AI move generation uses `validateMove` for backend validation and scoring, then `finishMove` only after a valid candidate. Django `WordAuthority.accepts_tokens` is the sole formed-word authority over physical tiles and the selected variant's lexicons; Collins 2019 applies to English. Free-form model text cannot authorize a move.
- AI judge (Tier 3) via /api/ai/judge uses the same queue: up to three sequential attempts, `maxRetries: 0`, 10 s per attempt, 30 s overall, HTTP 503 on exhaustion, never synthesizing false invalid verdicts.
- Move prompt: non-overridable TypeScript CORE plus advisory SEARCH_PROFILE, legality-first anchor search, an early backend-validated scoring floor, and budget-bounded diversity. Judge prompt: Collins-2019-only, no natural-usage override. Seeded presets refresh through reversible SHA-256 hash-gated migrations `0010` and `0011`; customized rows are preserved.
- Thinking overlay: ordered attempt pills with a lifecycle-bound gold/black ping-pong tile (zero artificial delay, reduced-motion safe, readable without Premium Look).
- Status: **Implemented** (frontend/src/app/api/ai/, frontend/src/lib/prompts.ts, openrouter.ts, nvidia-nim.ts, ai-runtimes.ts, ai-fallback.ts, model-catalog.ts, AIThinkingOverlay.tsx).

### FR-05: 3-Tier Word Validation
- Tier 1: Local per-variant word list, Collins 2019 for the English variant (in-memory frozenset, O(1) lookup).
- Tier 2: Optional online dictionary assistance is planned and not implemented.
- Tier 3: Advisory Collins-2019-conservative AI Judge via the shared free-rival fallback queue (up to three attempts; HTTP 503 on exhaustion). It never overrides a persisted Django verdict.
- Status: **Tier 1 + advisory Tier 3 implemented**; Tier 2 remains optional planned work.

### FR-06: Eye-Candy Frontend
- Dark theme with warm accents, glassmorphism panels, deep layered shadows.
- 3D tile feel with CSS perspective, embossed letters, spring animations.
- Starting draw animation: tiles enter, flip to reveal letters, and highlight the starting player.
- Drag-and-drop (rack to board) with @dnd-kit, snap-to-cell, ghost preview.
- Tile exchange mode: tap to select tiles, confirm/cancel, fly-to-bag animation.
- Blank tile picker: grid modal using the selected variant's alphabet, with an English fallback.
- Score display: animated slot-machine counters, "+N" popup, bingo explosion.
- AI thinking: overlay with ordered fallback-rival pills and a lifecycle-bound ping-pong tile.
- Game end: confetti explosion (victory), respectful "Game Over" (loss), score breakdown card.
- Planned: per-game move timeline with expandable word details. Game-list history and reopening saved games are implemented.
- Responsive layouts and touch drag-and-drop are implemented; mobile bottom-sheet rack and pinch-zoom remain planned.
- Assigned blank tiles represent a selected variant token and score zero.
- Animated judge results display (eye-candy word validation feedback).
- Status: **Core implemented** (Board, Tile, TileRack, ScorePanel, GameControls, BlankPicker, DnD, confetti). Shared optional Premium Look chrome is implemented; remaining UI work is listed in Known Gaps.

### FR-07: Settings (MVP)
- AI model selection: selectable free rivals from the catalog API (name, description, Free badge, provider badge, selected state). Eligible active direct rows precede the flag-selected compatibility tail.
- Fetched from Django catalog API.
- Timeout and search-step controls remain.
- Status: **Implemented** (frontend/src/app/settings/page.tsx).

### FR-08: Django Admin Configuration
- AIModel: add inactive models and edit permitted metadata; activation and fallback ordering use the reviewed Admin workflow. Model deletion is disabled. No token or per-game prices.
- GameSession: inspect active/finished games, view board state, moves.
- Move: audit trail with AI metadata.
- User: manage accounts, view preferred models.
- Status: **Implemented** (admin.py in each live app; billing is not an installed Django app).

### FR-09: Free-only play (no application money)
- The product does not handle money: no app credits, USD balances, token prices, per-game charges, Stripe, or top-up UX.
- Play and Judge use the selectable free-rival catalog, with eligible active direct rows followed by the flag-selected compatibility tail. Judge uses the same preference-first fallback queue as Play.
- Provider quotas or trial terms are external and may change; they are not Libre Tiles credits or charges.
- Stripe is rejected for this product direction, not unfinished work.
- Status: **Implemented**.

### FR-10: Human vs Human Multiplayer
- Authenticated players join or cancel the human matchmaking queue.
- A waiting room becomes an active two-player game when a compatible opponent joins.
- Django Channels and Redis synchronize game state and in-game chat over authenticated websockets.
- Django derives the acting player from authentication and returns only that player's private rack.
- Status: **Implemented** (game services, websocket consumers, and frontend waiting-room/game flows).

### FR-11: Catalog refresh, rollout, and rollback
- Documented production schedule name: `libretiles-openrouter-catalog-refresh`, daily at 03:17 UTC, invoking `python manage.py sync_openrouter_models` under a non-overlapping platform lock. One run: exactly one unauthenticated OpenRouter catalog GET, 20-second timeout, no retries, no per-model probes, no NVIDIA/NIM request. Host configuration is separate production authority.
- Compatibility-tail rollout: deploy compatible code with `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false`, obtain migrate/sync evidence, then enable the flag and restart Django. Direct-provider activation is a separate credential, capability-probe, and reviewed Admin operation.
- Compatibility-tail rollback: set the flag false and restart Django; pause the optional schedule and/or deactivate affected rows through the reviewed Admin workflow. Existing active direct rows remain ahead of the compatibility tail.
- Status: **Documented**. Scheduler installation is not part of this cut.

### FR-12: Interface Localization
- Twelve interface locales. `LOCALES` in `frontend/src/lib/i18n/locales.ts` is `en sk cs pl de pt is it nl da sv af`, `translate.ts` wires all twelve `messages.XX.ts` catalogs, and every catalog defines the same 324 keys (304 text + 20 parameterised).
- Locale resolution: `Accept-Language` primary-subtag detection, the `libretiles_locale` cookie, and an explicit interface-language picker in Settings that offers all twelve endonyms.
- Localized variant names: `VARIANT_NAME_KEYS` in `GameLanguagePanel.tsx` covers all twelve slugs, so the variant picker, the human-queue label, and lexicon-rejection copy name the language in the active interface locale.
- Status: **Implemented for gameplay** (frontend/src/lib/i18n/, GameLanguagePanel.tsx, frontend/src/app/settings/page.tsx). Second-opinion review of the eight machine-authored catalogs is open work — see Known Gaps.

## 6. Non-Functional Requirements

### NFR-01: Code Quality
- Python: ruff + mypy strict.
- TypeScript: ESLint + strict TypeScript.
- Tests: pytest (backend) and Vitest (frontend); Playwright E2E coverage is planned.

### NFR-02: Performance
- Game state reconstruction from DB: < 5ms per move.
- Collins 2019 dictionary lookup: O(1) via frozenset.
- AI turn timeout and provider-step budget are configurable in Settings (`aiTimeout`, `aiMaxSteps`); the move route bounds the requested per-attempt timeout and remaining steps.

### NFR-03: Responsive Design
- Desktop (>1024px), Tablet (768-1024px), Mobile (<768px).
- Touch-first drag-and-drop with @dnd-kit sensors.

### NFR-04: Open Source
- MIT license.
- Repository documentation and environment examples are present; GitHub Actions workflows remain planned.
- No secrets committed.

## 7. Testing Strategy

- **Gamecore tests**: Pure Python, offline, fast. Must pass on every build.
- **API tests**: Django TestCase, full request/response cycle.
- **Live AI probes**: Explicit operator-only capability checks; ordinary tests use synthetic behavior and skip live provider calls.
- **Frontend tests**: Vitest unit and integration tests; Playwright E2E tests remain planned.
- **Planned CI**: ruff + mypy + offline pytest (backend), eslint + tsc + vitest (frontend).

## 8. Known Gaps

- The eight newest interface catalogs (German, Portuguese, Icelandic, Italian, Dutch, Danish, Swedish, Afrikaans) are machine-authored and have had no second-opinion review.
- Localization tests pin exact expected wording for four of the twelve locales (`REVIEWED_LOCALES` = `en sk cs pl`) and cover the other eight structurally instead.
- The Slovak word list is a hunspell expansion of the LibreOffice `sk_SK` dictionary: playable, not an SSS-official list.
- Optional online dictionary assistance (Tier 2) is not implemented.
- A per-game move timeline with expandable word details remains unimplemented; game-list history is available.
- Mobile bottom-sheet rack and pinch-zoom not yet implemented.

## 9. Roadmap

1. **Phase 1** (done): Scaffolding, gamecore extraction, Django project, assets, tests.
2. **Phase 2** (done): Django apps (accounts, catalog, game), REST API, admin. Historical `backend/billing/` remains an inert migration tombstone, not a live app.
3. **Phase 3** (done): OpenRouter free-rival tool-calling (Next.js API routes, agent, prompts). Historical Gateway/direct-OpenAI/LM Studio paths remain out of this cut.
4. **Phase 4** (done): Eye-candy frontend (board, tiles, DnD, animations, settings, game flow).
5. **Phase 5** (partial): Starting draw animation, game-list history, and shared Premium Look chrome are implemented; mobile bottom-sheet/pinch-zoom UX, a per-game move timeline, and AI thinking particles remain planned.
6. **Phase 6** (done): Human vs human multiplayer (queue join/cancel, waiting room, WebSocket synchronization, and in-game chat).
7. **Phase 7**: Deployment (self-hosted VPS: Docker Compose with Next.js standalone + Daphne/Django behind nginx). Stripe is rejected for this product direction.
8. **Phase 8**: CI/CD (GitHub Actions), E2E tests (Playwright), performance optimization.
