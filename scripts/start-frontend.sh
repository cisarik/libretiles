#!/usr/bin/env bash
# Start the Next.js frontend for Libre Tiles
# Usage: ./scripts/start-frontend.sh

set -euo pipefail
cd "$(dirname "$0")/../frontend"

echo "=== Libre Tiles — Frontend ==="

# Classify a named env assignment as usable or not. Never print the value.
env_key_is_usable() {
    local env_file="$1"
    local name="$2"
    local raw=""
    local key=""

    if [ ! -f "$env_file" ]; then
        return 1
    fi

    raw="$(grep -E "^[[:space:]]*${name}=" "$env_file" | tail -n 1 || true)"
    if [ -z "$raw" ]; then
        return 1
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
        ""|"your-openrouter-api-key"|"your-nvidia-api-key"|"change-me"|"your-vercel-ai-gateway-api-key")
            return 1
            ;;
        *)
            return 0
            ;;
    esac
}

warn_if_no_ai_credential_usable() {
    local env_file="$1"
    local openrouter_ok=1
    local nvidia_ok=1

    if env_key_is_usable "$env_file" "OPENROUTER_API_KEY"; then
        openrouter_ok=0
    fi
    if env_key_is_usable "$env_file" "NVIDIA_API_KEY"; then
        nvidia_ok=0
    fi

    if [ "$openrouter_ok" -ne 0 ] && [ "$nvidia_ok" -ne 0 ]; then
        echo "warning: neither OPENROUTER_API_KEY nor NVIDIA_API_KEY is usable (missing, empty, or a known placeholder); the UI can boot, but AI turns will fail until at least one server-only key is set" >&2
    fi
}

# Copy env only when absent. Never overwrite an existing developer .env.local.
if [ ! -f .env.local ]; then
    echo "Creating .env.local from .env.local.example..."
    cp .env.local.example .env.local
fi

warn_if_no_ai_credential_usable .env.local

# Install dependencies
echo "Installing Node dependencies..."
npm install --silent

echo ""
echo "Starting Next.js on http://0.0.0.0:3000"
echo "Open the app from your tablet using this machine's LAN IP on port 3000."
echo "Press Ctrl+C to stop."
echo ""

npm run dev:host
