"""Listen & watch: a checklist of videos and songs, shown on the public /music/ page.

Stored as one Markdown list, /srv/data/notes/listen.md (same item format as the notes buckets):

    ## Bold as Love (John Mayer) · Live in LA
    - link: https://www.youtube.com/watch?v=…
    - by: John Mayer
    - added: 2026-11-26
    - done: 2026-11-27          (only once checked off)

Titles come from the link (YouTube/Shorts and Spotify oEmbed, Instagram's caption) when none is
typed. Anyone can read the list (GET /inbox/listen.json); adding, checking, and deleting need
the home network / Tailscale or the inbox login (server.py routes). Deletes go to
notes/.deleted.md like the other notes.
"""

from __future__ import annotations

import hashlib
import threading
from datetime import date, datetime
from urllib.parse import urlparse

import notes

PATH = notes.NOTES / "listen.md"
_lock = threading.Lock()


class Stale(Exception):
    """The list changed since the page loaded it (another tab or device)."""


def load() -> tuple[list[dict], str]:
    text = PATH.read_text(encoding="utf-8") if PATH.exists() else ""
    return notes.parse(text), hashlib.sha1(text.encode()).hexdigest()[:12]


def _write(items: list[dict]) -> None:
    notes.NOTES.mkdir(parents=True, exist_ok=True)
    body = "# Listen & watch\n\n" + "\n".join(notes.item_md(i) for i in items)
    PATH.write_text(body, encoding="utf-8")


def title_for(url: str) -> tuple[str, str]:
    """(title, creator) for a link: the video's / track's own title when we can get it."""
    info = notes.link_info(url) if url else {}
    cap = " ".join((info.get("caption") or "").split("\n")[0].split())
    if notes.IG.search(url) and len(cap) > 80:  # a reel's caption, not a real title
        cap = cap[:80].rsplit(" ", 1)[0] + "…"
    if cap:
        return cap, info.get("creator", "")
    u = urlparse(url)
    return (u.netloc.removeprefix("www.") + u.path).rstrip("/") or url, ""


def public() -> dict:
    items, version = load()
    out = []
    for i, it in enumerate(items):
        out.append(
            {
                "i": i,
                "title": it["title"],
                "link": notes.field(it, "link"),
                "by": notes.field(it, "by"),
                "added": notes.field(it, "added"),
                "done": notes.field(it, "done"),
            }
        )
    return {"items": out, "version": version}


def add(link: str, title: str = "") -> str:
    link = link.strip()
    if not link and not title.strip():
        return "Paste a link (or type a title)."
    got, by = title_for(link) if link and not title.strip() else (title.strip(), "")
    item = {"title": got, "fields": [], "extra": []}
    if link:
        item["fields"].append(("link", link))
    if by:
        item["fields"].append(("by", by))
    item["fields"].append(("added", str(date.today())))
    with _lock:
        items, _ = load()
        _write(items + [item])
    return f"Added: {got}"


def toggle(i: int, version: str) -> None:
    with _lock:
        items, v = load()
        if v != version:
            raise Stale
        it = items[i]
        notes.set_field(
            it, "done", "" if notes.field(it, "done") else str(date.today())
        )
        _write(items)


def delete(i: int, version: str) -> None:
    with _lock:
        items, v = load()
        if v != version:
            raise Stale
        gone = items.pop(i)
        stamp = f"{datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}"
        with (notes.NOTES / ".deleted.md").open("a", encoding="utf-8") as fh:
            fh.write(
                f"<!-- from listen.md, deleted {stamp} -->\n{notes.item_md(gone)}\n"
            )
        _write(items)
