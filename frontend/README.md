# Cesium Lab frontend

This is an Astro static site. `npm run build` writes deployable files to `frontend/dist`; Apache serves that directory on the self-hosted server.

## Local development

```bash
cd frontend
npm ci
npm run dev
```

Before committing (CI runs the same two checks on every push):

```bash
npm run format:check
npm run build
```

`npm ci` installs locked dependencies. It does not create `dist`; `npm run build` does.

## Server deployment

```bash
./scripts/deploy-startup.sh
```

Its `scripts/deploy/frontend.sh` stage installs dependencies, builds, verifies `dist/index.html`, and installs `frontend-build.service`. Later stages reload Apache and check `http://127.0.0.1/`. To publish a content change without a full deploy, `npm run build` is enough: Apache serves the new `dist/` on the next request.

`frontend-build.service` rebuilds `dist/` at boot. `cesium-frontend.service` runs `astro dev` on port 42800 for live editing; it is not the public site.

```bash
systemctl status frontend-build.service --no-pager
journalctl -u frontend-build.service -n 100 --no-pager
```

Building does not serve the site. Apache remains necessary and should use:

```apache
DocumentRoot /home/cskin/Cesium/heart/frontend/dist
```
