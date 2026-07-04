# Telemetry Dashboard

Visualization and monitoring server for telemetry data from spacecraft.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Server runs on `http://localhost:42003`

## How It Works

- Polls backend for telemetry data
- Displays graphs, statistics, and real-time updates
- Shows health of all connected devices
- Calculates aggregate statistics (avg temperature, battery, etc.)

## API Endpoints

Visit `http://localhost:42003/docs` for interactive Swagger UI.

- `GET /api/v1/telemetry/all` — Get all device telemetry
- `GET /api/v1/telemetry/{device_id}` — Get specific device telemetry
- `GET /api/v1/stats` — Get aggregate statistics
- `GET /api/v1/health` — Health check of system

## Data Available

From each telemetry reading:
- Temperature
- Battery level
- Pressure
- Azimuth / Elevation angles
- Timestamp

## Notes

- Starts with 10 example satellites from backend
- Can be extended with real-time WebSocket updates
- Statistics auto-calculated from current telemetry
