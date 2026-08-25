# Cesium Heart

Cesium Heart contains the Astro frontend and backend services used by the site.

## Layout

- `frontend/` — Astro source; builds to `frontend/dist/`.
- `backend/services/` — Python APIs managed by systemd.
- `backend/music/setlister/` — Setlister backend and private configuration.
- `deploy/systemd/` — version-controlled systemd units.
- `scripts/deploy-startup.sh` — installs, builds, starts, and verifies the deployment.
- `archive/` — historical projects outside the active deployment.

## Deploy or repair the server

```bash
./scripts/deploy-startup.sh
```

The script runs `npm ci` and `npm run build`, installs tracked units into `/etc/systemd/system/`, enables and starts installed services, validates and reloads Apache, and checks systemd state and HTTP health endpoints. It requests `sudo` for system changes and skips optional units that are not installed.

Apache serves `/home/cskin/Cesium/heart/frontend/dist`. Configure `/etc/apache2/sites-available/000-default.conf` with:

```apache
DocumentRoot /home/cskin/Cesium/heart/frontend/dist

<Directory /home/cskin/Cesium/heart/frontend/dist>
    Options FollowSymLinks
    AllowOverride None
    Require all granted
</Directory>
```

`npm ci` installs dependencies; it does not create `dist`. `npm run build` creates `dist`, and Apache serves it.

## Troubleshooting

```bash
systemctl status frontend-build.service rotation-viz.service telemetry-viz.service apache2.service
journalctl -u frontend-build.service -u rotation-viz.service -u telemetry-viz.service -n 100 --no-pager
curl --fail http://127.0.0.1/
curl --fail http://127.0.0.1:5001/api/rotation/health
curl --fail http://127.0.0.1:5701/health
```

Never commit API keys or tokens. Keep production secrets in protected files under `/etc/cesium/`.
