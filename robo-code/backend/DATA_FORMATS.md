# Data Formats

## Telemetry

**POST /api/v1/telemetry**
```json
{
  "id": "sat_1",
  "timestamp": 1234567890,
  "sensors": {
    "temp": 45.2,
    "battery": 89,
    "pressure": 1013.25
  },
  "azimuth": 1.57,
  "elevation": 0.785
}
```

**GET /api/v1/telemetry/latest**
```json
{
  "sat_1": {
    "id": "sat_1",
    "timestamp": 1234567890,
    "sensors": {...},
    "azimuth": 1.57,
    "elevation": 0.785
  },
  "sat_2": {
    ...
  }
}
```

## Commands

**POST /api/v1/commands**
```json
{
  "device_id": "sat_1",
  "action": "thrust",
  "params": {
    "x": 10.5,
    "y": 20.3,
    "z": -5.2
  }
}
```

**Response**
```json
{
  "command_id": "cmd_123",
  "status": "queued",
  "queue_position": 3
}
```

**GET /api/v1/commands/pending**
```json
[
  {
    "device_id": "sat_1",
    "action": "thrust",
    "params": {
      "x": 10.5,
      "y": 20.3,
      "z": -5.2
    },
    "command_id": "cmd_123"
  }
]
```

**POST /api/v1/commands/pending/{command_id}/ack**
```json
{
  "status": "executed",
  "error": null
}
```

## Status

**GET /api/v1/status**
```json
{
  "status": "ok",
  "telemetry_devices": 2,
  "pending_commands": 1,
  "timestamp": "2024-01-15T10:30:45.123456"
}
```
