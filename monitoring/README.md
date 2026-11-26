# Monitoring

Prometheus + Grafana for mr-ray, in docker (`docker-compose.yaml`, started by
`scripts/deploy/monitoring.sh`). Both bind to loopback; reach them over SSH.

| Port  | What       | Config                                                  |
| ----- | ---------- | ------------------------------------------------------- |
| 42003 | Grafana    | `grafana/provisioning/` (datasources, dashboards)       |
| 42004 | Prometheus | `prometheus/prometheus.yaml` (what it scrapes, how often) |

What it watches today: the DataViz backend's `/metrics` (every second), charted in the
"Satellite telemetry" dashboard. A "Planes (to do)" placeholder dashboard is here too. New
things to watch (planes stats, drive health, room sensors; see `architecture/ideas.md`) go in
`prometheus.yaml` plus a dashboard JSON under `grafana/provisioning/dashboards/`.

Grafana's data lives in the docker volume `dataviz_grafana_data`.

```bash
./scripts/deploy/monitoring.sh                                # start or update (needs docker)
docker compose -f monitoring/docker-compose.yaml ps            # what's running
docker compose -f monitoring/docker-compose.yaml restart grafana
```
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
