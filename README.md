# Cesium Heart

Cesium Heart contains the Astro frontend and backend services used by the site.

## Layout

- `frontend/` — Astro source; builds to `frontend/dist/`.
- `backend/services/` — Python APIs managed by systemd.
- `projects/dataviz/` — DataViz backend, GUI, and monitoring stack.
- `backend/music/setlister/` — Setlister backend and private configuration.
- `deploy/systemd/` — version-controlled systemd units.
- `scripts/deploy-startup.sh` — installs, builds, starts, and verifies the deployment.
- `archive/` — historical projects outside the active deployment.

## Deploy or repair the server

```bash
./scripts/deploy-startup.sh
```

The script runs `npm ci` and `npm run build`, installs tracked units into `/etc/systemd/system/`, enables and starts installed services, validates and reloads Apache, and checks systemd state and HTTP health endpoints. It requests `sudo` for system changes and skips optional units that are not installed.

Apache serves `/home/cskin/Cesium/heart/frontend/dist`. Its configuration is split into:

- `deploy/apache/sites-available/cesiumlab.conf` — main static-site virtual host;
- `deploy/apache/sites-available/dataviz.conf` — DataViz Dashboard subdomain; and
- `deploy/apache/includes/api-proxies.conf` — backend API route mappings.

The deployment helper installs and enables these files. `npm ci` installs dependencies; it does not create `dist`. `npm run build` creates `dist`, and Apache serves it.


## Project and page progress

Status reflects a repository audit on 2026-08-24. “Working” means the implementation
is present and passes the available static/build checks; it does not guarantee that
an optional external API or production service is currently reachable.

| Area | Route or location | Status | Notes |
| --- | --- | --- | --- |
| Main site | `/`, `/about_me`, `/sitemap` | Working | Primary navigation and personal pages |
| Everything Hub | `/everything-hub` | Partial | Feeds use third-party browser APIs/proxies; system statistics are explicitly simulated |
| Clock / Now | `/now/` | Working | Alternate draft remains at `/now/swiss-versionnnn` |
| Utility pages | `/nerd/tools/numbers`, `/Others/minimal`, `/Others/terminal`, `/Others/cyberspace` | Working | Standalone browser pages |
| Legacy homepage | `/Others/old_index` | Archived | Kept as a historical page |
| Decorative dashboards | `/dash/system`, `/dash/visitors`, `/dash/vibes` | Partial | Presentation/mock data rather than live server data |
| Rotation Visualizer | `/rotation-viz/rotation-visualizer` plus `backend/services/rotation-viz/` | Working | Interactive UI and conversion API; depends on Three.js CDN |
| Custom Telemetry Visualizer | `archive/telemetry-viz/` | Archived | Replaced by DataViz Prometheus and Grafana monitoring |
| Setlister | `/music/setlister/` plus `backend/music/setlister/` | Working | UI/API implemented; production secrets remain external under `/etc/cesium/` |
| Piano | `/music/piano` | Partial | Standalone experimental music page |
| DataViz POC | `projects/dataviz/` and `https://dataviz.cesiumlab.net` | Partial | Backend, NiceGUI command UI, Prometheus, and Grafana are implemented and are the canonical telemetry UI; state is in-memory and access control/real hardware are unfinished |
| API checker | `/api-check` | Working | Reports health for deployed backend services |

DataViz-specific design, limitations, and startup instructions live in
`projects/dataviz/ARCHITECTURE.md` and `projects/dataviz/QUICKSTART.md`.

## Troubleshooting

```bash
curl --fail http://127.0.0.1/
curl --fail http://127.0.0.1:5001/api/rotation/health
```

Never commit API keys or tokens. Keep production secrets in protected files under `/etc/cesium/`.
