# DataViz Backend

Bare-bones FastAPI backend for dataviz telemetry and command coordination.

## Setup

```bash
../.venv/bin/pip install -r ../requirements.txt
../.venv/bin/python main.py
```

Server runs on `http://127.0.0.1:42000`

## API Documentation

Visit `http://127.0.0.1:42000/docs` for interactive Swagger UI

## Key Endpoints

**Status**
```
GET /api/v1/status
```

**Telemetry**
```
POST /api/v1/telemetry
GET /api/v1/telemetry/latest
GET /api/v1/telemetry/latest?id=sat_1
```

**Commands**
```
POST /api/v1/commands
GET /api/v1/commands/pending
POST /api/v1/commands/pending/{command_id}/ack
```

**WebSocket**
```
WS /api/v1/ws/telemetry
```

## Notes

- All state is in-memory (no database)
- Stateless design—each instance is independent
- For POC only
