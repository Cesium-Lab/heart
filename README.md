# Cesium Heart

Cesium Heart contains the Astro frontend and backend services used by the site.

## Layout

- `architecture/` — **source of truth**: machine, storage, services and ports, deploy, ideas.
- `frontend/` — Astro source; builds to `frontend/dist/`.
- `backend/services/` — Python APIs managed by systemd.
- `projects/dataviz/` — DataViz backend, GUI, and monitoring stack.
- `backend/music/setlister/` — Setlister backend and private configuration.
- `deploy/systemd/`, `deploy/apache/` — version-controlled systemd units and Apache config.
- `scripts/deploy-startup.sh` — full deploy; runs the stages in `scripts/deploy/`.
- `scripts/status.sh` — read-only overview of services, ports, docker, and disks.
- `.github/workflows/ci.yml` — CI: frontend build + Prettier, service imports, Planes smoke test, ruff, shellcheck.
- `archive/` — historical projects outside the active deployment.

## Deploy or repair the server

```bash
./scripts/deploy-startup.sh
```

The wrapper runs five stages from `scripts/deploy/`, each runnable on its own: `frontend.sh` (`npm ci` + `npm run build`), `backends.sh` (venvs and systemd units), `monitoring.sh` (Grafana/Prometheus in Docker), `apache.sh` (sites and proxies), and `verify.sh` (unit state and HTTP health checks). It requests `sudo` for system changes and skips optional units that are not installed. A redeploy does not restart services that are already running; use `sudo systemctl restart <name>` after code changes.

Apache serves `/home/cskin/Cesium/heart/frontend/dist`. Its configuration is split into:

- `deploy/apache/sites-available/cesiumlab.conf` — main static-site virtual host;
- `deploy/apache/sites-available/dataviz.conf` — DataViz Dashboard subdomain; and
- `deploy/apache/includes/api-proxies.conf` — backend API route mappings.

The deployment helper installs and enables these files. `npm ci` installs dependencies; it does not create `dist`. `npm run build` creates `dist`, and Apache serves it.

## Project and page progress

Status reflects a repository audit on 2026-08-24, updated 2026-11-22. “Working” means the implementation
is present and passes the available static/build checks; it does not guarantee that
an optional external API or production service is currently reachable.

| Area                        | Route or location                                                                  | Status   | Notes                                                                                                                                                                       |
| --------------------------- | ---------------------------------------------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Main site                   | `/`, `/about_me`, `/sitemap`                                                       | Working  | Primary navigation and personal pages                                                                                                                                       |
| Everything Hub              | `/everything-hub`                                                                  | Partial  | Feeds use third-party browser APIs/proxies; system statistics are explicitly simulated                                                                                      |
| Clock / Now                 | `/now/`                                                                            | Working  | Alternate draft remains at `/now/swiss-versionnnn`                                                                                                                          |
| Utility pages               | `/nerd/tools/numbers`, `/Others/minimal`, `/Others/terminal`, `/Others/cyberspace` | Working  | Standalone browser pages                                                                                                                                                    |
| Legacy homepage             | `/Others/old_index`                                                                | Archived | Kept as a historical page                                                                                                                                                   |
| Decorative dashboards       | `/dash/system`, `/dash/visitors`, `/dash/vibes`                                    | Partial  | Presentation/mock data rather than live server data                                                                                                                         |
| Rotation Visualizer         | `/rotation-viz/rotation-visualizer` plus `backend/services/rotation-viz/`          | Working  | Interactive UI and conversion API; depends on Three.js CDN                                                                                                                  |
| Custom Telemetry Visualizer | `archive/telemetry-viz/`                                                           | Archived | Replaced by DataViz Prometheus and Grafana monitoring                                                                                                                       |
| Setlister                   | `/music/setlister/` plus `backend/music/setlister/`                                | Working  | UI/API implemented; production secrets remain external under `/etc/cesium/`                                                                                                 |
| TapTempo                    | `/music/taptempo/`                                                                 | Working  | Tap tempo, metronome, and count-ins; reads the Setlister library from the browser                                                                                           |
| Planes (SFO board)          | `/planes/` plus `backend/services/planes/`                                         | Working  | Split-flap SFO departures/arrivals from live ADS-B data; page in the Astro build, data from the planes API                                                                  |
| Piano                       | `/music/piano`                                                                     | Partial  | Standalone experimental music page                                                                                                                                          |
| DataViz POC                 | `projects/dataviz/` and `https://dataviz.cesiumlab.net`                            | Partial  | Backend, NiceGUI command UI, Prometheus, and Grafana are implemented and are the canonical telemetry UI; state is in-memory and access control/real hardware are unfinished |
| API checker                 | `/api-check`                                                                       | Working  | Reports health for deployed backend services                                                                                                                                |

DataViz-specific design, limitations, and startup instructions live in
`projects/dataviz/ARCHITECTURE.md` and `projects/dataviz/QUICKSTART.md`.

## Troubleshooting

```bash
./scripts/status.sh                         # every service, port, health URL, and disk
journalctl -u <name> -n 50 --no-pager       # logs for one service
```

Never commit API keys or tokens. Keep production secrets in protected files under `/etc/cesium/`.
