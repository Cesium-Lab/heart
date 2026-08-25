# Backend services

These are active Python APIs used by the Astro frontend. They belong in `backend/services`, not `legacy-services`. Reserve a `legacy-services` directory for code that is retired, no longer deployed, or waiting to be removed.

## Included services

### Rotation visualizer

- Directory: `rotation-viz/`
- Framework: Flask
- Port: `5001`
- Health check: `GET http://127.0.0.1:5001/api/rotation/health`
- Conversion endpoint: `POST /api/rotation/convert`
- Frontend: `/rotation-viz/rotation-visualizer`

It converts quaternions, rotation matrices, Euler angles, and axis-angle representations. The browser page provides the interactive 3D visualization; this service performs conversion and validation calculations.

### Telemetry visualizer

- Directory: `telemetry-viz/`
- Framework: FastAPI
- Port: `5701`
- Health check: `GET http://127.0.0.1:5701/health`
- Data ingestion: `POST /telemetry`
- Buffered data: `GET /data`
- API documentation: `http://127.0.0.1:5701/docs`
- Frontend: `/telemetry-viz/dashboard`

It accepts single or batched sensor readings and keeps the latest 100 readings per sensor in memory. Its data is lost when the process restarts.

## One-time Python setup

Run these commands from the repository root:

```bash
python3 -m venv backend/services/rotation-viz/.venv
backend/services/rotation-viz/.venv/bin/pip install -r backend/services/rotation-viz/requirements.txt

python3 -m venv backend/services/telemetry-viz/.venv
backend/services/telemetry-viz/.venv/bin/pip install -r backend/services/telemetry-viz/requirements.txt
```

Test each service before installing its startup unit:

```bash
backend/services/rotation-viz/.venv/bin/python backend/services/rotation-viz/app.py
```

In another terminal:

```bash
curl http://127.0.0.1:5001/api/rotation/health
```

Then test telemetry:

```bash
cd backend/services/telemetry-viz
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 5701
```

In another terminal:

```bash
curl http://127.0.0.1:5701/health
```

## Run automatically at startup

The systemd unit files in `../../deploy/systemd/` assume:

- the repository is at `/home/cskin/Cesium/heart`;
- the Linux account is `cskin`;
- each service has the `.venv` created above.

If either the repository path or account differs, edit `WorkingDirectory`, `ExecStart`, and `User` in the unit files first.

Install and enable both units:

```bash
sudo install -m 0644 deploy/systemd/rotation-viz.service /etc/systemd/system/rotation-viz.service
sudo install -m 0644 deploy/systemd/telemetry-viz.service /etc/systemd/system/telemetry-viz.service
sudo systemctl daemon-reload
sudo systemctl enable --now rotation-viz.service telemetry-viz.service
```

`enable` registers the units for future boots; `--now` also starts them immediately.
### Cloudflare Tunnel

Cloudflare is also managed by systemd, but its live unit contains a secret tunnel token and must not be committed. `deploy/systemd/cloudflared.service.example` is a safe template. Put `TUNNEL_TOKEN=...` in `/etc/cesium/cloudflared.env`, restrict that file to root, install the template as `cloudflared.service`, and then run `sudo systemctl daemon-reload` followed by `sudo systemctl enable --now cloudflared.service`. Alternatively, let `cloudflared service install` manage the installed unit directly.

Verify them:

```bash
systemctl status rotation-viz.service telemetry-viz.service
curl http://127.0.0.1:5001/api/rotation/health
curl http://127.0.0.1:5701/health
```

View recent or live logs:

```bash
journalctl -u rotation-viz.service -u telemetry-viz.service -n 100
journalctl -u rotation-viz.service -u telemetry-viz.service -f
```

After changing Python code, restart the relevant service:

```bash
sudo systemctl restart rotation-viz.service
sudo systemctl restart telemetry-viz.service
```

After changing a `.service` file, reinstall it and reload systemd before restarting:

```bash
sudo install -m 0644 deploy/systemd/rotation-viz.service /etc/systemd/system/rotation-viz.service
sudo systemctl daemon-reload
sudo systemctl restart rotation-viz.service
```

## Disable or uninstall

Disable startup and stop the processes:

```bash
sudo systemctl disable --now rotation-viz.service telemetry-viz.service
```

To remove the installed units entirely:

```bash
sudo rm /etc/systemd/system/rotation-viz.service /etc/systemd/system/telemetry-viz.service
sudo systemctl daemon-reload
sudo systemctl reset-failed
```

## Network exposure

Do not expose these ports directly to the public internet. Keep them behind FastAPI/API routing, a firewall, or Cloudflare Tunnel as described in `../../api/BIG.md`. API keys belong in backend environment files or `/etc/cesium/api.env`, never in the Astro frontend.
