# Libre Tiles — Product Requirements Document

Updated: March 20, 2026

## 1. Product in One Sentence

Libre Tiles is an open-source web-based Libre Tiles game with an eye-candy animated frontend, AI opponents via OpenRouter free rivals, and a lightweight Django backend with full admin control.

## 2. Product Goals

1. Deliver a visually stunning, native-feeling Libre Tiles experience in the browser (desktop + mobile).
2. Let users choose which of the four curated OpenRouter free rivals to play against. This cut charges zero app credits per AI turn; Stripe remains unfinished.
3. Provide a Django Admin-first configuration model: all game settings, AI models, and pricing managed through /admin/.
4. Prepare architecture for human-vs-human multiplayer (v2).
5. Maintain open-source quality: tests, documentation, clean architecture, GitHub-ready.

## 3. Target Users

- Casual Libre Tiles players who want a beautiful web game they can play on any device.
- AI enthusiasts who want to test their skills against different language models.
- Administrators who manage the game platform via Django Admin.

## 4. Architecture Overview

- **Frontend**: Next.js 16 (React 19, TypeScript, Tailwind CSS 4, Framer Motion, @dnd-kit) deployed on **Vercel**.
- **AI**: Next.js API routes using Vercel AI SDK as an OpenAI-compatible adapter against OpenRouter (`OPENROUTER_API_KEY` only). Four native free-rival IDs; no Vercel AI Gateway configuration.
- **Backend**: Django 5.x + DRF on self-hosted VPS (game state, validation, auth, admin).
- **Database**: PostgreSQL (production), SQLite (dev).
- **Game Engine**: Pure Python `gamecore/` package ported from scrabgpt/core/ (zero UI dependencies).

## 5. Functional Requirements

### FR-01: Game Core (English Variant)
- Standard 15x15 board with premium squares (TW, DW, TL, DL).
- English tile distribution (100 tiles, SOWPODS dictionary with 172,823 words).
- Full move validation: placement rules, word formation, scoring with premiums, bingo (+50).
- Tile exchange, pass, endgame detection, and final scoring.
- Status: **Implemented** (gamecore/).

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

### FR-04: AI Opponent via OpenRouter Free Rivals
- AI models configured in Django Admin; this cut exposes the four curated OpenRouter free rivals.
- Frontend fetches available models from /api/catalog/models/.
- User selects preferred rival in Settings.
- AI move generation through Next.js API route (/api/ai/move) using Vercel AI SDK against OpenRouter.
- AI uses tool calling: validate moves, check words, score moves via Django API endpoints.
- AI judge fallback for word validation (Tier 3) via /api/ai/judge.
- AI prompt ported from desktop scrabgpt: strategic priorities, blank policy, anti-blunder rules.
- Status: **Implemented** (frontend/src/app/api/ai/, frontend/src/lib/prompts.ts, openrouter.ts, free-rivals.ts).

### FR-05: 3-Tier Word Validation
- Tier 1: Local SOWPODS dictionary (in-memory frozenset, O(1) lookup).
- Tier 2: Online dictionary API for words not in SOWPODS (optional, SOWPODS is comprehensive).
- Tier 3: AI Judge via OpenRouter for ambiguous cases.
- Status: **Tier 1 + 3 implemented**, Tier 2 optional.

### FR-06: Eye-Candy Frontend
- Dark theme with warm accents, glassmorphism panels, deep layered shadows.
- 3D tile feel with CSS perspective, embossed letters, spring animations.
- Starting draw animation: tiles fly from bag, flip to reveal, winner announced.
- Drag-and-drop (rack to board) with @dnd-kit, snap-to-cell, ghost preview.
- Tile exchange mode: tap to select tiles, confirm/cancel, fly-to-bag animation.
- Blank tile letter picker: 26-letter grid modal.
- Score display: animated slot-machine counters, "+N" popup, bingo explosion.
- AI thinking: shimmer overlay with floating particles.
- Game end: confetti explosion (victory), respectful "Game Over" (loss), score breakdown card.
- Move history timeline with expandable word details.
- Responsive: mobile bottom-sheet rack, pinch-zoom board, tap-to-place alternative.
- Premium squares configurable for any letter (blank tiles).
- Animated judge results display (eye-candy word validation feedback).
- Status: **Core implemented** (Board, Tile, TileRack, ScorePanel, GameControls, BlankPicker, DnD, confetti). Premium animations in progress.

### FR-07: Settings (MVP)
- AI model selection: the four curated OpenRouter free rivals (name, description, Free badge, selected state).
- Fetched from Django catalog API.
- Timeout and search-step controls remain.
- Status: **Implemented** (frontend/src/app/settings/page.tsx).

### FR-08: Django Admin Configuration
- AIModel: add/remove/toggle models, set pricing, set quality tier.
- GameSession: inspect active/finished games, view board state, moves.
- Move: audit trail with AI metadata.
- User: manage accounts, view preferred models.
- CreditBalance + Transaction: billing oversight.
- Status: **Implemented** (admin.py in each app).

### FR-09: Billing (Credits System)
- This cut charges **zero app credits** for AI turns.
- Stripe Checkout / credit purchase remains unfinished; do not document a top-up flow.
- Human vs human games are free.
- Billing models remain in Django Admin as dormant compatibility surfaces.
- Status: **Partial** — zero-charge AI cut shipped; Stripe planned.

### FR-10: Human vs Human Multiplayer (v2 Preparation)
- Data model supports 2-player games (PlayerSlot with user FK).
- Game lobby with invite links.
- Real-time via WebSocket (Django Channels) or polling.
- Status: **Data model ready**, implementation planned for v2.

## 6. Non-Functional Requirements

### NFR-01: Code Quality
- Python: ruff + mypy strict.
- TypeScript: ESLint + strict TypeScript.
- Tests: pytest (backend), Vitest + Playwright (frontend).

### NFR-02: Performance
- Game state reconstruction from DB: < 5ms per move.
- SOWPODS dictionary lookup: O(1) via frozenset.
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

- Stripe billing not yet integrated (Phase 6).
- Human vs human multiplayer deferred to v2.
- Online dictionary API (Tier 2) may not be needed if SOWPODS is sufficient.
- Starting draw animation not yet eye-candy (basic flow implemented).
- Move history timeline UI not yet implemented.
- Mobile bottom-sheet rack and pinch-zoom not yet implemented.

## 9. Roadmap

1. **Phase 1** (done): Scaffolding, gamecore extraction, Django project, assets, tests.
2. **Phase 2** (done): Django apps (accounts, catalog, game, billing), REST API, admin.
3. **Phase 3** (done): OpenRouter free-rival tool-calling (Next.js API routes, agent, prompts). Historical Gateway/direct-OpenAI/LM Studio paths are removed from this cut.
4. **Phase 4** (done): Eye-candy frontend (board, tiles, DnD, animations, settings, game flow).
5. **Phase 5**: Polish -- mobile UX, move history timeline, starting draw animation, AI thinking particles.
6. **Phase 6**: Human vs human multiplayer (WebSocket, lobby, invites).
7. **Phase 7**: Billing (Stripe) + deployment (Vercel + VPS).
8. **Phase 8**: CI/CD (GitHub Actions), E2E tests (Playwright), performance optimization.
