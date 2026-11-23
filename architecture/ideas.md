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
- **ADS-B feeder**: Pi 3 + RTL-SDR + 1090 MHz antenna (adsb.im image), feeding adsb.fi/adsb.lol/
  FlightAware/FR24 and the planes map. How-to and links: `backend/services/planes/README.md`.

## Infrastructure

- Move storage to a NAS someday.
