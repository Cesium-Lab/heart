#!/usr/bin/env bash

# Stop if Docker, Compose, or container startup fails.
set -Eeuo pipefail
# Load the canonical DataViz project path and common error helper.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

# Require Docker and then confirm the modern Compose plugin is available.
require_command docker
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is unavailable"
[[ -f "${DATAVIZ_DIR}/docker-compose.yaml" ]] || fail "Missing DataViz Compose file"

# Reconcile monitoring containers with Compose and print their resulting state.
log "Starting DataViz Prometheus and Grafana"
docker compose -f "${DATAVIZ_DIR}/docker-compose.yaml" up -d
docker compose -f "${DATAVIZ_DIR}/docker-compose.yaml" ps
