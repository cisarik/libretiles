#!/usr/bin/env bash
# Start the Next.js frontend for Libre Tiles
# Usage: ./scripts/start-frontend.sh

set -euo pipefail
cd "$(dirname "$0")/../frontend"

echo "=== Libre Tiles — Frontend ==="

# Ensure .env.local exists
if [ ! -f .env.local ]; then
    echo "Creating .env.local from .env.local.example..."
    cp .env.local.example .env.local
    echo ""
    echo "  !! Edit frontend/.env.local and set your AI_GATEWAY_API_KEY !!"
    echo "  !! Get it at https://vercel.com/ai-gateway                  !!"
    echo ""
fi

# Install dependencies
echo "Installing Node dependencies..."
npm install --silent

echo ""
echo "Starting Next.js on http://0.0.0.0:3000"
echo "Open the app from your tablet using this machine's LAN IP on port 3000."
echo "Press Ctrl+C to stop."
echo ""

npm run dev:host
