# Services, ports, and deploy

## How the site is served

- `astro build` turns `frontend/` into static files in `frontend/dist/`. Apache serves that folder
  and proxies `/api/...` routes to the backend services. `frontend-build.service` rebuilds at boot.
- To publish a content change: `./scripts/publish.sh` (no sudo). It builds into `dist.next/` and
  swaps it in, so the live site is never half-built and a failed build changes nothing. Apache
  serves the new files on the next request; no reload needed.
- `cesium-frontend.service` runs `astro dev` on port 42800 for live editing on the LAN. It is not
  the public site.
- Don't name a site folder `icons/`: Ubuntu's Apache aliases `/icons/` to its own
  `/usr/share/apache2/icons/` (`mods-available/alias.conf`), so those URLs 404 on the live site
  while working in `astro dev`. Site icons live in `frontend/public/favicons/`.
- Apache config is tracked in `deploy/apache/` (sites + `includes/api-proxies.conf`) and installed
  by `scripts/deploy/apache.sh`. Edit it there, not in `/etc`.

## Running services

| Service             | Unit                        | Local endpoint    | Reached at                                      |
| ------------------- | --------------------------- | ----------------- | ----------------------------------------------- |
| Apache              | `apache2`                   | `0.0.0.0:80`      | cesiumlab.net (tunnel), LAN                     |
| Cloudflare tunnel   | `cloudflared`               | -                 | -                                               |
| Astro dev server    | `cesium-frontend`           | `0.0.0.0:42800`   | LAN only (development)                          |
| Rotation visualizer | `rotation-viz`              | `127.0.0.1:42902` | `/api/rotation/`                                |
| Setlister           | `setlister`                 | `127.0.0.1:42903` | `/api/setlister/`                               |
| Planes (SFO map)    | `planes`                    | `127.0.0.1:42901` | `/planes/` (map + board drawer), `/api/planes/` |
| DataViz API         | `dataviz-backend`           | `127.0.0.1:42000` | `/api/dataviz/`                                 |
| DataViz GUI         | `dataviz-gui`               | `127.0.0.1:42002` | `dataviz.cesiumlab.net`                         |
| Grafana             | docker (`projects/dataviz`) | `127.0.0.1:42003` | private/admin                                   |
| Prometheus          | docker (`projects/dataviz`) | `127.0.0.1:42004` | private only                                    |

Retired: Telemetry Viz (`archive/telemetry-viz/`), replaced by DataViz + Grafana/Prometheus.
`./scripts/status.sh` shows what is actually running right now.

## Port allocation

Every service in this repo takes a port from the 42000–42999 scheme. It sits well away from
common defaults (3000, 5000, 8080…), so collisions are unlikely. Only Apache (80) and system
services (ssh, samba, mysql) keep standard ports.

| Port range  | Purpose                      |
| ----------- | ---------------------------- |
| 42000–42099 | Ground-station services      |
| 42100–42199 | Flight-computer telemetry    |
| 42200–42299 | GNC simulation               |
| 42300–42399 | Hardware-in-the-loop (HITL)  |
| 42400–42499 | Cameras and video            |
| 42500–42599 | Logging and data archive     |
| 42600–42699 | Robot control                |
| 42700–42799 | Sensor streaming             |
| 42800–42899 | Development and debugging    |
| 42900–42999 | Web dashboards and site APIs |

Assigned and reserved ports:

| Port  | Service                      |
| ----- | ---------------------------- |
| 42000 | DataViz T&C backend          |
| 42001 | (reserved: telemetry stream) |
| 42002 | DataViz dashboard (NiceGUI)  |
| 42003 | Grafana                      |
| 42004 | Prometheus                   |
| 42100 | Flight-computer telemetry    |
| 42101 | Flight-computer commands     |
| 42200 | 6DOF simulation              |
| 42201 | Monte Carlo runs             |
| 42300 | HITL sensor feed             |
| 42301 | HITL actuator feed           |
| 42600 | Robot state                  |
| 42601 | Robot commands               |
| 42800 | Astro dev server             |
| 42900 | Dashboard (reserved)         |
| 42901 | Planes (SFO map + board)     |
| 42902 | Rotation visualizer API      |
| 42903 | Setlister API                |

## Adding a service

1. Code in `backend/` (or `projects/` for bigger ones). Bind to `127.0.0.1`.
2. Pick a free port from the table above and add it here.
3. Unit in `deploy/systemd/`. Secrets in `/etc/cesium/<name>.env`; commit only `.env.example`.
4. Add the unit to `scripts/deploy/backends.sh` and a health check to `scripts/deploy/verify.sh`.
5. Add a line to `SERVICES` in `scripts/status.sh`.
6. Public route? Add it to `deploy/apache/includes/api-proxies.conf` (and the Astro dev proxy in
   `frontend/astro.config.mjs`). Add an import or smoke test to `.github/workflows/ci.yml`.

## Deploy

- `./scripts/deploy-startup.sh` runs the stages in `scripts/deploy/`: `frontend.sh`, `backends.sh`,
  `monitoring.sh`, `apache.sh`, `verify.sh`. Each can run on its own. Uses sudo.
- A redeploy does **not** restart services that are already running. After code changes:
  `sudo systemctl restart <name>`.
- Logs: `journalctl -u <name> -n 50 --no-pager`.

## CI

`.github/workflows/ci.yml` runs on every push and PR: frontend Prettier check + build, an import
test per Python service (each with its own requirements), a Planes smoke test (health, track, replay), ruff lint + format
(`ruff.toml`), and shellcheck on all scripts.
