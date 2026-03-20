# Libre Tiles -- Architecture

This document describes the technical architecture of the Libre Tiles project. It covers the system design, data flow, AI agent workflow, and deployment topology.

**Repository boundary**: The `libretiles/` tree is self-contained and can be published as a standalone Git repository. It does not import code from other monorepos; the game engine and `sowpods.txt` live under `backend/`.

## System Overview

Libre Tiles is a 2-tier web application:

1. **Next.js Frontend** (deployed on Vercel) -- UI, AI agent orchestration, model routing
2. **Django Backend** (self-hosted VPS) -- game state, validation, auth, admin, dictionary

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
                │ REST API (JWT Bearer)
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
│            Django Backend (VPS)               │
│                                              │
│  ┌─────────┐ ┌──────────┐ ┌─────────────┐   │
│  │accounts │ │ catalog  │ │    game      │   │
│  │(JWT)    │ │(models)  │ │(state,moves) │   │
│  └─────────┘ └──────────┘ └──────┬──────┘   │
│                                  │           │
│  ┌─────────────────────────────────────────┐ │
│  │           gamecore/ (pure Python)       │ │
│  │  board, rules, scoring, tiles, game     │ │
│  │  variant_store, fastdict (SOWPODS)      │ │
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
└──────────────────────────────────────────────┘
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
| `validateWords` | Check words against SOWPODS dictionary (172K words) | `POST /api/game/{id}/validate-words/` |

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
Frontend Settings ──► Zustand store (selectedModelId) ──► /api/ai/move POST body
                                                              │
                                                    ai-gateway.ts getModel()
                                                              │
                                                    ┌─────────┴──────────┐
                                                    │                    │
                                            AI_GATEWAY_API_KEY?   OPENAI_API_KEY
                                                    │                    │
                                            AI Gateway            Direct OpenAI
                                            (production)          (local dev)
```

- **Production** (Vercel): `AI_GATEWAY_API_KEY` + `AI_GATEWAY_BASE_URL` are set. Model IDs use `provider/model` format. All requests go through the Vercel AI Gateway.
- **Local dev**: Falls back to direct provider SDK. The `provider/` prefix is stripped from model IDs.

## Word Validation Pipeline

```
Word submitted
      │
      ▼
  Tier 1: SOWPODS
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

Tier 1 covers 172,823 words and handles nearly all cases. Tier 3 provides a fallback for edge cases using AI language understanding.

## Data Model

### Core entities

- **User** (accounts) -- custom user with preferred AI model
- **AIModel** (catalog) -- provider, model_id, display_name, cost, quality_tier
- **GameSession** (game) -- board state JSON, bag, turn tracking, game status
- **PlayerSlot** (game) -- links users (or AI) to game positions with rack + score
- **Move** (game) -- move history with placements, words, score, AI metadata
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
- Database: SQLite (zero config) or Docker Compose PostgreSQL

## Security Considerations

- JWT tokens for API auth (short-lived access + refresh tokens)
- AI API keys stored server-side only (Next.js server environment)
- CORS configured per environment
- Django Admin behind superuser auth
- No secrets in .env.example or .env.local.example files
- `.gitignore` excludes all env files, databases, and build artifacts
