#!/usr/bin/env bash
# deploy-startup.sh: build the site and (re)install/start every service on mr-ray.
# Runs the stages in scripts/deploy/ in order. Uses sudo. Run from anywhere.
#
#   Full deploy/repair (all stages: frontend backends monitoring apache verify):
#       ./scripts/deploy-startup.sh
#
#   Run one stage only (e.g. after changing a unit file or Apache config):
#       ./scripts/deploy/backends.sh      # or frontend.sh, apache.sh, monitoring.sh, verify.sh
#
#   Pick up code changes (deploy does NOT restart services that are already running):
#       sudo systemctl restart <name>
#
#   Something broke? Check, then read the logs:
#       ./scripts/status.sh
#       journalctl -u <name> -n 50 --no-pager

# Stop on errors, unset variables, and failed pipeline commands.
set -Eeuo pipefail

# Resolve this location so the wrapper works from any current directory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Authenticate once, then run each independently usable deployment stage.
# Cache sudo credentials once so individual stages do not repeatedly prompt.
sudo -v
for stage in frontend backends monitoring apache verify; do
    "${SCRIPT_DIR}/deploy/${stage}.sh"
done
