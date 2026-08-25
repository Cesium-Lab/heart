# Backend services

These active Python APIs support the Astro frontend. Retired services belong under `archive/` or `legacy-services/`.

## Services

| Service | Framework | Port | Health check |
| --- | --- | ---: | --- |
| Rotation visualizer | Flask | 5001 | `http://127.0.0.1:5001/api/rotation/health` |
| Telemetry visualizer | FastAPI | 5701 | `http://127.0.0.1:5701/health` |

Telemetry buffers the latest 100 readings per sensor in memory; its data is lost on restart.

## One-time Python setup

```bash
python3 -m venv backend/services/rotation-viz/.venv
backend/services/rotation-viz/.venv/bin/pip install -r backend/services/rotation-viz/requirements.txt

python3 -m venv backend/services/telemetry-viz/.venv
backend/services/telemetry-viz/.venv/bin/pip install -r backend/services/telemetry-viz/requirements.txt
```

Do not install these dependencies globally with `pip3 --break-system-packages`.

## Deploy, start, and verify

```bash
./scripts/deploy-startup.sh
```

The helper installs `rotation-viz.service`, `telemetry-viz.service`, and `frontend-build.service` from `deploy/systemd/`; reloads systemd; enables and starts installed components; validates Apache; and checks the site and API health endpoints.

The units assume the repository is `/home/cskin/Cesium/heart`, run as `cskin`, and have the virtual environments above. Edit `User`, `WorkingDirectory`, and `ExecStart` if those assumptions change.

Telemetry uses `.venv/bin/python -m uvicorn`, not `.venv/bin/uvicorn`. Virtualenv launchers have absolute shebangs that become stale after a directory move; invoking the module through the current Python avoids that failure.

Manual installation:

```bash
sudo install -m 0644 deploy/systemd/rotation-viz.service /etc/systemd/system/rotation-viz.service
sudo install -m 0644 deploy/systemd/telemetry-viz.service /etc/systemd/system/telemetry-viz.service
sudo systemctl daemon-reload
sudo systemctl enable --now rotation-viz.service telemetry-viz.service
```

## Operations

```bash
systemctl status rotation-viz.service telemetry-viz.service --no-pager
journalctl -u rotation-viz.service -u telemetry-viz.service -n 100 --no-pager
curl --fail http://127.0.0.1:5001/api/rotation/health
curl --fail http://127.0.0.1:5701/health
```

After code changes, restart the relevant API. After unit changes, rerun the deployment helper so tracked definitions are copied into `/etc`.

## Cloudflare Tunnel and exposure

`deploy/systemd/cloudflared.service.example` is a secret-free template. Keep its real token in protected `/etc/cesium/cloudflared.env`; never commit it. Keep API ports private and expose routes through Apache, a firewall, or the configured tunnel.
