# Mission Control GUI

Web dashboard for monitoring command execution status and history from the backend.

## Setup

```bash
pip install -r requirements.txt  # or top-level requirements
python app.py
```

Server runs on `http://localhost:42002`

## How It Works

Built with **NiceGUI** — a Python-based web GUI framework.

### Features
- **Command Execution Log** — View all commands with their execution status
- **Sequence Tracking** — Each command has a sequence number (0-255) for ordering
- **Status Display** — See real-time status updates:
  - `received` — Backend acknowledged receipt (immediate)
  - `done` — Execution completed (after 1 second simulation)

### Data Flow

```
External Command Source → Backend (receives, stores, executes)
                              ↓ (ACKs: received → done)
                    Mission Control GUI (monitors and displays)
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

- GUI is view-only (no sending commands)
- All commands come from external sources (not shown)
- Sequence numbers preserve command order (0-255 cycle)
- Status transitions: received → done
