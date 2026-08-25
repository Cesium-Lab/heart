#!/usr/bin/env bash

# This library is sourced by deployment stages; it is not run by itself.
# Shared paths and small helpers for the independently runnable deploy stages.
# Resolve every path from this file so callers can run from any directory.
DEPLOY_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${DEPLOY_SCRIPT_DIR}/../.." && pwd)"
FRONTEND_DIR="${REPO_ROOT}/frontend"
SETLISTER_DIR="${REPO_ROOT}/backend/music/setlister"
DATAVIZ_DIR="${REPO_ROOT}/projects/dataviz"
SYSTEMD_DIR="${REPO_ROOT}/deploy/systemd"
APACHE_DEPLOY_DIR="${REPO_ROOT}/deploy/apache"

log() {
    # Print a consistent, easy-to-scan stage heading.
    printf '\n==> %s\n' "$*"
}

fail() {
    # Report a fatal error on stderr and stop the current stage.
    printf '\nERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    # Fail early when a required executable is missing.
    command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

unit_exists() {
    # Distinguish an absent optional unit from an installed but inactive unit.
    [[ "$(systemctl show --property=LoadState --value "$1" 2>/dev/null)" != "not-found" ]]
}

enable_installed_unit() {
    # Enable and start an installed unit while permitting partial checkouts.
    local unit="$1"
    if unit_exists "${unit}"; then
        sudo systemctl enable --now "${unit}"
    else
        printf 'Skipping %s (not installed)\n' "${unit}"
    fi
}

check_unit() {
    # Show systemd diagnostics before failing an installed unit health check.
    local unit="$1"
    if unit_exists "${unit}"; then
        systemctl is-active --quiet "${unit}" || {
            systemctl status "${unit}" --no-pager --full || true
            fail "${unit} is not active"
        }
        printf '[OK] %s is active\n' "${unit}"
    fi
}

check_url() {
    # Retry briefly because freshly started applications may need to initialize.
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
