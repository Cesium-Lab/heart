#!/usr/bin/env bash

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
