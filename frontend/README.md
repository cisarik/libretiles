# Libre Tiles — Frontend

Next.js 16 + React 19 + TypeScript frontend for Libre Tiles.

> For full project documentation see the root [README.md](../README.md).

## Quick Start

```bash
cp .env.local.example .env.local
# Edit .env.local — set AI_GATEWAY_API_KEY (https://vercel.com/ai-gateway)
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Tech Stack

- **Framework**: Next.js 16 (App Router, Server Actions)
- **UI**: Tailwind CSS 4, Framer Motion
- **State**: Zustand (persisted to localStorage)
- **Drag & Drop**: @dnd-kit/core
- **AI**: Vercel AI SDK v6 via AI Gateway
- **Animations**: Framer Motion, canvas-confetti

## Project Structure

```
src/
├── app/              # Next.js App Router pages & API routes
│   ├── api/ai/       # AI move + judge endpoints (SSE streaming)
│   ├── api/models/   # AI model catalog proxy
│   ├── draw/[id]/    # Starting draw animation
│   ├── game/[id]/    # Main game board
│   └── settings/     # AI model & timeout settings
├── components/       # React components
│   ├── board/        # Board, Cell
│   ├── game/         # AIThinkingOverlay, GameControls, ScorePanel, BlankPicker
│   └── tiles/        # Tile, TileRack
├── hooks/            # Zustand store
└── lib/              # Types, constants, API client, AI gateway, prompts
```

## Environment Variables

See [.env.local.example](.env.local.example) for all available variables.

| Variable | Required | Description |
|---|---|---|
| `AI_GATEWAY_API_KEY` | Yes* | Vercel AI Gateway key |
| `AI_GATEWAY_BASE_URL` | Yes* | `https://ai-gateway.vercel.sh/v1` |
| `NEXT_PUBLIC_API_URL` | Yes | Django backend URL |
| `NEXT_PUBLIC_DEFAULT_MODEL` | No | Default AI model (`openai/gpt-4o-mini`) |

*Or use direct provider keys (`OPENAI_API_KEY`, etc.) for local dev without Gateway.
