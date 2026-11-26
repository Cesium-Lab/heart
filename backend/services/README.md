# Backend services

These Python APIs support the Astro frontend.

## Services

| Service              | Framework |  Port | Health check                                 |
| -------------------- | --------- | ----: | -------------------------------------------- |
| Rotation visualizer  | Flask     | 42902 | `http://127.0.0.1:42902/api/rotation/health` |
| Planes (SFO map API) | stdlib    | 42901 | `http://127.0.0.1:42901/api/planes/health`   |

DataViz telemetry is monitored through Prometheus and Grafana under `monitoring/`.

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

The wrapper runs the stages in `scripts/deploy/` in order: `frontend.sh` (build +
`frontend-build.service`), `backends.sh` (venvs and the Rotation, Setlister, Planes, and
DataViz units), `monitoring.sh` (Grafana/Prometheus in Docker), `apache.sh` (sites and
proxies from `deploy/apache/`), and `verify.sh` (unit state and health URLs). Each stage
can be run on its own. `./scripts/status.sh` shows the result at any time.

Ports and the checklist for adding a service are in `architecture/services.md`.

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
curl --fail http://127.0.0.1:42902/api/rotation/health
```

After code changes, restart the relevant API. After unit changes, rerun the
deployment helper so tracked definitions are copied into `/etc`.

## Cloudflare Tunnel and exposure

`deploy/systemd/cloudflared.service.example` is a secret-free template. Keep its
real token in protected `/etc/cesium/cloudflared.env`; never commit it. Keep API
ports private and expose routes through Apache, a firewall, or the configured tunnel.
