# Libre Tiles — Frontend

Next.js 16 + React 19 + TypeScript frontend for Libre Tiles.

> For full project documentation see the root [README.md](../README.md).

## Quick Start

```bash
[ -f .env.local ] || cp .env.local.example .env.local
# Edit .env.local — set OPENROUTER_API_KEY (https://openrouter.ai/keys)
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The UI still boots if the key is missing or a placeholder; AI turns fail until a real key is set.

For LAN testing, start the frontend with `npm run dev:host` and open
`http://<your-machine-ip>:3000` from the tablet or phone. Browser-side API
calls will reuse that hostname for the Django backend when
`NEXT_PUBLIC_API_URL` still points at `localhost`.
Next.js dev assets are allowed for the machine's current LAN IPv4 addresses by
default. If you need an extra hostname, set `NEXT_DEV_ALLOWED_ORIGINS`.

AI-only local play needs the Django backend in a second terminal. Redis is not
required unless you are testing human-vs-human websockets.

## Tech Stack

- **Framework**: Next.js 16 (App Router, Server Actions)
- **UI**: Tailwind CSS 4, Framer Motion
- **State**: Zustand (persisted to localStorage)
- **Drag & Drop**: @dnd-kit/core
- **AI**: Vercel AI SDK v6 via OpenRouter (OpenAI-compatible adapter)
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
└── lib/              # Types, constants, API client, OpenRouter, free-rivals, prompts
```

## Environment Variables

See [.env.local.example](.env.local.example) for all available variables.

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes* | Server-only OpenRouter key from https://openrouter.ai/keys |
| `NEXT_PUBLIC_API_URL` | Yes | Django backend URL for browser-side requests |
| `BACKEND_URL` | Yes | Django backend URL for Next.js server-side routes |
| `NEXT_DEV_ALLOWED_ORIGINS` | No | Extra hostnames/IPs allowed to load Next.js dev assets |
| `NEXT_PUBLIC_DEFAULT_MODEL` | No | Optional move/judge fallback (`google/gemma-4-31b-it:free`). Store default is `DEFAULT_FREE_MODEL_ID`. |

*The UI boots without a key; AI turns fail until a real key is set. The OpenRouter base URL is hardcoded in `src/lib/openrouter.ts`. Do not add a base-URL env var. Transitive `@ai-sdk/gateway` in the lockfile is unused.
