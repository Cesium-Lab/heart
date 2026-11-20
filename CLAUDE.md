# CLAUDE.md

This repo (`~/Cesium/heart`) lives on **mr-ray**, Colin's home server. It runs the cesiumlab.net
site and a few small backend services. Keep things simple: add features only when they're needed.

## The machine  (checked 2026-11-20)

- Nimo mini PC, Intel N100, 8 GB RAM, Ubuntu 24.04. Mac is `psyche`. Both are on Tailscale.
- Internal 128 GB NVMe: 40 GB Linux root (`/`, ~72% used) + 76 GB ext4 `/srv/state` (label `state`).
  Windows was deleted on 2026-11-20.
- External 2 TB Samsung USB drive (~2010, exFAT, UUID 69AB-FB81) is auto-mounted at `/srv/data`
  (`nofail` + `x-systemd.automount`). It was kept as exFAT so the Mac can read it directly. It holds
  ~371 GB of Colin's older files (Music, Emgineering, archiv, photos, taxes, Old, movies…) and may be the
  only copy of some of them. A new drive is planned.
- Running: Apache (serves `frontend/dist`), cloudflared tunnel, setlister, rotation-viz,
  cesium-frontend (astro dev), dataviz + grafana/prometheus in docker, mysql, samba, ssh.

## Rules

- Editing files in this repo is fine. **Ask first** before anything that changes the machine:
  installing packages, disks/mounts, deleting data, restarting services, network/exposure changes, git push.
- Never commit or print secrets. Secrets go in `/etc/cesium/<name>.env`; commit only `.env.example`.
- New service: code in `backend/`, unit in `deploy/systemd/`, bind to `127.0.0.1`, pick a port from
  `docs/homenet/network.md` and add it there.
- Deploy/repair: `./scripts/deploy-startup.sh` (uses sudo, so ask first).

## Storage

- `/srv/data`: files (music, cesium). Lives on an external/data drive.
- `/srv/state`: app data (databases, indexes). Lives on the internal NVMe once Windows is gone.
- Apps get these paths from config (e.g. `/etc/cesium/paths.env`), never hard-coded. That way a
  new drive or a NAS can be mounted at the same path later without touching the apps.
- **Safe if the drive is unplugged:** mount with `nofail` so the server still boots, keep the empty
  mountpoint unwritable so nothing lands on the system disk, and give services that need it
  `RequiresMountsFor=/srv/data` so they just stay off.

```
/srv/data/
├── music/        # grouping (by artist vs flat) not decided yet
│   └── <song>/
│       ├── lyrics/   # lyric drafts + notes
│       ├── memos/    # voice memos
│       ├── demos/
│       ├── logic/    # copies of the Logic project; active sessions stay on the Mac
│       ├── mixes/
│       ├── stems/
│       └── masters/
└── cesium/       # engineering projects + datasets
```

**Files are the truth.** No metadata files for now; folder and file names carry the info. Anything
built later (search index, catalog DB) must be rebuildable from the files.

## Now

Done 2026-11-20: freed root space (96% → 72%), mounted the Samsung at `/srv/data`, deleted Windows,
created `/srv/state`.

1. Decide how to organize music on `/srv/data` (existing `Music/` folder vs a new `music/` tree).
2. Keep a second copy of the irreplaceable files (taxes, important, photos, Music) until the new drive arrives.
3. When the new drive arrives, decide its role (data vs backup).

## Ideas for later (not planned in detail on purpose)

- **Juice**: a small API that Claude/Codex can call to search lyrics and notes.
- **Coda**: a music catalog that indexes the song folders, maybe SQLite. Rebuildable from the files.
- Share selected mixes with MONARCH.
- Move storage to a NAS someday.

`docs/api/MUSIC_STORAGE.md` has an older, more detailed music-catalog sketch if it's ever useful.
