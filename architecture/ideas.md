# Ideas for someday

Not planned in detail on purpose. No stack is picked for any of these; decide when one is
actually being built. They all follow the principles in [README.md](README.md): files are the
truth, any database is an index rebuildable from files (or small and backed up), and Apache keeps
serving the site.

## Data

- **Coda**: a music catalog that indexes the song folders on `/srv/data/music`, maybe SQLite.
  Rebuildable from the files. Reference sketch: `docs/api/MUSIC_STORAGE.md` (assumes Postgres).
- **Juice**: a small API that Claude/Codex can call to search lyrics and notes. Reference sketch:
  `docs/api/ASSISTANT_MEMORY.md` (assumes Postgres + a memories table).
- **Contacts**: a private people database (who someone is, how you know them, organizations,
  relationships), replacing Notion. Someday, private only. The old plan's people model lives in
  `archive/docs/api/BIG.md` and `BACKEND.md`.

## Music

- Share selected mixes with MONARCH.
- Music toys for the site, in the same style as Setlister (`/music/setlister/`) and TapTempo
  (`/music/taptempo/`):
  - **TUNER**: mic-based guitar/bass tuner with a needle display (browser only, pitch detection).
  - **SPECTRUM**: live spectrogram, waveform and loudness meter for the mic or a dropped-in mix
    (browser only).
  - **STEMS PLAYER**: play a song's stems with per-track mute and solo; files come from
    `/srv/data`, opt-in songs only.
- **MIDI logger**: Pi 3 plugged into the Alesis piano, records everything played with timestamps.
- **Logic database**: an index of Logic projects (likely part of Coda).
- **Music visualizer with I2C lights** driven by the mix or the mic.
- **Radio station**: Icecast streaming the music library.

## Nerd stuff

- **Planes traffic stats** in Grafana (arrivals/departures per hour, busiest airlines): a `/metrics`
  endpoint on the planes service for Prometheus. Placeholder note: Grafana dashboard "Planes (to do)"
  (`projects/dataviz/telemetry_server/grafana/provisioning/dashboards/planes-todo.json`).
- **Planes: bigger range when zoomed out.** Tiers by zoom, still centered on SFO: 40 nm (now),
  100 nm (~240 aircraft, ~32 KB/update), 250 nm (~430 aircraft, ~58 KB; adsb.fi's max). Cache per
  tier so viewers share fetches; look up routes only within 40 nm (plus clicked/hovered planes)
  so adsbdb isn't flooded; board/classification/replay stay at 40 nm; range ring follows the tier.
  Measured 2026-11-23. Details in `backend/services/planes/README.md` ("Later").
- Drive-health alerts (smartctl exporter → Prometheus/Grafana) and ntfy push notifications.
- restic backups of the irreplaceable files (offsite or to the new drive).
- ESP32 room sensors feeding Prometheus.
- **Live 6DOF sim viewer**: simulation data over sockets, rendered in the browser.
- **Engineering playgrounds** for the site: interactive Bode plot / root locus (a fun learning
  tool), and regex / cron / CIDR / unit-converter tools.
- **Fun pages**: a 404 game page, in-browser Doom.
- **Wall displays**: old tablets/phones as wall clocks or dashboards.
- **ADS-B feeder**: Pi 3 + RTL-SDR + 1090 MHz antenna (adsb.im image), feeding adsb.fi/adsb.lol/
  FlightAware/FR24 and the planes map. How-to and links: `backend/services/planes/README.md`.

## Homelab

Self-hosted apps, all optional, each one small and in docker or a unit like the rest:

- **Pi-hole**: network-wide ad blocking (DNS); would sit next to or replace dnsmasq.
- **Navidrome** (or Airsonic): your own Spotify for the local music files on `/srv/data`.
- **Jellyfin** (or Plex): your own Netflix for movies/shows you own (`/srv/data/movies`).
- **Photo gallery** for the photos on `/srv/data`.
- **RSS reader** (Miniflux or FreshRSS): your own Feedly; more polished than a homemade feed.
- **Wiki** (Wiki.js or BookStack) for notes and docs.
- **Homepage / Homarr**: a landing page with service status, weather, and system stats (could
  replace the hand-made dashboards).
- **n8n or Node-RED** for automations.

## Infrastructure

- Move storage to a NAS someday.
