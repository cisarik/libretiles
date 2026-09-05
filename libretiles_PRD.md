# Libre Tiles — Product Requirements Document

Updated: August 25, 2026

## 1. Product in One Sentence

Libre Tiles is an open-source web-based Libre Tiles game playable in twelve board languages with a twelve-locale interface, an eye-candy animated frontend, AI opponents via provider-diverse free rivals, and a lightweight Django backend with full admin control.

## 2. Product Goals

1. Deliver a visually stunning, native-feeling Libre Tiles experience in the browser (desktop + mobile).
2. Let users choose a free rival from the selectable catalog. Flag-off (default) is five curated bootstrap pairs; flag-on is the four newest eligible OpenRouter models plus the seeded NIM tuple. The product does not handle money; play and Judge share one preference-first fallback queue. Provider quotas or trial terms are external and may change — they are not Libre Tiles credits or charges. Stripe is rejected for this product direction.
3. Provide a Django Admin-first configuration model: all game settings and AI model catalog activation/availability managed through /admin/. Catalog Admin does not manage token or per-game prices.
4. Prepare architecture for human-vs-human multiplayer (v2).
5. Maintain open-source quality: tests, documentation, clean architecture, GitHub-ready.

## 3. Target Users

- Casual Libre Tiles players who want a beautiful web game they can play on any device.
- AI enthusiasts who want to test their skills against different language models.
- Administrators who manage the game platform via Django Admin.

## 4. Architecture Overview

- **Frontend**: Next.js 16 (React 19, TypeScript, Tailwind CSS 4, Framer Motion, @dnd-kit) deployed on **Vercel**.
- **AI**: Next.js API routes using Vercel AI SDK as an OpenAI-compatible adapter. Nine providers ship — `openrouter`, `nvidia-nim`, `groq`, `google-gemini`, `cloudflare-workers-ai`, `mistral`, `ibm-watsonx`, `aion`, `huggingface` — of which `EXACT_PROVIDER_METADATA` marks five `direct`, two `watchlist` and one `legacy`. Dispatch is `ai-runtimes.ts`: `nvidia-nim`, `openrouter` and `ibm-watsonx` have their own runtimes and every other provider goes through the shared OpenAI-compatible constructor. Credentials are server-only. Catalog gated by `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` (default false = bootstrap pairs). Hardcoded bases; no Vercel AI Gateway, LM Studio, or base-URL env vars. There is no `NEXT_PUBLIC_DEFAULT_MODEL`.
- **Backend**: Django 5.x + DRF on self-hosted VPS (game state, validation, auth, admin).
- **Database**: PostgreSQL (production), SQLite (dev).
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
- Create game (vs AI or vs human placeholder).
- Full game state persistence in database (board, racks, bag, scores, moves).
- Move history with audit trail.
- Starting draw animation data (which tiles drawn, who goes first).
- Status: **Implemented** (game/).

### FR-04: AI Opponent via Provider-Diverse Free Rivals
- AI models configured in Django Admin. `DYNAMIC_FREE_MODEL_CATALOG_ENABLED` (default false) returns the five curated bootstrap pairs (OpenRouter Gemma, NVIDIA NIM Nemotron, and three other OpenRouter rows). When true, `/api/catalog/models/` returns the four newest eligible OpenRouter models plus the seeded NIM tuple, newest-first, with only row 1 marked flagship. Admin `is_active` is the operational kill switch.
- Frontend fetches available models from /api/catalog/models/. There is no static frontend ID allowlist (`frontend/src/lib/model-catalog.ts`).
- User selects preferred rival in Settings (`model_id` preference). A valid preference is attempt 1; remaining attempts follow untouched catalog order. New users receive catalog row 1. Play and Judge share `buildFallbackQueue`, capped at three distinct pairs.
- AI move generation through Next.js API route (/api/ai/move) using Vercel AI SDK against the selected provider runtime. Terminal SSE metadata includes `provider_requests_used`; `max_steps` is the remaining whole-turn provider-call budget.
- AI uses tool calling: validate moves, check words, score moves via Django API endpoints. Collins 2019 on Django remains the move validator.
- AI judge (Tier 3) via /api/ai/judge uses the same queue: up to three sequential attempts, `maxRetries: 0`, 10 s per attempt, 30 s overall, HTTP 503 on exhaustion, never synthesizing false invalid verdicts.
- Move prompt: legality-first anchor search, early backend-validated scoring floor, budget-bounded diversity, strict JSON. Judge prompt: Collins-2019-only, no natural-usage override. Seeded Admin presets refresh only via reversible SHA-256 hash-gated migration `0010` (unmodified seed rows only).
- Thinking overlay: ordered attempt pills with a lifecycle-bound gold/black ping-pong tile (zero artificial delay, reduced-motion safe, readable without Premium Look).
- Status: **Implemented** (frontend/src/app/api/ai/, frontend/src/lib/prompts.ts, openrouter.ts, nvidia-nim.ts, ai-runtimes.ts, ai-fallback.ts, model-catalog.ts, AIThinkingOverlay.tsx).

### FR-05: 3-Tier Word Validation
- Tier 1: Local per-variant word list, Collins 2019 for the English variant (in-memory frozenset, O(1) lookup).
- Tier 2: Online dictionary API for words not in the Collins 2019 list (optional; the local list is comprehensive).
- Tier 3: AI Judge via the shared free-rival fallback queue (up to three attempts; HTTP 503 on exhaustion).
- Status: **Tier 1 + 3 implemented**, Tier 2 optional.

### FR-06: Eye-Candy Frontend
- Dark theme with warm accents, glassmorphism panels, deep layered shadows.
- 3D tile feel with CSS perspective, embossed letters, spring animations.
- Starting draw animation: tiles fly from bag, flip to reveal, winner announced.
- Drag-and-drop (rack to board) with @dnd-kit, snap-to-cell, ghost preview.
- Tile exchange mode: tap to select tiles, confirm/cancel, fly-to-bag animation.
- Blank tile letter picker: 26-letter grid modal.
- Score display: animated slot-machine counters, "+N" popup, bingo explosion.
- AI thinking: overlay with ordered fallback-rival pills and a lifecycle-bound ping-pong tile.
- Game end: confetti explosion (victory), respectful "Game Over" (loss), score breakdown card.
- Move history timeline with expandable word details.
- Responsive: mobile bottom-sheet rack, pinch-zoom board, tap-to-place alternative.
- Premium squares configurable for any letter (blank tiles).
- Animated judge results display (eye-candy word validation feedback).
- Status: **Core implemented** (Board, Tile, TileRack, ScorePanel, GameControls, BlankPicker, DnD, confetti). Premium animations in progress.

### FR-07: Settings (MVP)
- AI model selection: selectable free rivals from the catalog API (name, description, Free badge, provider badge, selected state). Flag-off shows the five bootstrap pairs; flag-on shows newest-four-plus-NIM.
- Fetched from Django catalog API.
- Timeout and search-step controls remain.
- Status: **Implemented** (frontend/src/app/settings/page.tsx).

### FR-08: Django Admin Configuration
- AIModel: add/remove/toggle models, set quality tier; catalog activation and availability. No token or per-game prices.
- GameSession: inspect active/finished games, view board state, moves.
- Move: audit trail with AI metadata.
- User: manage accounts, view preferred models.
- Status: **Implemented** (admin.py in each live app; billing is not an installed Django app).

### FR-09: Free-only play (no application money)
- The product does not handle money: no app credits, USD balances, token prices, per-game charges, Stripe, or top-up UX.
- Play and Judge use the selectable free-rival catalog only (flag-off: five curated bootstrap pairs; flag-on: four newest eligible OpenRouter models plus seeded NIM). Judge uses the same fallback queue as Play.
- Provider quotas or trial terms are external and may change; they are not Libre Tiles credits or charges.
- Stripe is rejected for this product direction, not unfinished work.
- Status: **Implemented**.

### FR-10: Human vs Human Multiplayer (v2 Preparation)
- Data model supports 2-player games (PlayerSlot with user FK).
- Game lobby with invite links.
- Real-time via WebSocket (Django Channels) or polling.
- Status: **Data model ready**, implementation planned for v2.

### FR-11: Catalog refresh, rollout, and rollback
- Documented production schedule name: `libretiles-openrouter-catalog-refresh`, daily at 03:17 UTC, invoking `python manage.py sync_openrouter_models` under a non-overlapping platform lock. One run: exactly one unauthenticated OpenRouter catalog GET, 20-second timeout, no retries, no per-model probes, no NVIDIA/NIM request. Host configuration is separate production authority.
- Rollout: deploy backend with `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false` → deploy the dynamic-capable frontend → run migrate/sync evidence → enable the flag.
- Rollback: set the flag false and restart Django; pause the schedule and/or deactivate rows in Admin; roll backend selection to curated-only before rolling back the dynamic-capable frontend.
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
- Tests: pytest (backend), Vitest + Playwright (frontend).

### NFR-02: Performance
- Game state reconstruction from DB: < 5ms per move.
- Collins 2019 dictionary lookup: O(1) via frozenset.
- AI move timeout: configurable via AI_MOVE_TIMEOUT_SECONDS.

### NFR-03: Responsive Design
- Desktop (>1024px), Tablet (768-1024px), Mobile (<768px).
- Touch-first drag-and-drop with @dnd-kit sensors.

### NFR-04: Open Source
- MIT license.
- GitHub-ready: README, PRD, CI workflows, .env.example.
- No secrets committed.

## 7. Testing Strategy

- **Gamecore tests**: Pure Python, offline, fast. Must pass on every build.
- **API tests**: Django TestCase, full request/response cycle.
- **Live AI tests**: Not part of this cut. Do not add an internet pytest suite for OpenRouter.
- **Frontend tests**: Vitest (components), Playwright (E2E).
- **CI**: ruff + mypy + offline pytest (backend), eslint + tsc + vitest (frontend).

## 8. Known Gaps

- The eight newest interface catalogs (German, Portuguese, Icelandic, Italian, Dutch, Danish, Swedish, Afrikaans) are machine-authored and have had no second-opinion review.
- Localization tests pin exact expected wording for four of the twelve locales (`REVIEWED_LOCALES` = `en sk cs pl`) and cover the other eight structurally instead.
- The Slovak word list is a hunspell expansion of the LibreOffice `sk_SK` dictionary: playable, not an SSS-official list.
- Human vs human multiplayer deferred to v2.
- Online dictionary API (Tier 2) may not be needed if the local Collins 2019 list is sufficient.
- Starting draw animation not yet eye-candy (basic flow implemented).
- Move history timeline UI not yet implemented.
- Mobile bottom-sheet rack and pinch-zoom not yet implemented.

## 9. Roadmap

1. **Phase 1** (done): Scaffolding, gamecore extraction, Django project, assets, tests.
2. **Phase 2** (done): Django apps (accounts, catalog, game), REST API, admin. Historical `backend/billing/` remains an inert migration tombstone, not a live app.
3. **Phase 3** (done): OpenRouter free-rival tool-calling (Next.js API routes, agent, prompts). Historical Gateway/direct-OpenAI/LM Studio paths remain out of this cut.
4. **Phase 4** (done): Eye-candy frontend (board, tiles, DnD, animations, settings, game flow).
5. **Phase 5**: Polish -- mobile UX, move history timeline, starting draw animation, AI thinking particles.
6. **Phase 6**: Human vs human multiplayer (WebSocket, lobby, invites).
7. **Phase 7**: Deployment (Vercel + VPS). Stripe is rejected for this product direction.
8. **Phase 8**: CI/CD (GitHub Actions), E2E tests (Playwright), performance optimization.
