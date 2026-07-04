#!/bin/bash

####################################################################################################
#               ROBO-CODE SERVER LAUNCHER
####################################################################################################
# Starts all 3 servers in a tmux session with 3 panes

SESSION_NAME="robo-code"
PROJECT_DIR="$(pwd)"

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

# Pane 2: Telemetry Dashboard (bottom)
tmux send-keys -t $SESSION_NAME:0.2 "cd '$PROJECT_DIR/telemetry_server' && python app.py" Enter

# Set pane titles
tmux select-pane -t $SESSION_NAME:0.0 -T "Backend (42000)"
tmux select-pane -t $SESSION_NAME:0.1 -T "Mission Control (42002)"
tmux select-pane -t $SESSION_NAME:0.2 -T "Telemetry (42003)"

# Select first pane
tmux select-pane -t $SESSION_NAME:0.0

# Show status
echo ""
echo "======================================"
echo "  Robo-Code Servers Started"
echo "======================================"
echo ""
echo "  Mission Control: http://localhost:42002/docs"
echo "  Telemetry:      http://localhost:42003/docs"
echo ""
echo "  Tmux Controls:"
echo "    Ctrl+B → arrow keys = switch panes"
echo "    Ctrl+B → D = detach (servers keep running)"
echo "    Ctrl+B → X = kill pane"
echo ""

# Attach to session
tmux attach-session -t $SESSION_NAME
