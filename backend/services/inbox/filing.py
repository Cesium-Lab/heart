"""Sort inbox entries into bucket lists in /srv/data/notes/ (see FILING.md).

A Claude Code session runs this, shows Colin the plan, and applies it only after he approves:

    filing.py unfiled                 # every unfiled entry as JSON (with link captions)
    filing.py caption <url>           # one link's caption (Instagram reel/post, YouTube)
    filing.py apply plan.json         # file / delete the approved items, mark them filed
    filing.py thumbs                  # save missing thumbnails for items already filed
    filing.py unmark 2026-11-25#4     # undo a filed mark (the bucket item stays)

Bucket items are appended to the Markdown lists (notes.py); inbox entries stay where they are
with a `_filed → licks.md_` line. Deletes go through the inbox's own delete (the day's .deleted/).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notes  # noqa: E402
import server  # noqa: E402  (the inbox's own read/write functions)

CACHE = server.DIR / ".captions.json"
LINK = re.compile(r"https?://\S+")


def captions(urls: list[str]) -> dict[str, dict]:
    return notes.captions(urls, CACHE)


def unfiled() -> list[dict]:
    out = []
    for day in sorted(server.days_with_entries()):
        for e in server.read_day(day):
            if e.get("filed"):
                continue
            texts = [e["text"]] + [r["text"] for r in e["replies"]]
            links = [u.rstrip(").,") for t in texts for u in LINK.findall(t)]
            files = e["files"] + [f for r in e["replies"] for f in r["files"]]
            out.append(
                {
                    "id": f"{day}#{e['n']}",
                    "text": e["text"],
                    "replies": [
                        {"id": r["id"], "text": r["text"], "files": r["files"]}
                        for r in e["replies"]
                    ],
                    "files": [str(server.day_dir(day) / f) for f in files],
                    "links": captions(links) if links else {},
                    "pinned": bool(e.get("pinned")),
                }
            )
    return out


def _split(ident: str) -> tuple[str, int]:
    day, n = ident.split("#")
    return day, int(n)


def bucket_item(p: dict) -> dict:
    """A plan line -> a bucket item (format in FILING.md), with a saved thumbnail."""
    day, n = _split(p["id"])
    links = p.get("links", [])
    f = [("from", f"[{p['id']}](/inbox/{day}#{n})"), ("filed", str(date.today()))]
    f += [("link", u) for u in links]
    if p.get("caption"):
        f.append(("caption", " / ".join(p["caption"].splitlines())))
    if links:
        info = captions(links[:1])[links[0]]
        if thumb := notes.save_thumb(links[0], info.get("thumb_url", "")):
            f.append(("thumb", thumb))
    f += [("file", x) for x in p.get("files", [])]
    f += [("note", notes.clean_note(p["note"]))] if p.get("note") else []
    return {"title": p["title"], "fields": f, "extra": []}


def apply(plan: list[dict]) -> None:
    """plan: [{"id", "action": "file"|"delete"|"skip", "bucket", "title", "links", "caption",
    "files", "note"}]. An entry may be filed into several buckets (one item each)."""
    for p in plan:  # check everything before writing anything
        if p["action"] == "file" and p.get("bucket") not in notes.BUCKETS:
            sys.exit(f"{p['id']}: unknown bucket {p.get('bucket')!r}")
    filed: dict[str, list[str]] = {}
    for p in plan:
        if p["action"] == "file":
            notes.append(p["bucket"], bucket_item(p))
            filed.setdefault(p["id"], []).append(f"{p['bucket']}.md")
    for ident, where in filed.items():
        day, n = _split(ident)
        names = ", ".join(dict.fromkeys(where))
        server.set_filed(day, n, names)
        print(f"filed {ident} → {names} ({len(where)} items)")
    deletes: dict[str, set[int]] = {}
    for p in plan:
        if p["action"] == "delete":
            day, n = _split(p["id"])
            pos = [i for i, e in enumerate(server.read_day(day)) if e["n"] == n]
            deletes.setdefault(day, set()).update(pos)
            print(f"deleted {p['id']} (to {day}/.deleted/)")
    for day, idx in deletes.items():
        server.delete_entries(day, idx)


def backfill_thumbs() -> None:
    """Save a thumbnail for every filed item with a link but no thumb line yet."""
    for bucket in notes.BUCKETS:
        with notes._lock:
            items, _ = notes.load(bucket)
            changed = 0
            for it in items:
                links = notes.fields(it, "link")
                if not links or notes.field(it, "thumb"):
                    continue
                info = captions(links[:1])[links[0]]
                if thumb := notes.save_thumb(links[0], info.get("thumb_url", "")):
                    it["fields"].append(("thumb", thumb))
                    changed += 1
            if changed:
                notes._write(bucket, items)
        print(f"{bucket}: {changed} thumbnails")


def main() -> None:
    args = sys.argv[1:]
    if args == ["unfiled"]:
        print(json.dumps(unfiled(), indent=1, ensure_ascii=False))
    elif len(args) == 2 and args[0] == "caption":
        print(json.dumps(notes.link_info(args[1]), indent=1, ensure_ascii=False))
    elif len(args) == 2 and args[0] == "apply":
        apply(json.loads(Path(args[1]).read_text()))
    elif args == ["thumbs"]:
        backfill_thumbs()
    elif len(args) == 2 and args[0] == "unmark":
        print("ok" if server.set_filed(*_split(args[1]), "") else "no such entry")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
