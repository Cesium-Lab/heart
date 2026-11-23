# Planes: SFO map + board

**`/planes/`** on the site is a live map of every aircraft within 40 nm of SFO, with a split-flap
departures/arrivals board in a drawer. The page lives in the Astro build
(`frontend/src/pages/planes/index.astro`); this service (`server.py`) only serves JSON.
`/planes/map/` redirects to `/planes/` (`frontend/astro.config.mjs`).

```text
browser → cesiumlab.net/planes/              static page from frontend/dist
        → fetch /api/planes/...              Apache → planes service on 127.0.0.1:42901
                                             → adsb.fi (positions), adsbdb.com (routes)
```

Routing: `/api/planes/` is proxied by Apache (`deploy/apache/includes/api-proxies.conf`) and by the
Astro dev server (`frontend/astro.config.mjs`), so the page works on cesiumlab.net, `http://mr-ray/`,
and `http://mr-ray:42800/`.

## The page

- **Map** (MapLibre GL + OpenFreeMap "Positron" tiles, no API key). Planes point along their
  heading and glide between updates (dead reckoning from each position's timestamp).
  - Colors: green arriving SFO, red departing SFO, amber on the ground at SFO with direction
    unknown, blue other traffic. Planes on the ground are smaller and faded.
  - Callsign labels; the 40 nm range ring; a "data Ns ago" timer (red past 30 s).
  - **Search** (top bar, or press `/`): flight number (`UA 2482`), callsign (`UAL2482`), or
    registration (`N566AS`). Planes on the map are found instantly; otherwise the service looks the
    flight up anywhere and offers to follow it.
  - **Weather chip**: SFO's latest METAR (temperature, wind, visibility, ceiling, flight category
    with a colored dot), linking to the full report on aviationweather.gov.
  - **Replay**: scrub the last hour of recorded traffic at 1×/10×/60×; LIVE returns to now.
  - Hover or click a plane: its past track (solid, colored by altitude) and a dashed great-circle
    line to its destination. Click opens an info panel (route, type, registration, altitude,
    speed, vertical rate, heading, squawk, takeoff/landing time) with links to the real flight on
    Flightradar24, FlightAware, and the adsb.fi globe.
- **Board drawer** (left edge, chevron tab; open/closed is remembered).
  - Tabs **SFO** (ALL / DEPARTURES / ARRIVALS / AT SFO) and **OTHER** (flight, route, altitude,
    nearest first). Every flight gets a row; the list scrolls.
  - SFO rows have a **TIME** column: white = what the service saw (takeoff, landing), amber = an
    estimate (takeoff from distance flown, arrival ETA), `--:--` = unknown (e.g. still at the gate).
    No free source has airline schedules, so there are no scheduled times.
  - While the drawer is open, hovering a plane highlights its row (and scrolls to it), hovering a
    row rings the plane. Clicking a row selects the plane and snaps the map to it. An edge arrow
    points to a hovered/selected plane that is off screen.
  - **MAP: ALL / DIM / ONLY** fades or hides planes that aren't in the current list.
- **Follow mode** (button in the info panel). The map stays on the plane for its whole journey,
  beyond the 40 nm area. Toggles: **Auto zoom** (in near the ground, out at cruise) and **Rotate**
  (plane points up). Dragging pauses (Resume button). Ends when the plane has landed and slowed
  below 40 kt, or after 5 min without a signal, with a popup: flight, route, type, registration,
  time, how long it was followed, distance flown, max altitude, top speed, and a mini map.
- Tab, map filter, and follow camera choices are saved in the browser (`localStorage`).

## API

| Endpoint                   | What it returns                                                                                                                                                                  |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/api/planes/board`        | Board lists `departures`, `arrivals`, `at_sfo`, `other`, plus `aircraft` (every plane in range for the map, with an absolute `pos_time`), `updated`, `routes_pending`, `source`. |
| `/api/planes/track/<hex>`  | What the service remembers of one plane's path: `[[lon, lat, alt_ft, epoch_s], ...]`. The map loads it on hover/select.                                                          |
| `/api/planes/replay`       | Every plane's points from the last hour (`PLANES_REPLAY_MIN`), compacted: `{since, now, planes: [{hex, flight, kind, type, points}]}`.                                           |
| `/api/planes/find/<query>` | Looks a flight up anywhere by callsign, flight number (via adsbdb), or registration: `{hex, callsign, reg}`, or 404. One or two small upstream requests per search.              |
| `/api/planes/weather`      | SFO's latest METAR from aviationweather.gov (cached 10 min, fetched only when a page asks): temperature, wind, visibility, clouds, category, raw text, link.                     |
| `/api/planes/follow/<hex>` | Where one plane is now, anywhere in the world (follow mode). HTTP 429 when 5 planes are already being followed.                                                                  |
| `/api/planes/health`       | `{"ok": true}` (also at `/health`).                                                                                                                                              |

Board lists are in time order, like an airport board. No free source has schedules, so times are
what the service watched happen (takeoff, landing) or estimates from distance and speed:
departures = already gone (by takeoff time), then taxiing, then at the gate; arrivals = landed, then
airborne by ETA; `at_sfo` = taxiing first; `other` = nearest first.

## Data sources and limits

- **Positions: [adsb.fi](https://adsb.fi) open data** (free, no key, 1 request/s). The board fetch
  happens at most every 10 s however many people are watching, and **only while someone has a page
  open**. Follow mode adds one ~0.4 KB lookup per followed plane every 10 s, only while followed.
  All adsb.fi requests are spaced at least 1.1 s apart and gzip-compressed (~6 KB per board fetch).
  On HTTP 429 the service waits as long as asked (default 60 s).
  `PLANES_SOURCE=adsblol` switches to adsb.lol, but that caps anonymous use at 500 requests/day
  (~1.5 h of viewing), so it's only a fallback.
- **Weather: [aviationweather.gov](https://aviationweather.gov)** METAR API (free, no key), at most
  once per 10 min, only while a page is open.
- **Routes: [adsbdb.com](https://www.adsbdb.com)**, looked up once per callsign (one at a time,
  ~0.5 s apart) and cached 6 h. adsbdb matches by flight number only, so routes are often for a
  different leg (AS 404 "SEA → ORD" while landing at SFO).

## How flights are classified

Near SFO, what the plane is doing beats the route database:

- Seen taking off from SFO, or climbing out within 12 nm while nearer SFO than OAK/SJC →
  **departure**.
- Seen landing, or descending toward SFO within 25 nm on a loose approach profile (lined up on SFO
  rather than OAK/SJC beyond 8 nm) → **arrival**.
- On the ground at SFO: the route decides if it mentions SFO; otherwise **at SFO** (direction
  unknown) until the plane moves. Airport ground vehicles are dropped entirely.
- Further out, the route decides (origin or destination SFO). Everything else is **other**.
- When the route contradicts what the plane is doing, only the known part is shown: `? → SFO` for an
  arrival, `SFO → ?` for a departure, with a note in the info panel; the board's city shows `?`.

## What the service remembers (all in memory; a restart wipes it)

| What                                         | Kept for                                                                                                                                                                             |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Routes per callsign                          | 6 h                                                                                                                                                                                  |
| SFO weather (METAR)                          | 10 min                                                                                                                                                                               |
| What each plane was seen doing at SFO        | 45 min                                                                                                                                                                               |
| Track points (only from page-driven fetches) | `PLANES_TRACK_HOURS` (default 5 h); a plane's track is dropped `PLANES_REPLAY_MIN` (default 60 min) after it leaves the area, so replay can show it; parked planes add no new points |
| Followed planes' tracks                      | Whole journey (exempt from the limits above) until nobody has followed the plane for 2 min                                                                                           |

Roughly 3-6 MB on top of the ~13 MB the service uses (more of it now, since planes that left are
kept an hour for replay).

## Config

All optional env vars: `PLANES_PORT` (42901), `PLANES_HOST` (127.0.0.1), `PLANES_AIRPORT` (SFO),
`PLANES_LAT` / `PLANES_LON`, `PLANES_RADIUS_NM` (40), `PLANES_CACHE_S` (10), `PLANES_SOURCE`
(`adsbfi` or `adsblol`), `PLANES_TRACK_HOURS` (5), `PLANES_REPLAY_MIN` (60).

## Run locally

```bash
python3 backend/services/planes/server.py
curl http://127.0.0.1:42901/api/planes/board
```

The page: `npm --prefix frontend run dev` and open `http://localhost:42800/planes/` (the dev server
proxies `/api/planes/` to the service).

## Deploy (changes the machine, so ask first)

- Service: `./scripts/deploy-startup.sh` installs and starts `planes.service`. After code changes:
  `sudo systemctl restart planes` (this also clears everything the service remembers; routes refill
  within about a minute, shown as "looking up N routes…" on the map).
- Page: `npm --prefix frontend run build` publishes it; Apache serves the new files immediately.
