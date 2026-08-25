#!/usr/bin/env bash

# Stop the frontend deployment at the first failed prerequisite or build step.
set -Eeuo pipefail
# Load shared paths and error-reporting helpers.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

# Verify the tools and lockfile needed for a reproducible production build.
require_command npm
require_command sudo
require_command systemctl
[[ -f "${FRONTEND_DIR}/package-lock.json" ]] || fail "Missing frontend/package-lock.json"
[[ -x /usr/bin/npm ]] || fail "frontend-build.service expects npm at /usr/bin/npm"

# Install exactly the dependency versions recorded in package-lock.json.
log "Installing frontend dependencies"
npm --prefix "${FRONTEND_DIR}" ci

# Generate the static site that Apache serves from frontend/dist.
log "Building Astro frontend"
npm --prefix "${FRONTEND_DIR}" run build
[[ -f "${FRONTEND_DIR}/dist/index.html" ]] || fail "Build did not create dist/index.html"

# Install the boot-time oneshot unit after confirming the build succeeds.
log "Installing frontend build service"
sudo install -m 0644 "${SYSTEMD_DIR}/frontend-build.service" /etc/systemd/system/frontend-build.service
sudo systemctl daemon-reload
sudo systemctl enable --now frontend-build.service
