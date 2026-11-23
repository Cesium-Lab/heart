#!/usr/bin/env bash

set -Eeuo pipefail

SESSION_NAME="dataviz"
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PROJECT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
    printf 'Missing %s; run ../../scripts/deploy-startup.sh or create the virtualenv first.\n' "${PYTHON}" >&2
    exit 1
fi

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
    printf 'Attaching to existing %s session.\n' "${SESSION_NAME}"
    exec tmux attach-session -t "${SESSION_NAME}"
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose -f "${PROJECT_DIR}/docker-compose.yaml" up -d
else
    printf 'Docker Compose unavailable; skipping Prometheus and Grafana.\n'
fi

tmux new-session -d -s "${SESSION_NAME}" -x 200 -y 50 \
    "cd '${PROJECT_DIR}/backend' && '${PYTHON}' main.py"
tmux split-window -t "${SESSION_NAME}:0" -h \
    "cd '${PROJECT_DIR}/dashboard' && '${PYTHON}' app.py"
tmux select-pane -t "${SESSION_NAME}:0.0" -T "Backend (42000)"
tmux select-pane -t "${SESSION_NAME}:0.1" -T "DataViz Dashboard (42002)"
tmux select-pane -t "${SESSION_NAME}:0.0"

printf '\nDataViz started. Detach with Ctrl+B then D; services remain running.\n'
printf 'DataViz Dashboard: http://127.0.0.1:42002\n'
printf 'Grafana:        http://127.0.0.1:42003\n'
printf 'Prometheus:     http://127.0.0.1:42004\n\n'

exec tmux attach-session -t "${SESSION_NAME}"
