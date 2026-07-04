# Quick Start

## Setup

```bash
cd heart/robo-code
pip install -r requirements.txt
```

## Run All Servers at Once

```bash
./start_servers.sh
```

This opens a tmux session with 3 panes:
- **Left**: Backend (port 42000)
- **Right**: Mission Control GUI (port 42002)
- **Bottom**: Telemetry Dashboard (port 42003)

## Tmux Controls

| Command | Action |
|---------|--------|
| `Ctrl+B` then `←/→/↑/↓` | Move between panes |
| `Ctrl+B` then `D` | Detach from session (servers keep running) |
| `Ctrl+B` then `X` | Kill pane |
| `Ctrl+B` then `[` | Scroll up in pane (use arrows, `Q` to exit) |

## Stop All Servers

```bash
tmux kill-session -t robo-code
```

Or from inside tmux:
```bash
Ctrl+B :kill-session
```

## Access the Services

- **Mission Control GUI** (send commands): `http://localhost:42002`
- **Telemetry Dashboard** (view data): `http://localhost:42003/docs`

## Frozen State

The backend starts with telemetry frozen—10 example satellites loaded but not updating. Commands are queued but nothing moves until a spacecraft simulator is added.

## Manual Setup (if tmux issues)

Run in 3 separate terminals:

```bash
# Terminal 1
cd backend && python main.py

# Terminal 2
cd mission_control_gui && python app.py

# Terminal 3
cd telemetry_server && python app.py
```
