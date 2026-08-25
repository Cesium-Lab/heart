# Telemetry Viz

This FastAPI service accepts sensor telemetry, buffers the latest 100 points per sensor in memory, and serves a live dashboard.

## Runtime and API

- Application: `app.py`
- Port: `5701`
- Dashboard: `GET /`
- API docs: `GET /docs`
- Ingest: `POST /telemetry`
- Buffered data: `GET /data`
- Health: `GET /health`
- Unit: `deploy/systemd/telemetry-viz.service`

Single readings and batches use objects like:

```json
{"timestamp": 12.5, "sensor_name": "altitude_m", "value": 1024.3}
```

## One-time setup

```bash
python3 -m venv backend/services/telemetry-viz/.venv
backend/services/telemetry-viz/.venv/bin/pip install -r backend/services/telemetry-viz/requirements.txt
```

Do not use global `pip3 --break-system-packages` installs.

## Local run

```bash
cd backend/services/telemetry-viz
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 5701
```

Then check `curl --fail http://127.0.0.1:5701/health`.

## Deploy and verify

```bash
./scripts/deploy-startup.sh
```

Manual alternative:

```bash
sudo install -m 0644 deploy/systemd/telemetry-viz.service /etc/systemd/system/telemetry-viz.service
sudo systemctl daemon-reload
sudo systemctl enable --now telemetry-viz.service
systemctl status telemetry-viz.service --no-pager
curl --fail http://127.0.0.1:5701/health
```

The unit runs `.venv/bin/python -m uvicorn` instead of `.venv/bin/uvicorn`. Virtualenv launchers contain absolute shebang paths and can fail after a repository move; the module form remains tied to the current virtualenv Python.

Keep port 5701 private unless intentional LAN ingestion is required. Prefer Apache or the configured tunnel for public access.
