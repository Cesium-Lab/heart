# CLAUDE.md

This repo (`~/Cesium/heart`) lives on **mr-ray**, Colin's home server. It runs the cesiumlab.net
site and a few small backend services. Keep things simple: add features only when they're needed.

Facts about the machine, services, ports, and ideas live in `architecture/` (the source of truth)
and are imported below. When something changes, update the matching `architecture/` file.

## Rules

- Editing files in this repo is fine. **Ask first** before anything that changes the machine:
  installing packages, disks/mounts, deleting data, restarting services, network/exposure changes, git push.
- Never commit or print secrets. Secrets go in `/etc/cesium/<name>.env`; commit only `.env.example`.
- New service: follow "Adding a service" in `architecture/services.md` (loopback bind, 42xxx port,
  unit, deploy stages, `status.sh`, CI).
- Deploy/repair: `./scripts/deploy-startup.sh` (uses sudo, so ask first).

## Now

Done 2026-11-20: freed root space (96% → 72%), mounted the Samsung at `/srv/data`, deleted Windows,
created `/srv/state`. In the repo 2026-11-22: merged the `dataviz` branch, retired Telemetry Viz,
moved every service to the 42xxx port scheme, added CI, `scripts/status.sh`, and the Planes board.

0. **Cut the machine over to the new ports** (still on 5001/5702/4321/5901 until done): set
   `SETLISTER_PORT=42903` in `/etc/cesium/music.env`, then
   `sudo systemctl restart rotation-viz setlister planes cesium-frontend`, then
   `./scripts/deploy-startup.sh` and `./scripts/status.sh`. Restart before deploying.
1. Decide how to organize music on `/srv/data` (existing `Music/` folder vs a new `music/` tree).
2. Keep a second copy of the irreplaceable files (taxes, important, photos, Music) until the new drive arrives.
3. When the new drive arrives, decide its role (data vs backup), and whether to merge `/srv/state`
   into root (`docs/homenet/merge-root-partition.md`, deferred).

## Architecture

@architecture/README.md
@architecture/machine.md
@architecture/services.md
@architecture/ideas.md
