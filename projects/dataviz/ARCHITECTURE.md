# DataViz Architecture

Three-server POC for spacecraft command and telemetry management.

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         DataViz Dashboard                  │
│                    (User sends commands)                     │
│                       Port 42002                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Commands
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend Store                             │
│            (Central hub - stores everything)                 │
│                       Port 42000                             │
│  • Telemetry data (10 examples loaded)                       │
│  • Command queue                                             │
│  • WebSocket for real-time updates                           │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Telemetry Data
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Telemetry Dashboard                         │
│               (Graphs, stats, monitoring)                    │
│                       Port 42003                             │
└─────────────────────────────────────────────────────────────┘
```

## Servers

### Backend (Port 42000)
**Dumb central store** — just holds data, no active logic

- Loads 10 example satellites from `backend/examples/telemetry10.json`
- Stores telemetry data
- Queues commands (when "freeze" command sent, nothing moves—just stored)
- Provides GET/POST endpoints for telemetry and commands
- WebSocket endpoint for real-time streaming

### DataViz Dashboard (Port 42002)
**User-facing command interface**

- User sends commands via API
- Views pending commands
- Acknowledges command execution
- Proxies all requests to backend

### Telemetry Dashboard (Port 42003)
**Visualization and monitoring**

- Displays all telemetry data
- Shows graphs and statistics
- Calculates health metrics (avg temp, battery, etc.)
- Polls backend for real-time updates
- Health check endpoint

## Ports

| Port  | Service                          |
|-------|----------------------------------|
| 42000 | Backend Store                    |
| 42001 | (Reserved for telemetry stream)  |
| 42002 | DataViz Dashboard              |
| 42003 | Telemetry Dashboard              |

## Data Flow

**User Commanding:**
```
User → DataViz Dashboard → Backend (stores) → Done (until spacecraft integrated)
```

**Telemetry Monitoring:**
```
Backend (10 examples) → Telemetry Dashboard (displays) → User
```

## Future Extensions

1. **Spacecraft Simulator** — Simulates device behavior, receives commands, generates telemetry
2. **Real Spacecraft** — Replace simulator with actual hardware
3. **Frontend Web UI** — Build web interfaces for DataViz Dashboard and Telemetry Dashboard
4. **Database** — Replace in-memory store with persistent storage
5. **Authentication** — Add user auth and command validation

## Quick Start

```bash
# Terminal 1: Backend
cd backend
pip install -r requirements.txt
../.venv/bin/python main.py

# Terminal 2: DataViz Dashboard
cd dashboard
pip install -r requirements.txt
../.venv/bin/python app.py

# Terminal 3: Telemetry Dashboard
cd telemetry_server
pip install -r requirements.txt
../.venv/bin/python app.py
```

Then visit:
- DataViz Dashboard: `http://127.0.0.1:42002/docs` — Send commands
- Telemetry: `http://127.0.0.1:42003/docs` — View data
