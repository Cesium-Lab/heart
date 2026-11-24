"""Inbox: drop notes, links, and photos through the day; get them emailed at night.

A minimal form at /inbox/ (Apache: open on the home LAN and Tailscale, password elsewhere).
Each entry is free text (a note, a URL, anything) plus optional files. Files are the truth:

    /srv/data/inbox/2026-11-23/inbox.md        the day's entries, readable/pasteable
    /srv/data/inbox/2026-11-23/140512-IMG_1234.jpg

Every evening (INBOX_DIGEST_HOUR, default 21) the day's entries are emailed through Gmail
(app password in /etc/cesium/inbox.env), with photo thumbnails and a plain-text block to paste
into Claude/ChatGPT. Binds 127.0.0.1:42904. Standard library + Pillow (thumbnails only).
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import html
import io
import ipaddress
import secrets
import shutil
import tempfile
import sys
import json
import os
import re
import smtplib
import ssl
import threading
import zipfile
import time
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote

try:  # thumbnails in the email; without Pillow the email just links to the files
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None

HOST = os.getenv("INBOX_HOST", "127.0.0.1")
PORT = int(os.getenv("INBOX_PORT", "42904"))
DIR = Path(os.getenv("INBOX_DIR", "/srv/data/inbox"))
DIGEST_HOUR = int(os.getenv("INBOX_DIGEST_HOUR", "21"))
SMTP_HOST = os.getenv("INBOX_SMTP_HOST", "smtp.gmail.com")
SMTP_USER = os.getenv("INBOX_SMTP_USER", "")
SMTP_PASS = os.getenv("INBOX_SMTP_PASS", "")
MAIL_TO = os.getenv("INBOX_TO", SMTP_USER)
PUBLIC_URL = os.getenv("INBOX_PUBLIC_URL", "https://cesiumlab.net/inbox/")
# Upload limit per entry/reply (all its files together). From the web (Cloudflare) it's 95 MB:
# Cloudflare's free plan rejects requests over 100 MB before they reach us (a "413 Payload Too
# Large" page), so stay under it with room for the form's own overhead. At home / on Tailscale
# there's no Cloudflare in the way: 1 GB (tentative). Uploads stream to disk, so a big one
# doesn't sit in RAM. The page shows and checks the limit before uploading; the server
# enforces it too.
MAX_UPLOAD_MB = 95
HOME_UPLOAD_MB = int(os.getenv("INBOX_HOME_UPLOAD_MB", "1024"))
DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Login for visitors outside the home network (see "auth" below). The hash comes from
# `python server.py hash-password`; without one set, off-network visitors can't get in at all.
USERNAME = os.getenv("INBOX_USERNAME", "colin")
PASSWORD_HASH = os.getenv("INBOX_PASSWORD_HASH", "")
HOME_NETS = [
    ipaddress.ip_network(n)
    for n in os.getenv(
        "INBOX_HOME_NETS", "192.168.0.0/24,100.64.0.0/10,fd7a:115c:a1e0::/48"
    ).split(",")
    if n.strip()
]
IDLE_S = int(os.getenv("INBOX_IDLE_MIN", "10")) * 60  # log out after this long unused
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}
_write_lock = threading.Lock()


# ------------------------------------------------------------------- storage


def day_dir(day: str) -> Path:
    return DIR / day


def safe_name(name: str) -> str:
    """A file name that can't escape the day folder."""
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "file"
    return name[:80]


def _save_files(
    folder: Path, stamp: str, files: list[tuple[str, bytes | Path]]
) -> list[str]:
    saved = []
    for name, data in files:
        fname = f"{stamp}-{safe_name(name)}"
        k = 1
        while (folder / fname).exists():  # same name in the same second: keep both
            fname = f"{stamp}-{k}-{safe_name(name)}"
            k += 1
        if isinstance(data, Path):  # an upload already streamed to disk: move it in
            shutil.move(data, folder / fname)
        else:
            (folder / fname).write_bytes(data)
        saved.append(fname)
    return saved


def _meta_line(now: datetime, source: str) -> str:
    utc = now.astimezone(timezone.utc)
    meta = f"UTC {utc:%Y-%m-%dT%H:%M:%SZ} · unix {int(now.timestamp())}"
    return meta + (f" · from {source}" if source else "")


def _block(level: str, ident: str, item: dict) -> list[str]:
    """One entry ("##", ident "5") or reply ("###", ident "5.1") as Markdown lines."""
    out = [f"{level} {ident} · {item['time']}"]
    out += [f"_{item['meta']}_"] if item.get("meta") else []
    out += [f"_edited {item['edited']}_"] if item.get("edited") else []
    out += ["_pinned_"] if item.get("pinned") else []
    out.append("")
    # Text is quoted so nothing a user types can look like an entry header.
    out += [f"> {line}" if line else ">" for line in item["text"].splitlines()]
    if item["text"] and item["files"]:
        out.append("")
    out += [f"- [{f}]({quote(f)})" for f in item["files"]]
    return out + [""]


def _append(day: str, lines: list[str]) -> None:
    md = day_dir(day) / "inbox.md"
    with md.open("a", encoding="utf-8") as fh:
        if fh.tell() == 0:
            fh.write(f"# Inbox {day}\n\n")
        fh.write("\n".join(lines) + "\n")


def add_reply(
    day: str, parent: int, text: str, files: list[tuple[str, bytes]], source: str = ""
) -> str | None:
    """Add a reply under entry `parent` of `day` (stored in that day's file, numbered parent.m,
    fixed with gaps like entries). Returns the reply's id ("5.1"), or None if no such entry."""
    now = datetime.now().astimezone()
    with _write_lock:
        entries = read_day(day)
        target = next((e for e in entries if e["n"] == parent), None)
        if target is None:
            return None
        m = max((r["m"] for r in target["replies"]), default=0) + 1
        gone = day_dir(day) / ".deleted" / "deleted.md"
        if gone.exists():
            used = re.findall(
                rf"^### {parent}\.(\d+) ·", gone.read_text(encoding="utf-8"), re.M
            )
            m = max([m] + [int(u) + 1 for u in used])
        saved = _save_files(day_dir(day), now.strftime("%H%M%S"), files)
        item = {
            "time": f"{now:%H:%M:%S %Z}",
            "meta": _meta_line(now, source),
            "text": text.strip(),
            "files": saved,
        }
        _append(day, _block("###", f"{parent}.{m}", item))
        return f"{parent}.{m}"


def find_item(entries: list[dict], ident: str) -> dict | None:
    """Entry ("5") or reply ("5.1") by id."""
    for e in entries:
        if ident == str(e["n"]):
            return e
        for r in e["replies"]:
            if ident == r["id"]:
                return r
    return None


def edit_item(day: str, ident: str, text: str) -> bool:
    """Replace an entry's or reply's note (no history kept) and mark it edited."""
    with _write_lock:
        entries = read_day(day)
        item = find_item(entries, ident)
        if item is None:
            return False
        item["text"] = text.strip()
        item["edited"] = f"{datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}"
        write_day(day, entries)
        return True


def set_pinned(day: str, n: int, on: bool) -> bool:
    """Pin or unpin entry n of a day (stored as a `_pinned_` line in its block)."""
    with _write_lock:
        entries = read_day(day)
        e = next((x for x in entries if x["n"] == n), None)
        if e is None:
            return False
        e["pinned"] = on
        write_day(day, entries)
        return True


def pinned_entries() -> list[tuple[str, dict]]:
    """Every pinned entry, newest day first: [(day, entry)]. Built from the day files."""
    out = []
    for day in days_with_entries():  # newest first
        for e in reversed(read_day(day)):
            if e.get("pinned"):
                out.append((day, e))
    return out


def delete_reply(day: str, ident: str) -> bool:
    """Remove one reply (and its files, to .deleted/)."""
    with _write_lock:
        entries = read_day(day)
        for e in entries:
            for r in e["replies"]:
                if r["id"] == ident:
                    trash = day_dir(day) / ".deleted"
                    trash.mkdir(exist_ok=True)
                    with (trash / "deleted.md").open("a", encoding="utf-8") as fh:
                        fh.write(
                            "\n".join(
                                _block(
                                    "###",
                                    ident,
                                    {
                                        **r,
                                        "time": f"{r['time']} (deleted {datetime.now():%H:%M:%S})",
                                    },
                                )
                            )
                            + "\n"
                        )
                    for f in r["files"]:
                        src = day_dir(day) / safe_name(f)
                        if src.is_file():
                            src.rename(trash / src.name)
                    e["replies"].remove(r)
                    write_day(day, [x for x in entries if _alive(x)])
                    return True
        return False


def _alive(e: dict) -> bool:
    """An entry stays in the list while it has a note, files, or replies."""
    return bool(e["text"] or e["files"] or e["replies"])


def add_entry(text: str, files: list[tuple[str, bytes]], source: str = "") -> str:
    """Append one entry to today's inbox.md and save its files. Returns the day.

    source: where it was sent from, e.g. "Tailscale 100.120.196.52" (see describe_source)."""
    now = datetime.now().astimezone()  # local time with its zone (PST/PDT)
    day, stamp = now.strftime("%Y-%m-%d"), now.strftime("%H%M%S")
    with _write_lock:
        folder = day_dir(day)
        folder.mkdir(parents=True, exist_ok=True)
        saved = _save_files(folder, stamp, files)
        # Fixed per-day number: one past the highest ever used today (gaps stay after deletes).
        n = max((e["n"] for e in read_day(day)), default=0) + 1
        gone = folder / ".deleted" / "deleted.md"
        if gone.exists():
            used = re.findall(r"^## (\d+) ·", gone.read_text(encoding="utf-8"), re.M)
            n = max([n] + [int(u) + 1 for u in used])
        # Header: number + local time + zone; then UTC, Unix time, where it came from.
        item = {
            "time": f"{now:%H:%M:%S %Z}",
            "meta": _meta_line(now, source),
            "text": text.strip(),
            "files": saved,
        }
        _append(day, _block("##", str(n), item))
    return day


def write_day(day: str, entries: list[dict]) -> None:
    """Rewrite a day's inbox.md from entries (each followed by its replies)."""
    out = [f"# Inbox {day}", ""]
    for e in entries:
        out += _block("##", str(e["n"]), e)
        for r in e["replies"]:
            out += _block("###", r["id"], r)
    (day_dir(day) / "inbox.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def delete_entries(day: str, indexes: set[int]) -> int:
    """Remove entries (by position) from a day. Their files move to <day>/.deleted/, so a
    mistake can be undone by hand. Returns how many were removed."""
    with _write_lock:
        entries = read_day(day)
        keep = [e for i, e in enumerate(entries) if i not in indexes]
        gone = [e for i, e in enumerate(entries) if i in indexes]
        if not gone:
            return 0
        trash = day_dir(day) / ".deleted"
        trash.mkdir(exist_ok=True)
        with (trash / "deleted.md").open("a", encoding="utf-8") as fh:
            for e in gone:
                fh.write(
                    f"## {e['n']} · {e['time']} (deleted {datetime.now():%H:%M:%S})\n\n"
                )
                fh.write("".join(f"> {ln}\n" for ln in e["text"].splitlines()))
                fh.write("".join(f"- {f}\n" for f in e["files"]) + "\n")
                for f in e["files"]:
                    src = day_dir(day) / safe_name(f)
                    if src.is_file():
                        src.rename(trash / src.name)
        write_day(day, keep)
        return len(gone)


def delete_file(day: str, name: str) -> bool:
    """Remove one attachment from its entry and move the file to <day>/.deleted/. An entry left
    with no note and no files is removed too."""
    name = safe_name(name)
    with _write_lock:
        entries = read_day(day)
        items = entries + [r for e in entries for r in e["replies"]]
        hit = next((x for x in items if name in x["files"]), None)
        if not hit:
            return False
        hit["files"].remove(name)
        trash = day_dir(day) / ".deleted"
        trash.mkdir(exist_ok=True)
        with (trash / "deleted.md").open("a", encoding="utf-8") as fh:
            fh.write(
                f"## {hit['time']}: file {name} (deleted {datetime.now():%H:%M:%S})\n\n"
            )
        src = day_dir(day) / name
        if src.is_file():
            src.rename(trash / name)
        write_day(day, [e for e in entries if _alive(e)])
        return True


def delete_selection(
    day: str, indexes: set[int], files: set[str], replies: set[str] = frozenset()
) -> tuple[int, int, int]:
    """Delete what's selected. Everything moves to <day>/.deleted/.

    - Selected entry: always takes ALL its replies (the page only allows this when they're all
      ticked). All its files ticked (or none): deleted whole. Some files unticked: the note and
      ticked files go, the unticked files stay as an entry without text.
    - Files or replies ticked on their own (entry not selected): just those.
    An entry left with no note, files, or replies disappears from the list.
    Returns (entries deleted, files deleted, replies deleted)."""
    files = {safe_name(f) for f in files}
    stamp = lambda: datetime.now().strftime("%H:%M:%S")  # noqa: E731
    with _write_lock:
        entries = read_day(day)
        trash = day_dir(day) / ".deleted"
        trash.mkdir(exist_ok=True)
        n_entries = n_files = n_replies = 0
        keep: list[dict] = []
        moving: list[str] = []
        with (trash / "deleted.md").open("a", encoding="utf-8") as fh:
            for i, e in enumerate(entries):
                if i in indexes:
                    n_entries += 1
                    for r in e["replies"]:  # an entry never goes without its replies
                        fh.write(
                            "\n".join(
                                _block(
                                    "###",
                                    r["id"],
                                    {**r, "time": f"{r['time']} (deleted {stamp()})"},
                                )
                            )
                            + "\n"
                        )
                        moving += r["files"]
                        n_replies += 1
                    if set(e["files"]) <= files:
                        fh.write(
                            "\n".join(
                                _block(
                                    "##",
                                    str(e["n"]),
                                    {**e, "time": f"{e['time']} (deleted {stamp()})"},
                                )
                            )
                            + "\n"
                        )
                        moving += e["files"]
                    else:  # note + ticked files go; unticked files stay, without text or replies
                        gone = [f for f in e["files"] if f in files]
                        fh.write(
                            "\n".join(
                                _block(
                                    "##",
                                    str(e["n"]),
                                    {
                                        **e,
                                        "files": gone,
                                        "time": f"{e['time']}: note (deleted {stamp()}; other files kept)",
                                    },
                                )
                            )
                            + "\n"
                        )
                        moving += gone
                        keep.append(
                            {
                                **e,
                                "text": "",
                                "replies": [],
                                "files": [f for f in e["files"] if f not in files],
                            }
                        )
                    continue
                gone = [f for f in e["files"] if f in files]
                if gone:
                    fh.write(
                        f"## {e['n']} · {e['time']}: files {', '.join(gone)} (deleted {stamp()})\n\n"
                    )
                    moving += gone
                kept_replies = []
                for r in e["replies"]:
                    if r["id"] in replies:
                        fh.write(
                            "\n".join(
                                _block(
                                    "###",
                                    r["id"],
                                    {**r, "time": f"{r['time']} (deleted {stamp()})"},
                                )
                            )
                            + "\n"
                        )
                        moving += r["files"]
                        n_replies += 1
                    else:
                        kept_replies.append(r)
                keep.append(
                    {
                        **e,
                        "files": [f for f in e["files"] if f not in files],
                        "replies": kept_replies,
                    }
                )
        for f in moving:
            src = day_dir(day) / safe_name(f)
            if src.is_file():
                src.rename(trash / src.name)
                n_files += 1
        write_day(day, [e for e in keep if _alive(e)])
        return n_entries, n_files, n_replies


def read_day(day: str) -> list[dict]:
    """Parse a day's inbox.md: [{n, time, meta, edited, text, files, replies: [{id, m, ...}]}].

    Entries are "## 5 · time", replies "### 5.1 · time" (grouped under entry 5 wherever they
    appear in the file)."""
    md = day_dir(day) / "inbox.md"
    if not md.exists():
        return []
    entries: list[dict] = []
    replies: list[dict] = []
    cur: dict | None = None
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            num = re.match(r"(\d+)\.(\d+) · (.*)$", line[4:].strip())
            if not num:
                cur = None
                continue
            cur = {
                "id": f"{num[1]}.{num[2]}",
                "parent": int(num[1]),
                "m": int(num[2]),
                "time": num[3],
                "meta": "",
                "edited": "",
                "text": [],
                "files": [],
            }
            replies.append(cur)
        elif line.startswith("## "):
            head = line[3:].strip()
            num = re.match(r"(\d+) · (.*)$", head)
            cur = {
                "n": int(num[1]) if num else None,
                "time": num[2] if num else head,
                "meta": "",
                "edited": "",
                "text": [],
                "files": [],
                "replies": [],
            }
            entries.append(cur)
        elif cur is None:
            continue
        elif line == "_pinned_":
            cur["pinned"] = True
        elif line.startswith("_edited ") and line.endswith("_"):
            cur["edited"] = line[8:-1]
        elif line.startswith("_") and line.endswith("_") and not cur["text"]:
            cur["meta"] = line[1:-1]
        elif line.startswith("> ") or line == ">":
            cur["text"].append(line[2:])
        elif m := re.match(r"- \[(.+?)\]\((.+?)\)$", line):
            cur["files"].append(unquote(m[2]))
    for item in entries + replies:
        item["text"] = "\n".join(item["text"])
    # Entries saved before numbering existed: number them in order, skipping used numbers.
    used = {e["n"] for e in entries if e["n"]}
    nxt = 1
    for e in entries:
        if not e["n"]:
            while nxt in used:
                nxt += 1
            e["n"] = nxt
            used.add(nxt)
    by_n = {e["n"]: e for e in entries}
    for r in replies:
        if r["parent"] in by_n:  # replies to a deleted entry are dropped from view
            by_n[r["parent"]]["replies"].append(r)
    for e in entries:
        e["replies"].sort(key=lambda r: r["m"])
    return entries


def days_with_entries() -> list[str]:
    if not DIR.exists():
        return []
    return sorted(
        (
            p.name
            for p in DIR.iterdir()
            if DAY_RE.fullmatch(p.name) and (p / "inbox.md").exists()
        ),
        reverse=True,
    )


# ------------------------------------------------------------------- digest email

URL_RE = re.compile(r"https?://[^\s<>\"]+")


# "#5" (entry 5 of the same day), "#5.2" (its 2nd reply), "2026-11-20#3" (another day).
# Only "#" + digits counts, so hashtags like #flowers stay plain text.
REF_RE = re.compile(r"(?<![\w/#])(\d{4}-\d{2}-\d{2})?#(\d+(?:\.\d+)?)\b")


def _refs(text: str, day: str | None, base: str) -> str:
    """Escape text, turning entry references into links (when a day is known)."""
    if day is None:
        return html.escape(text)
    out, last = [], 0
    for m in REF_RE.finditer(text):
        out.append(html.escape(text[last : m.start()]))
        ref_day = m[1] or day
        href = (
            f"#{m[2]}"
            if ref_day == day and base == "/inbox/"
            else f"{base}{ref_day}#{m[2]}"
        )
        out.append(f'<a class="ref" href="{html.escape(href)}">{html.escape(m[0])}</a>')
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


def linkify(text: str, day: str | None = None, base: str = "/inbox/") -> str:
    """Escape text and link URLs, plus entry references like #5 when `day` is given."""
    out, last = [], 0
    for m in URL_RE.finditer(text):
        out.append(_refs(text[last : m.start()], day, base))
        url = m.group(0)
        out.append(f'<a href="{html.escape(url)}">{html.escape(url)}</a>')
        last = m.end()
    out.append(_refs(text[last:], day, base))
    return "".join(out).replace("\n", "<br>")


def thumbnail(path: Path, size: int = 480) -> bytes | None:
    if Image is None or path.suffix.lower() not in IMAGE_EXT:
        return None
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((size, size))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
            return buf.getvalue()
    except (
        Exception
    ):  # unreadable or unsupported (e.g. HEIC without a plugin): link it instead
        return None


def _item_lines(day: str, item: dict, ident: str, indent: str = "") -> list[str]:
    lines = [f"{indent}[{day}#{ident} · {item['time']}] {item['text'] or '(no note)'}"]
    if item.get("meta"):
        lines.append(f"{indent}  ({item['meta']})")
    return lines


def entry_head(day: str, e: dict, replies: bool = True) -> str:
    """An entry's id, time, note, metadata, and (by default) its replies; no attachments."""
    lines = _item_lines(day, e, str(e["n"]))
    if replies:
        for r in e["replies"]:
            lines += _item_lines(day, r, r["id"], "    reply ")
            lines += ["    " + attach_line(day, f).strip() for f in r["files"]]
    return "\n".join(lines)


def attach_line(day: str, f: str) -> str:
    return f"  attachment: {f} ({PUBLIC_URL}files/{day}/{quote(f)})"


def entry_text(day: str, e: dict) -> str:
    """One entry as plain text (for Claude/ChatGPT), with attachments and replies."""
    lines = _item_lines(day, e, str(e["n"]))
    lines += [attach_line(day, f) for f in e["files"]]
    for r in e["replies"]:
        lines += _item_lines(day, r, r["id"], "    reply ")
        lines += ["    " + attach_line(day, f).strip() for f in r["files"]]
    return "\n".join(lines)


def plain_text(day: str, entries: list[dict]) -> str:
    """The block meant for pasting into Claude/ChatGPT."""
    head = f"My inbox for {day} ({len(entries)} entries). Each is something I saved to deal with later."
    return "\n\n".join([head] + [entry_text(day, e) for e in entries])


def export_zip(
    day: str,
    indexes: set[int],
    files: set[str] | None = None,
    replies: set[str] | None = None,
) -> bytes:
    """Exactly what's selected, as a zip: selected.md (same format as inbox.md) plus files.

    indexes: selected entries (their notes). files / replies: ticked attachments and replies;
    a selected entry brings only its ticked files and replies, and ones ticked on their own
    come under their entry's id without its note. None means "all of the selected entries'"."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        md = [f"# Inbox {day} (selected)", ""]
        for i, e in enumerate(read_day(day)):
            sel = i in indexes
            keep = [
                f
                for f in e["files"]
                if (files is None and sel) or (files and f in files)
            ]
            reps = [
                r
                for r in e["replies"]
                if (replies is None and sel) or (replies and r["id"] in replies)
            ]
            if not (sel or keep or reps):
                continue
            head = {
                **e,
                "text": e["text"] if sel else "",
                "files": keep,
                "time": e["time"] + ("" if sel else " (only parts selected)"),
            }
            md += _block("##", str(e["n"]), head)
            for r in reps:
                md += _block("###", r["id"], r)
            for f in keep + [f for r in reps for f in r["files"]]:
                src = day_dir(day) / safe_name(f)
                if src.is_file():
                    z.write(src, src.name)
        z.writestr("selected.md", "\n".join(md) + "\n")
    return buf.getvalue()


def build_digest(day: str) -> EmailMessage | None:
    entries = read_day(day)
    if not entries:
        return None
    msg = EmailMessage()
    msg["Subject"] = f"Inbox {day}: {len(entries)} saved"
    msg["From"] = SMTP_USER or "inbox@mr-ray"
    msg["To"] = MAIL_TO or SMTP_USER
    text = plain_text(day, entries)
    pins = pinned_entries()
    pin_lines = [
        f"{d}#{e['n']}: {(e['text'].splitlines() or ['(no note)'])[0][:120]}"
        for d, e in pins
    ]
    msg.set_content(text + ("\n\nPinned:\n" + "\n".join(pin_lines) if pins else ""))

    thumbs: list[tuple[str, bytes]] = []
    rows = []
    for e in entries:
        parts = [
            f'<div style="color:#6b7280;font-size:12px">{html.escape(e["time"])}</div>'
        ]
        if e.get("meta"):
            parts.append(
                f'<div style="color:#9ca3af;font-size:11px">{html.escape(e["meta"])}</div>'
            )
        if e["text"]:
            parts.append(
                f'<div style="font-size:15px;margin:4px 0 8px">{linkify(e["text"])}</div>'
            )
        for f in e["files"]:
            url = f"{PUBLIC_URL}files/{day}/{quote(f)}"
            data = thumbnail(day_dir(day) / f)
            if data:
                cid = f"t{len(thumbs)}"
                thumbs.append((cid, data))
                parts.append(
                    f'<a href="{url}"><img src="cid:{cid}" alt="{html.escape(f)}" style="max-width:100%;border-radius:8px;margin:4px 0"></a>'
                )
            else:
                parts.append(f'<div><a href="{url}">{html.escape(f)}</a></div>')
        rows.append(
            '<div style="padding:12px 0;border-bottom:1px solid #e5e7eb">'
            + "".join(parts)
            + "</div>"
        )
    body = (
        '<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:640px">'
        f'<h2 style="margin:0 0 4px">Inbox {day}</h2>'
        f'<div style="color:#6b7280">{len(entries)} saved · <a href="{PUBLIC_URL}{day}">open on the server</a></div>'
        + "".join(rows)
        + (
            '<h3 style="margin-top:20px">Pinned</h3><ul style="padding-left:18px">'
            + "".join(
                f'<li><a href="{PUBLIC_URL}pins/{d}/{e["n"]}">{d}#{e["n"]}</a> '
                f"{html.escape((e['text'].splitlines() or ['(no note)'])[0][:120])}</li>"
                for d, e in pins
            )
            + "</ul>"
            if pins
            else ""
        )
        + '<h3 style="margin-top:20px">Paste into Claude / ChatGPT</h3>'
        f'<pre style="white-space:pre-wrap;background:#f4f4f2;padding:12px;border-radius:8px;font-size:12px">{html.escape(text)}</pre>'
        "</div>"
    )
    msg.add_alternative(body, subtype="html")
    html_part = msg.get_payload()[-1]
    for cid, data in thumbs:
        html_part.add_related(data, maintype="image", subtype="jpeg", cid=f"<{cid}>")
    return msg


EMAIL_RE = re.compile(r"[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+")


def send_digest(day: str, to: str = "") -> str:
    """Send (or, without credentials, save) the day's digest, to `to` or the default address.
    Returns what happened."""
    msg = build_digest(day)
    if msg is None:
        return "nothing saved that day"
    if to:
        del msg["To"]
        msg["To"] = to
    if not (SMTP_USER and SMTP_PASS):
        out = day_dir(day) / "digest-preview.eml"
        out.write_bytes(bytes(msg))
        return f"no Gmail app password set; saved {out} instead"
    with smtplib.SMTP_SSL(
        SMTP_HOST, 465, context=ssl.create_default_context(), timeout=30
    ) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    if not to:  # only the nightly/default send counts as "today's digest went out"
        (day_dir(day) / ".digest-sent").write_text(datetime.now().isoformat())
    return f"sent to {msg['To']}"


def send_pins(to: str = "") -> str:
    """Email every pinned entry (text + links, plus the paste-into-Claude block), to `to` or
    the default address. Without credentials it saves pins-preview.eml instead."""
    pins = pinned_entries()
    if not pins:
        return "nothing pinned"
    text = f"My pinned inbox entries ({len(pins)}).\n\n" + "\n\n".join(
        entry_text(d, e) for d, e in pins
    )
    msg = EmailMessage()
    msg["Subject"] = f"Inbox: {len(pins)} pinned"
    msg["From"] = SMTP_USER or "inbox@mr-ray"
    msg["To"] = to or MAIL_TO or SMTP_USER
    msg.set_content(text)
    rows = "".join(
        '<div style="padding:12px 0;border-bottom:1px solid #e5e7eb">'
        f'<a href="{PUBLIC_URL}pins/{d}/{e["n"]}">{d}#{e["n"]}</a> '
        f'<span style="color:#6b7280;font-size:12px">{html.escape(e["time"])}</span>'
        + (
            f'<div style="font-size:15px;margin:4px 0">{linkify(e["text"])}</div>'
            if e["text"]
            else ""
        )
        + "".join(
            f'<div><a href="{PUBLIC_URL}files/{d}/{quote(f)}">{html.escape(f)}</a></div>'
            for f in e["files"]
        )
        + "</div>"
        for d, e in pins
    )
    msg.add_alternative(
        '<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:640px">'
        f'<h2 style="margin:0 0 4px">Pinned ({len(pins)})</h2>'
        f'<div style="color:#6b7280"><a href="{PUBLIC_URL}pins">open on the server</a></div>'
        + rows
        + '<h3 style="margin-top:20px">Paste into Claude / ChatGPT</h3>'
        f'<pre style="white-space:pre-wrap;background:#f4f4f2;padding:12px;border-radius:8px;font-size:12px">{html.escape(text)}</pre>'
        "</div>",
        subtype="html",
    )
    if not (SMTP_USER and SMTP_PASS):
        out = DIR / "pins-preview.eml"
        out.write_bytes(bytes(msg))
        return f"no Gmail app password set; saved {out} instead"
    with smtplib.SMTP_SSL(
        SMTP_HOST, 465, context=ssl.create_default_context(), timeout=30
    ) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    return f"sent to {msg['To']}"


def digest_worker() -> None:
    """Once a day at DIGEST_HOUR, email the day's entries (once; survives restarts)."""
    while True:
        now = datetime.now()
        day = now.strftime("%Y-%m-%d")
        folder = day_dir(day)
        if (
            now.hour >= DIGEST_HOUR
            and (folder / "inbox.md").exists()
            and not (folder / ".digest-sent").exists()
        ):
            try:
                print(f"digest {day}: {send_digest(day)}", flush=True)
            except Exception as e:  # keep running; retry next loop
                print(f"digest {day} failed: {e}", flush=True)
                time.sleep(600)
        time.sleep(60)


# ------------------------------------------------------------------- auth
# Apache decides nothing here; it only proxies, and its mod_proxy appends the real visitor
# address to X-Forwarded-For. The *last* entry is that address (anything a visitor sends is
# earlier in the list), so it can't be faked. Home LAN and Tailscale need no login. Everyone
# else (including everything through the Cloudflare tunnel, which reaches Apache from
# 127.0.0.1) gets a login page. A login lasts while the tab is open and expires after IDLE_S
# unused; the page also asks again in every new tab or app launch (see LOGOUT script).

_sessions: dict[
    str, dict
] = {}  # token -> {"seen": epoch, "tag": short id for the tab check}
_fails: dict[str, list[float]] = {}  # visitor ip -> recent failed login times
_auth_lock = threading.Lock()


def hash_password(pw: str, iterations: int = 600_000) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def check_login(user: str, pw: str) -> bool:
    ok_user = hmac.compare_digest(user.strip().lower(), USERNAME.lower())
    return check_password(pw) and ok_user


def check_password(pw: str) -> bool:
    try:
        algo, iters, salt, want = PASSWORD_HASH.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(iters))
    return hmac.compare_digest(dk.hex(), want)


def visitor_ip(headers) -> str:
    xff = headers.get("X-Forwarded-For", "")
    return xff.split(",")[-1].strip() if xff else ""


def is_home(headers) -> bool:
    try:
        ip = ipaddress.ip_address(visitor_ip(headers))
    except ValueError:
        return False  # no proxy header (e.g. the dev server or a direct local request): log in
    return any(ip in net for net in HOME_NETS)


def describe_source(headers) -> str:
    """Where a request came from, for the record: home network / Tailscale / internet + IP."""
    ip_s = visitor_ip(headers)
    try:
        ip = ipaddress.ip_address(ip_s)
    except ValueError:
        return "the server itself"
    if ip.is_loopback:
        # Through the Cloudflare tunnel (cloudflared reaches Apache from 127.0.0.1). Cloudflare
        # sets CF-Connecting-IP to the real visitor; trusted only on this path.
        real = headers.get("CF-Connecting-IP", "").strip()
        return f"internet {real} (via cesiumlab.net)" if real else "the server itself"
    if ip in ipaddress.ip_network("192.168.0.0/24"):
        return f"home network {ip}"
    if ip in ipaddress.ip_network("100.64.0.0/10") or ip in ipaddress.ip_network(
        "fd7a:115c:a1e0::/48"
    ):
        return f"Tailscale {ip}"
    if ip.is_private:
        return f"other local network {ip}"
    return f"internet {ip}"


def session_for(headers) -> dict | None:
    m = re.search(r"(?:^|;\s*)inbox_s=([A-Za-z0-9_-]{20,})", headers.get("Cookie", ""))
    if not m:
        return None
    with _auth_lock:
        s = _sessions.get(m[1])
        if not s or time.time() - s["seen"] > IDLE_S:
            _sessions.pop(m[1], None)
            return None
        s["seen"] = time.time()
        return {"token": m[1], **s}


def too_many_fails(ip: str) -> bool:
    now = time.time()
    with _auth_lock:
        recent = [t for t in _fails.get(ip, []) if now - t < 300]
        _fails[ip] = recent
        return len(recent) >= 5  # 5 wrong passwords in 5 minutes: wait


LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Inbox</title>
<meta name="robots" content="noindex"><link rel="icon" href="/favicon.svg?v=5" type="image/svg+xml">
<style>
:root{--bg:#fafaf7;--card:#fff;--ink:#111;--muted:#4a4a45;--line:#e5e3dc;--accent:#c4541c;--bright:#111}
@media(prefers-color-scheme:dark){:root{--bg:#14140f;--card:#1c1c17;--ink:#fff;--muted:#c4c4bc;--line:#3a3a32;--accent:#f0997b;--bright:#fff}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,Helvetica,Arial,sans-serif}
form{max-width:320px;margin:18vh auto 0;padding:20px;background:var(--card);border:1px solid var(--line);border-radius:12px;display:grid;gap:12px}
h1{font-size:18px;margin:0}input{font:inherit;padding:10px;border:1px solid var(--line);border-radius:8px;background:transparent;color:inherit}
button{font:inherit;font-weight:600;color:#fff;background:var(--accent);border:0;border-radius:8px;padding:10px;cursor:pointer}
.msg{color:#dc2626;font-size:13px;min-height:1em}
</style></head><body>
<form method="post" action="/inbox/login">
  <h1>Inbox</h1>
  <input name="username" placeholder="Username" autocomplete="username" autocapitalize="none" autofocus required>
  <input type="password" name="password" placeholder="Password" autocomplete="current-password" required>
  <button>Log in</button>
  <div class="msg">{msg}</div>
</form></body></html>"""


def login_page(msg: str = "") -> bytes:
    return LOGIN_PAGE.replace("{msg}", html.escape(msg)).encode()


# ------------------------------------------------------------------- pages

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Inbox</title>
<meta name="robots" content="noindex">
<link rel="icon" href="/favicon.svg?v=5" type="image/svg+xml">
<style>
:root{--bg:#fafaf7;--card:#fff;--ink:#111;--muted:#4a4a45;--line:#e5e3dc;--accent:#c4541c;--bright:#111}
@media(prefers-color-scheme:dark){:root{--bg:#14140f;--card:#1c1c17;--ink:#fff;--muted:#c4c4bc;--line:#3a3a32;--accent:#f0997b;--bright:#fff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,Helvetica,Arial,sans-serif}
main{max-width:640px;margin:0 auto;padding:20px 16px 60px}
/* Desktop: entries on the left, the entry box on the right (stays in view while scrolling). */
@media(min-width:900px){
  main{max-width:1440px}
  /* about 65/35: entries get most of the width; the divider line sits at the split */
  .cols{display:grid;grid-template-columns:minmax(0,2.8fr) minmax(0,1fr);gap:0;align-items:start}
  .list{padding-right:28px}
  .compose{padding-left:28px;border-left:1px solid var(--line);min-height:calc(100vh - 140px)}
  .compose{grid-column:2;grid-row:1;position:sticky;top:20px}
  .compose textarea{min-height:45vh}  /* desktop: a tall writing box */
  .list{grid-column:1;grid-row:1}
  .list h2{margin-top:0}
  .compose .del{position:static;margin-top:12px}
}
form{display:grid;gap:10px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
textarea{width:100%;min-height:96px;font:inherit;color:inherit;background:transparent;border:0;outline:0;resize:vertical}
/* Typing boxes (pencil, reply, edit) use exactly the notes' font: 16px, same family/line height. */
textarea,.replyform textarea,.editform textarea{font:16px/1.45 -apple-system,Helvetica,Arial,sans-serif}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
label.file{flex:1;color:var(--muted);font-size:13px;cursor:pointer}
input[type=file]{font-size:13px;max-width:100%}
button{font:inherit;font-weight:600;color:#fff;background:var(--accent);border:0;border-radius:8px;padding:9px 18px;cursor:pointer}
.ok{color:#16a34a;font-size:13px;margin:8px 2px}
.sizerow{display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin:0 2px}
.clear{font-size:13px;font-weight:500;color:var(--ink);background:transparent;border:1px solid var(--line);padding:4px 10px}
.picked{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.picked li{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px;padding:5px 8px;border:1px solid var(--line);border-radius:8px;overflow-wrap:anywhere}
.picked .x{flex:none;width:26px;height:26px;padding:0;font-size:18px;line-height:1;color:var(--muted);background:transparent;border:1px solid var(--line);border-radius:6px}
.size{font-size:13px;color:var(--muted);margin:0 2px}.size.bad{color:#dc2626;font-weight:600}
button:disabled{opacity:.4;cursor:not-allowed}
.num{color:var(--bright);font-weight:600;font-size:16px}
.details{position:relative;margin-left:10px;text-decoration:underline;text-underline-offset:2px;cursor:default;outline:0}
/* The card fades in, stays open while the mouse moves onto it (so its text can be selected and
   copied), and waits 0.05 s before fading out so tiny slips don't close it. */
.details .tip{position:absolute;left:calc(100% + 8px);top:-7px;z-index:20;width:max-content;max-width:min(360px,80vw);
  padding:8px 10px;border-radius:8px;background:var(--bright);color:var(--bg);font-size:13px;line-height:1.5;
  text-decoration:none;box-shadow:0 6px 18px rgba(0,0,0,.25);overflow-wrap:anywhere;cursor:text;user-select:text;
  opacity:0;visibility:hidden;transform:translateX(-3px);
  transition:opacity .15s ease .05s,transform .15s ease .05s,visibility 0s linear .2s}
/* Invisible bridge over the 8px gap between "details" and the card (which opens to its right),
   so moving across never leaves the hover area. */
.details .tip::before{content:"";position:absolute;top:0;bottom:0;left:-8px;width:8px}
.details:hover .tip,.details:focus .tip,.details:focus-within .tip{opacity:1;visibility:visible;transform:none;
  transition:opacity .15s ease,transform .15s ease,visibility 0s}
/* Entries list: a vertical divider near the left. Notes, attachments, and replies start at it.
   Left of it (the gutter) each line gets: its select circle in its own column at the far left,
   then its icons right next to the divider, all on the same line as what they act on. */
.elist{--gut:34px;position:relative}
.gut{display:inline-flex;align-items:center;gap:6px;flex:none}
.gicons,.gcircle{display:flex;align-items:center;gap:6px}
.phoneonly{display:contents}
.micons{display:none;gap:6px;margin-left:auto}
@media(min-width:900px){
  .elist{padding-left:var(--gut)}
  /* No positioned elements inside .elist, so left:0 is the list's left edge while each group
     keeps its own line's height. */
  .gut{position:absolute;left:0;width:calc(var(--gut) - 10px);justify-content:flex-end}
  .gcircle{width:18px;justify-content:center}
}
@media(max-width:899px){.gicons{display:none}.micons{display:flex}
  /* phones: half the desktop height, fixed, scrolling inside when the text is longer */
  .compose textarea{height:22.5vh;min-height:22.5vh;max-height:22.5vh;overflow-y:auto;resize:none}}
.hicons{display:flex;flex-wrap:nowrap;align-items:center;gap:6px;margin-left:auto;flex:none}
.ehead{flex-wrap:nowrap}.ehead .t{min-width:0;overflow-wrap:anywhere}
.ehead a.num{text-decoration:none}
.edited{margin-left:8px}
.actions{display:flex;align-items:center;gap:6px;margin:8px 0 0;font-size:13px;color:var(--muted)}
/* TEST (may be undone): Reply · Edit stay left; Copy · Raw ↗ (· Delete…) go right. */
.actions .copyid{margin-left:auto}.actions span[aria-hidden]:has(+ .copyid){display:none}
.actions[hidden],.replyform[hidden]{display:none}
.replyline,.editline{padding:0;font:inherit;font-size:13px;font-weight:500;color:var(--bright);background:none;border:0;cursor:pointer}
.actions{color:var(--bright)}
.rawarrow{font-size:70%}
.replyline:hover,.editline:hover{color:var(--bright);text-decoration:underline}
a.editline{text-decoration:none}
.replies{margin:6px 0 0 18px;border-left:2px solid var(--line);padding-left:12px}
.replies:empty,.replies[hidden]{display:none}
.replies.barhover{cursor:pointer;border-left-color:var(--muted)}
.rtoggle{display:block;width:50%;text-align:left;background:none;border:0;padding:2px 0;margin:4px 0 0;font:inherit;font-size:13px;color:var(--muted);cursor:pointer}
.rtoggle:hover{color:var(--bright)}.rarrow{font-size:2em;line-height:0;vertical-align:-.12em}
.r{padding:8px 6px;border-radius:8px}.r+.r{border-top:1px solid var(--line)}
.r.flash,.r.rsel{background:var(--hl)}
.r{cursor:default}
/* Select circles: hidden (but keeping their space, so nothing shifts) until something is
   selected, or on the row under the mouse on devices that can hover. */
.pick,.apick,.rpick{visibility:hidden}
body.selecting .pick,body.selecting .apick,body.selecting .rpick{visibility:visible}
@media(hover:hover){
  .e:hover>.ehead .pick,.att:hover .apick,.r:hover .rpick,.pick:focus-visible,.apick:focus-visible,.rpick:focus-visible{visibility:visible}
}
.rpick{appearance:none;-webkit-appearance:none;flex:none;width:14px;height:14px;margin:0 2px 0 0;border:2px solid var(--muted);border-radius:50%;cursor:pointer;display:grid;place-items:center}
.rpick:checked{background:var(--accent);border-color:var(--accent)}
.rpick:checked::after{content:"";width:3px;height:6px;border:solid #fff;border-width:0 1.5px 1.5px 0;transform:translateY(-1px) rotate(45deg)}
.del .brk{flex-basis:100%;height:0}  /* count + Copy text on line 1; the other actions below */
.delwhy{flex-basis:100%;font-size:13px;color:#dc2626}
#seldelete:disabled{opacity:.45;cursor:not-allowed}
.r .note{margin:4px 0}
.replyform,.editform{display:grid;gap:6px;margin:8px 0}
.replyform textarea,.editform textarea{width:100%;min-height:70px;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px}
.replyform .row,.editform .row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.replyform .plain,.editform .plain,.sendform .plain{background:transparent;color:var(--muted);border:1px solid var(--line)}
a.ref{font-weight:600}
.sendform{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.sendform[hidden]{display:none}.sendform input{font:inherit;padding:6px;border:1px solid var(--line);border-radius:6px;background:transparent;color:inherit;min-width:200px}
.ehead{display:flex;justify-content:space-between;align-items:center;gap:8px}
.e{-webkit-touch-callout:none;cursor:default;border-radius:8px;padding-left:8px;padding-right:8px;transition:background .1s}
.e.sel{background:var(--hl)}
/* round checkbox on the right */
.pick{appearance:none;-webkit-appearance:none;flex:none;width:18px;height:18px;margin:0;border:2px solid var(--muted);border-radius:50%;cursor:pointer;display:grid;place-items:center}
.pick:checked{background:var(--accent);border-color:var(--accent)}
.pick:checked::after{content:"";width:5px;height:9px;border:solid #fff;border-width:0 2px 2px 0;transform:translateY(-1px) rotate(45deg)}
.pick:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
label.t{cursor:pointer;user-select:none}
/* Same size/style as the "N saved · emailed" text beside it, in white. */
.selall{font:inherit;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--bright);background:transparent;border:1px solid var(--line);border-radius:6px;padding:2px 8px;margin-left:8px;cursor:pointer}.meta{font-size:13px}
@media(max-width:899px){.del{position:fixed;left:12px;right:12px;bottom:12px;z-index:30}}
.del{position:sticky;bottom:12px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:12px;
  background:var(--card);border:1px solid #dc2626;border-radius:12px;padding:10px;box-shadow:0 6px 20px rgba(0,0,0,.15)}
.del[hidden]{display:none}.del input{flex:1;min-width:110px;font:inherit;padding:7px;border:1px solid var(--line);border-radius:8px;background:transparent;color:inherit}
.del button{background:#dc2626}.del form{display:flex;flex-wrap:wrap;gap:8px;flex-basis:100%}
.del form[hidden]{display:none}.del .plain{background:transparent;color:var(--muted);border:1px solid var(--line)}
.top{display:flex;justify-content:flex-end;margin:-8px 0 8px}
.top button{font-size:13px;font-weight:500;color:var(--muted);background:transparent;border:1px solid var(--line);padding:5px 10px}
h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:28px 2px 8px;display:flex;justify-content:space-between;align-items:baseline}
h2 .dtitle{font-size:18px;font-style:italic;color:#b8860b}
@media(prefers-color-scheme:dark){h2 .dtitle{color:#f5c518}}
h2 a,.nav a{color:var(--muted);font-weight:400;text-transform:none;letter-spacing:0}
.e{padding:12px 2px}
/* Between entries: a thicker divider in a small gap, so neighbouring highlights stay separate. */
.esep{border:0;height:2px;background:var(--line);margin:5px 0}.t{color:var(--muted);font-size:13px}
.e p{margin:4px 0;white-space:pre-wrap;overflow-wrap:anywhere}.e a{color:var(--accent)}
.atts{border:1px solid var(--line);border-radius:10px;margin-top:8px;padding:0}
.att:first-child{border-radius:9px 9px 0 0}.att:last-child{border-radius:0 0 9px 9px}.att:only-child{border-radius:9px}
.att{cursor:default;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 10px;font-size:13px}
.att+.att{border-top:1px solid var(--line)}
.delfile{display:flex;flex-wrap:wrap;gap:6px;padding:6px 0 8px}
.delfile input{flex:1;min-width:100px;font:inherit;font-size:13px;padding:6px;border:1px solid var(--line);border-radius:6px;background:transparent;color:inherit}
.delfile button{font-size:13px;padding:6px 12px;background:#dc2626}.delfile .plain{background:transparent;color:var(--muted);border:1px solid var(--line)}
.delatt:hover{color:#dc2626;border-color:#dc2626}
.atticons{align-items:center}
.apick{appearance:none;-webkit-appearance:none;flex:none;width:14px;height:14px;margin:0 2px 0 0;border:2px solid var(--muted);border-radius:50%;cursor:pointer;display:grid;place-items:center}
.apick:checked{background:var(--accent);border-color:var(--accent)}
.apick:checked::after{content:"";width:3px;height:6px;border:solid #fff;border-width:0 1.5px 1.5px 0;transform:translateY(-1px) rotate(45deg)}
/* Files box keeps the page background even inside a selected (tinted) entry, so only the
   ticked files look highlighted. */
.atts{background:var(--bg)}
:root{--hl:color-mix(in srgb,var(--accent) 14%,var(--bg))}  /* one solid highlight shade, never layered */
/* rows fill the box edge to edge, so a highlight reaches all sides (corners clipped by .atts) */
.att.asel{background:var(--hl)}
.att>.attname{flex:0 1 auto;margin-right:auto}
.ehead>.pick,.ehead>.rpick{margin-right:2px}
.attname{min-width:0;overflow-wrap:anywhere}.atticons{display:flex;gap:6px;flex:none}
.attbtn{display:inline-grid;place-items:center;flex:none;width:24px;height:24px;padding:0;color:var(--muted);background:transparent;border:1px solid var(--line);border-radius:6px;text-decoration:none;cursor:pointer}
.attbtn:hover{color:var(--bright);border-color:var(--muted)}.attbtn.ok{color:#16a34a;border-color:#16a34a}
/* Preview overlay (click a file name) */
.pv{position:fixed;inset:0;z-index:50;display:grid;place-items:center;background:rgba(0,0,0,.72);padding:16px}
.pv[hidden]{display:none}
.pvbox{position:relative;max-width:min(1000px,100%);max-height:100%;display:flex;flex-direction:column;background:var(--card);border-radius:12px;overflow:hidden}
.pvhead{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 12px;font-size:13px;border-bottom:1px solid var(--line)}
.pvhead span{overflow-wrap:anywhere}.pvclose{font-size:18px;line-height:1;color:var(--bright);background:transparent;border:0;padding:0 4px;cursor:pointer}
.pvbody{overflow:auto;min-height:0}.pvbody img,.pvbody video{display:block;max-width:100%;max-height:80vh;margin:auto}
.pvbody pre{margin:0;padding:12px;font:13px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:80vh}
.pvbody iframe{display:block;width:min(1000px,92vw);height:80vh;border:0;background:#fff}.pvbody audio{display:block;margin:20px}
.e img{max-width:100%;max-height:320px;border-radius:8px;margin-top:6px;display:block}
.tools{display:flex;gap:8px;margin:14px 2px;flex-wrap:wrap}.tools button,.tools a{font-size:13px;background:transparent;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:6px 10px;text-decoration:none;font-weight:500}
/* three columns: equal sides keep the middle link centered whatever the dates say */
.nav{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px;margin:0 2px 12px;font-size:13px}
.nav>:first-child{justify-self:end}.nav>:last-child{justify-self:start}
.nav a,.nav .today{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}

.nav .today{font-weight:600;color:var(--bright);text-align:center}
.title{font-size:28px;margin:4px 2px 12px;letter-spacing:-.01em}
.title a{color:inherit;text-decoration:none}
.pencil{font-size:18px;font-style:italic;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#b8860b;margin:0 2px 6px}
@media(prefers-color-scheme:dark){.pencil{color:#f5c518}}
.pinsnav{float:right;margin-top:4px}.pinsnav a,.nav a{display:inline-block;font-size:13px;font-weight:500;color:var(--bright);border:1px solid var(--line);border-radius:6px;padding:5px 10px;text-decoration:none}.pinsnav a:hover,.nav a:hover{border-color:var(--bright)}
.pinbox{display:inline-flex;flex-direction:row-reverse;align-items:center;gap:8px}
.pinbtn{background:none;border:0;padding:0;font:inherit;font-family:ui-monospace,monospace;font-size:13px;color:var(--muted);cursor:pointer}
.pinbtn{filter:grayscale(1);opacity:.35}
.pinbtn:hover{opacity:.8}
.pinbox.on .pinbtn{filter:none;opacity:1}
.pingo{display:none;font-size:13px;color:var(--accent)}
.pinbox:hover .pingo,.pinbox:focus-within .pingo{display:inline}
form.inline{display:contents}
</style></head><body><main>
<script data-nav>
// Day buttons (← · Today · →) swap the page in place instead of a full reload, so rapid clicks
// all register (Chrome ignores clicks while it holds the old page during a reload). The new
// day's page is fetched, its <body> swapped in, and its scripts re-run inside a block so their
// top-level consts don't clash. Listeners the page scripts put on window/document are tracked
// and removed before each swap so they don't pile up. Anything odd falls back to a normal load.
(() => {
  if (window.__dayNav) return;
  const on = (t, type, fn) => EventTarget.prototype.addEventListener.call(t, type, fn);
  const rec = [];
  for (const t of [window, document]) {
    t.addEventListener = (type, fn, opt) => { rec.push([t, type, fn, opt]); EventTarget.prototype.addEventListener.call(t, type, fn, opt); };
  }
  let seq = 0, path = location.pathname;
  async function load(url, push) {
    const my = ++seq;
    let doc;
    try {
      const r = await fetch(url, { credentials: "same-origin" });
      if (!r.ok || r.redirected) throw 0;
      doc = new DOMParser().parseFromString(await r.text(), "text/html");
    } catch { location.href = url; return; }
    if (my !== seq) return;  // a newer click won
    if (!doc.querySelector(".nav")) { location.href = url; return; }
    for (const [t, type, fn, opt] of rec.splice(0)) EventTarget.prototype.removeEventListener.call(t, type, fn, opt);
    if (push) history.pushState(null, "", url);
    path = location.pathname;
    document.title = doc.title;
    document.body.replaceWith(document.adoptNode(doc.body));
    for (const old of document.body.querySelectorAll("script")) {
      if (old.hasAttribute("data-nav")) { old.remove(); continue; }
      const sc = document.createElement("script");
      sc.textContent = "{\\n" + old.textContent + "\\n}";
      old.replaceWith(sc);
    }
    if (!location.hash) window.scrollTo(0, 0);
  }
  window.__dayNav = load;
  on(document, "click", (e) => {
    const a = e.target.closest && e.target.closest(".nav a");
    if (!a || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    load(a.href, true);
  });
  on(window, "popstate", () => { if (location.pathname !== path) load(location.href, false); });
})();
</script>
<script>
// Clipboard that also works on plain http (http://mr-ray/inbox/ at home): browsers only allow
// navigator.clipboard on https, so fall back to the classic hidden-textarea copy.
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try { await navigator.clipboard.writeText(text); return true; } catch {}
  }
  const ta = document.createElement("textarea");
  ta.value = text; ta.setAttribute("readonly", "");
  ta.style.cssText = "position:fixed;top:0;left:0;opacity:0;pointer-events:none";
  document.body.append(ta); ta.select(); ta.setSelectionRange(0, text.length);
  let ok = false;
  try { ok = document.execCommand("copy"); } catch {}
  ta.remove();
  return ok;
}
</script>
{logout}
{pins_link}
<h1 class="title"><a href="/inbox/" title="Today">Drop a line.</a></h1>
<div class="nav">{prev}{today}{next}</div>
<div class="cols">
<aside class="compose">{form}
{flash}
<div id="selbar" class="del" hidden>
  <b id="delcount"></b>
  <span class="brk" aria-hidden="true"></span>
  <button type="button" id="selcopy" class="plain" title="Notes with time, source, and attachment links">Copy data</button>
  <button type="button" id="selexport" class="plain">Export .zip</button>
  <button type="button" id="seldelete">Delete…</button>
  <span class="delwhy" id="delwhy" hidden></span>
  <button type="button" id="delcancel" class="plain">Cancel</button>
  <form id="delform" method="post" action="{base}delete/{day}" hidden>
    <input name="username" placeholder="Username" autocomplete="username" autocapitalize="none" required>
    <input type="password" name="password" placeholder="Password" autocomplete="current-password" required>
    <button>Delete</button>
  </form>
</div></aside>
<section class="list">
<h2><span class="dtitle">{title}</span><span>{count} <button type="button" id="selectall" class="selall" hidden>Select all</button></span></h2>
{entries}
<script>
// Multi-select delete: tick entries (shift-click ticks a range, "Select all" ticks
// everything), then confirm with username + password.
(() => {
  const bar = document.getElementById("selbar"), form = document.getElementById("delform");
  const picks = [...document.querySelectorAll(".pick")];
  const ENTRIES = {entries_json};  // entry head (number, time, note, source) per position
  const FILES = {files_json};      // per position: file name -> its attachment line
  const RTEXT = {replies_json};    // reply id -> its text block (with its attachments)
  const NOTES = {notes_json};      // just the note per position, for "Copy text"
  const chosen = () => picks.filter((p) => p.checked).map((p) => Number(p.value)).sort((a, b) => a - b);
  const all = document.getElementById("selectall");
  let last = null;
  const update = (fromFile = false) => {
    if (!fromFile && typeof syncFiles === "function") syncFiles();
    const n = picks.filter((p) => p.checked).length;
    bar.hidden = n === 0;
    if (n === 0) form.hidden = true;
    document.getElementById("delcount").textContent = `${n} selected`;
    all.textContent = n === picks.length && n ? "Select none" : "Select all";
    picks.forEach((p) => p.closest(".e").classList.toggle("sel", p.checked));
    apicks.flat().forEach((a) => a.closest(".att") && a.closest(".att").classList.toggle("asel", a.checked));
    rpicks.flat().forEach((a) => a.closest(".r") && a.closest(".r").classList.toggle("rsel", a.checked));
    const files = apicks.flat().filter((a) => a.checked).length;
    const reps = rpicks.flat().filter((a) => a.checked).length;
    // Circles show everywhere while anything is selected (see .selecting in the CSS).
    if (document.body) document.body.classList.toggle("selecting", n + files + reps > 0);
    bar.hidden = n === 0 && files === 0 && reps === 0;
    // An entry can't be deleted without all its replies: block Delete and say why.
    const blocked = picks.map((p, i) => (p.checked && rpicks[i].some((a) => !a.checked) ? i : -1)).filter((i) => i >= 0);
    const why = document.getElementById("delwhy"), sd = document.getElementById("seldelete");
    if (sd) sd.disabled = blocked.length > 0;
    if (why) {
      why.hidden = !blocked.length;
      why.textContent = blocked.length
        ? `Deleting ${blocked.map((i) => "#" + rows[i].id).join(", ")} also deletes all ${blocked.length > 1 ? "their" : "its"} replies: tick them all, or untick the entry.`
        : "";
    }
    if (blocked.length && form) form.hidden = true;
    document.getElementById("delcount").textContent =
      `${n} entr${n === 1 ? "y" : "ies"}` + (reps ? `, ${reps} repl${reps === 1 ? "y" : "ies"}` : "") +
      (files ? `, ${files} file${files === 1 ? "" : "s"}` : "") + " selected";
  };
  all.hidden = picks.length === 0;
  // Outlook-style: click an entry to select it (Ctrl/Cmd-click adds or removes one,
  // Shift-click selects a range). The round checkbox on the right ticks just that entry.
  const rows = picks.map((p) => p.closest(".e"));
  // Attachment circles: independent, except that changing an entry's selection sets all of its
  // attachments to match (select entry -> all its files; deselect entry -> none of them).
  const apicks = rows.map((r) => (r && r.querySelectorAll ? [...r.querySelectorAll(".apick")] : []));
  // Reply circles work like file circles: independent, but follow their entry's selection.
  const rpicks = rows.map((r) => (r && r.querySelectorAll ? [...r.querySelectorAll(".rpick")] : []));
  const subs = (i) => [...apicks[i], ...rpicks[i]];
  const allSubs = () => [...apicks.flat(), ...rpicks.flat()];
  let before = picks.map((p) => p.checked);
  var syncFiles = () => {  // entries whose selection changed: their files follow
    picks.forEach((p, i) => {
      if (p.checked !== before[i]) subs(i).forEach((a) => (a.checked = p.checked));
    });
    before = picks.map((p) => p.checked);
  };
  rpicks.forEach((list) => list.forEach((a) => {
    a.addEventListener("click", (e) => { e.stopPropagation(); update(true); });
    const box = a.closest(".r");
    if (box && box.addEventListener) box.addEventListener("click", (e) => {
      e.stopPropagation();
      if (e.target.closest("a, button, input, textarea, form, .details")) return;
      a.checked = !a.checked;
      update(true);
    });
  }));
  apicks.forEach((list) => list.forEach((a) => {
    a.addEventListener("click", (e) => { e.stopPropagation(); update(true); });
    // Click anywhere on the file's line (not its name link or icons) to toggle it, like entries.
    const line = a.closest(".att");
    if (line && line.addEventListener) line.addEventListener("click", (e) => {
      e.stopPropagation();  // a file click never toggles the entry around it
      if (e.target.closest("a, button, input, form")) return;
      a.checked = !a.checked;
      update(true);
    });
  }));
  const range = (a, b, on) => { const [x, y] = a < b ? [a, b] : [b, a]; for (let k = x; k <= y; k++) picks[k].checked = on; };
  // Phones: press and hold an entry to select it; while anything is selected, taps add or
  // remove entries. With nothing selected a tap does nothing, so scrolling never selects.
  const busy = (t) => t.closest("a, button, input, textarea, select, form, video, audio, .details, .replies");
  let touchTimer = null, held = false, lastTouch = 0;
  rows.forEach((row, i) => {
    row.addEventListener("touchstart", (e) => {
      lastTouch = Date.now(); held = false;
      if (busy(e.target)) return;
      touchTimer = setTimeout(() => {
        held = true; picks[i].checked = !picks[i].checked; last = i; update();
        if (navigator.vibrate) navigator.vibrate(15);
      }, 450);
    }, { passive: true });
    const cancelHold = () => clearTimeout(touchTimer);
    row.addEventListener("touchmove", cancelHold, { passive: true });
    row.addEventListener("touchend", cancelHold);
    row.addEventListener("contextmenu", (e) => { if (held) e.preventDefault(); }); // no long-press menu
    row.addEventListener("mousedown", (e) => { if (e.shiftKey) e.preventDefault(); }); // no text highlight on shift-click
    row.addEventListener("click", (e) => {
      if (busy(e.target)) return;
      if (Date.now() - lastTouch < 800) {  // a tap (touch screens)
        if (held) { held = false; return; }  // the hold already selected it
        if (picks.some((p) => p.checked)) { picks[i].checked = !picks[i].checked; last = i; update(); }
        return;
      }
      // Selected entry with a deselected file: clicking it deselects the entry and its files.
      if (picks[i].checked && subs(i).some((a) => !a.checked) && !e.shiftKey) {
        picks[i].checked = false; subs(i).forEach((a) => (a.checked = false)); last = i; update(); return;
      }
      const add = e.ctrlKey || e.metaKey;
      if (e.shiftKey && last !== null) {
        if (!add) picks.forEach((p) => (p.checked = false));
        range(last, i, true);
      } else if (add) {
        picks[i].checked = !picks[i].checked;
        last = i;
      } else {
        const onlyThis = picks[i].checked && picks.filter((p) => p.checked).length === 1;
        picks.forEach((p) => (p.checked = false));
        picks[i].checked = !onlyThis;  // clicking the lone selected entry again unselects it
        last = i;
      }
      update();
    });
  });
  picks.forEach((p, i) => p.addEventListener("click", (e) => {
    if (e.shiftKey && last !== null && last !== i) range(last, i, p.checked);
    last = i;
    update();
  }));
  all.onclick = () => {
    const on = !picks.every((p) => p.checked);
    picks.forEach((p) => (p.checked = on));
    last = null;
    update();
  };
  const clearAll = () => { picks.forEach((p) => (p.checked = false)); allSubs().forEach((a) => (a.checked = false)); last = null; update(); };
  document.getElementById("delcancel").onclick = clearAll;
  // /inbox/2026-11-23#5 selects entry 5; #5.1 highlights that reply (also on #N links).
  const goTo = () => {
    const id = decodeURIComponent(location.hash.slice(1));
    if (!/^\\d+(\\.\\d+)?$/.test(id)) return;
    const el = document.getElementById(id);
    if (!el) return;
    openRepliesFor(el);
    document.querySelectorAll(".r.flash").forEach((x) => x.classList.remove("flash"));
    const k = picks.findIndex((p) => p.closest(".e") === el.closest(".e"));
    if (el.classList.contains("e") && k >= 0) {
      picks.forEach((p) => (p.checked = false)); allSubs().forEach((a) => (a.checked = false));
      picks[k].checked = true; last = k; update();
    } else el.classList.add("flash");
    el.scrollIntoView({ block: "center", behavior: "smooth" });
  };
  window.addEventListener("hashchange", goTo);
  setTimeout(goTo, 0);
  // Escape deselects everything; Ctrl/Cmd+A selects everything (both skipped while a preview
  // is open).
  document.addEventListener("keydown", (e) => {
    const pv = document.getElementById("pv");
    if (pv && !pv.hidden) return;
    // Ctrl/Cmd+A selects every entry, except while typing (then it selects text as usual).
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
      if (e.target.closest("input, textarea, [contenteditable]") || !picks.length) return;
      e.preventDefault();
      picks.forEach((p) => (p.checked = true));
      update();
      return;
    }
    if (e.key !== "Escape") return;
    if (!picks.some((p) => p.checked) && !allSubs().some((a) => a.checked)) return;
    clearAll();
  });
  document.getElementById("seldelete").onclick = () => { form.hidden = false; form.querySelector("input").focus(); };
  // What's selected, entry by entry: selected entries with only their ticked files; files
  // ticked on their own come under their entry's number marked "(files only)".
  const ticked = (i) => apicks[i].filter((a) => a.checked).map((a) => a.value);
  const tickedReplies = (i) => rpicks[i].filter((a) => a.checked).map((a) => RTEXT[a.value]).filter(Boolean);
  document.getElementById("selcopy").onclick = async (e) => {
    const blocks = [];
    picks.forEach((p, k) => {
      const i = Number(p.value), files = ticked(k).map((f) => FILES[i][f]).filter(Boolean);
      const reps = tickedReplies(k);
      if (p.checked) blocks.push([ENTRIES[i], ...files, ...reps].join("\\n"));
      else if (files.length || reps.length) blocks.push([(ENTRIES[i].match(/^\\[[^\\]]*\\]/) || [""])[0] + " (only parts selected)", ...files, ...reps].join("\\n"));
    });
    const text = [`From my inbox for {day}:`, ...blocks.reverse()].join("\\n\\n");  // oldest first
    copyOut(e.target, text, "Copy data");
  };
  async function copyOut(btn, text, label) {
    btn.textContent = (await copyText(text)) ? "Copied" : "Couldn't copy";
    setTimeout(() => (btn.textContent = label), 1500);
  }
  document.getElementById("selexport").onclick = () => {
    const files = apicks.flat().filter((a) => a.checked).map((a) => "f=" + encodeURIComponent(a.value));
    const reps = rpicks.flat().filter((a) => a.checked).map((a) => "r=" + encodeURIComponent(a.value));
    location.href = "{base}export/{day}?" + [...chosen().map((i) => "i=" + i), ...(files.length ? files : ["f="]), ...(reps.length ? reps : ["r="])].join("&");
  };
})();
</script>
<div class="pv" id="pv" hidden role="dialog" aria-modal="true" aria-labelledby="pvname">
  <div class="pvbox"><div class="pvhead"><span id="pvname"></span><button type="button" class="pvclose" id="pvclose" aria-label="Close">×</button></div>
  <div class="pvbody" id="pvbody"></div></div>
</div>
<div class="tools">
  <button type="button" id="copy">Copy for Claude</button>
  <a href="{base}day/{day}.md" target="_blank" rel="noopener">inbox.md</a>
  {send}
</div>
</section>
</div>
</main>
<script>
const text = {plain};
const CHECK = {check_icon};
const NOTE = {allnotes_json};  // id ("5", "5.1") -> raw note text, for edit/copy
// Reply: clicking the "Reply" line under an entry opens its reply box (in place of the line).
document.querySelectorAll(".replyline").forEach((b) => b.addEventListener("click", (e) => {
  e.stopPropagation();
  const f = b.closest(".e").querySelector(".replyform");
  f.hidden = false; b.closest(".actions").hidden = true; b.setAttribute("aria-expanded", "true");
  const box = b.closest(".e").querySelector(".replies"); if (box) setReplies(box, true);  // box stays above them
  f.querySelector("textarea").focus();
}));
document.querySelectorAll(".cancelreply").forEach((b) => b.addEventListener("click", (e) => {
  e.stopPropagation();
  const f = b.closest(".replyform"), acts = f.closest(".e").querySelector(".actions");
  f.hidden = true; acts.hidden = false; acts.querySelector(".replyline").setAttribute("aria-expanded", "false");
}));
// Edit: swap the note for a text box (Save overwrites it; marked "edited").
document.querySelectorAll(".editbtn").forEach((b) => b.addEventListener("click", (e) => {
  e.stopPropagation();
  const id = b.dataset.id, item = b.closest(".r") || b.closest(".e");
  if (item.querySelector(".editform")) return;
  const note = item.querySelector(`.note[data-id="${CSS.escape(id)}"]`);
  const f = document.createElement("form");
  f.method = "post"; f.action = "{base}edit/{day}"; f.className = "editform";
  f.innerHTML = '<input type="hidden" name="id"><textarea name="text"></textarea>' +
    '<div class="row"><button>Save</button><button type="button" class="plain">Cancel</button></div>';
  f.elements.id.value = id; f.elements.text.value = NOTE[id] || "";
  f.querySelector(".plain").onclick = () => { f.remove(); note.hidden = !NOTE[id]; };
  note.hidden = true; note.after(f);
  f.elements.text.focus();
}));
// Copy a note (entries and replies).
document.querySelectorAll(".copyid").forEach((b) => b.addEventListener("click", async (e) => {
  e.stopPropagation();
  const label = b.textContent, ok = await copyText(NOTE[b.dataset.id] || "");
  b.textContent = ok ? "Copied" : "Couldn't copy";
  setTimeout(() => (b.textContent = label), 1500);
}));
// Delete a reply: confirm under it with username + password.
document.querySelectorAll(".delreply").forEach((b) => b.addEventListener("click", (e) => {
  e.stopPropagation();
  const r = b.closest(".r");
  if (r.querySelector(".delfile")) return;
  const f = document.createElement("form");
  f.method = "post"; f.action = "{base}delete/{day}"; f.className = "delfile";
  f.innerHTML = '<input type="hidden" name="reply">' +
    '<input name="username" placeholder="Username" autocomplete="username" autocapitalize="none" required>' +
    '<input type="password" name="password" placeholder="Password" autocomplete="current-password" required>' +
    '<button>Delete reply</button><button type="button" class="plain">Cancel</button>';
  f.elements.reply.value = b.dataset.id;
  f.querySelector(".plain").onclick = () => f.remove();
  r.querySelector(".ehead").after(f);
  f.elements.username.focus();
}));
// Email this day: open the "To" box (your address prefilled), then Send.
const emailOpen = document.getElementById("emailopen");
if (emailOpen) {
  const sf = document.getElementById("sendform");
  emailOpen.onclick = () => { sf.hidden = false; emailOpen.hidden = true; sf.querySelector("input").focus(); };
  document.getElementById("emailcancel").onclick = () => { sf.hidden = true; emailOpen.hidden = false; };
}
// Trash icon on a file: confirm right under that line with username + password.
document.querySelectorAll(".delatt").forEach((btn) => btn.onclick = () => {
  const line = btn.closest(".att");
  if (line.nextElementSibling && line.nextElementSibling.classList.contains("delfile")) return;
  const f = document.createElement("form");
  f.method = "post"; f.action = "{base}delete/{day}"; f.className = "delfile";
  f.innerHTML = '<input type="hidden" name="file">' +
    '<input name="username" placeholder="Username" autocomplete="username" autocapitalize="none" required>' +
    '<input type="password" name="password" placeholder="Password" autocomplete="current-password" required>' +
    '<button>Delete file</button><button type="button" class="plain">Cancel</button>';
  f.elements.file.value = btn.dataset.file;
  f.querySelector(".plain").onclick = () => f.remove();
  line.after(f);
  f.elements.username.focus();
});
// Click a file name: preview it here (image, text, video/audio, PDF); other types open normally.
(() => {
  const pv = document.getElementById("pv"), body = document.getElementById("pvbody");
  const close = () => { pv.hidden = true; body.replaceChildren(); };
  document.getElementById("pvclose").onclick = close;
  pv.addEventListener("click", (e) => { if (e.target === pv) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !pv.hidden) close(); });
  document.querySelectorAll(".attname").forEach((a) => a.addEventListener("click", async (e) => {
    const card = a.closest(".att"), url = card.dataset.url, ext = (url.split(".").pop() || "").toLowerCase();
    const media = { mp4: "video", mov: "video", webm: "video", m4v: "video", m4a: "audio", mp3: "audio", wav: "audio", aac: "audio", ogg: "audio" }[ext];
    let el;
    if (card.dataset.kind === "image") { el = document.createElement("img"); el.src = url; el.alt = ""; }
    else if (media) { el = document.createElement(media); el.src = url; el.controls = true; el.autoplay = true; }
    else if (ext === "pdf") { el = document.createElement("iframe"); el.src = url; el.title = a.textContent; }
    else if (card.dataset.kind === "text") {
      el = document.createElement("pre"); el.textContent = "Loading…";
      fetch(url).then((r) => r.text()).then((t) => (el.textContent = t)).catch(() => (el.textContent = "Couldn't load it."));
    } else return;  // zip etc.: let the link open/download as usual
    e.preventDefault();
    document.getElementById("pvname").textContent = a.textContent;
    body.replaceChildren(el);
    pv.hidden = false;
  }));
})();
// Attachment Copy: text files copy their text, images copy the picture (as PNG, what
// clipboards accept), anything else copies its full link.
document.querySelectorAll(".copyatt").forEach((btn) => btn.onclick = async () => {
  const card = btn.closest(".att"), url = new URL(card.dataset.url, location.href).href;
  // Like GitHub: the copy icon turns into a green check for a moment.
  const icon = btn.innerHTML;
  const done = (t) => { btn.innerHTML = CHECK; btn.classList.add("ok"); btn.title = t;
    setTimeout(() => { btn.innerHTML = icon; btn.classList.remove("ok"); btn.title = "Copy"; }, 1500); };
  try {
    if (card.dataset.kind === "text") {
      if (!(await copyText(await (await fetch(url)).text()))) throw 0;
    } else if (card.dataset.kind === "image" && window.ClipboardItem && window.isSecureContext) {
      const bmp = await createImageBitmap(await (await fetch(url)).blob()), c = document.createElement("canvas");
      c.width = bmp.width; c.height = bmp.height; c.getContext("2d").drawImage(bmp, 0, 0);
      const png = await new Promise((r) => c.toBlob(r, "image/png"));
      await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
    } else {
      // Images can only go on the clipboard over https; on http (at home) copy the link.
      return (await copyText(url)) ? done("Link copied") : done("Couldn't copy");
    }
    done("Copied");
  } catch { done((await copyText(url)) ? "Link copied" : "Couldn't copy"); }
});
document.getElementById("copy").onclick = async (e) => {
  e.target.textContent = (await copyText(text)) ? "Copied" : "Couldn't copy";
};
</script>
{replies_js}</body></html>"""

FORM = """<div class="pencil">pencil pencil.</div>
<form method="post" id="addform" action="{base}add" enctype="multipart/form-data">
  <textarea name="text" placeholder="Anything: a note, a link, what this photo is for…" autofocus></textarea>
  <div class="row">
    <label class="file"><input type="file" name="file" id="file" multiple></label>
    <button id="save">Save</button>
  </div>
  <ul class="picked" id="picked" hidden></ul>
  <div class="sizerow"><span class="size" id="size" aria-live="polite"></span>
    <button type="button" id="clearall" class="clear" hidden>Remove all files</button></div>
</form>
<script>
// ⌘/Ctrl+Enter in the box saves: it clicks Save, so it does nothing while Save is disabled
// (files over the size limit).
document.querySelector("#addform textarea").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); document.getElementById("save").click(); }
});
// Picked files build up in a list (each with an x to remove it); the input is kept in sync so
// a normal form post sends exactly the listed files. Total is checked against MAX_MB before
// uploading (95 MB from the web, where Cloudflare rejects anything over 100 MB; more at home).
(() => {
  const MAX_MB = {max_mb};
  const LIMIT = MAX_MB >= 1024 && MAX_MB % 1024 === 0 ? MAX_MB / 1024 + " GB" : MAX_MB + " MB";
  const input = document.getElementById("file"), save = document.getElementById("save");
  const out = document.getElementById("size"), list = document.getElementById("picked");
  const clearAll = document.getElementById("clearall");
  const canEdit = typeof DataTransfer === "function";  // older browsers: plain file input
  let picked = [];
  const mb = (b) => (b / 1048576).toFixed(b < 10485760 ? 1 : 0);
  const sync = () => {
    if (!canEdit) return;
    const dt = new DataTransfer();
    picked.forEach((f) => dt.items.add(f));
    input.files = dt.files;
  };
  const render = () => {
    const files = canEdit ? picked : [...input.files];
    const total = files.reduce((n, f) => n + f.size, 0);
    const tooBig = total > MAX_MB * 1048576;
    save.disabled = tooBig;
    list.replaceChildren(...files.map((f, i) => {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = `${f.name} (${mb(f.size)} MB)`;
      li.append(name);
      if (canEdit) {
        const x = document.createElement("button");
        x.type = "button"; x.className = "x"; x.textContent = "\u00d7"; x.title = "Remove";
        x.setAttribute("aria-label", `Remove ${f.name}`);
        x.onclick = () => { picked.splice(i, 1); sync(); render(); };
        li.append(x);
      }
      return li;
    }));
    list.hidden = !files.length;
    clearAll.hidden = !files.length;
    out.className = "size" + (tooBig ? " bad" : "");
    out.textContent = !files.length ? `Files up to ${LIMIT}` : tooBig
      ? `${mb(total)} MB is over the ${LIMIT} limit. Remove some files (your text stays), or save a link instead.`
      : `${files.length} file${files.length > 1 ? "s" : ""}, ${mb(total)} MB`;
  };
  // Clearing the input's value un-picks everything (works even without DataTransfer).
  clearAll.addEventListener("click", () => { picked = []; input.value = ""; render(); });
  input.addEventListener("change", () => {
    if (canEdit) { picked = picked.concat([...input.files]); sync(); }
    render();
  });
  render();
  input.form.addEventListener("submit", (e) => { render(); if (save.disabled) e.preventDefault(); else save.textContent = "Saving\u2026"; });
})();
</script>"""


# Shown only to visitors who logged in (outside the home network). Also enforces "log in again
# on every new open": the login is remembered per tab (sessionStorage), so a new tab, a
# reopened home-screen app, or a restarted browser logs out and shows the login page.
LOGOUT = """<div class="top"><button type="button" id="logout">Log out</button></div>
<script>
(() => {
  const TAG = "{tag}";
  const logout = () => fetch("{base}logout", { method: "POST", cache: "no-store" })
    .catch(() => {}).then(() => location.replace("{base}"));
  const fresh = new URLSearchParams(location.search).get("login");
  if (fresh === TAG) { try { sessionStorage.setItem("inbox_tab", TAG); } catch {} history.replaceState(null, "", location.pathname); }
  else { let mine = null; try { mine = sessionStorage.getItem("inbox_tab"); } catch {} if (mine !== TAG) logout(); }
  document.getElementById("logout").onclick = logout;
})();
</script>"""


TEXT_EXT = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".xml",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".sh",
    ".c",
    ".h",
    ".cpp",
    ".rs",
    ".tsv",
}


# GitHub-style 16px line icons (Octicons shapes), drawn in the text color.
_SVG = '<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="{d}"/></svg>'
ICON_DOWNLOAD = _SVG.format(
    d="M2.75 14A1.75 1.75 0 0 1 1 12.25v-2.5a.75.75 0 0 1 1.5 0v2.5c0 .138.112.25.25.25h10.5a.25.25 0 0 0 .25-.25v-2.5a.75.75 0 0 1 1.5 0v2.5A1.75 1.75 0 0 1 13.25 14ZM7.25 7.689V2a.75.75 0 0 1 1.5 0v5.689l1.97-1.969a.749.749 0 1 1 1.06 1.06l-3.25 3.25a.749.749 0 0 1-1.06 0L4.22 6.78a.749.749 0 1 1 1.06-1.06l1.97 1.969Z"
)
ICON_COPY = _SVG.format(
    d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Zm5-5C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"
)
ICON_TRASH = _SVG.format(
    d="M11 1.75V3h2.25a.75.75 0 0 1 0 1.5H2.75a.75.75 0 0 1 0-1.5H5V1.75C5 .784 5.784 0 6.75 0h2.5C10.216 0 11 .784 11 1.75ZM4.496 6.675l.66 6.6a.25.25 0 0 0 .249.225h5.19a.25.25 0 0 0 .249-.225l.66-6.6a.75.75 0 0 1 1.492.149l-.66 6.6A1.748 1.748 0 0 1 10.595 15h-5.19a1.75 1.75 0 0 1-1.741-1.575l-.66-6.6a.75.75 0 1 1 1.492-.15ZM6.5 1.75V3h3V1.75a.25.25 0 0 0-.25-.25h-2.5a.25.25 0 0 0-.25.25Z"
)
ICON_OPEN = _SVG.format(
    d="M3.75 2h3.5a.75.75 0 0 1 0 1.5h-3.5a.25.25 0 0 0-.25.25v8.5c0 .138.112.25.25.25h8.5a.25.25 0 0 0 .25-.25v-3.5a.75.75 0 0 1 1.5 0v3.5A1.75 1.75 0 0 1 12.25 14h-8.5A1.75 1.75 0 0 1 2 12.25v-8.5C2 2.784 2.784 2 3.75 2Zm6.854-1h4.146a.25.25 0 0 1 .25.25v4.146a.25.25 0 0 1-.427.177L13.03 4.03 9.28 7.78a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042l3.75-3.75-1.543-1.543A.25.25 0 0 1 10.604 1Z"
)
ICON_REPLY = _SVG.format(
    d="M6.78 1.97a.75.75 0 0 1 0 1.06L3.81 6h6.44A4.75 4.75 0 0 1 15 10.75v2.5a.75.75 0 0 1-1.5 0v-2.5a3.25 3.25 0 0 0-3.25-3.25H3.81l2.97 2.97a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215L1.47 7.28a.75.75 0 0 1 0-1.06l4.25-4.25a.75.75 0 0 1 1.06 0Z"
)
ICON_EDIT = _SVG.format(
    d="M11.013 1.427a1.75 1.75 0 0 1 2.474 0l1.086 1.086a1.75 1.75 0 0 1 0 2.474l-8.61 8.61c-.21.21-.47.364-.756.445l-3.251.93a.75.75 0 0 1-.927-.928l.929-3.25c.081-.286.235-.547.445-.758l8.61-8.61Zm.176 4.823L9.75 4.81l-6.286 6.287a.253.253 0 0 0-.064.108l-.558 1.953 1.953-.558a.253.253 0 0 0 .108-.064Zm1.238-3.763a.25.25 0 0 0-.354 0L10.811 3.75l1.439 1.44 1.263-1.263a.25.25 0 0 0 0-.354Z"
)
ICON_CHECK = _SVG.format(
    d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"
)


def attachment_card(day: str, f: str, selectable: bool = True) -> str:
    """One attachment as one line: the file name (a link that opens it) on the left, and
    Download / Copy icons right-justified. Copy copies a text file's text, an image itself, or
    otherwise the file's link."""
    url = f"/inbox/files/{day}/{quote(f)}"
    ext = Path(f).suffix.lower()
    kind = (
        "image"
        if ext in IMAGE_EXT - {".heic", ".heif"}
        else "text"
        if ext in TEXT_EXT
        else "link"
    )
    name = html.escape(f)
    icons = (
        f'<a class="attbtn" href="{url}" target="_blank" rel="noopener" title="Open in new tab" aria-label="Open {name} in a new tab">{ICON_OPEN}</a>'
        f'<button type="button" class="attbtn copyatt" title="Copy" aria-label="Copy {name}">{ICON_COPY}</button>'
        f'<a class="attbtn" href="{url}?download=1" title="Download" aria-label="Download {name}">{ICON_DOWNLOAD}</a>'
    )  # delete a file by selecting it and using the selection bar
    circle = (
        f'<input type="checkbox" class="apick" name="dfile" value="{name}" form="delform" aria-label="Select {name}">'
        if selectable
        else ""
    )
    # Only the file name opens it (preview); clicking anywhere else on the line selects it.
    return (
        f'<div class="att" data-kind="{kind}" data-url="{url}">'
        + gutter("", circle)
        + f'<a class="attname" href="{url}" target="_blank" rel="noopener">{name}</a>'
        + f'<span class="atticons">{icons}</span></div>'
    )


PINS_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Pinned</title>
<meta name="robots" content="noindex"><link rel="icon" href="/favicon.svg?v=5" type="image/svg+xml">
{style}
<style>.pcard.flash{background:var(--hl)}.pcard .atts .apick{display:none}.pins .elist{padding-left:0}
.pcard .delfile[hidden]{display:none}.copyatt{display:none}
/* Same room as the day page's selection bar (12px gap + ~70px bar); on phones that bar floats. */
.pinsend{margin-top:82px}@media(max-width:899px){.pinsend{margin-top:12px}}</style></head><body class="pins"><main>
{logout}
<div class="pinsnav"><a href="/inbox/">Today</a></div>
<h1 class="title"><a href="/inbox/" title="Today">Drop a line.</a></h1>
<div class="nav">{prev}{today}<span></span></div>
<div class="cols">
<aside class="compose">{form}
{flash}
<div class="pinsend">{send}</div></aside>
<section class="list">
<h2><span class="dtitle">Pinned</span><span>{count}</span></h2>
<div class="elist">{cards}</div>
</section></div>
</main>
<script>
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) { try { await navigator.clipboard.writeText(text); return true; } catch {} }
  const ta = document.createElement("textarea"); ta.value = text; ta.style.cssText = "position:fixed;opacity:0";
  document.body.append(ta); ta.select(); let ok = false; try { ok = document.execCommand("copy"); } catch {} ta.remove(); return ok;
}
// Same actions as a day page; each card knows its own day (data-day), since pins span days.
const NOTE = {notes};  // "2026-11-23#5" / "2026-11-23#5.1" -> raw note text
const cardOf = (el) => el.closest(".pcard");
const key = (el, id) => cardOf(el).dataset.day + "#" + id;
const back = (el) => `/inbox/pins/${cardOf(el).dataset.day}/${cardOf(el).dataset.n}`;
document.querySelectorAll(".replyline").forEach((b) => b.onclick = () => {
  const f = cardOf(b).querySelector(".replyform");
  f.hidden = false; b.closest(".actions").hidden = true;
  const box = cardOf(b).querySelector(".replies"); if (box) setReplies(box, true);
  f.querySelector("textarea").focus();
});
document.querySelectorAll(".cancelreply").forEach((b) => b.onclick = () => {
  const f = b.closest(".replyform"); f.hidden = true; cardOf(b).querySelector(".actions").hidden = false;
});
document.querySelectorAll(".editbtn").forEach((b) => b.onclick = () => {
  const id = b.dataset.id, item = b.closest(".r") || cardOf(b);
  if (item.querySelector(".editform")) return;
  const note = item.querySelector(`.note[data-id="${CSS.escape(id)}"]`), raw = NOTE[key(b, id)] || "";
  const f = document.createElement("form");
  f.method = "post"; f.action = "/inbox/edit/" + cardOf(b).dataset.day; f.className = "editform";
  f.innerHTML = '<input type="hidden" name="id"><input type="hidden" name="back"><textarea name="text"></textarea>' +
    '<div class="row"><button>Save</button><button type="button" class="plain">Cancel</button></div>';
  f.elements.id.value = id; f.elements.back.value = back(b); f.elements.text.value = raw;
  f.querySelector(".plain").onclick = () => { f.remove(); note.hidden = !raw; };
  note.hidden = true; note.after(f); f.elements.text.focus();
});
document.querySelectorAll(".copyid").forEach((b) => b.onclick = async () => {
  const label = b.textContent; b.textContent = (await copyText(NOTE[key(b, b.dataset.id)] || "")) ? "Copied" : "Couldn't copy";
  setTimeout(() => (b.textContent = label), 1500);
});
document.querySelectorAll(".pdel").forEach((b) => b.onclick = () => {
  const f = cardOf(b).querySelector(".pdelform"); f.hidden = !f.hidden; if (!f.hidden) f.querySelector("input[name=username]").focus();
});
const emailOpen = document.getElementById("emailopen");
if (emailOpen) {
  const sf = document.getElementById("sendform");
  emailOpen.onclick = () => { sf.hidden = false; emailOpen.hidden = true; sf.querySelector("input").focus(); };
  document.getElementById("emailcancel").onclick = () => { sf.hidden = true; emailOpen.hidden = false; };
}
const target = document.querySelector(".pcard.flash"); if (target) target.scrollIntoView({ block: "center" });
</script>{replies_js}</body></html>"""


def render_pins(
    focus: tuple[str, int] | None = None,
    flash: str = "",
    session: dict | None = None,
    max_mb: int = MAX_UPLOAD_MB,
) -> bytes:
    """All pinned entries (newest day first), with the same actions as a day page (📌, Reply,
    Edit, Copy, Raw, replies with their own Edit/Copy/Raw) plus Delete… per entry. The add box
    here saves to today and pins the new entry. "Email pinned…" sends the whole list."""
    style = PAGE[PAGE.index("<style>") : PAGE.index("</style>") + len("</style>")]
    sep = '<span aria-hidden="true">·</span>'
    cards, notes = [], {}
    for day, e in pinned_entries():
        n, ident = e["n"], str(e["n"])
        pos = next(i for i, x in enumerate(read_day(day)) if x["n"] == n)
        back = f"/inbox/pins/{day}/{n}"
        notes[f"{day}#{ident}"] = e["text"]
        parts = [
            item_head(
                day,
                e,
                ident,
                f"{day}#{ident}",
                pin_toggle(day, e, ident, back="/inbox/pins"),
                href=f"/inbox/{day}#{ident}",
            ),
            item_note(day, e, ident),
        ]
        if e["files"]:
            parts.append(
                '<div class="atts">'
                + "".join(attachment_card(day, f, selectable=False) for f in e["files"])
                + "</div>"
            )
        # Delete: the whole entry, with all its files and replies (password, like the day page).
        hidden = f'<input type="hidden" name="del" value="{pos}"><input type="hidden" name="back" value="/inbox/pins">'
        hidden += "".join(
            f'<input type="hidden" name="dfile" value="{html.escape(f)}">'
            for f in e["files"]
        )
        hidden += "".join(
            f'<input type="hidden" name="dreply" value="{r["id"]}">'
            for r in e["replies"]
        )
        acts = text_actions(day, e, ident, reply=True)
        acts = (
            acts[: -len("</div>")]
            + f'{sep}<button type="button" class="editline pdel">Delete…</button></div>'
        )
        parts.append(
            acts
            + f'<form class="replyform" method="post" action="/inbox/reply/{day}/{ident}" '
            f'enctype="multipart/form-data" hidden><input type="hidden" name="back" value="{back}">'
            f'<textarea name="text" placeholder="Reply to {day}#{ident}… (use #N to reference)"></textarea>'
            f'<div class="row"><input type="file" name="file" multiple><button>Reply</button>'
            f'<button type="button" class="plain cancelreply">Cancel</button></div></form>'
            f'<form class="delfile pdelform" method="post" action="/inbox/delete/{day}" hidden>{hidden}'
            '<input name="username" placeholder="Username" autocomplete="username" autocapitalize="none" required>'
            '<input type="password" name="password" placeholder="Password" autocomplete="current-password" required>'
            "<button>Delete entry</button></form>"
        )
        reps = []
        for r in e["replies"]:
            notes[f"{day}#{r['id']}"] = r["text"]
            rb = [
                item_head(
                    day, r, r["id"], f"#{r['id']}", "", href=f"/inbox/{day}#{r['id']}"
                ),
                item_note(day, r, r["id"]),
            ]
            if r["files"]:
                rb.append(
                    '<div class="atts">'
                    + "".join(
                        attachment_card(day, f, selectable=False) for f in r["files"]
                    )
                    + "</div>"
                )
            rb.append(text_actions(day, r, r["id"], reply=False))
            reps.append('<div class="r">' + "".join(rb) + "</div>")
        parts.append(replies_block(reps))
        cls = "e pcard" + (" flash" if focus == (day, n) else "")
        cards.append(
            f'<div class="{cls}" id="p-{day}-{n}" data-day="{day}" data-n="{n}">'
            + "".join(parts)
            + "</div>"
        )
    form = (
        FORM.replace("{base}", "/inbox/")
        .replace("{max_mb}", str(max_mb))
        .replace(
            'enctype="multipart/form-data">',
            'enctype="multipart/form-data"><input type="hidden" name="pin" value="1">',
            1,
        )
    )
    send = (
        '<button type="button" id="emailopen">Email pinned…</button>'
        '<form class="sendform" id="sendform" method="post" action="/inbox/send-pins" hidden>'
        f'<label>To <input type="email" name="to" value="{html.escape(MAIL_TO)}" required></label>'
        '<button>Send</button><button type="button" class="plain" id="emailcancel">Cancel</button></form>'
        if cards
        else ""
    )
    page = (
        PINS_PAGE.replace("{style}", style)
        .replace("{replies_js}", REPLIES_JS)
        .replace(
            "{logout}",
            LOGOUT.replace("{tag}", session["tag"]).replace("{base}", "/inbox/")
            if session
            else "",
        )
        .replace(
            "{prev}",
            f'<a href="/inbox/{date.today() - timedelta(days=1)}">← {date.today() - timedelta(days=1)}</a>',
        )
        .replace(
            "{today}",
            f'<a class="today" href="/inbox/">Today · {date.today():%a %b %-d}</a>',
        )
        .replace("{form}", form)
        .replace("{send}", send)
        .replace("{notes}", js_json(notes))
        .replace("{count}", f"{len(cards)} pinned")
        .replace(
            "{flash}", f'<div class="ok">{html.escape(flash)}</div>' if flash else ""
        )
        .replace(
            "{cards}",
            '<hr class="esep">'.join(cards)
            or '<div class="e t">Nothing pinned yet. Add one here, or click 📌 on an entry.</div>',
        )
    )
    return page.encode()


def replies_block(reps: list[str]) -> str:
    """An entry's replies, minimized by default behind a "▸ N replies" line. Clicking that line
    or the bar on the replies' left opens/closes them (see REPLIES_JS)."""
    if not reps:
        return ""
    n = len(reps)
    label = f"{n} repl{'y' if n == 1 else 'ies'}"
    return (
        f'<button type="button" class="rtoggle" aria-expanded="false" data-label="{label}"><span class="rarrow">▸</span> {label}</button>'
        f'<div class="replies" hidden>{"".join(reps)}</div>'
    )


REPLIES_JS = """<script>
// Replies: "▸ N replies" opens them; clicking it again or the bar on their left closes them.
// Going to a reply's link (#5.1) opens its entry's replies first.
function setReplies(box, open) {
  const t = box.previousElementSibling;
  box.hidden = !open;
  t.setAttribute("aria-expanded", String(open));
  t.firstElementChild.textContent = open ? "▾" : "▸";
}
function openRepliesFor(el) { const box = el && el.closest(".replies"); if (box && box.hidden) setReplies(box, true); }
document.querySelectorAll(".rtoggle").forEach((t) => t.addEventListener("click", (e) => {
  e.stopPropagation(); setReplies(t.nextElementSibling, t.nextElementSibling.hidden);
}));
document.querySelectorAll(".replies").forEach((box) => {
  const onBar = (e) => e.target === box && e.offsetX < 32;
  box.addEventListener("mousemove", (e) => box.classList.toggle("barhover", onBar(e)));
  box.addEventListener("mouseleave", () => box.classList.remove("barhover"));
  box.addEventListener("click", (e) => { if (onBar(e)) { e.stopPropagation(); setReplies(box, false); box.classList.remove("barhover"); } });
});
{ const id = decodeURIComponent(location.hash.slice(1)); if (id.includes(".")) openRepliesFor(document.getElementById(id)); }
// 📌 on a day page toggles in place (no reload, so the page doesn't jump or select the entry).
// On the Pinned page it still reloads, so an unpinned card drops off the list.
if (!document.body.classList.contains("pins")) document.querySelectorAll(".pinbox form").forEach((f) => f.addEventListener("submit", async (e) => {
  e.preventDefault();
  const box = f.closest(".pinbox"), on = f.elements.on.value === "1";
  try { await fetch(f.action, { method: "POST", body: new URLSearchParams(new FormData(f)), redirect: "manual" }); }
  catch { f.submit(); return; }
  box.classList.toggle("on", on);
  f.elements.on.value = on ? "0" : "1";
  const btn = f.querySelector(".pinbtn"); btn.title = btn.ariaLabel = on ? "Unpin" : "Pin";
  let go = box.querySelector(".pingo");
  if (on && !go) { go = document.createElement("a"); go.className = "pingo"; go.href = "/inbox/pins/" + f.action.split("/").pop() + "/" + f.elements.n.value; go.textContent = "go to pinned"; box.append(go); }
  if (!on && go) go.remove();
  const link = document.querySelector('.pinsnav a[href="/inbox/pins"]');
  if (link) link.textContent = link.textContent.replace(/\\d+/, (k) => String(Number(k) + (on ? 1 : -1)));
}));
// Pinned page: the card you just came back to (after a reply or edit) shows its replies.
document.querySelectorAll(".pcard.flash .replies").forEach((b) => setReplies(b, true));
</script>"""


def pins_link() -> str:
    n = len(pinned_entries())
    return f'<div class="pinsnav"><a href="/inbox/pins">Pinned ({n})</a></div>'


def text_actions(day: str, item: dict, ident: str, reply: bool) -> str:
    """The row under an entry/reply: Reply (entries) · Edit · Copy · Raw ↗ (the note as plain
    text in a new tab). Copy and Raw only when there's a note."""
    sep = '<span aria-hidden="true">·</span>'
    parts = []
    if reply:
        parts.append(
            '<button type="button" class="replyline" aria-expanded="false">Reply</button>'
        )
    parts.append(
        f'<button type="button" class="editline editbtn" data-id="{ident}">Edit</button>'
    )
    if item["text"]:
        parts.append(
            f'<button type="button" class="editline copyid" data-id="{ident}">Copy</button>'
        )
        parts.append(
            f'<a class="editline" href="/inbox/{day}/{ident}.txt" target="_blank" rel="noopener" '
            f'title="The note as plain text, in a new tab">Raw <span class="rawarrow">↗</span></a>'
        )
    return '<div class="actions">' + sep.join(parts) + "</div>"


def gutter(icons: str, circle: str) -> str:
    """Select circle + icons for one line. On desktop they sit left of the entries' divider,
    beside their line: the circle in its own column at the far left, the icons right next to
    the divider. On phones the circle stays at the line's start and the icons show in the
    bottom row instead."""
    return f'<span class="gut"><span class="gcircle">{circle}</span><span class="gicons">{icons}</span></span>'


def pin_toggle(day: str, item: dict, ident: str, back: str = "") -> str:
    """[pin] at an entry's top right: click toggles the pin. When pinned, hovering shows a
    "go to pinned" link beside it."""
    on = bool(item.get("pinned"))
    go = (
        f'<a class="pingo" href="/inbox/pins/{day}/{ident}">go to pinned</a>'
        if on
        else ""
    )
    return (
        f'<span class="pinbox{" on" if on else ""}">'
        f'<form method="post" action="/inbox/pin/{day}" class="inline">'
        f'<input type="hidden" name="n" value="{ident}"><input type="hidden" name="on" value="{int(not on)}">'
        f'<input type="hidden" name="back" value="{back or f"/inbox/{day}#{ident}"}">'
        f'<button class="pinbtn" title="{"Unpin" if on else "Pin"}" aria-label="{"Unpin" if on else "Pin"}">📌</button></form>{go}</span>'
    )


def item_head(
    day: str,
    item: dict,
    ident: str,
    label: str,
    icons: str,
    lead: str = "",
    href: str = "",
) -> str:
    """Header line of an entry or reply: its id (a link to itself), "details" (time + metadata on
    hover), "edited" (edit time on hover), then icons."""
    tip = html.escape(item["time"]) + (
        f"<br>{html.escape(item['meta'])}" if item.get("meta") else ""
    )
    edited = (
        f'<span class="details edited" tabindex="0">edited<span class="tip" role="tooltip">'
        f"{html.escape(item['edited'])}</span></span>"
        if item.get("edited")
        else ""
    )
    return (
        f'<div class="ehead">{lead}<span class="t"><a class="num" href="{href or "#" + ident}">{html.escape(label)}</a>'
        f'<span class="details" tabindex="0">details<span class="tip" role="tooltip">{tip}</span></span>'
        f'{edited}</span><span class="hicons">{icons}</span></div>'
    )


def item_icons(
    day: str, item: dict, ident: str, reply: bool = False, delete: bool = False
) -> str:
    """Open-as-text, reply, edit, copy (and delete for replies) icons for an entry or reply."""
    out = ""
    if item["text"]:
        out += (
            f'<a class="attbtn" href="/inbox/{day}/{ident}.txt" target="_blank" rel="noopener" '
            f'title="Open as text in new tab" aria-label="Open {day}#{ident} as text">{ICON_OPEN}</a>'
        )
    if reply:
        out += f'<button type="button" class="attbtn replybtn" title="Reply" aria-label="Reply to {day}#{ident}">{ICON_REPLY}</button>'
    if item["text"]:
        out += f'<button type="button" class="attbtn copyid" data-id="{ident}" title="Copy text" aria-label="Copy the note of {day}#{ident}">{ICON_COPY}</button>'
    if delete:
        out += f'<button type="button" class="attbtn delreply" data-id="{ident}" title="Delete reply" aria-label="Delete {day}#{ident}">{ICON_TRASH}</button>'
    return out


def item_note(day: str, item: dict, ident: str) -> str:
    return (
        f'<p class="note" data-id="{ident}">{linkify(item["text"], day)}</p>'
        if item["text"]
        else f'<p class="note" data-id="{ident}" hidden></p>'
    )


def js_json(value) -> str:
    """JSON safe to drop into an inline <script>: no "</script>", and nothing shaped like one of
    this page's {placeholders} (so user text can never be substituted). JSON's own braces stay."""
    out = json.dumps(value).replace("</", "<\\/")
    return re.sub(r"\{([A-Za-z_]+)\}", r"\\u007b\1\\u007d", out)


def render(
    day: str, flash: str = "", session: dict | None = None, max_mb: int = MAX_UPLOAD_MB
) -> bytes:
    base = "/inbox/"
    entries = read_day(day)
    today = date.today().isoformat()
    items = []
    for i, e in reversed(
        list(enumerate(entries))
    ):  # newest first; i = position in inbox.md
        ident = str(e["n"])
        circle = (
            f'<input type="checkbox" class="pick" name="del" value="{i}" form="delform" '
            f'aria-label="Select entry {day}#{ident}">'
        )
        body = [
            # The day is already on the page, so the label is just "#5"; the full
            # "2026-11-23#5" stays in links, copies, exports, and the email.
            item_head(
                day,
                e,
                ident,
                f"#{ident}",
                pin_toggle(day, e, ident),
                lead=gutter("", circle),
            ),
            item_note(day, e, ident),
        ]
        if e["files"]:
            cards = "".join(attachment_card(day, f) for f in e["files"])
            body.append(f'<div class="atts">{cards}</div>')
        reps = []
        for r in e["replies"]:
            rb = [
                item_head(
                    day,
                    r,
                    r["id"],
                    f"#{r['id']}",
                    "",
                    lead=gutter(
                        "",
                        f'<input type="checkbox" class="rpick" name="dreply" value="{r["id"]}" '
                        f'form="delform" aria-label="Select reply #{r["id"]}">',
                    ),
                ),
                item_note(day, r, r["id"]),
            ]
            if r["files"]:
                cards = "".join(
                    attachment_card(day, f, selectable=False) for f in r["files"]
                )
                rb.append(f'<div class="atts">{cards}</div>')
            rb.append(text_actions(day, r, r["id"], reply=False))
            reps.append(f'<div class="r" id="{r["id"]}">' + "".join(rb) + "</div>")
        reply_form = (
            f'<form class="replyform" method="post" action="{base}reply/{day}/{ident}" '
            f'enctype="multipart/form-data" hidden>'
            f'<textarea name="text" placeholder="Reply to #{ident}… (use #N to reference)"></textarea>'
            f'<div class="row"><input type="file" name="file" multiple><button>Reply</button>'
            f'<button type="button" class="plain cancelreply">Cancel</button></div></form>'
        )
        # "Reply · Edit" right under the note and attachments; the reply box opens only on click.
        body.append(text_actions(day, e, ident, reply=True) + reply_form)
        body.append(replies_block(reps))
        # Icons twice: a left column (desktop) and in the bottom row (phones); CSS shows one.
        items.append(f'<div class="e" id="{ident}">' + "".join(body) + "</div>")
    d = date.fromisoformat(day)
    prev_day, next_day = (
        (d - timedelta(days=1)).isoformat(),
        (d + timedelta(days=1)).isoformat(),
    )
    sent = (day_dir(day) / ".digest-sent").exists()
    # "Email this day" opens a small box with the address (yours prefilled); Send sends.
    send = (
        f'<button type="button" id="emailopen">{"Email again…" if sent else "Email this day…"}</button>'
        f'<form class="sendform" id="sendform" method="post" action="{base}send/{day}" hidden>'
        f'<label>To <input type="email" name="to" value="{html.escape(MAIL_TO)}" required></label>'
        f'<button>Send</button><button type="button" class="plain" id="emailcancel">Cancel</button></form>'
        if entries
        else ""
    )
    # Fill the template's own placeholders first, then insert user content (which may contain
    # anything, including "{day}").
    page = (
        PAGE.replace("{replies_js}", REPLIES_JS)
        .replace("{logout}", LOGOUT.replace("{tag}", session["tag"]) if session else "")
        .replace("{base}", base)
        .replace("{day}", day)
        .replace(
            "{form}",
            FORM.replace("{base}", base).replace("{max_mb}", str(max_mb))
            if day == today
            else "",
        )
        .replace(
            "{flash}", f'<div class="ok">{html.escape(flash)}</div>' if flash else ""
        )
        .replace("{title}", "Today" if day == today else day)
        .replace("{count}", f"{len(entries)} saved" + (" · emailed" if sent else ""))
        .replace(
            "{entries}",
            '<div class="elist">'
            + ('<hr class="esep">'.join(items) or '<div class="e t">Nothing yet.</div>')
            + "</div>",
        )
        .replace("{send}", send)
        .replace("{prev}", f'<a href="{base}{prev_day}">← {prev_day}</a>')
        .replace(
            "{today}",
            f'<a class="today" href="{base}">Today · {date.today():%a %b %-d}</a>'
            if day != today
            else f'<a class="today" href="{base}" aria-current="page">Today · {date.today():%a %b %-d}</a>',
        )
        .replace(
            "{next}",
            f'<a href="{base}{next_day}">{next_day} →</a>'
            if day < today
            else "<span></span>",
        )
        .replace("{check_icon}", js_json(ICON_CHECK))
        .replace("{pins_link}", pins_link())
        .replace(
            "{allnotes_json}",
            js_json(
                {
                    **{str(e["n"]): e["text"] for e in entries},
                    **{r["id"]: r["text"] for e in entries for r in e["replies"]},
                }
            ),
        )
        .replace("{plain}", js_json(plain_text(day, entries)))
        .replace(
            "{entries_json}",
            js_json([entry_head(day, e, replies=False) for e in entries]),
        )
        .replace(
            "{replies_json}",
            js_json(
                {
                    r["id"]: "\n".join(
                        _item_lines(day, r, r["id"], "    reply ")
                        + ["    " + attach_line(day, f).strip() for f in r["files"]]
                    )
                    for e in entries
                    for r in e["replies"]
                }
            ),
        )
        .replace(
            "{files_json}",
            js_json([{f: attach_line(day, f) for f in e["files"]} for e in entries]),
        )
        .replace("{notes_json}", js_json([e["text"] for e in entries]))
    )
    return page.encode()


# ------------------------------------------------------------------- http


def mb_label(mb: int) -> str:
    return f"{mb // 1024} GB" if mb >= 1024 and mb % 1024 == 0 else f"{mb} MB"


def upload_mb(headers) -> int:
    """This visitor's upload limit in MB: bigger at home / on Tailscale (no Cloudflare)."""
    return HOME_UPLOAD_MB if is_home(headers) else MAX_UPLOAD_MB


def stream_form(rfile, length: int, ctype: str):
    """Read a multipart form straight off the socket: text fields into memory, file parts into
    temp files (in DIR/.uploading, same drive, so saving is just a rename). Returns
    (fields, files) with files = [(filename, Path)]. Raises ValueError on a broken form."""
    m = re.search(r'boundary="?([^";]+)"?', ctype)
    if not m:
        raise ValueError("no boundary")
    delim = b"\r\n--" + m[1].encode()
    tmpdir = DIR / ".uploading"
    tmpdir.mkdir(parents=True, exist_ok=True)
    fields: dict[str, list[str]] = {}
    files: list[tuple[str, Path]] = []
    buf, left = b"\r\n", length
    tmp: Path | None = None

    def more() -> bool:
        nonlocal buf, left
        if left <= 0:
            return False
        chunk = rfile.read(min(1 << 20, left))
        if not chunk:
            left = 0
            return False
        left -= len(chunk)
        buf += chunk
        return True

    try:
        while (i := buf.find(delim)) < 0:
            buf = buf[-len(delim) :]
            if not more():
                raise ValueError("no parts")
        buf = buf[i + len(delim) :]
        while True:
            while len(buf) < 2 and more():
                pass
            if buf[:2] == b"--":
                break
            while (j := buf.find(b"\r\n\r\n")) < 0:
                if len(buf) > 16384 or not more():
                    raise ValueError("bad part header")
            head = buf[2:j].decode("utf-8", "replace")
            buf = buf[j + 4 :]
            nm = re.search(r'\bname="([^"]*)"', head)
            fn = re.search(r'filename="([^"]*)"', head)
            tmp = None
            if fn and fn[1]:
                fd, tmp_name = tempfile.mkstemp(dir=tmpdir)
                tmp = Path(tmp_name)
                out = os.fdopen(fd, "wb")
            else:
                out = io.BytesIO()
            with out:
                while (k := buf.find(delim)) < 0:
                    if len(buf) > len(delim):
                        out.write(buf[: -len(delim)])
                        buf = buf[-len(delim) :]
                    if not more():
                        raise ValueError("form cut off")
                out.write(buf[:k])
                if tmp is None:
                    fields.setdefault(nm[1] if nm else "", []).append(
                        out.getvalue().decode("utf-8", "replace")
                    )
            buf = buf[k + len(delim) :]
            if tmp is not None:
                if tmp.stat().st_size:
                    tmp.chmod(
                        0o664
                    )  # mkstemp makes it owner-only; match the other files
                    # Browsers send a quote in a file name as %22.
                    files.append((fn[1].replace("%22", '"'), tmp))
                else:
                    tmp.unlink()
    except BaseException:
        for _, t in files:
            t.unlink(missing_ok=True)
        if tmp is not None:
            tmp.unlink(missing_ok=True)
        raise
    return fields, files


def form_fields(ctype: str, body: bytes) -> dict[str, list[str]]:
    """Text fields from a urlencoded or multipart form."""
    if ctype.startswith("multipart/form-data"):
        msg = BytesParser(policy=email_policy).parsebytes(
            f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        )
        out: dict[str, list[str]] = {}
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if name and not part.get_filename():
                raw = part.get_payload(decode=True) or b""
                out.setdefault(name, []).append(raw.decode("utf-8", "replace"))
        return out
    return parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)


class Handler(BaseHTTPRequestHandler):
    def _send(
        self, code: int, body: bytes, ctype: str, extra: dict | None = None
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, to: str) -> None:
        self._send(303, b"", "text/plain", {"Location": to})

    def _gate(self, path: str) -> tuple[bool, dict | None]:
        """(allowed, session). Home network: allowed, no session. Elsewhere: needs a login."""
        if path == "/inbox/health" or is_home(self.headers):
            return True, None
        sess = session_for(self.headers)
        return sess is not None, sess

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(self.path.split("?", 1)[0])
        allowed, session = self._gate(path)
        if not allowed:
            self._send(
                200 if path in ("/inbox", "/inbox/") else 401,
                login_page(),
                "text/html; charset=utf-8",
            )
            return
        flash = "Saved." if self.path.endswith("?saved") else ""
        if m := re.search(r"\?sent=(.*)$", self.path):
            flash = unquote(m[1])
        if m := re.search(r"[?&]deleted=(\d+)", self.path):
            flash = f"Deleted {m[1]}."
        if path in ("/inbox/day", "/inbox/day/"):
            self._redirect("/inbox/")  # no day given: today
            return
        if path in ("/inbox", "/inbox/"):
            page = render(
                date.today().isoformat(), flash, session, upload_mb(self.headers)
            )
            self._send(200, page, "text/html; charset=utf-8")
        elif m := re.fullmatch(
            r"/inbox/(\d{4}-\d{2}-\d{2})/(\d+(?:\.\d+)?)\.txt", path
        ):
            item = find_item(
                read_day(m[1]), m[2]
            )  # a note as plain text (open-in-new-tab icon)
            if item is None:
                self._send(404, b"not found", "text/plain")
            else:
                self._send(200, item["text"].encode(), "text/plain; charset=utf-8")
        elif path in ("/inbox/pins", "/inbox/pins/"):
            self._send(
                200,
                render_pins(None, flash, session, upload_mb(self.headers)),
                "text/html; charset=utf-8",
            )
        elif m := re.fullmatch(r"/inbox/pins/(\d{4}-\d{2}-\d{2})/(\d+)", path):
            self._send(
                200,
                render_pins((m[1], int(m[2])), flash, session, upload_mb(self.headers)),
                "text/html; charset=utf-8",
            )
        elif m := re.fullmatch(r"/inbox/(?:day/)?(\d{4}-\d{2}-\d{2})", path):
            self._send(
                200,
                render(m[1], flash, session, upload_mb(self.headers)),
                "text/html; charset=utf-8",
            )
        elif m := re.fullmatch(r"/inbox/day/(\d{4}-\d{2}-\d{2})\.md", path):
            md = day_dir(m[1]) / "inbox.md"
            body = (
                md.read_bytes()
                if md.exists()
                else f"# Inbox {m[1]}\n\n(nothing saved)\n".encode()
            )
            self._send(200, body, "text/plain; charset=utf-8")
        elif m := re.fullmatch(r"/inbox/files/(\d{4}-\d{2}-\d{2})/([^/]+)", path):
            f = day_dir(m[1]) / safe_name(m[2])
            if f.is_file() and f.parent == day_dir(m[1]):
                ctype = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                    ".mp4": "video/mp4",
                    ".mov": "video/quicktime",
                    ".pdf": "application/pdf",
                    ".m4a": "audio/mp4",
                }.get(f.suffix.lower(), "application/octet-stream")
                extra = {}
                if "download=1" in self.path:
                    extra["Content-Disposition"] = f'attachment; filename="{f.name}"'
                elif (
                    ctype == "application/octet-stream" or f.suffix.lower() in TEXT_EXT
                ):
                    # Text-like files are shown on the page; served as plain text so the
                    # browser never runs an uploaded .html/.js.
                    ctype = "text/plain; charset=utf-8"
                self._send(200, f.read_bytes(), ctype, extra)
            else:
                self._send(404, b"not found", "text/plain")
        elif m := re.fullmatch(r"/inbox/export/(\d{4}-\d{2}-\d{2})", path):
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            q = parse_qs(query, keep_blank_values=True)
            picks = {int(v) for v in q.get("i", []) if v.isdigit()}
            files = {f for f in q["f"] if f} if "f" in q else None
            reps = {r for r in q["r"] if r} if "r" in q else None
            name = f"inbox-{m[1]}-selected.zip"
            self._send(
                200,
                export_zip(m[1], picks, files, reps),
                "application/zip",
                {"Content-Disposition": f'attachment; filename="{name}"'},
            )
        elif path == "/inbox/health":
            ok = DIR.parent.exists()
            self._send(
                200 if ok else 503,
                json.dumps({"ok": ok, "dir": str(DIR)}).encode(),
                "application/json",
            )
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        ctype = self.headers.get("Content-Type", "")
        upload = path == "/inbox/add" or re.fullmatch(
            r"/inbox/reply/\d{4}-\d{2}-\d{2}/\d+", path
        )
        limit = upload_mb(self.headers) if upload else MAX_UPLOAD_MB
        if length > limit * 1024 * 1024:
            self._send(413, f"too big ({mb_label(limit)} max)".encode(), "text/plain")
            return
        fields: dict[str, list[str]] = {}
        files: list[tuple[str, Path]] = []
        if upload and ctype.startswith("multipart/form-data"):
            # Check the login before taking in a big upload, then stream it to disk.
            if not self._gate(path)[0]:
                self.close_connection = True
                self._send(
                    401, login_page("Please log in again."), "text/html; charset=utf-8"
                )
                return
            try:
                fields, files = stream_form(self.rfile, length, ctype)
            except ValueError:
                self._send(400, b"upload was cut off or malformed", "text/plain")
                return
            body = b""
        else:
            body = self.rfile.read(length)
        try:
            self._post(path, ctype, body, fields, files)
        finally:  # anything not saved (an error, an empty note) doesn't linger
            for _, t in files:
                t.unlink(missing_ok=True)

    def _post(self, path, ctype, body, fields, files) -> None:
        if path == "/inbox/login":
            ip = visitor_ip(self.headers) or "?"
            if too_many_fails(ip):
                self._send(
                    429,
                    login_page("Too many tries. Wait a few minutes."),
                    "text/html; charset=utf-8",
                )
                return
            f = form_fields(ctype, body)
            if PASSWORD_HASH and check_login(
                (f.get("username") or [""])[0], (f.get("password") or [""])[0]
            ):
                token, tag = secrets.token_urlsafe(32), secrets.token_hex(6)
                with _auth_lock:
                    _sessions[token] = {"seen": time.time(), "tag": tag}
                secure = (
                    "; Secure"
                    if self.headers.get("X-Forwarded-Proto") == "https"
                    else ""
                )
                cookie = (
                    f"inbox_s={token}; Path=/inbox/; HttpOnly; SameSite=Strict{secure}"
                )
                # No Max-Age: the cookie dies with the browser; the per-tab check handles new tabs.
                self._send(
                    303,
                    b"",
                    "text/plain",
                    {"Location": f"/inbox/?login={tag}", "Set-Cookie": cookie},
                )
            else:
                with _auth_lock:
                    _fails.setdefault(ip, []).append(time.time())
                msg = (
                    "Wrong username or password."
                    if PASSWORD_HASH
                    else "No password is set up on the server yet."
                )
                self._send(401, login_page(msg), "text/html; charset=utf-8")
            return
        if path == "/inbox/logout":
            sess = session_for(self.headers)
            if sess:
                with _auth_lock:
                    _sessions.pop(sess["token"], None)
            self._send(
                200,
                b"logged out",
                "text/plain",
                {"Set-Cookie": "inbox_s=; Path=/inbox/; Max-Age=0"},
            )
            return
        allowed, _ = self._gate(path)
        if not allowed:
            self._send(
                401, login_page("Please log in again."), "text/html; charset=utf-8"
            )
            return
        if m := re.fullmatch(r"/inbox/delete/(\d{4}-\d{2}-\d{2})", path):
            # Always confirmed with username + password, even at home.
            f = form_fields(ctype, body)
            ip = visitor_ip(self.headers) or "?"
            back = (f.get("back") or [""])[0]
            home = back if back.startswith("/inbox/pins") else f"/inbox/{m[1]}"
            user, pw = (f.get("username") or [""])[0], (f.get("password") or [""])[0]
            if too_many_fails(ip) or not (PASSWORD_HASH and check_login(user, pw)):
                with _auth_lock:
                    _fails.setdefault(ip, []).append(time.time())
                self._redirect(
                    f"{home}?sent={quote('Not deleted: wrong username or password.')}"
                )
                return
            if f.get("reply"):  # one reply (trash icon on its line)
                ok = delete_reply(m[1], f["reply"][0])
                msg = "Deleted the reply." if ok else "That reply wasn't found."
                self._redirect(f"{home}?sent={quote(msg)}")
                return
            if f.get("file"):  # one attachment (trash icon on its line)
                ok = delete_file(m[1], f["file"][0])
                msg = "Deleted the file." if ok else "That file wasn't found."
                self._redirect(f"{home}?sent={quote(msg)}")
                return
            picks = {int(v) for v in f.get("del", []) if v.isdigit()}
            rsel = set(f.get("dreply", []))
            # An entry can't be deleted without all of its replies (the page blocks this too).
            day_entries = read_day(m[1])
            partial = [
                f"#{e['n']}"
                for i, e in enumerate(day_entries)
                if i in picks and any(r["id"] not in rsel for r in e["replies"])
            ]
            if partial:
                msg = f"Not deleted: deleting {', '.join(partial)} also deletes all {'their' if len(partial) > 1 else 'its'} replies, so tick them all first."
                self._redirect(f"{home}?sent={quote(msg)}")
                return
            whole, nfiles, nreplies = delete_selection(
                m[1], picks, set(f.get("dfile", [])), rsel
            )
            plural = lambda n, one, many: f"{n} {one if n == 1 else many}"  # noqa: E731
            parts = [plural(whole, "entry", "entries")] if whole else []
            parts += [plural(nreplies, "reply", "replies")] if nreplies else []
            parts += [plural(nfiles, "file", "files")] if nfiles else []
            msg = "Deleted " + (", ".join(parts) if parts else "nothing") + "."
            self._redirect(f"{home}?sent={quote(msg)}")
            return
        if path == "/inbox/add":
            text = (fields.get("text") or [""])[0]
            if not text.strip() and not files:
                self._redirect("/inbox/")
                return
            day = add_entry(text, files, describe_source(self.headers))
            if (fields.get("pin") or [""])[0] == "1":
                n = read_day(day)[-1]["n"]
                set_pinned(day, n, True)
                self._redirect(f"/inbox/pins/{day}/{n}")
                return
            self._redirect("/inbox/?saved")
        elif m := re.fullmatch(r"/inbox/reply/(\d{4}-\d{2}-\d{2})/(\d+)", path):
            text = (fields.get("text") or [""])[0]
            if not text.strip() and not files:
                self._redirect(f"/inbox/{m[1]}#{m[2]}")
                return
            rid = add_reply(m[1], int(m[2]), text, files, describe_source(self.headers))
            back = (fields.get("back") or [""])[0]
            self._redirect(
                (back if back.startswith("/inbox/pins") else f"/inbox/{m[1]}#{rid}")
                if rid
                else f"/inbox/{m[1]}?sent={quote('That entry no longer exists.')}"
            )
        elif m := re.fullmatch(r"/inbox/pin/(\d{4}-\d{2}-\d{2})", path):
            f = form_fields(ctype, body)
            n = (f.get("n") or [""])[0]
            back = (f.get("back") or [""])[0]
            if not back.startswith("/inbox/"):  # only ever go back inside the inbox
                back = f"/inbox/{m[1]}"
            if n.isdigit():
                set_pinned(m[1], int(n), (f.get("on") or ["1"])[0] == "1")
            self._redirect(back)
        elif m := re.fullmatch(r"/inbox/edit/(\d{4}-\d{2}-\d{2})", path):
            f = form_fields(ctype, body)
            ident = (f.get("id") or [""])[0]
            ok = re.fullmatch(r"\d+(\.\d+)?", ident) and edit_item(
                m[1], ident, (f.get("text") or [""])[0]
            )
            back = (f.get("back") or [""])[0]
            self._redirect(
                (back if back.startswith("/inbox/pins") else f"/inbox/{m[1]}#{ident}")
                if ok
                else f"/inbox/{m[1]}?sent={quote('Not found.')}"
            )
        elif path == "/inbox/send-pins":
            to = (form_fields(ctype, body).get("to") or [""])[0].strip()
            if to and not EMAIL_RE.fullmatch(to):
                result = "Not sent: that email address looks wrong."
            else:
                try:
                    result = send_pins(to)
                except Exception as e:
                    result = f"email failed: {e.__class__.__name__}: {e}"
            self._redirect(f"/inbox/pins?sent={quote(result)}")
        elif m := re.fullmatch(r"/inbox/send/(\d{4}-\d{2}-\d{2})", path):
            to = (form_fields(ctype, body).get("to") or [""])[0].strip()
            if to and not EMAIL_RE.fullmatch(to):
                self._redirect(
                    f"/inbox/{m[1]}?sent={quote('Not sent: that email address looks wrong.')}"
                )
                return
            try:
                result = send_digest(m[1], to)
            except Exception as e:
                result = f"email failed: {e.__class__.__name__}: {e}"
            self._redirect(f"/inbox/{m[1]}?sent={quote(result)}")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    if sys.argv[1:] == ["hash-password"]:
        pw = getpass.getpass("New inbox password: ")
        if pw != getpass.getpass("Again: ") or not pw:
            sys.exit("Passwords didn't match.")
        print("Put this line in /etc/cesium/inbox.env:\n")
        print(f"INBOX_PASSWORD_HASH={hash_password(pw)}")
        return
    threading.Thread(target=digest_worker, daemon=True).start()
    print(
        f"inbox on http://{HOST}:{PORT}/inbox/ -> {DIR} (digest at {DIGEST_HOUR}:00)",
        flush=True,
    )
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
