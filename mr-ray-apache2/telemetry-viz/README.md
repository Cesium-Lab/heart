# Telemetry Viz

FastAPI server that accepts sensor telemetry over POST, buffers the last 100 points per sensor in memory, and serves a live Chart.js dashboard.

## Files

- `app.py` — FastAPI backend (port 5701)
- `dashboard.html` — browser dashboard at `/`
- `example_client.py` — synthetic data pusher for testing
- `requirements.txt` — Python deps

## Quick start

```bash
cd mr-ray-apache2/telemetry-viz
pip3 install -r requirements.txt --break-system-packages
python3 app.py
```

Or use a venv:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Open `http://localhost:5701/` for the dashboard. API docs at `http://localhost:5701/docs`.

## API

### POST /telemetry

Single point:

```json
{"timestamp": 12.5, "sensor_name": "altitude_m", "value": 1024.3}
```

Batch (one timestep, multiple sensors):

```json
[
  {"timestamp": 12.5, "sensor_name": "altitude_m", "value": 1024.3},
  {"timestamp": 12.5, "sensor_name": "velocity_m_s", "value": 245.1}
]
```

### GET /data

Returns all buffered data keyed by sensor name.

### GET /health

Returns `{"status": "ok"}`.

## Push from your sim machine

```python
import requests

SERVER = "http://192.168.x.x:5701"  # server LAN IP

requests.post(f"{SERVER}/telemetry", json={
    "timestamp": t,
    "sensor_name": "x_m",
    "value": x,
}, timeout=1)
```

Test with the included client:

```bash
python3 example_client.py http://192.168.x.x:5701
```

## Deploy as systemd service

```bash
sudo cp telemetry-viz.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telemetry-viz
sudo systemctl start telemetry-viz
```

Check: `curl http://localhost:5701/health`

If using a firewall: `sudo ufw allow 5701/tcp`

## LAN access

- Dashboard: `http://<server-lan-ip>:5701/`
- Push endpoint: `http://<server-lan-ip>:5701/telemetry`
