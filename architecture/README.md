# Architecture

This folder is the source of truth for how mr-ray and cesiumlab.net are put together.
CLAUDE.md imports these files, so keep them short, current, and factual. When something
changes on the machine, update the matching file here in the same commit.

| File                       | What it covers                                             |
| -------------------------- | ---------------------------------------------------------- |
| [machine.md](machine.md)   | Hardware, network, disks, storage layout                   |
| [services.md](services.md) | How the site is served, every service and port, deploy, CI |
| [ideas.md](ideas.md)       | Things for someday, deliberately not planned in detail     |

## Principles

- **Keep it simple.** Add features only when they're needed. One small service per job.
- **Files are the truth.** Folder and file names carry the info. Any index or catalog built
  later must be rebuildable from the files.
- **Static site + small APIs.** Astro builds the site, Apache serves the build and proxies
  `/api/...` to services bound to `127.0.0.1`. No big platform layer.
- **Private by default.** Services listen on loopback. Anything public goes through Apache and
  the Cloudflare tunnel; anything private is reached over SSH or the LAN.
- **Paths and secrets come from config** (`/etc/cesium/*.env`), never hard-coded or committed.

## Big picture

```text
Internet ─ Cloudflare ─ cloudflared ─┐
                                     ▼
LAN / SSH ───────────────────────► Apache :80 ── serves frontend/dist (astro build)
                                     │
                                     └─ /api/rotation  → rotation-viz   :42902
                                        /api/setlister → setlister      :42903
                                        /api/planes    → planes         :42901
                                        /inbox/        → inbox          :42904  (password off-LAN)
                                        /tasks/        → tasks          :42906  (password off-LAN)
                                        /hq/           → hq             :42907  (password always)
                                        /api/dataviz   → dataviz API    :42000
                                        dataviz.cesiumlab.net → NiceGUI :42002
                                        docs.cesiumlab.net    → SilverBullet :42905
Private (SSH tunnel): Grafana :42003 · Prometheus :42004
LAN (development):    astro dev :42800
```

## Other docs

- `docs/homenet/merge-root-partition.md`: deferred runbook for growing the root partition.
- `docs/api/MUSIC_STORAGE.md`, `docs/api/ASSISTANT_MEMORY.md`: older, detailed sketches kept as
  reference for Coda and Juice (see [ideas.md](ideas.md)). They assume a Postgres/FastAPI stack
  that is not the plan.
