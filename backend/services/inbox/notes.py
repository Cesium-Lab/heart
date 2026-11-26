"""Notes: the filed inbox items, one Markdown list per bucket in /srv/data/notes/ (FILING.md).

Read and changed by the inbox's /inbox/notes/ pages (list, add, edit, move, delete) and by
filing.py. Files are the truth: each bucket is a plain .md file, thumbnails are saved copies in
notes/thumbs/, and deleted items are appended to notes/.deleted.md so they can be restored.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

NOTES = Path(os.getenv("NOTES_DIR", "/srv/data/notes"))
INBOX = Path(os.getenv("INBOX_DIR", "/srv/data/inbox"))
BUCKETS = {  # file stem -> (title, icon)
    "licks": ("Licks to learn", "🎸"),
    "song-ideas": ("Song ideas", "🎵"),
    "content-tips": ("Content tips", "📱"),
    "business": ("Business and production", "💼"),
    "later": ("Later (not music)", "🗂️"),
}
UA = "Mozilla/5.0"  # a full browser UA gets a script-only page without the caption
IG = re.compile(r"instagram\.com/(?:[\w.]+/)?(reel|reels|p|tv)/([\w-]+)")
YT = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/)|youtu\.be/)([\w-]{11})")
_lock = threading.Lock()


# ---------- links: caption + thumbnail ----------


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def link_info(url: str) -> dict:
    """{"creator", "caption", "thumb_url"} for an Instagram or YouTube link; {} if neither,
    {"error"} if the fetch failed (Instagram blocked it, the post is gone...)."""
    try:
        if m := IG.search(url):
            kind = "p" if m[1] == "p" else "reel"
            page = _get(
                f"https://www.instagram.com/{kind}/{m[2]}/embed/captioned/"
            ).decode("utf-8", "replace")
            out = {}
            if img := re.search(r'class="EmbeddedMediaImage"[^>]*src="([^"]+)"', page):
                out["thumb_url"] = html.unescape(img[1])
            if cap := re.search(r'class="Caption"(.*?)</div>', page, re.S):
                user = re.search(r'class="CaptionUsername"[^>]*>([^<]+)<', cap[1])
                creator = user[1].strip() if user else ""
                text = html.unescape(re.sub(r"<br\s*/?>", "\n", cap[1]))
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"View all [\d,]+ comments?\s*$", "", text.strip())
                if creator:
                    text = re.sub(r"^[>\s]*" + re.escape(creator), "", text)
                text = re.sub(
                    r"\s*\n\s*(?=#)", " ", text
                )  # hashtags back onto one line
                text = re.sub(r"[ \t]+", " ", text)
                out["creator"] = creator
                out["caption"] = re.sub(r"\n\s*\n*", "\n", text).strip()
            return out
        if m := YT.search(url):
            q = urllib.parse.quote(url, safe="")
            j = json.loads(_get(f"https://www.youtube.com/oembed?url={q}&format=json"))
            return {
                "creator": j.get("author_name", ""),
                "caption": j.get("title", ""),
                "thumb_url": f"https://i.ytimg.com/vi/{m[1]}/hqdefault.jpg",
            }
    except Exception as exc:  # network, 404, layout change: no caption
        return {"error": str(exc)[:200]}
    return {}


def save_thumb(url: str, thumb_url: str) -> str:
    """Download a link's thumbnail once into notes/thumbs/ (Instagram's image links expire).
    Returns its path relative to NOTES ("thumbs/DgJpiXOyev4.jpg"), or "" if it failed."""
    m = IG.search(url) or YT.search(url)
    if not m or not thumb_url:
        return ""
    name = f"{m[m.lastindex]}.jpg"
    path = NOTES / "thumbs" / name
    if not path.exists():
        try:
            data = _get(thumb_url)
        except Exception:
            return ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return f"thumbs/{name}"


# ---------- bucket files ----------


def path_of(bucket: str) -> Path:
    if bucket not in BUCKETS:
        raise KeyError(bucket)
    return NOTES / f"{bucket}.md"


def parse(text: str) -> list[dict]:
    """A bucket file -> [{"title", "fields": [(key, value)], "extra": [lines]}]."""
    items: list[dict] = []
    for line in text.splitlines():
        if line.startswith("## "):
            items.append({"title": line[3:].strip(), "fields": [], "extra": []})
        elif not items:
            continue  # the "# Bucket" header
        elif m := re.match(r"- ([a-z]+): ?(.*)$", line):
            items[-1]["fields"].append((m[1], m[2]))
        elif (
            line.strip()
            and items[-1]["fields"]
            and items[-1]["fields"][-1][0] == "note"
        ):
            # A multi-line note: the lines after "- note:" belong to it.
            k, v = items[-1]["fields"][-1]
            items[-1]["fields"][-1] = (k, v + "\n" + line)
        elif line.strip():
            items[-1]["extra"].append(line)
    return items


def item_md(item: dict) -> str:
    title = " ".join(item["title"].split())  # one line, so it stays a heading
    lines = [f"## {title}", ""]
    lines += [f"- {k}: {v}" for k, v in item["fields"]]
    lines += item.get("extra", [])
    return "\n".join(lines) + "\n"


def load(bucket: str) -> tuple[list[dict], str]:
    """(items, version). The version is a hash of the file, sent with every form so a change
    made meanwhile (another tab, a filing run) is noticed instead of hitting the wrong item."""
    p = path_of(bucket)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    return parse(text), hashlib.sha1(text.encode()).hexdigest()[:12]


def _write(bucket: str, items: list[dict]) -> None:
    NOTES.mkdir(parents=True, exist_ok=True)
    body = f"# {BUCKETS[bucket][0]}\n\n" + "\n".join(item_md(i) for i in items)
    path_of(bucket).write_text(body, encoding="utf-8")


def append(bucket: str, item: dict) -> None:
    with _lock:
        items, _ = load(bucket)
        _write(bucket, items + [item])


def field(item: dict, key: str) -> str:
    return next((v for k, v in item["fields"] if k == key), "")


def fields(item: dict, key: str) -> list[str]:
    return [v for k, v in item["fields"] if k == key]


def set_field(item: dict, key: str, value: str) -> None:
    """Set (or remove, if empty) a single-valued field, keeping its place."""
    out, done = [], False
    for k, v in item["fields"]:
        if k != key:
            out.append((k, v))
        elif value and not done:
            out.append((key, value))
            done = True
    if value and not done:
        out.append((key, value))
    item["fields"] = out


class Stale(Exception):
    """The bucket changed since the page was loaded."""


def _take(bucket: str, picks: set[int], version: str) -> tuple[list[dict], list[dict]]:
    items, v = load(bucket)
    if v != version:
        raise Stale
    keep = [x for i, x in enumerate(items) if i not in picks]
    gone = [x for i, x in enumerate(items) if i in picks]
    return keep, gone


def delete(bucket: str, picks: set[int], version: str) -> int:
    with _lock:
        keep, gone = _take(bucket, picks, version)
        if gone:
            NOTES.mkdir(parents=True, exist_ok=True)
            stamp = f"{datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}"
            with (NOTES / ".deleted.md").open("a", encoding="utf-8") as fh:
                for g in gone:
                    fh.write(
                        f"<!-- from {bucket}.md, deleted {stamp} -->\n{item_md(g)}\n"
                    )
            _write(bucket, keep)
        return len(gone)


def move(bucket: str, picks: set[int], target: str, version: str) -> int:
    path_of(target)  # unknown bucket -> KeyError
    with _lock:
        keep, gone = _take(bucket, picks, version)
        if gone and target != bucket:
            dest, _ = load(target)
            _write(target, dest + gone)
            _write(bucket, keep)
        return len(gone)


def clean_note(note: str) -> str:
    """Keep line breaks (lists like the daily games are one per line), drop blank lines and
    lines that would read as a new field or heading."""
    lines = [" ".join(x.split()) for x in note.splitlines()]
    lines = [("· " + x if re.match(r"- [a-z]+:|#", x) else x) for x in lines if x]
    return "\n".join(lines)


def linkify_note(text: str) -> str:
    """Escape a note and link its web addresses, bare ones too ("krillion.io",
    "nytimes.com/games/wordle/")."""
    out, last = [], 0
    for m in NOTE_URL_RE.finditer(text):
        url = m[0].rstrip(".,;:!?)")
        href = url if re.match(r"https?://", url) else "https://" + url
        out.append(html.escape(text[last : m.start()]))
        out.append(
            f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{html.escape(url)}</a>'
        )
        last = m.start() + len(url)
    out.append(html.escape(text[last:]))
    return "".join(out)


NOTE_URL_RE = re.compile(
    r"\bhttps?://\S+|\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|app|co|me|dev|ai|gg|fm|tv|xyz|edu|gov|us|uk|ca|so|sh|info|games?)\b(?:/\S*)?",
    re.I,
)


def edit(bucket: str, n: int, title: str, note: str, version: str) -> bool:
    with _lock:
        items, v = load(bucket)
        if v != version:
            raise Stale
        if not 0 <= n < len(items):
            return False
        items[n]["title"] = title.strip() or items[n]["title"]
        set_field(items[n], "note", clean_note(note))
        _write(bucket, items)
        return True


def new_item(title: str, link: str = "", note: str = "", source: str = "") -> dict:
    """A bucket item; for an Instagram/YouTube link, also its caption and a saved thumbnail."""
    info = link_info(link) if link else {}
    if not title:
        first = (info.get("caption") or "").split("\n")[0]
        first = first if len(first) <= 60 else first[:60].rsplit(" ", 1)[0] + "…"
        title = (
            f"{first} ({info['creator']})"
            if info.get("creator")
            else (link or note[:60] or "Untitled")
        )
    f = [("from", source)] if source else []
    f.append(("filed", str(date.today())))
    f += [("link", link)] if link else []
    if info.get("caption"):
        f.append(("caption", " / ".join(info["caption"].splitlines())))
    if thumb := save_thumb(link, info.get("thumb_url", "")):
        f.append(("thumb", thumb))
    f += [("note", " ".join(note.split()))] if note.strip() else []
    return {"title": title.strip(), "fields": f, "extra": []}


def counts() -> dict[str, int]:
    return {b: len(load(b)[0]) for b in BUCKETS}


# ---------- pages ----------


def _file_href(path: str) -> str:
    """/srv/data/inbox/<day>/<name> -> the inbox's file URL; other paths aren't served."""
    p = Path(path)
    if p.parent.parent == INBOX:
        return f"/inbox/files/{p.parent.name}/{urllib.parse.quote(p.name)}"
    return ""


NOTES_CSS = """<style>
.ncard.flash{background:var(--hl);border-radius:8px;transition:background 2s}
.nlist{list-style:none;padding:0;margin:0}
.nlist li a{display:flex;align-items:center;gap:12px;padding:14px 12px;margin:8px 0;background:var(--card);
  border:1px solid var(--line);border-radius:12px;color:var(--ink);text-decoration:none;font-size:17px}
.nlist li a:hover{border-color:var(--bright)}.nlist .ct{margin-left:auto;color:var(--muted)}
.ncard{display:grid;grid-template-columns:28px 72px minmax(0,1fr);gap:10px;align-items:start;padding:12px 0;
  border-bottom:1px solid var(--line)}
.ncard.nothumb{grid-template-columns:28px minmax(0,1fr)}
.ncard input[type=checkbox]{width:20px;height:20px;margin:4px 0 0}
.ncard .th img{width:72px;height:96px;object-fit:cover;border-radius:8px;display:block;background:var(--line)}
.ncard h3{margin:0 0 4px;font-size:16px;line-height:1.3}.ncard h3 a{color:var(--ink)}
.cap{color:var(--muted);font-size:14px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;
  overflow:hidden;cursor:pointer;overflow-wrap:anywhere}.cap.open{display:block}
.nnote{font-size:14px;margin-top:4px;white-space:pre-line;overflow-wrap:anywhere}.nmeta{font-size:12px;color:var(--muted);margin-top:6px;display:flex;
  flex-wrap:wrap;gap:4px 10px;align-items:center}.nmeta a{color:var(--muted)}.nnote a,.nfiles a{color:var(--accent)}
.nfiles{font-size:13px;margin-top:4px;overflow-wrap:anywhere}
.nedit{display:none;margin-top:8px}.ncard.editing .nedit{display:grid}.ncard.editing .nview{display:none}
.nedit input,.nedit textarea,.nadd input,.nadd textarea,.nadd select,.selbar select{font:inherit;padding:8px;border:1px solid var(--line);
  border-radius:8px;background:var(--bg);color:var(--ink);width:100%}
.nadd{margin:12px 0}.nadd summary{cursor:pointer;font-weight:500}
.selbar{position:sticky;bottom:0;display:none;gap:8px;align-items:center;padding:10px 12px;margin-top:12px;
  background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.12)}
.selbar.on{display:flex}.selbar select{width:auto;flex:1;min-width:0}.selbar .n{white-space:nowrap}
.linkbtn{background:none;border:0;padding:0;color:var(--muted);font:inherit;font-size:12px;text-decoration:underline;cursor:pointer}
</style>"""


def _page(title: str, body: str, style: str, logout: str, flash: str) -> bytes:
    flash_html = f'<div class="ok">{html.escape(flash)}</div>' if flash else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html.escape(title)}</title><meta name="robots" content="noindex">'
        '<link rel="icon" href="/favicon.svg?v=5" type="image/svg+xml">'
        f"{style}{NOTES_CSS}</head><body><main>{logout}"
        '<div class="pinsnav"><a href="/inbox/">Inbox</a></div>'
        f"{body}{flash_html}</main></body></html>"
    ).encode()


def render_index(style: str, logout: str, flash: str = "") -> bytes:
    rows = "".join(
        f'<li><a href="/inbox/notes/{b}"><span>{icon}</span><span>{html.escape(t)}</span>'
        f'<span class="ct">{n} ›</span></a></li>'
        for b, n in counts().items()
        for t, icon in [BUCKETS[b]]
    )
    body = f'<h1 class="title">Notes</h1><ul class="nlist">{rows}</ul>'
    return _page("Notes", body, style, logout, flash)


def source_id(item: dict) -> str:
    """The inbox entry a note came from ("2026-11-25#4"), or "" if it was added by hand."""
    m = re.match(r"\[(\d{4}-\d{2}-\d{2}#\d+)\]", field(item, "from"))
    return m[1] if m else ""


def anchor(ident: str) -> str:
    """Card id for a source entry: "2026-11-25#4" -> "from-2026-11-25-4"."""
    return "from-" + ident.replace("#", "-")


def find(ident: str, hint: str = "") -> str | None:
    """Where the note filed from inbox entry `ident` lives now: "/inbox/notes/<bucket>#from-…".
    Looks in `hint` (the bucket it was filed to) first, then everywhere, so a note moved to
    another bucket since filing is still found. None if it's been deleted."""
    order = [hint] if hint in BUCKETS else []
    order += [b for b in BUCKETS if b != hint]
    for b in order:
        items, _ = load(b)
        if any(source_id(it) == ident for it in items):
            return f"/inbox/notes/{b}#{anchor(ident)}"
    return None


def _card(bucket: str, i: int, it: dict, version: str, cid: str = "") -> str:
    esc = html.escape
    links = fields(it, "link")
    first = links[0] if links else ""
    thumb = field(it, "thumb")
    th = (
        f'<a class="th" href="{esc(first)}"><img src="/inbox/notes/{esc(thumb)}" alt="" loading="lazy"></a>'
        if thumb
        else ""
    )
    title = (
        f'<a href="{esc(first)}">{esc(it["title"])}</a>' if first else esc(it["title"])
    )
    cap = field(it, "caption")
    note = field(it, "note")
    files = []
    for f in fields(it, "file"):
        href = _file_href(f)
        name = esc(Path(f).name)
        files.append(f'<a href="{href}">{name}</a>' if href else name)
    src = field(it, "from")
    src_html = ""
    if m := re.match(r"\[(.+?)\]\((/inbox/[^)]+)\)", src):
        src_html = f'<a href="{esc(m[2])}">from {esc(m[1])}</a>'
    extra_links = "".join(f' · <a href="{esc(u)}">link</a>' for u in links[1:])
    return (
        f'<div class="ncard{"" if thumb else " nothumb"}"{f' id="{cid}"' if cid else ""}>'
        f'<input type="checkbox" name="i" value="{i}" form="sel" aria-label="select">{th}<div>'
        f'<div class="nview"><h3>{title}</h3>'
        + (f'<div class="cap">{esc(cap)}</div>' if cap else "")
        + (f'<div class="nnote">{linkify_note(note)}</div>' if note else "")
        + (f'<div class="nfiles">{" · ".join(files)}</div>' if files else "")
        + f'<div class="nmeta">{src_html}<span>filed {esc(field(it, "filed"))}</span>{extra_links}'
        '<button type="button" class="linkbtn edit">Edit</button></div></div>'
        f'<form class="nedit" method="post" action="/inbox/notes/{bucket}/edit">'
        f'<input type="hidden" name="n" value="{i}"><input type="hidden" name="v" value="{version}">'
        f'<input name="title" value="{esc(it["title"])}" aria-label="title">'
        f'<textarea name="note" rows="3" placeholder="note" aria-label="note">{esc(note)}</textarea>'
        '<div class="row"><button>Save</button><button type="button" class="plain cancel">Cancel</button></div>'
        "</form></div></div>"
    )


def render_bucket(bucket: str, style: str, logout: str, flash: str = "") -> bytes:
    items, version = load(bucket)
    name, icon = BUCKETS[bucket]
    # Each card gets an id from its inbox entry (the first one, if an entry was filed twice
    # here), so the inbox's "filed → …" link lands on it.
    seen, cards = set(), []
    for i, it in enumerate(items):
        cid = anchor(source_id(it)) if source_id(it) else ""
        cards.append(_card(bucket, i, it, version, "" if cid in seen else cid))
        seen.add(cid)
    cards = "".join(cards)
    others = "".join(
        f'<option value="{b}">{html.escape(t)}</option>'
        for b, (t, _) in BUCKETS.items()
        if b != bucket
    )
    body = (
        '<div class="nav"><a href="/inbox/notes/">‹ Notes</a><span></span></div>'
        f'<h1 class="title">{icon} {html.escape(name)} <span class="ct">({len(items)})</span></h1>'
        f'<details class="nadd"><summary>+ Add</summary>'
        f'<form method="post" action="/inbox/notes/{bucket}/add">'
        '<input name="link" placeholder="link (reel, video, tab…)" inputmode="url">'
        '<input name="title" placeholder="title (optional: taken from the caption)">'
        '<textarea name="note" rows="2" placeholder="note"></textarea>'
        "<button>Add</button></form></details>"
        f"{cards or '<p>Nothing here yet.</p>'}"
        f'<form id="sel" class="selbar" method="post" action="/inbox/notes/{bucket}/move">'
        f'<input type="hidden" name="v" value="{version}"><span class="n">0 selected</span>'
        f'<select name="to" aria-label="move to"><option value="">Move to…</option>{others}</select>'
        f'<button formaction="/inbox/notes/{bucket}/delete" class="del">Delete</button></form>'
        + NOTES_JS
    )
    return _page(name, body, style, logout, flash)


NOTES_JS = """<script>
const bar = document.getElementById("sel"), boxes = [...document.querySelectorAll('input[name=i]')];
const sync = () => { const n = boxes.filter((b) => b.checked).length;
  bar.classList.toggle("on", n > 0); bar.querySelector(".n").textContent = n + " selected"; };
boxes.forEach((b) => b.onchange = sync);
bar.elements.to.onchange = () => { if (bar.elements.to.value) bar.requestSubmit(); };
bar.querySelector(".del").onclick = (ev) => {
  const n = boxes.filter((b) => b.checked).length;
  if (!confirm(`Delete ${n} item${n > 1 ? "s" : ""}? (kept in notes/.deleted.md)`)) ev.preventDefault();
};
// Arrived from an inbox entry's "filed → …" link: bring that card to the middle and flash it.
const hit = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
if (hit) { hit.scrollIntoView({ block: "center" }); hit.classList.add("flash"); }
document.querySelectorAll(".cap").forEach((c) => c.onclick = () => c.classList.toggle("open"));
document.querySelectorAll(".ncard .edit").forEach((b) => b.onclick = () => b.closest(".ncard").classList.add("editing"));
document.querySelectorAll(".ncard .cancel").forEach((b) => b.onclick = () => b.closest(".ncard").classList.remove("editing"));
</script>"""
