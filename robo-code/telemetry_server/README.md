# Telemetry Dashboard

Real-time visualization of satellite telemetry data with Grafana.

Server runs on `http://localhost:42003`

## How It Works

**Polling:** Telemetry server polls backend every **second** for latest telemetry data.
<!-- 
## Layout

**Left Column (1/5 width) - Statistics:**
- 📊 Total packets received
- 🌡️ Average temperature
- 🔋 Average battery level
- 🛰️ Active satellites count
- ⏱️ Last update timestamp

**Right Column (4/5 width) - Live Charts:**
- Temperature over time (all satellites)
- Battery over time (all satellites)
- Pressure over time (all satellites)
- Azimuth over time (all satellites)
- Elevation over time (all satellites)

Each chart shows all satellites with color-coded lines.

## Features

- **Real-time updates** — 0.1 second refresh rate
- **Historical data** — Keeps last 1000 points per satellite per sensor
- **Interactive plots** — Hover for details, click legend to toggle satellites
- **Dark mode** — By default
- **Live stats** — Auto-calculating averages and counts

## Data Flow

```
Backend (42000) 
    ↓ (polls every 0.1s)
GET /api/v1/telemetry/latest
    ↓
Telemetry Server (42003)
    ↓
Update plots + stats
    ↓
Display to user
``` -->
