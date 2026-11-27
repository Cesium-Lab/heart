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

# Prepare the inbox (Pillow for email thumbnails). Its Gmail app password lives in
# /etc/cesium/inbox.env (see backend/services/inbox/.env.example); without it, digests are
# saved to the day folder instead of emailed.
if [[ -f "${INBOX_DIR}/server.py" ]]; then
    log "Preparing Inbox"
    [[ -x "${INBOX_DIR}/.venv/bin/python" ]] || python3 -m venv "${INBOX_DIR}/.venv"
    "${INBOX_DIR}/.venv/bin/pip" install -r "${INBOX_DIR}/requirements.txt"
    install -d -m 0755 /srv/data/inbox 2>/dev/null || true
fi

# HQ keeps hq.json (contacts) on the internal drive, owner-only; daily backups to /srv/data/backups/hq.
if [[ -f "${REPO_ROOT}/backend/services/hq/server.py" ]]; then
    sudo install -d -m 0700 -o cskin -g cskin /srv/state/hq
fi

# Tasks keeps tasks.json on the internal drive; daily backups go to /srv/data/backups/tasks.
if [[ -f "${REPO_ROOT}/backend/services/tasks/server.py" ]]; then
    sudo install -d -m 0755 -o cskin -g cskin /srv/state/tasks
fi

# hashcheck (weekly file check of /srv/data) keeps its list on the internal drive.
if [[ -f "${REPO_ROOT}/backend/services/hashcheck/hashcheck.py" ]]; then
    sudo install -d -m 0755 -o cskin -g cskin /srv/state/hashcheck
fi

# Prepare the DataViz API and dashboard when the project is present.
if [[ -f "${DATAVIZ_DIR}/backend/main.py" ]]; then
    log "Preparing DataViz"
    [[ -x "${DATAVIZ_DIR}/.venv/bin/python" ]] || python3 -m venv "${DATAVIZ_DIR}/.venv"
    "${DATAVIZ_DIR}/.venv/bin/pip" install -r "${DATAVIZ_DIR}/requirements.txt"
fi

# Copy each available unit definition into systemd.
log "Installing backend service definitions"
for unit in rotation-viz.service setlister.service planes.service inbox.service tasks.service hq.service dataviz-backend.service dataviz-gui.service hashcheck.service hashcheck.timer; do
    if [[ -f "${SYSTEMD_DIR}/${unit}" ]]; then
        sudo install -m 0644 "${SYSTEMD_DIR}/${unit}" "/etc/systemd/system/${unit}"
    fi
done
# Tell systemd to reread newly installed or updated unit files.
sudo systemctl daemon-reload

# Configure installed backend services to start now and at boot.
log "Enabling backend services"
for unit in rotation-viz.service setlister.service planes.service inbox.service tasks.service hq.service dataviz-backend.service dataviz-gui.service; do
    enable_installed_unit "${unit}"
done
# hashcheck runs from its timer only (enabling the service itself would start a full,
# hours-long check right now).
enable_installed_unit hashcheck.timer
