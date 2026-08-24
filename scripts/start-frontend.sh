#!/usr/bin/env bash
# Start the Next.js frontend for Libre Tiles
# Usage: ./scripts/start-frontend.sh

set -euo pipefail
cd "$(dirname "$0")/../frontend"

echo "=== Libre Tiles — Frontend ==="

warn_if_openrouter_key_unusable() {
    local env_file="$1"
    local raw=""
    local key=""

    if [ ! -f "$env_file" ]; then
        echo "warning: OPENROUTER_API_KEY is missing; the UI can boot, but AI turns will fail until you set a key from https://openrouter.ai/keys" >&2
        return 0
    fi

    raw="$(grep -E '^[[:space:]]*OPENROUTER_API_KEY=' "$env_file" | tail -n 1 || true)"
    if [ -z "$raw" ]; then
        echo "warning: OPENROUTER_API_KEY is missing; the UI can boot, but AI turns will fail until you set a key from https://openrouter.ai/keys" >&2
        return 0
    fi

    key="${raw#*=}"
    if [ "${key#\"}" != "$key" ] && [ "${key%\"}" != "$key" ]; then
        key="${key#\"}"
        key="${key%\"}"
    elif [ "${key#\'}" != "$key" ] && [ "${key%\'}" != "$key" ]; then
        key="${key#\'}"
        key="${key%\'}"
    fi
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"

    case "$key" in
        ""|"your-openrouter-api-key"|"change-me"|"your-vercel-ai-gateway-api-key")
            echo "warning: OPENROUTER_API_KEY is missing or a placeholder; the UI can boot, but AI turns will fail until you set a key from https://openrouter.ai/keys" >&2
            ;;
    esac
}

# Copy env only when absent. Never overwrite an existing developer .env.local.
if [ ! -f .env.local ]; then
    echo "Creating .env.local from .env.local.example..."
    cp .env.local.example .env.local
fi

warn_if_openrouter_key_unusable .env.local

# Install dependencies
echo "Installing Node dependencies..."
npm install --silent

echo ""
echo "Starting Next.js on http://0.0.0.0:3000"
echo "Open the app from your tablet using this machine's LAN IP on port 3000."
echo "Press Ctrl+C to stop."
echo ""

npm run dev:host
