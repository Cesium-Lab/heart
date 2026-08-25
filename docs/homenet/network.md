# Home network

## Domain

The public domain is [cesiumlab.net](https://cesiumlab.net), registered and routed through Cloudflare.

## Devices

### mr-ray

`mr-ray` is the host running the Cesium Heart web deployment. Local DNS may expose it as `mr.ray`.

Core infrastructure:

- Apache serves the Astro static build and proxies backend API routes.
- `cloudflared` provides the external tunnel.
- `dnsmasq` provides local DNS services.
- Tailscale provides private remote access.

Application services:

| Service | Local endpoint | Public path |
| --- | --- | --- |
| Apache frontend | `127.0.0.1:80` | `/` |
| Rotation visualizer | `127.0.0.1:5001` | `/api/rotation/` |
| Telemetry visualizer | `127.0.0.1:5701` | deployment-specific |
| Setlister | `127.0.0.1:5702` | `/api/setlister/` |
| DataViz API | `127.0.0.1:42000` | `/api/dataviz/` |
| DataViz GUI | `127.0.0.1:42002` | `dataviz.cesiumlab.net` |
| Grafana | `127.0.0.1:42003` | private/admin access |
| Prometheus | `127.0.0.1:42004` | private only |

See `scripts/deploy-startup.sh` for the deployment and health-check sequence. A topology document can be added under this directory when the network diagram is ready.

## Port allocation

| Port range | Purpose |
| --- | --- |
| 5000–5099 | Ground-station services |
| 5100–5199 | Flight-computer telemetry |
| 5200–5299 | GNC simulation |
| 5300–5399 | HITL |
| 5400–5499 | Cameras and video |
| 5500–5599 | Logging and data archive |
| 5600–5699 | Robot control |
| 5700–5799 | Sensor streaming and related APIs |
| 5800–5899 | Development and debugging |
| 5900–5999 | Web dashboards |

Backend ports should remain private unless LAN access is intentional. Prefer Apache or Cloudflare Tunnel for public routes.
