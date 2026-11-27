#!/usr/bin/env bash
# Deploy stage: SilverBullet (docs.cesiumlab.net), the browser editor for /srv/data/docs.

set -Eeuo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

COMPOSE="${REPO_ROOT}/backend/services/silverbullet/docker-compose.yaml"
require_command docker
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is unavailable"
[[ -f "${COMPOSE}" ]] || fail "Missing ${COMPOSE}"

# The login must exist first: without it SilverBullet would start with no password.
sudo test -f /etc/cesium/silverbullet.env ||
    fail "Create /etc/cesium/silverbullet.env first (see backend/services/silverbullet/.env.example)"
sudo grep -q '^SB_USER=..*:..*' /etc/cesium/silverbullet.env ||
    fail "/etc/cesium/silverbullet.env needs SB_USER=username:password"

# Only with the data drive mounted, so nothing is written to the system disk by mistake.
mountpoint -q /srv/data || fail "/srv/data is not mounted"
install -d -m 0755 /srv/data/docs

log "Starting SilverBullet"
docker compose -f "${COMPOSE}" up -d
docker compose -f "${COMPOSE}" ps
