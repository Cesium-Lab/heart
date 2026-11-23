"""SFO departure/arrival board.

Polls adsb.lol for aircraft near SFO, looks up routes on adsbdb.com, and serves a
split-flap style board. Standard library only. Binds to 127.0.0.1; view it through
an SSH tunnel (see README).
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HOST = os.getenv("PLANES_HOST", "127.0.0.1")
PORT = int(os.getenv("PLANES_PORT", "42901"))
AIRPORT = os.getenv("PLANES_AIRPORT", "SFO")
LAT = float(os.getenv("PLANES_LAT", "37.6213"))
LON = float(os.getenv("PLANES_LON", "-122.3790"))
RADIUS_NM = int(os.getenv("PLANES_RADIUS_NM", "40"))
CACHE_S = float(os.getenv("PLANES_CACHE_S", "10"))
ROUTE_TTL_S = 6 * 3600
UA = "cesium-planes/1.0"
HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- upstream


def fetch_json(url: str, timeout: float = 8) -> dict | None:
    try:
        with urlopen(Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
            return json.load(r)
    except HTTPError as e:
        if e.code == 404:
            return None
        raise


# Route cache: callsign -> (fetched_at, route dict or None)
_routes: dict[str, tuple[float, dict | None]] = {}
_routes_lock = threading.Lock()
_route_q: queue.Queue[str] = queue.Queue()
_queued: set[str] = set()


def route_worker() -> None:
    """Look up callsigns one at a time so we stay polite to adsbdb."""
    while True:
        cs = _route_q.get()
        route = None
        try:
            data = fetch_json(f"https://api.adsbdb.com/v0/callsign/{cs}", timeout=6)
            fr = (data or {}).get("response", {})
            fr = fr.get("flightroute") if isinstance(fr, dict) else None
            if fr:
                o, d, al = (
                    fr.get("origin") or {},
                    fr.get("destination") or {},
                    fr.get("airline") or {},
                )
                route = {
                    "iata": fr.get("callsign_iata"),
                    "airline": al.get("name"),
                    "origin": o.get("iata_code"),
                    "origin_city": o.get("municipality"),
                    "dest": d.get("iata_code"),
                    "dest_city": d.get("municipality"),
                }
        except (URLError, HTTPError, TimeoutError, ValueError, OSError):
            route = None  # cache the miss too; retried after TTL
        with _routes_lock:
            _routes[cs] = (time.time(), route)
            _queued.discard(cs)
        time.sleep(0.5)


def get_route(cs: str) -> dict | None:
    with _routes_lock:
        hit = _routes.get(cs)
        if hit and time.time() - hit[0] < ROUTE_TTL_S:
            return hit[1]
        if cs not in _queued:
            _queued.add(cs)
            _route_q.put(cs)
    return hit[1] if hit else None


# ---------------------------------------------------------------- board logic


def ascii_upper(s: str) -> str:
    """Split-flap boards only have plain letters: MONTRÉAL -> MONTREAL."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


def flight_label(cs: str, route: dict | None) -> str:
    iata = (route or {}).get("iata")
    if iata:
        i = next((n for n, c in enumerate(iata) if n >= 2 and c.isdigit()), len(iata))
        return f"{iata[:i]} {iata[i:]}".strip()
    return cs


def classify(ac: dict) -> dict | None:
    cs = (ac.get("flight") or "").strip()
    alt = ac.get("alt_baro")
    on_ground = alt == "ground"
    alt_ft = 0 if on_ground else (alt if isinstance(alt, (int, float)) else None)
    gs = ac.get("gs") or 0
    vr = ac.get("baro_rate") or ac.get("geom_rate") or 0
    dist = ac.get("dst")  # nm from the query point (SFO)
    if not cs or alt_ft is None or dist is None:
        return None
    route = get_route(cs)

    kind = None
    if route and route.get("origin") == AIRPORT:
        kind = "dep"
    elif route and route.get("dest") == AIRPORT:
        kind = "arr"
    # Route data is a best guess (multi-leg flight numbers); drop obvious contradictions.
    if kind == "dep" and not on_ground and vr < -500 and alt_ft < 10000:
        kind = None
    if kind == "arr" and not on_ground and vr > 500 and alt_ft > 5000:
        kind = None
    if on_ground and dist > 2.5:  # parked at OAK/SJC/etc.
        return None
    if kind is None:
        return {"kind": "over"} if not on_ground else None

    if kind == "dep":
        city = (route or {}).get("dest_city") or (route or {}).get("dest") or ""
        if on_ground:
            status = "AT GATE" if gs < 3 else "TAXIING" if gs < 50 else "TAKEOFF"
        elif alt_ft < 1500 and dist < 4:
            status = "TAKEOFF"
        elif vr > 300 and alt_ft < 20000:
            status = "CLIMBING"
        else:
            status = "DEPARTED"
        sort = (0 if on_ground else 1, dist)
    else:
        city = (route or {}).get("origin_city") or (route or {}).get("origin") or ""
        if on_ground:
            status = "LANDED" if gs >= 50 else "TAXIING" if gs >= 3 else "AT GATE"
            eta = 0
        else:
            # Approach paths are longer than the straight line, and a plane needs
            # ~3 nm of track per 1000 ft it still has to lose.
            track_nm = max(dist * 1.25 + 3, alt_ft / 1000 * 3)
            eta = max(1, round(track_nm / max(gs, 120) * 60))
            status = "ON FINAL" if alt_ft < 3000 and dist < 12 else f"ETA {eta} MIN"
        sort = (0 if on_ground else 1, eta)

    return {
        "kind": kind,
        "flight": flight_label(cs, route),
        "callsign": cs,
        "airline": (route or {}).get("airline") or "",
        "city": ascii_upper(city),
        "type": ac.get("t") or "",
        "reg": ac.get("r") or "",
        "alt": alt_ft,
        "gs": round(gs),
        "dist": round(dist, 1),
        "status": status,
        "lat": ac.get("lat"),
        "lon": ac.get("lon"),
        "track": ac.get("track"),
        "_sort": sort,
    }


_board: dict = {}
_board_at = 0.0
_board_lock = threading.Lock()


def build_board() -> dict:
    data = fetch_json(f"https://api.adsb.lol/v2/point/{LAT}/{LON}/{RADIUS_NM}") or {}
    deps, arrs, over = [], [], 0
    for ac in data.get("ac", []):
        row = classify(ac)
        if not row:
            continue
        if row["kind"] == "over":
            over += 1
            continue
        (deps if row["kind"] == "dep" else arrs).append(row)
    for rows in (deps, arrs):
        rows.sort(key=lambda r: r.pop("_sort"))
    return {
        "airport": AIRPORT,
        "updated": time.time(),
        "departures": deps,
        "arrivals": arrs,
        "overhead": over,
        "tracked": len(data.get("ac", [])),
    }


def board() -> dict:
    global _board, _board_at
    with _board_lock:
        if time.time() - _board_at > CACHE_S:
            try:
                _board, _board_at = build_board(), time.time()
                _board.pop("error", None)
            except (URLError, HTTPError, TimeoutError, ValueError, OSError) as e:
                _board_at = time.time()  # back off for one cache period
                _board = {**_board, "error": f"upstream: {e.__class__.__name__}"}
        return _board


# ---------------------------------------------------------------- http


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("/", "/index.html"):
            self._send(
                200, (HERE / "board.html").read_bytes(), "text/html; charset=utf-8"
            )
        elif path == "/api/board":
            self._send(200, json.dumps(board()).encode(), "application/json")
        elif path == "/health":
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    threading.Thread(target=route_worker, daemon=True).start()
    print(
        f"planes board on http://{HOST}:{PORT}/ ({AIRPORT}, {RADIUS_NM} nm)", flush=True
    )
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
