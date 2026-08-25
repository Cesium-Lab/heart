# SETLISTER.EXE

Setlister is a local-first song library and setlist builder. Browser source lives under `frontend/src/`; the Python proxy in this directory keeps the GetSongBPM key out of the browser.

## Layout

- `server.py` — Flask lookup proxy on `127.0.0.1:5702`.
- `requirements.txt` — backend-only Python dependencies.
- `.env.example` — safe local configuration template.
- `frontend/src/pages/music/setlister/index.astro` — Astro page route.
- `frontend/src/scripts/setlister.js` — browser application bundled by Astro.
- `frontend/src/styles/setlister.css` — page styles bundled by Astro.
- `frontend/src/data/setlister-example-library.json` — example data imported at build time.
- `deploy/systemd/setlister.service` — production service definition.

Apache serves `/music/setlister/` from the Astro build and proxies `/api/setlister/` to port 5702.

## Local setup

From the repository root:

```bash
cp backend/music/setlister/.env.example backend/music/setlister/.env
python3 -m venv backend/music/setlister/.venv
backend/music/setlister/.venv/bin/pip install -r backend/music/setlister/requirements.txt
backend/music/setlister/.venv/bin/python backend/music/setlister/server.py
```

Set the real API key in `.env` and keep port 5702:

```dotenv
GETSONGBPM_API_KEY=replace-with-your-real-key
SETLISTER_PORT=5702
SETLISTER_API_TIMEOUT=8
SETLISTER_CACHE_TTL=3600
SETLISTER_RATE_LIMIT=60
```

Never commit `.env` or expose the key through Astro `PUBLIC_*` variables.

## Production secrets

The tracked unit reads `/etc/cesium/music.env`:

```bash
sudo install -d -m 0750 -o root -g cskin /etc/cesium
sudo install -m 0640 -o root -g cskin backend/music/setlister/.env /etc/cesium/music.env
```

## Deploy and verify

```bash
./scripts/deploy-startup.sh
```

The helper builds the static UI, installs `setlister.service`, starts it, and checks its health endpoint. Manual alternative:

```bash
sudo install -m 0644 deploy/systemd/setlister.service /etc/systemd/system/setlister.service
sudo systemctl daemon-reload
sudo systemctl enable --now setlister.service
systemctl status setlister.service --no-pager
curl --fail http://127.0.0.1:5702/api/setlister/health
```

Apache needs these rules inside the active virtual host:

```apache
ProxyPass /api/setlister/ http://127.0.0.1:5702/api/setlister/
ProxyPassReverse /api/setlister/ http://127.0.0.1:5702/api/setlister/
```

Keep port 5702 bound to loopback. The browser should call `/api/setlister/search`, never the upstream service directly.
