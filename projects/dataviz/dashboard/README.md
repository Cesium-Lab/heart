# DataViz Dashboard

Web dashboard for sending simulated commands and monitoring their execution status.

## Setup

```bash
../.venv/bin/pip install -r ../requirements.txt  # or top-level requirements
../.venv/bin/python app.py
```

Server runs on `http://127.0.0.1:42002`

## How It Works

Built with **NiceGUI** — a Python-based web GUI framework.

### Features

- **Command Form** — Send thrust commands to one of the ten simulated satellites
- **Freeze Control** — Pause telemetry simulation and queued command execution
- **Command Execution Log** — View pending and completed commands
- **Sequence Tracking** — Each command has a sequence number (0-255) for ordering
- **Status Display** — See real-time status updates:
  - `received` — Backend acknowledged receipt (immediate)
  - `done` — Execution completed (after 1 second simulation)

### Data Flow

```
External Command Source → Backend (receives, stores, executes)
                              ↓ (ACKs: received → done)
                    DataViz Dashboard (monitors and displays)
```

### Status Timeline

1. Command sent to backend
2. Backend immediately returns "received" ACK with seq_num
3. Backend simulates 1 second execution asynchronously
4. Backend updates status to "done"
5. GUI polls and displays the progression

## Controls

- **Refresh** — Manually refresh the command log
- **Auto-Refresh** — Set 1-second auto-refresh timer

## Notes

- State and command history are in memory and reset when the backend restarts
- Sequence numbers preserve command order (0-255 cycle)
- Status transitions: received → done
