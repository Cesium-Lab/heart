# Backend services

These active Python APIs support the Astro frontend. Retired services belong under `archive/`.

## Services

| Service | Framework | Port | Health check |
| --- | --- | ---: | --- |
| Rotation visualizer | Flask | 5001 | `http://127.0.0.1:5001/api/rotation/health` |

DataViz telemetry is monitored through Prometheus and Grafana under
`projects/dataviz/`; the former custom telemetry API and Chart.js page are archived.

## One-time Python setup

```bash
python3 -m venv backend/services/rotation-viz/.venv
backend/services/rotation-viz/.venv/bin/pip install -r backend/services/rotation-viz/requirements.txt
```

Do not install these dependencies globally with `pip3 --break-system-packages`.

## Deploy, start, and verify

```bash
./scripts/deploy-startup.sh
```

The helper installs `rotation-viz.service` and `frontend-build.service`, reloads
systemd, enables and starts installed components, validates Apache, and checks the
site and API health endpoints.

The units assume the repository is `/home/cskin/Cesium/heart` and run as `cskin`.
Edit `User`, `WorkingDirectory`, and `ExecStart` if those assumptions change.

Manual installation:

```bash
sudo install -m 0644 deploy/systemd/rotation-viz.service /etc/systemd/system/rotation-viz.service
sudo systemctl daemon-reload
sudo systemctl enable --now rotation-viz.service
```

## Operations

```bash
systemctl status rotation-viz.service --no-pager
journalctl -u rotation-viz.service -n 100 --no-pager
curl --fail http://127.0.0.1:5001/api/rotation/health
```

After code changes, restart the relevant API. After unit changes, rerun the
deployment helper so tracked definitions are copied into `/etc`.

## Cloudflare Tunnel and exposure

`deploy/systemd/cloudflared.service.example` is a secret-free template. Keep its
real token in protected `/etc/cesium/cloudflared.env`; never commit it. Keep API
ports private and expose routes through Apache, a firewall, or the configured tunnel.
