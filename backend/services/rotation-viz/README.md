# Rotation Visualizer API

The Flask API converts and validates quaternion, rotation-matrix, Euler-angle, and axis-angle representations. The Astro frontend contains the browser visualization; Apache serves the compiled frontend from `frontend/dist`.

## Runtime

- Application: `app.py`
- Dependencies: `requirements.txt`
- Port: `5001`
- Health: `GET http://127.0.0.1:5001/api/rotation/health`
- Unit: `deploy/systemd/rotation-viz.service`
- Apache proxy prefix: `/api/rotation/`

## One-time setup

```bash
python3 -m venv backend/services/rotation-viz/.venv
backend/services/rotation-viz/.venv/bin/pip install -r backend/services/rotation-viz/requirements.txt
```

## Deploy and verify

```bash
./scripts/deploy-startup.sh
```

The helper installs the unit, enables and starts it, validates Apache, and checks health. Manual alternative:

```bash
sudo install -m 0644 deploy/systemd/rotation-viz.service /etc/systemd/system/rotation-viz.service
sudo systemctl daemon-reload
sudo systemctl enable --now rotation-viz.service
systemctl status rotation-viz.service --no-pager
curl --fail http://127.0.0.1:5001/api/rotation/health
```

Apache proxies the public API route:

```apache
ProxyPass /api/rotation/ http://127.0.0.1:5001/api/rotation/
ProxyPassReverse /api/rotation/ http://127.0.0.1:5001/api/rotation/
```

Keep port 5001 private rather than exposing it directly to the internet.
