"""Server-side GetSongBPM proxy for SETLISTER.EXE."""
from __future__ import annotations

import json
import os
import time
from collections import deque
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

API_BASE = "https://api.getsong.co"
API_KEY = os.getenv("GETSONGBPM_API_KEY", "").strip()
PORT = int(os.getenv("SETLISTER_PORT", "5702"))
TIMEOUT = float(os.getenv("SETLISTER_API_TIMEOUT", "8"))
CACHE_TTL = int(os.getenv("SETLISTER_CACHE_TTL", "3600"))
RATE_LIMIT = int(os.getenv("SETLISTER_RATE_LIMIT", "60"))

app = Flask(__name__)
_cache: dict[str, tuple[float, list[dict]]] = {}
_requests: deque[float] = deque()
_lock = Lock()


def normalize_key(raw: object) -> str | None:
    """Convert API values such as Em, C#m, or Bb major to Setlister keys."""
    if not raw:
        return None
    value = str(raw).strip().replace("♯", "#").replace("♭", "b")
    lower = value.lower()
    minor = lower.endswith("m") or "minor" in lower
    root = value.split()[0]
    if root.lower().endswith("minor"):
        root = root[:-5]
    elif root.lower().endswith("major"):
        root = root[:-5]
    elif root.endswith("m"):
        root = root[:-1]
    root = root.strip().capitalize().replace("#", "♯").replace("b", "♭")
    # Setlister uses one spelling for each pitch class.
    root = {"D♭": "C♯", "D♯": "E♭", "G♭": "F♯", "G♯": "A♭", "A♯": "B♭"}.get(root, root)
    if root not in {"C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"}:
        return None
    return f"{root} {'minor' if minor else 'major'}"


def artist_name(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("name", ""))
    if isinstance(value, list) and value:
        return artist_name(value[0])
    return str(value or "")


def normalize_song(item: dict) -> dict:
    artist = item.get("artist", {})
    genres = artist.get("genres") if isinstance(artist, dict) else []
    if not isinstance(genres, list):
        genres = []
    album = item.get("album", {})
    if isinstance(album, list):
        album = album[0] if album else {}
    if not isinstance(album, dict):
        album = {}
    return {
        "sourceId": str(item.get("id", "")),
        "title": str(item.get("title", item.get("song_title", ""))),
        "artist": artist_name(artist),
        "album": str(album.get("title", "")),
        "year": album.get("year"),
        "timeSignature": item.get("time_sig"),
        "key": normalize_key(item.get("key_of")),
        "bpm": float(item["tempo"]) if str(item.get("tempo", "")).replace(".", "", 1).isdigit() else None,
        "danceability": item.get("danceability"),
        "acousticness": item.get("acousticness"),
        "tags": [str(tag) for tag in genres[:5]],
        "sourceUrl": str(item.get("uri", item.get("song_uri", ""))),
    }


def allowed_request() -> bool:
    now = time.monotonic()
    with _lock:
        while _requests and _requests[0] < now - 60:
            _requests.popleft()
        if len(_requests) >= RATE_LIMIT:
            return False
        _requests.append(now)
        return True


def upstream_search(title: str, artist: str) -> list[dict]:
    lookup = f"song:{title} artist:{artist}" if artist else title
    params = urlencode({"type": "both" if artist else "song", "lookup": lookup, "limit": 10})
    req = Request(f"{API_BASE}/search/?{params}", headers={"X-API-KEY": API_KEY, "Accept": "application/json", "User-Agent": "mr-ray-setlister/1.0"})
    with urlopen(req, timeout=TIMEOUT) as response:
        payload = json.load(response)
    items = payload.get("search", []) if isinstance(payload, dict) else payload
    return [normalize_song(item) for item in items if isinstance(item, dict)]


@app.get("/api/setlister/health")
def health():
    return jsonify({"status": "ok", "configured": bool(API_KEY)})


@app.get("/api/setlister/search")
def search():
    if not API_KEY:
        return jsonify({"error": "Song lookup is not configured on the server."}), 503
    title = request.args.get("title", "").strip()
    artist = request.args.get("artist", "").strip()
    if len(title) < 2:
        return jsonify({"error": "Enter at least two characters of a song title."}), 400
    if len(title) > 120 or len(artist) > 120:
        return jsonify({"error": "Search terms are too long."}), 400
    if not allowed_request():
        return jsonify({"error": "Too many searches. Please wait a minute."}), 429

    # One-character artist refinements are too broad for the upstream API.
    # Search by title alone until at least two artist characters are present.
    search_artist = artist if len(artist) >= 2 else ""
    cache_key = f"{title.casefold()}|{search_artist.casefold()}"
    cached = _cache.get(cache_key)
    if cached and cached[0] > time.monotonic():
        return jsonify({"results": cached[1], "cached": True})
    try:
        results = upstream_search(title, search_artist)
    except HTTPError as exc:
        status = 429 if exc.code == 429 else 502
        return jsonify({"error": "The song database rejected the request.", "upstreamStatus": exc.code}), status
    except (URLError, TimeoutError, json.JSONDecodeError):
        return jsonify({"error": "The song database is temporarily unavailable."}), 502

    with _lock:
        if len(_cache) > 500:
            _cache.clear()
        _cache[cache_key] = (time.monotonic() + CACHE_TTL, results)
    return jsonify({"results": results, "cached": False})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT)
