# Archived custom Telemetry Visualizer

This directory preserves the retired FastAPI telemetry buffer and Chart.js page.
It was archived on 2026-08-24 because DataViz already provides telemetry collection
and visualization through Prometheus and Grafana.

Nothing here is installed, built, linked, or health-checked by the active deployment.
The last systemd definition is retained under `deploy/` for historical reference.

## Archived layout

- `backend/` — FastAPI service, example client, and frozen requirements
- `frontend/dashboard.astro` — former `/telemetry-viz/dashboard` page
- `deploy/telemetry-viz.service` — former systemd unit

The implementation used port 5701 and the former `/api/telemetry/` Apache route.
Those allocations are now free.
