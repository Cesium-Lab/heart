#!/usr/bin/env bash

# Exit on command failures, unset variables, and failed pipeline components.
# These strict settings keep a broken step from producing a partial deployment.
set -Eeuo pipefail

# Resolve every project path from this file's location. The script therefore
# works whether it is launched from the repo root, a home directory, or cron.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${REPO_ROOT}/frontend"
SETLISTER_DIR="${REPO_ROOT}/backend/music/setlister"
SYSTEMD_DIR="${REPO_ROOT}/deploy/systemd"
FRONTEND_UNIT="${SYSTEMD_DIR}/frontend-build.service"

# Print a visible heading before each major deployment stage.
log() {
    printf '\n==> %s\n' "$*"
}

# Stop with a consistent, human-readable error message.
fail() {
    printf '\nERROR: %s\n' "$*" >&2
    exit 1
}

# Check prerequisites before the script starts changing the system.
require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

# Return success when systemd knows about a unit. Some backend services are
# optional, so the script detects what is actually installed on this machine.
unit_exists() {
    [[ "$(systemctl show --property=LoadState --value "$1" 2>/dev/null)" != "not-found" ]]
}

# Enable an installed unit at boot and start it now. Missing optional units are
# reported and skipped so one undeployed backend does not block the frontend.
enable_installed_unit() {
    local unit="$1"

    if unit_exists "${unit}"; then
        log "Enabling and starting ${unit}"
        sudo systemctl enable --now "${unit}"
    else
        printf 'Skipping %s (not installed)\n' "${unit}"
    fi
}

# Confirm an installed unit stayed active. On failure, print its full systemd
# status before exiting so the service's error is immediately visible.
check_unit() {
    local unit="$1"

    if unit_exists "${unit}"; then
        systemctl is-active --quiet "${unit}" || {
            systemctl status "${unit}" --no-pager --full || true
            fail "${unit} is not active"
        }
        printf '[OK] %s is active\n' "${unit}"
    fi
}

# Retry HTTP checks because a service may become "active" just before its socket
# is ready. Ten attempts also tolerate a modestly slow machine during startup.
check_url() {
    local name="$1"
    local url="$2"
    local attempt

    for attempt in {1..10}; do
        if curl --fail --silent --show-error --max-time 5 --output /dev/null "${url}"; then
            printf '[OK] %s responded at %s\n' "${name}" "${url}"
            return 0
        fi
        sleep 1
    done

    fail "${name} did not respond successfully at ${url}"
}

# Verify all commands used later are available before requesting sudo access.
require_command npm
require_command python3
require_command curl
require_command systemctl
require_command sudo
require_command apache2ctl

# Check repo inputs. The absolute npm path matters because systemd does not use
# the interactive shell's PATH; frontend-build.service calls /usr/bin/npm.
[[ -f "${FRONTEND_DIR}/package-lock.json" ]] || fail "Missing ${FRONTEND_DIR}/package-lock.json"
[[ -f "${FRONTEND_UNIT}" ]] || fail "Missing ${FRONTEND_UNIT}"
[[ -x /usr/bin/npm ]] || fail "The systemd unit expects npm at /usr/bin/npm"

# Authenticate once so later privileged steps do not repeatedly ask for a
# password in the middle of the deployment.
log "Refreshing sudo credentials"
sudo -v


# Install exactly the dependency versions recorded in package-lock.json. npm ci
# is deterministic and replaces node_modules, making it appropriate for deploys.
log "Installing frontend dependencies"
npm --prefix "${FRONTEND_DIR}" ci

# Compile Astro into static files in frontend/dist, then verify that the main
# page actually exists before pointing the web server at the build.
log "Building Astro frontend"
npm --prefix "${FRONTEND_DIR}" run build
[[ -f "${FRONTEND_DIR}/dist/index.html" ]] || fail "Build completed without creating dist/index.html"

# Create Setlister's isolated Python environment when its backend is present,
# then synchronize its dependencies before systemd attempts to start the API.
if [[ -f "${SETLISTER_DIR}/server.py" ]]; then
    log "Installing Setlister backend dependencies"
    if [[ ! -x "${SETLISTER_DIR}/.venv/bin/python" ]]; then
        python3 -m venv "${SETLISTER_DIR}/.venv"
    fi
    "${SETLISTER_DIR}/.venv/bin/pip" install -r "${SETLISTER_DIR}/requirements.txt"
fi

# Install the version-controlled units so /etc cannot retain stale commands
# after services move within the repository. The frontend unit runs at boot;
# backend units keep the API processes alive and restart them after failures.
log "Installing systemd service definitions"
for unit in frontend-build.service rotation-viz.service telemetry-viz.service setlister.service; do
    if [[ -f "${SYSTEMD_DIR}/${unit}" ]]; then
        sudo install -m 0644 "${SYSTEMD_DIR}/${unit}" "/etc/systemd/system/${unit}"
    fi
done

# Make systemd reread the newly installed definitions, then enable the frontend
# build for later boots and run it now. This also tests systemd's restricted
# execution environment rather than only the current interactive shell.
sudo systemctl daemon-reload
sudo systemctl enable --now frontend-build.service

# Do not touch a running Apache instance if its configuration has a syntax error.
# Its DocumentRoot should be /home/cskin/Cesium/heart/frontend/dist.
log "Validating Apache configuration"
sudo apache2ctl configtest

# Apache serves the site. The other units are optional APIs/tunnel components;
# each is enabled and started only if its unit is installed on this host.
enable_installed_unit apache2.service
enable_installed_unit rotation-viz.service
enable_installed_unit telemetry-viz.service
enable_installed_unit setlister.service
enable_installed_unit cloudflared.service

# Reload Apache without stopping the process or dropping active connections.
log "Reloading Apache"
sudo systemctl reload apache2.service

# Starting a process does not prove it remained healthy, so check every installed
# unit after all startup operations finish.
log "Checking services"
check_unit apache2.service
check_unit frontend-build.service
check_unit rotation-viz.service
check_unit telemetry-viz.service
check_unit setlister.service
check_unit cloudflared.service

# Test real HTTP responses. This verifies that Apache can read dist and that the
# installed APIs are listening, not merely that their processes exist.
log "Checking HTTP endpoints"
check_url "Frontend" "http://127.0.0.1/"

# Hit backend ports directly so an Apache proxy error cannot hide the real cause.
if unit_exists rotation-viz.service; then
    check_url "Rotation API" "http://127.0.0.1:5001/api/rotation/health"
fi

if unit_exists telemetry-viz.service; then
    check_url "Telemetry API" "http://127.0.0.1:5701/health"
fi

if unit_exists setlister.service; then
    check_url "Setlister API" "http://127.0.0.1:5702/api/setlister/health"
fi

# This line is reached only if every required build, unit, and HTTP check passed.
log "Deployment and startup checks passed"
