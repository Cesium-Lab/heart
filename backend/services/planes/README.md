# Planes: SFO map + board API

Data for **`/planes/`** on the site: a live map of every aircraft around SFO, with the split-flap
departures/arrivals board as a drawer on the left. The page lives in the Astro build
(`frontend/src/pages/planes/index.astro`); this service only serves JSON. `/planes/map/` redirects
to `/planes/` (`frontend/astro.config.mjs`).

```text
browser → cesiumlab.net/planes/          (static page from frontend/dist)
        → fetch /api/planes/board        → Apache → this service on 127.0.0.1:42901
```

- `server.py`: standard-library Python, no venv needed. Binds `127.0.0.1:42901`.
  - `/api/planes/board`: departures, arrivals, plus lat/lon/track per flight (for a future map)
  - Board lists, each in time order like an airport board: `departures` (already gone by takeoff
    time, then taxiing, then at the gate), `arrivals` (landed, then airborne by ETA), `at_sfo`
    (on the ground at SFO, direction unknown), and `other` (everything else, nearest first). No free
    source has schedules, so times are what the service watched happen, or estimates.
  - `/api/planes/health` (and `/health`)
- Positions come from [adsb.fi](https://adsb.fi) open data (free, no key, 1 request/s allowed),
  fetched at most once every 10 s however many people are watching, and only while someone has a
  page open. If the source answers HTTP 429, the service waits as long as it asks (default 60 s).
  `PLANES_SOURCE=adsblol` switches to adsb.lol, but that caps anonymous use at 500 requests/day
  (~1.5 h of viewing), so it's only a fallback.
- `/api/planes/board` also has an `aircraft` list (every plane in range, for the map), with
  an absolute `pos_time` per position, so the map can glide planes correctly.
- Routes come from [adsbdb.com](https://www.adsbdb.com) and are cached for 6 h per callsign. They are
  best guesses (airlines reuse flight numbers across legs), so a few flights are missing or mislabeled.
- How a flight is classified (location beats the route database near SFO, because routes are often
  for a different leg of the same flight number):
  - Seen taking off from SFO, or climbing out within 12 nm while nearer SFO than OAK/SJC →
    **departure** (red).
  - Seen landing, or descending toward SFO within 25 nm (lined up on SFO rather than OAK/SJC
    beyond 8 nm) → **arrival** (green).
  - On the ground at SFO: the route decides if it mentions SFO; otherwise **at SFO** (amber,
    direction unknown, listed with departures) until the plane moves. Airport vehicles are skipped.
  - Further out, the route decides (origin/destination SFO). Everything else is other traffic (blue).
  - When the route disagrees with what the plane is doing, the board still shows its city with a "?".
  - What each plane was seen doing is remembered for 45 min (in memory; reset on restart).

Config (all optional, env vars): `PLANES_PORT`, `PLANES_AIRPORT`, `PLANES_LAT`, `PLANES_LON`,
`PLANES_RADIUS_NM`, `PLANES_CACHE_S`, `PLANES_SOURCE` (`adsbfi` or `adsblol`).

Routing: `/api/planes/` is proxied by Apache (`deploy/apache/includes/api-proxies.conf`) and by the
Astro dev server (`frontend/astro.config.mjs`), so the page works on cesiumlab.net, `http://mr-ray/`,
and `http://mr-ray:42800/`.

## Run locally

```bash
python3 backend/services/planes/server.py
curl http://127.0.0.1:42901/api/planes/board
```

## Deploy (changes the machine, so ask first)

`./scripts/deploy-startup.sh` installs and starts `planes.service`. After code changes:
`sudo systemctl restart planes`.
