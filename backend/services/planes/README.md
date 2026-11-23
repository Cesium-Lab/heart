# Planes: SFO board

A split-flap style departures/arrivals board for SFO, built from live ADS-B data.
**Private**: it binds to localhost only and is not part of the public Astro site. View it through an SSH tunnel.

- `server.py`: standard-library Python, no venv needed. Binds `127.0.0.1:5901`.
  - `/`: the board (`board.html`)
  - `/api/board`: JSON (departures, arrivals, plus lat/lon/track per flight for the future map)
  - `/health`
- Positions come from [adsb.lol](https://api.adsb.lol) (free, no key), fetched at most once
  every 10 s and only while someone has the page open.
- Routes come from [adsbdb.com](https://www.adsbdb.com) and are cached for 6 h per callsign. They are
  best guesses (airlines reuse flight numbers across legs), so a few flights are missing or mislabeled.
- How a flight is classified: the route says origin SFO → departure, destination SFO → arrival.
  Planes on the ground more than 2.5 nm from SFO are ignored (OAK/SJC). Everything else counts as an overflight.

Config (all optional, env vars): `PLANES_PORT`, `PLANES_AIRPORT`, `PLANES_LAT`, `PLANES_LON`,
`PLANES_RADIUS_NM`, `PLANES_CACHE_S`.

## Run locally

```bash
python3 backend/services/planes/server.py   # http://127.0.0.1:5901/
```

## Deploy (changes the machine, so ask first)

`./scripts/deploy-startup.sh` installs and starts `planes.service`, or do it by hand:

```bash
sudo install -m 0644 deploy/systemd/planes.service /etc/systemd/system/planes.service
sudo systemctl daemon-reload && sudo systemctl enable --now planes.service
```

## View it from the Mac

```bash
ssh -L 5901:127.0.0.1:5901 cskin@mr-ray    # then open http://localhost:5901/
```

Or add `LocalForward 5901 127.0.0.1:5901` under the mr-ray `Host` entry in `~/.ssh/config`,
and the tunnel opens with every ssh session.
