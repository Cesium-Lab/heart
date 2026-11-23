# DataViz quick start

## Production deployment

From the Cesium Heart repository root:

```bash
./scripts/deploy-startup.sh
```

The `scripts/deploy/backends.sh` stage creates `projects/dataviz/.venv`, installs Python dependencies, starts Prometheus and Grafana when Docker Compose is available, installs the DataViz systemd units, and checks ports 42000 and 42002.

Repository-owned deployment files:

- `deploy/systemd/dataviz-backend.service`
- `deploy/systemd/dataviz-gui.service`
- `deploy/apache/sites-available/cesiumlab.conf`
- `deploy/apache/sites-available/dataviz.conf`
- `deploy/apache/includes/api-proxies.conf`

The main site exposes the backend at `/api/dataviz/`. DataViz Dashboard is intended for `https://dataviz.cesiumlab.net`.

## Local development

```bash
cd /home/cskin/Cesium/heart/projects/dataviz
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./start_servers.sh
```

The launcher uses tmux for the backend and NiceGUI, and Docker Compose for Prometheus and Grafana.

| Component         | Local address            |
| ----------------- | ------------------------ |
| Backend API       | `http://127.0.0.1:42000` |
| DataViz Dashboard | `http://127.0.0.1:42002` |
| Grafana           | `http://127.0.0.1:42003` |
| Prometheus        | `http://127.0.0.1:42004` |

Detach with `Ctrl+B`, then `D`. Reattach with:

```bash
tmux attach -t dataviz
```

Stop the development stack:

```bash
tmux kill-session -t dataviz
docker compose -f projects/dataviz/docker-compose.yaml down
```

## Verification

```bash
curl --fail http://127.0.0.1:42000/api/v1/health
curl --fail http://127.0.0.1:42002/
curl --fail http://127.0.0.1/api/dataviz/health
```

Command endpoints can change simulated vehicle state. Protect DataViz Dashboard and command routes with Cloudflare Access before exposing them publicly.
