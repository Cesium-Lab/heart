# Cesium Lab frontend

Frontend built with Astro for Cloudflare Pages.

## Local development

```bash
npm ci
npm run dev

npm run format:check
npm run build
```

## Cloudflare Pages settings

- Root directory: `backend`
- Framework preset: `Astro`
- Build command: `npm run build`
- Build output directory: `dist`
- Deploy command: leave blank
- Node version: 22 or newer

Backend services and secrets live in `../backend`, outside this frontend project.
