#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/var/www/sydag"
COMPOSE_FILE="compose.sydag.yml"
SERVICE="frontend"
LOCAL_URL="http://127.0.0.1:8188/"
PUBLIC_URL="https://sydag.aboutsharma.com/"

echo "======================================"
echo " SoilSignal Production Deployment"
echo "======================================"
echo

cd "$APP_DIR"

echo "[1/6] Checking repository..."
if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: Working tree has local changes."
    git status --short
    exit 1
fi

echo
echo "[2/6] Pulling latest main..."
git fetch origin main
git checkout main
git pull --ff-only origin main

echo
echo "[3/6] Validating Docker Compose..."
docker compose -f "$COMPOSE_FILE" config >/dev/null

echo
echo "[4/6] Building and deploying SoilSignal..."
docker compose -f "$COMPOSE_FILE" up -d --build "$SERVICE"

echo
echo "[5/6] Waiting for frontend health check..."

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
    docker compose -f "$COMPOSE_FILE" logs --tail=100 "$SERVICE"
    exit 1
fi

echo
echo "[6/6] Verifying public endpoint..."

if curl --fail --silent "$PUBLIC_URL" >/dev/null 2>&1; then
    echo "Public endpoint: OK"
else
    echo "WARNING: Local deployment is healthy, but the public endpoint did not respond."
fi

echo
docker compose -f "$COMPOSE_FILE" ps

echo
echo "======================================"
echo " SoilSignal deployment successful"
echo " $PUBLIC_URL"
echo "======================================"
