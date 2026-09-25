#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/var/www/sydag"
COMPOSE_FILE="compose.sydag.yml"
SERVICES=(frontend backend)
LOCAL_URL="http://127.0.0.1:8188/"
LOCAL_API="http://127.0.0.1:8189/api/health"
PUBLIC_URL="https://sydag.aboutsharma.com/"
PUBLIC_API="https://sydag.aboutsharma.com/api/health"

echo "======================================"
echo " SoilSignal Production Deployment"
echo "======================================"
echo

cd "$APP_DIR"

echo "[1/7] Checking repository..."
if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: Working tree has local changes."
    git status --short
    exit 1
fi

echo
echo "[2/7] Pulling latest main..."
git fetch origin main
git checkout main
git pull --ff-only origin main

echo
echo "[3/7] Validating Docker Compose..."
docker compose -f "$COMPOSE_FILE" config >/dev/null

echo
echo "[4/7] Building and deploying SoilSignal (frontend + backend)..."
# Both halves ship together: the frontend reads everything from the backend's /api,
# and new models (backend/artifacts) only load when the backend restarts.
docker compose -f "$COMPOSE_FILE" up -d --build "${SERVICES[@]}"

echo
echo "[5/7] Waiting for frontend health check..."

SUCCESS=false

for i in {1..30}; do
    if curl --fail --silent "$LOCAL_URL" >/dev/null 2>&1; then
        SUCCESS=true
        break
    fi

    echo "Waiting for frontend... attempt $i/30"
    sleep 2
done

if [[ "$SUCCESS" != "true" ]]; then
    echo
    echo "ERROR: SoilSignal failed its local health check."
    docker compose -f "$COMPOSE_FILE" ps
    docker compose -f "$COMPOSE_FILE" logs --tail=100 frontend
    exit 1
fi

echo
echo "[6/7] Waiting for the API to serve model forecasts..."

API_OK=false
HEALTH=""

for i in {1..30}; do
    HEALTH="$(curl --fail --silent "$LOCAL_API" 2>/dev/null || true)"
    # Model-backed forecasts with at least one model loaded; never mock or unavailable.
    if [[ "$HEALTH" == *'"dataSource":"model"'* && "$HEALTH" != *'"modelsLoaded":0'* ]]; then
        API_OK=true
        break
    fi

    echo "Waiting for backend... attempt $i/30"
    sleep 2
done

if [[ "$API_OK" != "true" ]]; then
    echo
    echo "ERROR: The API is not serving model forecasts."
    echo "Health: ${HEALTH:-no response}"
    docker compose -f "$COMPOSE_FILE" logs --tail=100 backend
    exit 1
fi

echo "API: $HEALTH"

echo
echo "[7/7] Verifying public endpoints..."

if curl --fail --silent "$PUBLIC_URL" >/dev/null 2>&1; then
    echo "Public endpoint: OK"
else
    echo "WARNING: Local deployment is healthy, but the public endpoint did not respond."
fi

if curl --fail --silent "$PUBLIC_API" >/dev/null 2>&1; then
    echo "Public API: OK"
else
    echo "WARNING: The API is healthy locally, but $PUBLIC_API did not respond."
fi

echo
docker compose -f "$COMPOSE_FILE" ps

echo
echo "======================================"
echo " SoilSignal deployment successful"
echo " $PUBLIC_URL"
echo "======================================"
