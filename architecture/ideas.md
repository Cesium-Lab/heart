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

- **Planes map**: a map view for the SFO board (`/api/board` already has lat/lon/track).
- Drive-health alerts (smartctl exporter → Prometheus/Grafana) and ntfy push notifications.
- restic backups of the irreplaceable files (offsite or to the new drive).
- ESP32 room sensors feeding Prometheus; Pi ADS-B receiver (RTL-SDR) feeding FR24/adsb.lol.

## Infrastructure

- Move storage to a NAS someday.
