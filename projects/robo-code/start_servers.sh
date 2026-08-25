#!/bin/bash

####################################################################################################
#               ROBO-CODE SERVER LAUNCHER
####################################################################################################
# Starts all servers (backend, mission control, Prometheus + Grafana) in a tmux session

SESSION_NAME="robo-code"
PROJECT_DIR="$(pwd)"

# Cleanup trap: stop docker-compose and kill tmux session when script exits
cleanup() {
  echo ""
  echo "Stopping docker-compose containers..."
  cd "$PROJECT_DIR" && docker-compose down 2>/dev/null
  echo "Killing tmux session..."
  tmux kill-session -t $SESSION_NAME 2>/dev/null
}
trap cleanup EXIT

# Kill existing session if it exists
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Create new session with first pane
tmux new-session -d -s $SESSION_NAME -x 200 -y 50

# Split into 3 panes
tmux split-window -t $SESSION_NAME -h
tmux split-window -t $SESSION_NAME:0.1 -v

# Pane 0: Backend (top left)
tmux send-keys -t $SESSION_NAME:0.0 "cd '$PROJECT_DIR/backend' && python main.py" Enter

# Pane 1: Mission Control GUI (top right)
tmux send-keys -t $SESSION_NAME:0.1 "cd '$PROJECT_DIR/mission_control_gui' && python app.py" Enter

# Pane 2: Prometheus + Grafana (bottom)
tmux send-keys -t $SESSION_NAME:0.2 "cd '$PROJECT_DIR' && docker-compose up" Enter

# Set pane titles
tmux select-pane -t $SESSION_NAME:0.0 -T "Backend (42000)"
tmux select-pane -t $SESSION_NAME:0.1 -T "Mission Control (42002)"
tmux select-pane -t $SESSION_NAME:0.2 -T "Grafana (42003) + Prometheus (42004)"

# Select first pane
tmux select-pane -t $SESSION_NAME:0.0

# Open browser tabs in background (wait for services to start first)
(
  sleep 5
  open "http://localhost:42002" 2>/dev/null
  sleep 1
  open "http://localhost:42003" 2>/dev/null
  sleep 1
  open "http://localhost:42004" 2>/dev/null
) &

# Show status
echo ""
echo "======================================"
echo "  Robo-Code Servers Started"
echo "======================================"
echo ""
echo "  Mission Control: http://localhost:42002"
echo "  Grafana:        http://localhost:42003"
echo "  Prometheus:     http://localhost:42004"
echo ""
echo "  Tmux Controls:"
echo "    Ctrl+B → arrow keys = switch panes"
echo "    Ctrl+B → D = detach (servers keep running)"
echo "    Ctrl+B → X = kill pane"
echo ""

# Attach to session
tmux attach-session -t $SESSION_NAME
