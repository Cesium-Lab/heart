# Cesium Lab frontend

This is an Astro static site. `npm run build` writes deployable files to `frontend/dist`; Apache serves that directory on the self-hosted server.

## Local development

```bash
cd frontend
npm ci
npm run dev
```

Before committing or deploying:

```bash
npm run format:check
npm run build
```

`npm ci` installs locked dependencies. It does not create `dist`; `npm run build` does.

## Server deployment

```bash
./scripts/deploy-startup.sh
```

The helper installs dependencies, builds, verifies `dist/index.html`, installs and enables `frontend-build.service`, validates and reloads Apache, and checks `http://127.0.0.1/`.

```bash
systemctl status frontend-build.service --no-pager
journalctl -u frontend-build.service -n 100 --no-pager
```

Building does not serve the site. Apache remains necessary and should use:

```apache
DocumentRoot /home/cskin/Cesium/heart/frontend/dist
```

## Cloudflare Pages

For a separate Pages deployment:

- Root directory: `frontend`
- Framework preset: `Astro`
- Build command: `npm run build`
- Output directory: `dist`
- Node version: 22 or newer

Cloudflare Pages performs its own build and does not use local Apache or systemd. Backend services and secrets remain under `../backend`; never expose secrets through Astro `PUBLIC_*` variables.
