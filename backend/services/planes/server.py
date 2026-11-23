"""SFO departure/arrival board.

Polls adsb.fi (or adsb.lol) for aircraft near SFO, looks up routes on adsbdb.com, and serves a
JSON API for the split-flap board page at /planes/ on the site. Standard library
only. Binds to 127.0.0.1; Apache proxies /api/planes/ here (see README).
"""

from __future__ import annotations

import gzip
import json
import math
import re
import signal
import os
import queue
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen

HOST = os.getenv("PLANES_HOST", "127.0.0.1")
PORT = int(os.getenv("PLANES_PORT", "42901"))
AIRPORT = os.getenv("PLANES_AIRPORT", "SFO")
LAT = float(os.getenv("PLANES_LAT", "37.6213"))
LON = float(os.getenv("PLANES_LON", "-122.3790"))
RADIUS_NM = int(os.getenv("PLANES_RADIUS_NM", "40"))
CACHE_S = float(os.getenv("PLANES_CACHE_S", "10"))
# Position source. adsb.fi allows 1 request/s with no daily cap; adsb.lol caps
# anonymous use at 500 requests/day, which a page polling every 10 s uses up in ~1.5 h.
SOURCE = os.getenv("PLANES_SOURCE", "adsbfi")
SOURCE_URLS = {
    "adsbfi": "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{nm}",
    "adsblol": "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}",
}
# One plane anywhere, for follow mode (same format, ~0.4 KB).
HEX_URLS = {
    "adsbfi": "https://opendata.adsb.fi/api/v2/hex/{hex}",
    "adsblol": "https://api.adsb.lol/v2/hex/{hex}",
}
FOLLOW_MAX = 5  # planes followed at once, across all viewers
FOLLOW_IDLE_S = 120  # a follow ends this long after its page stops asking
ROUTE_TTL_S = 6 * 3600
UA = "cesium-planes/1.0"

# ---------------------------------------------------------------- upstream


# adsb.fi allows 1 request/s. Board and follow fetches can coincide, so space them out.
_upstream_lock = threading.Lock()
_upstream_last = 0.0
UPSTREAM_GAP_S = 1.1


def _throttle(url: str) -> None:
    global _upstream_last
    if "adsbdb.com" in url:  # route lookups have their own pacing
        return
    with _upstream_lock:
        wait = _upstream_last + UPSTREAM_GAP_S - time.time()
        if wait > 0:
            time.sleep(wait)
        _upstream_last = time.time()


def fetch_json(url: str, timeout: float = 8) -> dict | None:
    _throttle(url)
    # gzip cuts the adsb.fi download from ~27 KB to ~6 KB per fetch.
    headers = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    try:
        with urlopen(Request(url, headers=headers), timeout=timeout) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return json.loads(body)
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
                    "origin_pos": [o.get("latitude"), o.get("longitude")],
                    "dest_pos": [d.get("latitude"), d.get("longitude")],
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


# What the service has watched each plane do at SFO: hex -> (phase, time).
# "dep" = seen taking off, "arr" = seen landing, "gnd" = seen parked/taxiing at SFO.
_phase: dict[str, tuple[str, float]] = {}
PHASE_TTL_S = 45 * 60


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = math.radians
    y = math.sin(r(lon2 - lon1)) * math.cos(r(lat2))
    x = math.cos(r(lat1)) * math.sin(r(lat2)) - math.sin(r(lat1)) * math.cos(
        r(lat2)
    ) * math.cos(r(lon2 - lon1))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


# Oakland and San Jose: their arrivals and departures share the sky with SFO's.
NEIGHBORS = [(37.7213, -122.2208), (37.3626, -121.9291)]


def nm_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = math.radians
    a = (
        math.sin(r(lat2 - lat1) / 2) ** 2
        + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin(r(lon2 - lon1) / 2) ** 2
    )
    return 2 * 3440.065 * math.asin(math.sqrt(a))


def angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def physical_kind(
    ac: dict, on_ground: bool, alt_ft: float, vr: float, dist: float
) -> str | None:
    """What the plane is visibly doing at SFO, regardless of the route database.

    dep/arr when movement proves it, "sfo" for a plane parked at SFO whose direction
    is unknown, None when it isn't an SFO movement (or we can't tell).
    """
    hex_ = ac.get("hex") or ""
    now = time.time()
    seen = _phase.get(hex_)
    seen = seen[0] if seen and now - seen[1] < PHASE_TTL_S else None

    if on_ground:
        if dist > 2.5:
            return None  # parked at OAK/SJC/etc.
        if seen == "air":
            _phase[hex_] = ("arr", now)  # was on approach, now on the ground: it landed
            return "arr"
        if seen in ("arr", "dep"):
            return seen
        _phase[hex_] = ("gnd", now)
        return "sfo"

    if seen == "gnd":
        _phase[hex_] = ("dep", now)  # was on the ground at SFO, now flying: it took off
        return "dep"
    if seen in ("arr", "dep"):
        return seen if dist < 40 else None
    if dist > 25 or alt_ft > 12000:
        return None

    track = ac.get("track")
    lat, lon = ac.get("lat"), ac.get("lon")
    if track is None or lat is None or lon is None:
        return None
    from_sfo = bearing(LAT, LON, lat, lon)
    to_sfo = (from_sfo + 180) % 360
    # Neighbors whose traffic passes near SFO. A plane pointed more at one of them, or
    # closer to one of them, is probably theirs.
    neighbors = [
        (bearing(lat, lon, a, o), nm_between(lat, lon, a, o)) for a, o in NEIGHBORS
    ]
    off_sfo = angle_diff(track, to_sfo)
    aimed_elsewhere = any(
        angle_diff(track, b) < off_sfo for b, d in neighbors if d < 30
    )
    nearer_elsewhere = any(d < dist for _, d in neighbors)

    # Descending toward SFO on a loose approach profile (glide path is ~320 ft/nm).
    if vr < -300 and alt_ft < dist * 400 + 1500:
        close_in = dist <= 8 and off_sfo < 60
        lined_up = off_sfo < 30 and not aimed_elsewhere
        if close_in or lined_up:
            _phase[hex_] = (
                "air",
                now,
            )  # remembered so the touchdown counts as a landing
            return "arr"
    # Climbing out of SFO: nearer SFO than OAK/SJC, on a loose climb profile. Close in, any
    # heading counts (departures often turn back over the airport); further out it must be
    # heading away from SFO.
    away = angle_diff(track, from_sfo) < 60
    if vr > 300 and dist < 12 and not nearer_elsewhere and alt_ft < dist * 1200 + 4000:
        if dist < 5 or away:
            _phase[hex_] = ("dep", now)
            return "dep"
    return None


def shown_route(route: dict | None, route_kind: str | None, kind: str | None) -> dict:
    """The route to display: adsbdb's when it fits what the plane is doing, else only what we know.

    adsbdb matches routes by flight number alone, so it is often a different leg (AS 404
    "SEA -> ORD" while landing at SFO). Then we show "? -> SFO" (or "SFO -> ?") instead.
    """
    r = route or {}
    raw = {
        "origin": r.get("origin") or "",
        "origin_city": ascii_upper(r.get("origin_city") or ""),
        "origin_pos": r.get("origin_pos"),
        "dest": r.get("dest") or "",
        "dest_city": ascii_upper(r.get("dest_city") or ""),
        "dest_pos": r.get("dest_pos"),
        "route_note": "",
    }
    if kind not in ("dep", "arr", "sfo") or (kind != "sfo" and route_kind == kind):
        return (
            raw  # not an SFO movement (nothing to check against), or the route agrees
        )
    sfo = {"code": AIRPORT, "city": "SAN FRANCISCO", "pos": [LAT, LON]}
    unknown = {"code": "", "city": "", "pos": None}
    frm = sfo if kind == "dep" else unknown
    to = sfo if kind == "arr" else unknown
    note = ""
    if route and (r.get("origin") or r.get("dest")):
        note = f"adsbdb route {r.get('origin') or '?'} -> {r.get('dest') or '?'} doesn't match what this plane is doing"
    return {
        "origin": frm["code"],
        "origin_city": frm["city"],
        "origin_pos": frm["pos"],
        "dest": to["code"],
        "dest_city": to["city"],
        "dest_pos": to["pos"],
        "route_note": note,
    }


def is_vehicle(ac: dict) -> bool:
    """Airport ground vehicles broadcast ADS-B too (OPS36, R22...): category C*, or on the
    ground with no aircraft type. They aren't flights, so they're left off map and board."""
    on_ground = ac.get("alt_baro") == "ground"
    return (ac.get("category") or "").startswith("C") or (on_ground and not ac.get("t"))


def classify(ac: dict) -> dict | None:
    cs = (ac.get("flight") or "").strip()
    alt = ac.get("alt_baro")
    on_ground = alt == "ground"
    alt_ft = 0 if on_ground else (alt if isinstance(alt, (int, float)) else None)
    gs = ac.get("gs") or 0
    vr = ac.get("baro_rate") or ac.get("geom_rate") or 0
    dist = ac.get("dst")  # nm from the query point (SFO)
    if alt_ft is None or dist is None:
        return None
    if is_vehicle(ac):
        return None
    route = get_route(cs) if cs else None

    route_kind = None
    if route and route.get("origin") == AIRPORT:
        route_kind = "dep"
    elif route and route.get("dest") == AIRPORT:
        route_kind = "arr"
    # Route data is a best guess (multi-leg flight numbers); drop obvious contradictions.
    if route_kind == "dep" and not on_ground and vr < -500 and alt_ft < 10000:
        route_kind = None
    if route_kind == "arr" and not on_ground and vr > 500 and alt_ft > 5000:
        route_kind = None

    # Near SFO, what the plane is doing beats the route database.
    phys = physical_kind(ac, on_ground, alt_ft, vr, dist)
    if phys == "sfo" and route_kind:
        kind = route_kind  # parked, and the route says which way
    else:
        kind = phys or route_kind
    if not cs and kind:
        cs = (
            ac.get("r") or ""
        )  # unnamed but clearly an SFO movement: label by registration
    if kind is None or not cs:
        return {"kind": "over"} if not on_ground and kind is None else None
    shown = shown_route(route, route_kind, kind)
    # Board city: where it's going (departures, at SFO) or coming from (arrivals); "?" if unknown.
    if kind == "arr":
        city = shown["origin_city"] or shown["origin"] or "?"
    else:
        city = shown["dest_city"] or shown["dest"] or "?"

    # Lists are in time order, like an airport board. No free source has schedules, so the
    # times are what we watched happen (takeoff/landing) or estimates from distance/speed.
    now = time.time()
    seen_at = _phase.get(ac.get("hex") or "", ("", 0.0))
    if kind == "sfo":
        status = "AT GATE" if gs < 3 else "TAXIING"
        sort = (0 if gs >= 3 else 1, dist)
        shown_time, time_kind = None, None
    elif kind == "dep":
        if on_ground:
            status = "AT GATE" if gs < 3 else "TAXIING" if gs < 50 else "TAKEOFF"
        elif alt_ft < 1500 and dist < 4:
            status = "TAKEOFF"
        elif vr > 300 and alt_ft < 20000:
            status = "CLIMBING"
        else:
            status = "DEPARTED"
        shown_time, time_kind = None, None  # unknown for planes still on the ground
        if on_ground:  # still to go: taxiing leaves before parked
            when = now + (300 if gs >= 3 else 1800)
        elif seen_at[0] == "dep":
            when = seen_at[1]  # when we saw it take off / start climbing out
            shown_time, time_kind = when, "actual"
        else:
            when = (
                now - dist / max(gs, 150) * 3600
            )  # estimated takeoff from distance flown
            shown_time, time_kind = when, "est"
        sort = (when,)
    else:
        if on_ground:
            status = "LANDED" if gs >= 50 else "TAXIING" if gs >= 3 else "AT GATE"
            eta = 0
        else:
            # Approach paths are longer than the straight line, and a plane needs
            # ~3 nm of track per 1000 ft it still has to lose.
            track_nm = max(dist * 1.25 + 3, alt_ft / 1000 * 3)
            eta = max(1, round(track_nm / max(gs, 120) * 60))
            status = "ON FINAL" if alt_ft < 3000 and dist < 12 else f"ETA {eta} MIN"
        if (
            on_ground
        ):  # already down: when we saw it land, else a guess by how far it has taxied
            when = (
                seen_at[1] if seen_at[0] == "arr" else now - (300 if gs >= 3 else 1200)
            )
            # Landing time is only shown when we actually saw it land.
            shown_time, time_kind = (
                (when, "actual") if seen_at[0] == "arr" else (None, None)
            )
        else:
            when = now + eta * 60
            shown_time, time_kind = when, "est"
        sort = (when,)

    return {
        "kind": kind,
        "hex": ac.get("hex"),  # links a board row to its plane on the map
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
        # Board TIME: takeoff/landing we saw ("actual") or an estimate ("est"); None if unknown.
        "time": round(shown_time) if shown_time else None,
        "time_kind": time_kind,
        "lat": ac.get("lat"),
        "lon": ac.get("lon"),
        "track": ac.get("track"),
        "_sort": sort,
        "_route": shown,  # reused by map_entry so the map and board agree
    }


# Recent positions per plane, recorded only from fetches the pages trigger (nothing is
# fetched when nobody is watching). In memory only: a restart wipes it.
TRACK_TTL_S = float(os.getenv("PLANES_TRACK_HOURS", "5")) * 3600  # oldest point kept
# Planes that left keep their track this long, so replay can show the last hour of traffic.
REPLAY_S = float(os.getenv("PLANES_REPLAY_MIN", "60")) * 60
TRACK_GONE_S = REPLAY_S  # drop a plane's track this long after it leaves the area
_tracks: dict[str, list[list[float]]] = {}  # hex -> [[lon, lat, alt_ft, epoch_s], ...]
_track_seen: dict[str, float] = {}  # hex -> last time it was in the data
_followed: dict[str, float] = {}  # hex -> last time a page asked to follow it
_track_info: dict[str, dict] = {}  # hex -> label/kind for replay
_tracks_lock = threading.Lock()


def record_tracks(entries: list[dict]) -> None:
    now = time.time()
    with _tracks_lock:
        for e in entries:
            h = e.get("hex")
            if not h or e.get("lat") is None:
                continue
            _track_seen[h] = now
            _track_info[h] = {
                "flight": e.get("flight"),
                "kind": e.get("kind"),
                "type": e.get("type"),
            }
            pts = _tracks.setdefault(h, [])
            point = [e["lon"], e["lat"], e.get("alt") or 0, e["pos_time"]]
            if (
                not pts or pts[-1][:2] != point[:2]
            ):  # parked planes don't pile up points
                pts.append(point)
        for h in list(_tracks):
            # A followed plane keeps its whole history (a long flight outlasts the 5 h cap),
            # until nobody has followed it for FOLLOW_IDLE_S.
            if now - _followed.get(h, 0) < FOLLOW_IDLE_S:
                continue
            if now - _track_seen.get(h, 0) > TRACK_GONE_S:
                _tracks.pop(h, None)
                _track_seen.pop(h, None)
                _track_info.pop(h, None)
                continue
            pts = _tracks[h]
            while pts and now - pts[0][3] > TRACK_TTL_S:
                pts.pop(0)


_follow_cache: dict[str, tuple[float, dict]] = {}  # hex -> (fetched_at, response)
_follow_lock = threading.Lock()


def follow(hex_: str) -> tuple[int, dict]:
    """Where one followed plane is now, wherever it is (not just near SFO)."""
    now = time.time()
    with _follow_lock:
        for h in [h for h, t in _followed.items() if now - t > FOLLOW_IDLE_S]:
            del _followed[h]
        if hex_ not in _followed and len(_followed) >= FOLLOW_MAX:
            return 429, {
                "error": f"already following {FOLLOW_MAX} planes; try again soon"
            }
        _followed[hex_] = now
        hit = _follow_cache.get(hex_)
        if hit and now - hit[0] < CACHE_S:
            return 200, hit[1]
        try:
            data = fetch_json(HEX_URLS[SOURCE].format(hex=hex_)) or {}
        except (URLError, HTTPError, TimeoutError, ValueError, OSError) as e:
            return 502, {"error": f"upstream: {e.__class__.__name__}"}
        acs = data.get("ac") or data.get("aircraft") or []
        t = data.get("now") or now
        data_now = t / 1000 if t > 1e11 else t
        entry = None
        if acs and acs[0].get("lat") is not None:
            ac = acs[0]
            ac["dst"] = nm_between(
                LAT, LON, ac["lat"], ac["lon"]
            )  # the hex lookup omits it
            row = None if is_vehicle(ac) else classify(ac)
            kind = (
                row["kind"] if row and row["kind"] in ("dep", "arr", "sfo") else "other"
            )
            entry = map_entry(
                ac, kind, data_now, row.pop("_route", None) if row else None
            )
            if entry:
                record_tracks([entry])
        body = {"hex": hex_, "aircraft": entry, "updated": data_now}
        _follow_cache[hex_] = (now, body)
        return 200, body


def replay() -> dict:
    """Every plane's points from the last REPLAY_S, compacted (~5 m precision)."""
    since = time.time() - REPLAY_S
    with _tracks_lock:
        out = []
        for h, pts in _tracks.items():
            recent = [
                [round(p[0], 4), round(p[1], 4), int(p[2]), int(p[3])]
                for p in pts
                if p[3] >= since
            ]
            if recent:
                out.append({"hex": h, **_track_info.get(h, {}), "points": recent})
    return {"since": int(since), "now": int(time.time()), "planes": out}


def find(query: str) -> tuple[int, dict]:
    """Look up a flight anywhere: callsign (UAL2482), flight number (UA2482), or
    registration (N566AS). One or two small upstream requests per search."""
    q = re.sub(r"[^A-Z0-9-]", "", query.upper())[:10]
    if len(q) < 2:
        return 400, {"error": "type a flight, callsign, or registration"}
    base = (
        "https://opendata.adsb.fi/api/v2"
        if SOURCE == "adsbfi"
        else "https://api.adsb.lol/v2"
    )
    tries = [f"{base}/callsign/{q}"]
    if re.fullmatch(
        r"[A-Z0-9]{2}\d{1,4}[A-Z]?", q
    ):  # IATA flight number: ask adsbdb for the callsign
        r = None
        try:
            r = fetch_json(f"https://api.adsbdb.com/v0/callsign/{q}", timeout=6)
        except (URLError, HTTPError, TimeoutError, ValueError, OSError):
            pass
        fr = (r or {}).get("response") or {}
        icao = (
            fr.get("flightroute", {}).get("callsign_icao")
            if isinstance(fr, dict)
            else None
        )
        if icao and icao != q:
            tries.insert(0, f"{base}/callsign/{icao}")
    tries.append(f"{base}/registration/{q}")
    for url in tries:
        try:
            data = fetch_json(url) or {}
        except (URLError, HTTPError, TimeoutError, ValueError, OSError):
            continue
        acs = [
            a
            for a in (data.get("ac") or data.get("aircraft") or [])
            if a.get("lat") is not None
        ]
        if acs:
            a = acs[0]
            return 200, {
                "hex": a.get("hex"),
                "callsign": (a.get("flight") or "").strip(),
                "reg": a.get("r"),
            }
    return 404, {"error": f"no live aircraft found for {q}"}


_wx: tuple[float, dict] = (0.0, {})
_wx_lock = threading.Lock()
WX_URL = "https://aviationweather.gov/api/data/metar?ids=K{icao}&format=json"


def weather() -> dict:
    """Current METAR for the airport, cached 10 min (fetched only when a page asks)."""
    global _wx
    with _wx_lock:
        if time.time() - _wx[0] < 600 and _wx[1]:
            return _wx[1]
        try:
            rows = fetch_json(WX_URL.format(icao=AIRPORT)) or []
        except (URLError, HTTPError, TimeoutError, ValueError, OSError) as e:
            return {**_wx[1], "error": f"upstream: {e.__class__.__name__}"}
        m = rows[0] if isinstance(rows, list) and rows else {}
        body = {
            "station": f"K{AIRPORT}",
            "raw": m.get("rawOb"),
            "temp_c": m.get("temp"),
            "wind_dir": m.get("wdir"),
            "wind_kt": m.get("wspd"),
            "gust_kt": m.get("wgst"),
            "visibility_sm": m.get("visib"),
            "clouds": m.get("clouds") or [],
            "category": m.get("fltCat"),  # VFR / MVFR / IFR / LIFR
            "observed": m.get("obsTime"),
            "link": f"https://aviationweather.gov/data/metar/?id=K{AIRPORT}&hours=0&decoded=yes",
        }
        _wx = (time.time(), body)
        return body


def track_for(hex_: str) -> list[list[float]]:
    with _tracks_lock:
        return list(_tracks.get(hex_, []))


_board: dict = {}
_board_at = 0.0
_retry_at = 0.0  # set when the source says "slow down" (HTTP 429)
_board_lock = threading.Lock()


def map_entry(ac: dict, kind: str, data_now: float, shown: dict | None) -> dict | None:
    """Every aircraft with a position, for the map. kind: dep, arr, sfo, or other."""
    lat, lon = ac.get("lat"), ac.get("lon")
    if lat is None or lon is None:
        return None
    cs = (ac.get("flight") or "").strip()
    alt = ac.get("alt_baro")
    route = get_route(cs) if cs else None
    return {
        "hex": ac.get("hex"),
        "kind": kind,
        "flight": flight_label(cs, route) if cs else (ac.get("r") or ac.get("hex")),
        "callsign": cs,
        "airline": (route or {}).get("airline") or "",
        **(shown or shown_route(route, None, None)),
        "type": ac.get("t") or "",
        "reg": ac.get("r") or "",
        "ground": alt == "ground",
        "alt": 0 if alt == "ground" else alt if isinstance(alt, (int, float)) else None,
        "gs": ac.get("gs"),
        "track": ac.get("track"),
        "vr": ac.get("baro_rate") or ac.get("geom_rate"),
        "squawk": ac.get("squawk") or "",
        "lat": lat,
        "lon": lon,
        # When this position was received (epoch s). The map dead-reckons from here;
        # an absolute time stays correct however long the board sits in the cache.
        "pos_time": round(data_now - (ac.get("seen_pos") or 0), 2),
    }


def build_board() -> dict:
    url = SOURCE_URLS[SOURCE].format(lat=LAT, lon=LON, nm=RADIUS_NM)
    data = fetch_json(url) or {}
    # Same readsb format from both sources, except the list key and `now` units.
    acs = data.get("ac") or data.get("aircraft") or []
    now = data.get("now") or time.time()
    data_now = now / 1000 if now > 1e11 else now  # adsb.lol sends ms, adsb.fi seconds
    deps, arrs, at_sfo, other, over, aircraft = [], [], [], [], 0, []
    for ac in acs:
        if is_vehicle(ac):
            continue
        row = classify(ac)
        kind = row["kind"] if row and row["kind"] in ("dep", "arr", "sfo") else "other"
        entry = map_entry(ac, kind, data_now, row.pop("_route", None) if row else None)
        if entry:
            aircraft.append(entry)
            if kind == "other":
                o, d = entry["origin"], entry["dest"]
                other.append(
                    {
                        "hex": entry["hex"],
                        "flight": entry["flight"],
                        "callsign": entry["callsign"],
                        "airline": entry["airline"],
                        "type": entry["type"],
                        "route": f"{o or '?'}-{d or '?'}" if (o or d) else "",
                        "alt": entry["alt"],
                        "ground": entry["ground"],
                        "dist": round(ac.get("dst") or 0, 1),
                    }
                )
        if not row:
            continue
        if row["kind"] == "over":
            over += 1
            continue
        {"arr": arrs, "dep": deps, "sfo": at_sfo}[row["kind"]].append(row)
    record_tracks(aircraft)
    cutoff = time.time() - PHASE_TTL_S
    for h in [h for h, (_, t) in _phase.items() if t < cutoff]:
        del _phase[h]
    for rows in (deps, arrs, at_sfo):
        rows.sort(key=lambda r: r.pop("_sort"))
    other.sort(key=lambda r: r["dist"])  # nearest first
    return {
        "airport": AIRPORT,
        "updated": time.time(),
        "departures": deps,
        "arrivals": arrs,
        "at_sfo": at_sfo,  # on the ground at SFO, direction unknown
        "other": other,  # everything else in range
        "overhead": over,
        "tracked": len(acs),
        "source": SOURCE,
        # Callsigns still waiting for a route lookup (all of them right after a restart).
        "routes_pending": _route_q.qsize(),
        "aircraft": aircraft,
    }


def board() -> dict:
    global _board, _board_at, _retry_at
    with _board_lock:
        now = time.time()
        if now - _board_at > CACHE_S and now >= _retry_at:
            try:
                _board, _board_at = build_board(), now
                _board.pop("error", None)
            except HTTPError as e:
                _board_at = now
                if e.code == 429:  # rate limited: wait as long as asked (default 60 s)
                    wait = e.headers.get("Retry-After", "60")
                    _retry_at = now + (float(wait) if wait.isdigit() else 60)
                _board = {**_board, "error": f"upstream: HTTP {e.code}"}
            except (URLError, TimeoutError, ValueError, OSError) as e:
                _board_at = now  # back off for one cache period
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
        # Data only. The page lives in the Astro site (frontend/src/pages/planes/),
        # and Apache proxies /api/planes/ here.
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/api/planes/board":
            self._send(200, json.dumps(board()).encode(), "application/json")
        elif m := re.fullmatch(r"/api/planes/track/([0-9a-f~]{1,8})", path):
            body = {"hex": m[1], "points": track_for(m[1])}
            self._send(200, json.dumps(body).encode(), "application/json")
        elif path == "/api/planes/replay":
            self._send(
                200,
                json.dumps(replay(), separators=(",", ":")).encode(),
                "application/json",
            )
        elif path == "/api/planes/weather":
            self._send(200, json.dumps(weather()).encode(), "application/json")
        elif m := re.fullmatch(
            r"/api/planes/find/([A-Za-z0-9 -]{2,12})", unquote(path)
        ):
            code, body = find(m[1])
            self._send(code, json.dumps(body).encode(), "application/json")
        elif m := re.fullmatch(r"/api/planes/follow/([0-9a-f~]{1,8})", path):
            code, body = follow(m[1])
            self._send(code, json.dumps(body).encode(), "application/json")
        elif path in ("/api/planes/health", "/health"):
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args) -> None:
        pass


# ---------------------------------------------------------------- snapshot
# Everything above lives in memory. A snapshot every minute (and on stop) lets the service pick
# up where it left off after a crash or restart. It goes to /run/planes (systemd's
# RuntimeDirectory: a RAM disk, so a reboot still wipes it). Off when run by hand.
STATE_DIR = os.getenv("PLANES_STATE_DIR") or os.getenv("RUNTIME_DIRECTORY") or ""
STATE_FILE = os.path.join(STATE_DIR, "state.json") if STATE_DIR else ""
SNAPSHOT_EVERY_S = 60
SNAPSHOT_MAX_AGE_S = 6 * 3600  # older snapshots are ignored at startup


def save_snapshot() -> None:
    if not STATE_FILE:
        return
    with _routes_lock:
        routes = {k: list(v) for k, v in _routes.items()}
    with _tracks_lock:
        tracks = {k: list(v) for k, v in _tracks.items()}
        state = {
            "saved": time.time(),
            "routes": routes,
            "phase": {k: list(v) for k, v in dict(_phase).items()},  # copied in one step
            "tracks": tracks,
            "track_seen": dict(_track_seen),
            "track_info": dict(_track_info),
        }
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(state, f, separators=(",", ":"))
        os.replace(
            tmp, STATE_FILE
        )  # atomic: a crash mid-write never leaves a broken file
    except OSError as e:
        print(f"snapshot not saved: {e}", flush=True)


def load_snapshot() -> None:
    if not STATE_FILE or not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (OSError, ValueError) as e:
        print(f"snapshot ignored: {e}", flush=True)
        return
    age = time.time() - state.get("saved", 0)
    if age > SNAPSHOT_MAX_AGE_S:
        print(f"snapshot ignored: {age / 3600:.1f} h old", flush=True)
        return
    with _routes_lock:
        _routes.update({k: (v[0], v[1]) for k, v in state.get("routes", {}).items()})
    with _tracks_lock:
        _phase.update({k: (v[0], v[1]) for k, v in state.get("phase", {}).items()})
        _tracks.update(state.get("tracks", {}))
        _track_seen.update(state.get("track_seen", {}))
        _track_info.update(state.get("track_info", {}))
    print(
        f"snapshot loaded ({age:.0f}s old): {len(_routes)} routes, {len(_tracks)} tracks",
        flush=True,
    )


def snapshot_worker() -> None:
    while True:
        time.sleep(SNAPSHOT_EVERY_S)
        save_snapshot()


def main() -> None:
    load_snapshot()
    if STATE_FILE:
        threading.Thread(target=snapshot_worker, daemon=True).start()

        def stop(signum: int, _frame: object) -> None:
            save_snapshot()  # systemctl stop/restart sends SIGTERM: save the latest first
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, stop)
    threading.Thread(target=route_worker, daemon=True).start()
    print(
        f"planes API on http://{HOST}:{PORT}/api/planes/board ({AIRPORT}, {RADIUS_NM} nm)",
        flush=True,
    )
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
