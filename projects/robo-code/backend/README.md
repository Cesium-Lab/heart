# Mission Control Backend

Bare-bones FastAPI backend for robo-code telemetry and command coordination.

## Setup

```bash
pip install -r requirements.txt
python main.py
```

Server runs on `http://localhost:42000`

## API Documentation

Visit `http://localhost:42000/docs` for interactive Swagger UI

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
