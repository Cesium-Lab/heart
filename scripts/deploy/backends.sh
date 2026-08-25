#!/usr/bin/env bash

# Treat command failures and missing variables as deployment failures.
set -Eeuo pipefail
# Load canonical repository paths and systemd helper functions.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

# Confirm required host tools exist before changing anything.
require_command python3
require_command sudo
require_command systemctl

# Retire the archived custom telemetry service on hosts upgraded from older checkouts.
if unit_exists telemetry-viz.service; then
    log "Retiring archived telemetry-viz service"
    sudo systemctl disable --now telemetry-viz.service
    sudo rm -f /etc/systemd/system/telemetry-viz.service
fi

# Prepare Setlister only when that optional service exists in this checkout.
if [[ -f "${SETLISTER_DIR}/server.py" ]]; then
    log "Preparing Setlister"
    # Seed the protected production environment once; later deploys preserve it.
    if ! sudo test -f /etc/cesium/music.env; then
        [[ -f "${SETLISTER_DIR}/.env" ]] || fail "Create ${SETLISTER_DIR}/.env first"
        sudo install -d -m 0750 -o root -g cskin /etc/cesium
        sudo install -m 0640 -o root -g cskin "${SETLISTER_DIR}/.env" /etc/cesium/music.env
    fi
    [[ -x "${SETLISTER_DIR}/.venv/bin/python" ]] || python3 -m venv "${SETLISTER_DIR}/.venv"
    "${SETLISTER_DIR}/.venv/bin/pip" install -r "${SETLISTER_DIR}/requirements.txt"
fi

# Prepare the DataViz API and dashboard when the project is present.
if [[ -f "${DATAVIZ_DIR}/backend/main.py" ]]; then
    log "Preparing DataViz"
    [[ -x "${DATAVIZ_DIR}/.venv/bin/python" ]] || python3 -m venv "${DATAVIZ_DIR}/.venv"
    "${DATAVIZ_DIR}/.venv/bin/pip" install -r "${DATAVIZ_DIR}/requirements.txt"
fi

# Copy each available unit definition into systemd.
log "Installing backend service definitions"
for unit in rotation-viz.service setlister.service dataviz-backend.service dataviz-gui.service; do
    if [[ -f "${SYSTEMD_DIR}/${unit}" ]]; then
        sudo install -m 0644 "${SYSTEMD_DIR}/${unit}" "/etc/systemd/system/${unit}"
    fi
done
# Tell systemd to reread newly installed or updated unit files.
sudo systemctl daemon-reload

# Configure installed backend services to start now and at boot.
log "Enabling backend services"
for unit in rotation-viz.service setlister.service dataviz-backend.service dataviz-gui.service; do
    enable_installed_unit "${unit}"
done
