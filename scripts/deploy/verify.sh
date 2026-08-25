#!/usr/bin/env bash

# Make any failed health check fail the entire verification stage.
set -Eeuo pipefail
# Load reusable systemd and HTTP health-check helpers.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

# Verification needs read-only systemd inspection and HTTP requests.
require_command curl
require_command systemctl

# Check every installed unit while ignoring optional units not deployed here.
log "Checking installed services"
for unit in apache2.service frontend-build.service rotation-viz.service telemetry-viz.service setlister.service dataviz-backend.service dataviz-gui.service cloudflared.service; do
    check_unit "${unit}"
done

# Probe the frontend and each applicable locally bound application endpoint.
log "Checking HTTP endpoints"
check_url "Frontend" "http://127.0.0.1/"
unit_exists rotation-viz.service && check_url "Rotation API" "http://127.0.0.1:5001/api/rotation/health"
unit_exists telemetry-viz.service && check_url "Telemetry API" "http://127.0.0.1:5701/health"
unit_exists setlister.service && check_url "Setlister API" "http://127.0.0.1:5702/api/setlister/health"
unit_exists dataviz-backend.service && check_url "DataViz API" "http://127.0.0.1:42000/api/v1/health"
unit_exists dataviz-gui.service && check_url "DataViz Dashboard" "http://127.0.0.1:42002/"

# Monitoring is optional, so probe it only when Docker Compose is installed.
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    check_url "Grafana" "http://127.0.0.1:42003/login"
    check_url "Prometheus" "http://127.0.0.1:42004/-/healthy"
fi

# Reaching this point means every applicable service and endpoint passed.
log "All deployment checks passed"
