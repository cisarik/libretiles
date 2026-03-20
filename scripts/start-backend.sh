#!/usr/bin/env bash
# Start the Django backend for Libre Tiles
# Usage: ./scripts/start-backend.sh

set -euo pipefail
cd "$(dirname "$0")/../backend"

echo "=== Libre Tiles — Backend ==="

# Ensure .env exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Install dependencies
echo "Installing Python dependencies..."
poetry install --quiet

# Run migrations
echo "Running migrations..."
poetry run python manage.py migrate --run-syncdb

# Seed AI models (skip if already exist)
echo "Seeding AI models..."
poetry run python manage.py seed_models

echo ""
echo "Starting Django on http://localhost:8000"
echo "Admin: http://localhost:8000/admin/"
echo "Press Ctrl+C to stop."
echo ""

poetry run python manage.py runserver 0.0.0.0:8000
