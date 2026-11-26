#!/usr/bin/env bash

# Stop if Docker, Compose, or container startup fails.
set -Eeuo pipefail
# Load the canonical monitoring path and common error helper.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

# Require Docker and then confirm the modern Compose plugin is available.
require_command docker
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is unavailable"
[[ -f "${MONITORING_DIR}/docker-compose.yaml" ]] || fail "Missing monitoring Compose file"

# Reconcile monitoring containers with Compose and print their resulting state.
# Before monitoring/ existed, the same containers ran as compose project "dataviz";
# take those down first so the ports are free (Grafana's data volume is kept).
if docker ps -a --filter label=com.docker.compose.project=dataviz --format '{{.Names}}' | grep -q .; then
    log "Removing the old dataviz-* monitoring containers (data kept)"
    docker ps -a --filter label=com.docker.compose.project=dataviz -q | xargs docker rm -f
fi
log "Starting Prometheus and Grafana"
docker compose -f "${MONITORING_DIR}/docker-compose.yaml" up -d
docker compose -f "${MONITORING_DIR}/docker-compose.yaml" ps
