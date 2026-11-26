# The machine

Checked 2026-11-22.

## Hardware and network

- **mr-ray**: Nimo mini PC, Intel N100, 8 GB RAM, Ubuntu 24.04. The repo lives at `~/Cesium/heart`.
- **psyche**: Colin's Mac. Both are on Tailscale and the home LAN (mr-ray is `192.168.0.13`;
  local DNS may also call it `mr.ray`).
- **Domain**: [cesiumlab.net](https://cesiumlab.net), registered and routed through Cloudflare
  (about $12/year).
  The `cloudflared` tunnel sends `cesiumlab.net` and `dataviz.cesiumlab.net` to Apache on
  `127.0.0.1:80`; everything else gets a 404.
- **Tailscale**: private remote access only. `tailscale serve`/`funnel` are not used.
- `dnsmasq` provides local DNS (config: `/etc/dnsmasq.conf`).
- Other system services: mysql, samba, ssh.

## Disks

- **Internal 128 GB NVMe**: 40 GB Linux root (`/`, ~76% used) + 76 GB ext4 `/srv/state`
  (label `state`). Windows was deleted on 2026-11-20.
- **External 2 TB Samsung USB drive** (~2010, exFAT, UUID 69AB-FB81), auto-mounted at `/srv/data`
  (`nofail` + `x-systemd.automount`). It stays exFAT so the Mac can read it directly. It holds
  ~371 GB of Colin's older files (Music, Emgineering, archiv, photos, taxes, Old, movies…) and may
  be the only copy of some of them. A new drive is planned.
- Merging `/srv/state` into root is deferred until the new drive arrives:
  `docs/homenet/merge-root-partition.md`.

## Storage layout

- `/srv/data`: files (music, cesium). Lives on an external/data drive.
- `/srv/state`: app data (databases, indexes). Lives on the internal NVMe.
- **Weekly hash check** of everything on `/srv/data` (Sunday 02:00, `hashcheck.timer`): emails
  if a file changed silently, can't be read, or went missing. Its list lives in
  `/srv/state/hashcheck/`. See `backend/services/hashcheck/README.md`.
- Apps get these paths from config (e.g. `/etc/cesium/paths.env`), never hard-coded. That way a
  new drive or a NAS can be mounted at the same path later without touching the apps.
- **Safe if the drive is unplugged:** mount with `nofail` so the server still boots, keep the empty
  mountpoint unwritable so nothing lands on the system disk, and give services that need it
  `RequiresMountsFor=/srv/data` so they just stay off.

```text
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
├── inbox/        # the inbox's day folders (backend/services/inbox/)
├── notes/        # filed inbox items: song-ideas, licks, content-tips, business, later (.md)
└── cesium/       # engineering projects + datasets
```

**Files are the truth.** No metadata files for now; folder and file names carry the info.
