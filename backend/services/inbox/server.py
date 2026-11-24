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
# Per entry. Cloudflare's free plan rejects requests over 100 MB before they reach us (a
# "413 Payload Too Large" page), so stay under it with room for the form's own overhead. The
# page checks this before uploading; the server enforces it too.
MAX_UPLOAD_MB = 95
MAX_UPLOAD = MAX_UPLOAD_MB * 1024 * 1024
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


def add_entry(text: str, files: list[tuple[str, bytes]], source: str = "") -> str:
    """Append one entry to today's inbox.md and save its files. Returns the day.

    source: where it was sent from, e.g. "Tailscale 100.120.196.52" (see describe_source)."""
    now = datetime.now().astimezone()  # local time with its zone (PST/PDT)
    day, stamp = now.strftime("%Y-%m-%d"), now.strftime("%H%M%S")
    with _write_lock:
        folder = day_dir(day)
        folder.mkdir(parents=True, exist_ok=True)
        saved = []
        for i, (name, data) in enumerate(files):
            fname = f"{stamp}-{safe_name(name)}"
            n = 1
            while (folder / fname).exists():  # same name in the same second: keep both
                fname = f"{stamp}-{n}-{safe_name(name)}"
                n += 1
            (folder / fname).write_bytes(data)
            saved.append(fname)
        md = folder / "inbox.md"
        utc = now.astimezone(timezone.utc)
        # Header: local time + zone. Then one italic line: UTC, Unix time, where it came from.
        meta = f"UTC {utc:%Y-%m-%dT%H:%M:%SZ} · unix {int(now.timestamp())}"
        if source:
            meta += f" · from {source}"
        # Fixed per-day number: one past the highest ever used today (gaps stay after deletes).
        n = max((e["n"] for e in read_day(day)), default=0) + 1
        gone = folder / ".deleted" / "deleted.md"
        if gone.exists():
            used = re.findall(r"^## (\d+) ·", gone.read_text(encoding="utf-8"), re.M)
            n = max([n] + [int(u) + 1 for u in used])
        block = [f"## {n} · {now:%H:%M:%S %Z}", f"_{meta}_", ""]
        # Text is quoted so nothing a user types can look like an entry header.
        block += [f"> {line}" if line else ">" for line in text.strip().splitlines()]
        if text.strip() and saved:
            block.append("")
        block += [f"- [{f}]({quote(f)})" for f in saved]
        with md.open("a", encoding="utf-8") as fh:
            if fh.tell() == 0:
                fh.write(f"# Inbox {day}\n\n")
            fh.write("\n".join(block) + "\n\n")
    return day


def write_day(day: str, entries: list[dict]) -> None:
    """Rewrite a day's inbox.md from entries (used after deleting some)."""
    out = [f"# Inbox {day}", ""]
    for e in entries:
        out += (
            [f"## {e['n']} · {e['time']}"]
            + ([f"_{e['meta']}_"] if e.get("meta") else [])
            + [""]
        )
        out += [f"> {line}" if line else ">" for line in e["text"].splitlines()]
        if e["text"] and e["files"]:
            out.append("")
        out += [f"- [{f}]({quote(f)})" for f in e["files"]]
        out.append("")
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
        hit = next((e for e in entries if name in e["files"]), None)
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
        write_day(day, [e for e in entries if e["text"] or e["files"]])
        return True


def delete_selection(day: str, indexes: set[int], files: set[str]) -> tuple[int, int]:
    """Delete what's selected. Everything moves to <day>/.deleted/.

    - Selected entry, all its files ticked (or none): deleted whole.
    - Selected entry with some files unticked: its note is deleted along with the ticked files;
      the unticked files stay, as an entry without text.
    - Files ticked on their own (entry not selected): just those files; the note stays.
    An entry left with no note and no files disappears from the list.
    Returns (entries deleted, files deleted)."""
    files = {safe_name(f) for f in files}
    with _write_lock:
        entries = read_day(day)
        trash = day_dir(day) / ".deleted"
        trash.mkdir(exist_ok=True)
        whole, nfiles, keep = 0, 0, []
        with (trash / "deleted.md").open("a", encoding="utf-8") as fh:
            for i, e in enumerate(entries):
                gone = [f for f in e["files"] if f in files]
                if i in indexes and set(e["files"]) <= files:
                    whole += 1
                    gone = e["files"]
                    fh.write(
                        f"## {e['n']} · {e['time']} (deleted {datetime.now():%H:%M:%S})\n\n"
                    )
                    fh.write("".join(f"> {ln}\n" for ln in e["text"].splitlines()))
                    fh.write("".join(f"- {f}\n" for f in gone) + "\n")
                elif (
                    i in indexes
                ):  # selected, but some files kept: drop the note + ticked files
                    whole += 1
                    fh.write(
                        f"## {e['n']} · {e['time']}: note"
                        + (f" and files {', '.join(gone)}" if gone else "")
                        + f" (deleted {datetime.now():%H:%M:%S}; other files kept)\n\n"
                    )
                    fh.write(
                        "".join(f"> {ln}\n" for ln in e["text"].splitlines()) + "\n"
                    )
                    keep.append(
                        {
                            **e,
                            "text": "",
                            "files": [f for f in e["files"] if f not in files],
                        }
                    )
                elif gone:
                    fh.write(
                        f"## {e['n']} · {e['time']}: files {', '.join(gone)} (deleted {datetime.now():%H:%M:%S})\n\n"
                    )
                    e = {**e, "files": [f for f in e["files"] if f not in files]}
                    keep.append(e)
                else:
                    keep.append(e)
                for f in gone:
                    src = day_dir(day) / safe_name(f)
                    if src.is_file():
                        src.rename(trash / src.name)
                        nfiles += 1
        write_day(day, [e for e in keep if e["text"] or e["files"]])
        return whole, nfiles


def read_day(day: str) -> list[dict]:
    """Parse a day's inbox.md back into entries: [{time, text, files}]."""
    md = day_dir(day) / "inbox.md"
    if not md.exists():
        return []
    entries: list[dict] = []
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            head = line[3:].strip()
            num = re.match(r"(\d+) · (.*)$", head)
            entries.append(
                {
                    "n": int(num[1]) if num else None,
                    "time": num[2] if num else head,
                    "meta": "",
                    "text": [],
                    "files": [],
                }
            )
        elif (
            entries
            and line.startswith("_")
            and line.endswith("_")
            and not entries[-1]["text"]
        ):
            entries[-1]["meta"] = line[1:-1]
        elif entries and (line.startswith("> ") or line == ">"):
            entries[-1]["text"].append(line[2:])
        elif entries and (m := re.match(r"- \[(.+?)\]\((.+?)\)$", line)):
            entries[-1]["files"].append(unquote(m[2]))
    for e in entries:
        e["text"] = "\n".join(e["text"])
    # Entries saved before numbering existed: number them in order, skipping used numbers.
    used = {e["n"] for e in entries if e["n"]}
    nxt = 1
    for e in entries:
        if not e["n"]:
            while nxt in used:
                nxt += 1
            e["n"] = nxt
            used.add(nxt)
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


def linkify(text: str) -> str:
    out, last = [], 0
    for m in URL_RE.finditer(text):
        out.append(html.escape(text[last : m.start()]))
        url = m.group(0)
        out.append(f'<a href="{html.escape(url)}">{html.escape(url)}</a>')
        last = m.end()
    out.append(html.escape(text[last:]))
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


def entry_head(day: str, e: dict) -> str:
    """An entry's number, time, note, and metadata (no attachments)."""
    lines = [f"[{day}.{e['n']} · {e['time']}] {e['text'] or '(no note)'}"]
    if e.get("meta"):
        lines.append(f"  ({e['meta']})")
    return "\n".join(lines)


def attach_line(day: str, f: str) -> str:
    return f"  attachment: {f} ({PUBLIC_URL}files/{day}/{quote(f)})"


def entry_text(day: str, e: dict) -> str:
    """One entry as plain text (for Claude/ChatGPT)."""
    lines = [f"[{day}.{e['n']} · {e['time']}] {e['text'] or '(no note)'}"]
    if e.get("meta"):
        lines.append(f"  ({e['meta']})")
    for f in e["files"]:
        lines.append(f"  attachment: {f} ({PUBLIC_URL}files/{day}/{quote(f)})")
    return "\n".join(lines)


def plain_text(day: str, entries: list[dict]) -> str:
    """The block meant for pasting into Claude/ChatGPT."""
    head = f"My inbox for {day} ({len(entries)} entries). Each is something I saved to deal with later."
    return "\n\n".join([head] + [entry_text(day, e) for e in entries])


def export_zip(day: str, indexes: set[int], files: set[str] | None = None) -> bytes:
    """Exactly what's selected, as a zip: selected.md (same format as inbox.md) plus files.

    indexes: selected entries (their notes). files: ticked attachments; for a selected entry
    only its ticked files are included, and files ticked on their own come with their entry's
    number/time but not its note. files=None means "all files of the selected entries"."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        md = [f"# Inbox {day} (selected)", ""]
        for i, e in enumerate(read_day(day)):
            keep = [
                f
                for f in e["files"]
                if (files is None and i in indexes) or (files and f in files)
            ]
            if i not in indexes and not keep:
                continue
            md += [
                f"## {e['n']} · {e['time']}" + ("" if i in indexes else " (files only)")
            ]
            md += ([f"_{e['meta']}_"] if e.get("meta") else []) + [""]
            if i in indexes:
                md += [f"> {ln}" if ln else ">" for ln in e["text"].splitlines()]
            md += [f"- [{f}]({quote(f)})" for f in keep] + [""]
            for f in keep:
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
    msg.set_content(text)

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
        f'<div style="color:#6b7280">{len(entries)} saved · <a href="{PUBLIC_URL}day/{day}">open on the server</a></div>'
        + "".join(rows)
        + '<h3 style="margin-top:20px">Paste into Claude / ChatGPT</h3>'
        f'<pre style="white-space:pre-wrap;background:#f4f4f2;padding:12px;border-radius:8px;font-size:12px">{html.escape(text)}</pre>'
        "</div>"
    )
    msg.add_alternative(body, subtype="html")
    html_part = msg.get_payload()[-1]
    for cid, data in thumbs:
        html_part.add_related(data, maintype="image", subtype="jpeg", cid=f"<{cid}>")
    return msg


def send_digest(day: str) -> str:
    """Send (or, without credentials, save) the day's digest. Returns what happened."""
    msg = build_digest(day)
    if msg is None:
        return "nothing saved that day"
    if not (SMTP_USER and SMTP_PASS):
        out = day_dir(day) / "digest-preview.eml"
        out.write_bytes(bytes(msg))
        return f"no Gmail app password set; saved {out} instead"
    with smtplib.SMTP_SSL(
        SMTP_HOST, 465, context=ssl.create_default_context(), timeout=30
    ) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    (day_dir(day) / ".digest-sent").write_text(datetime.now().isoformat())
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
.msg{color:#dc2626;font-size:14px;min-height:1em}
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
  main{max-width:1100px}
  /* about 65/35: entries get most of the width; the divider line sits at the split */
  .cols{display:grid;grid-template-columns:minmax(0,1.85fr) minmax(0,1fr);gap:0;align-items:start}
  .list{padding-right:28px}
  .compose{padding-left:28px;border-left:1px solid var(--line);min-height:calc(100vh - 140px)}
  .compose{grid-column:2;grid-row:1;position:sticky;top:20px}
  .list{grid-column:1;grid-row:1}
  .list h2{margin-top:0}
  .compose:empty{display:none}
}
form{display:grid;gap:10px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
textarea{width:100%;min-height:96px;font:inherit;color:inherit;background:transparent;border:0;outline:0;resize:vertical}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
label.file{flex:1;color:var(--muted);font-size:14px;cursor:pointer}
input[type=file]{font-size:14px;max-width:100%}
button{font:inherit;font-weight:600;color:#fff;background:var(--accent);border:0;border-radius:8px;padding:9px 18px;cursor:pointer}
.ok{color:#16a34a;font-size:14px;margin:8px 2px}
.sizerow{display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin:0 2px}
.clear{font-size:12px;font-weight:500;color:var(--ink);background:transparent;border:1px solid var(--line);padding:4px 10px}
.picked{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.picked li{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px;padding:5px 8px;border:1px solid var(--line);border-radius:8px;overflow-wrap:anywhere}
.picked .x{flex:none;width:26px;height:26px;padding:0;font-size:17px;line-height:1;color:var(--muted);background:transparent;border:1px solid var(--line);border-radius:6px}
.size{font-size:13px;color:var(--muted);margin:0 2px}.size.bad{color:#dc2626;font-weight:600}
button:disabled{opacity:.4;cursor:not-allowed}
.num{color:var(--bright);font-weight:600}
.details{position:relative;margin-left:10px;text-decoration:underline;text-underline-offset:2px;cursor:default;outline:0}
/* The card fades in, stays open while the mouse moves onto it (so its text can be selected and
   copied), and waits 0.05 s before fading out so tiny slips don't close it. */
.details .tip{position:absolute;left:calc(100% + 8px);top:-7px;z-index:20;width:max-content;max-width:min(360px,80vw);
  padding:8px 10px;border-radius:8px;background:var(--bright);color:var(--bg);font-size:12px;line-height:1.5;
  text-decoration:none;box-shadow:0 6px 18px rgba(0,0,0,.25);overflow-wrap:anywhere;cursor:text;user-select:text;
  opacity:0;visibility:hidden;transform:translateX(-3px);
  transition:opacity .15s ease .05s,transform .15s ease .05s,visibility 0s linear .2s}
/* Invisible bridge over the 8px gap between "details" and the card (which opens to its right),
   so moving across never leaves the hover area. */
.details .tip::before{content:"";position:absolute;top:0;bottom:0;left:-8px;width:8px}
.details:hover .tip,.details:focus .tip,.details:focus-within .tip{opacity:1;visibility:visible;transform:none;
  transition:opacity .15s ease,transform .15s ease,visibility 0s}
.ehead .copynote{margin-left:auto}
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
.selall{font:inherit;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--bright);background:transparent;border:1px solid var(--line);border-radius:6px;padding:2px 8px;margin-left:8px;cursor:pointer}.meta{font-size:11px}
.del{position:sticky;bottom:12px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:12px;
  background:var(--card);border:1px solid #dc2626;border-radius:12px;padding:10px;box-shadow:0 6px 20px rgba(0,0,0,.15)}
.del[hidden]{display:none}.del input{flex:1;min-width:110px;font:inherit;padding:7px;border:1px solid var(--line);border-radius:8px;background:transparent;color:inherit}
.del button{background:#dc2626}.del form{display:flex;flex-wrap:wrap;gap:8px;flex-basis:100%}
.del form[hidden]{display:none}.del .plain{background:transparent;color:var(--muted);border:1px solid var(--line)}
.top{display:flex;justify-content:flex-end;margin:-8px 0 8px}
.top button{font-size:13px;font-weight:500;color:var(--muted);background:transparent;border:1px solid var(--line);padding:5px 10px}
h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:28px 2px 8px;display:flex;justify-content:space-between;align-items:baseline}
h2 a,.nav a{color:var(--muted);font-weight:400;text-transform:none;letter-spacing:0}
.e{padding:12px 2px;border-bottom:1px solid var(--line)}.t{color:var(--muted);font-size:12px}
.e p{margin:4px 0;white-space:pre-wrap;overflow-wrap:anywhere}.e a{color:var(--accent)}
.atts{border:1px solid var(--line);border-radius:10px;margin-top:8px;padding:0;overflow:hidden}
.att{cursor:default;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 10px;font-size:13px}
.att+.att{border-top:1px solid var(--line)}
.delfile{display:flex;flex-wrap:wrap;gap:6px;padding:6px 0 8px}
.delfile input{flex:1;min-width:100px;font:inherit;font-size:13px;padding:6px;border:1px solid var(--line);border-radius:6px;background:transparent;color:inherit}
.delfile button{font-size:13px;padding:6px 12px;background:#dc2626}.delfile .plain{background:transparent;color:var(--muted);border:1px solid var(--line)}
.delatt:hover{color:#dc2626;border-color:#dc2626}
.atticons{align-items:center}
.apick{appearance:none;-webkit-appearance:none;flex:none;width:14px;height:14px;margin:0 0 0 2px;border:2px solid var(--muted);border-radius:50%;cursor:pointer;display:grid;place-items:center}
.apick:checked{background:var(--accent);border-color:var(--accent)}
.apick:checked::after{content:"";width:3px;height:6px;border:solid #fff;border-width:0 1.5px 1.5px 0;transform:translateY(-1px) rotate(45deg)}
/* Files box keeps the page background even inside a selected (tinted) entry, so only the
   ticked files look highlighted. */
.atts{background:var(--bg)}
:root{--hl:color-mix(in srgb,var(--accent) 14%,var(--bg))}  /* one solid highlight shade, never layered */
/* rows fill the box edge to edge, so a highlight reaches all sides (corners clipped by .atts) */
.att.asel{background:var(--hl)}
.attname{min-width:0;overflow-wrap:anywhere}.atticons{display:flex;gap:6px;flex:none}
.attbtn{display:inline-grid;place-items:center;flex:none;width:24px;height:24px;padding:0;color:var(--muted);background:transparent;border:1px solid var(--line);border-radius:6px;text-decoration:none;cursor:pointer}
.attbtn:hover{color:var(--bright);border-color:var(--muted)}.attbtn.ok{color:#16a34a;border-color:#16a34a}
/* Preview overlay (click a file name) */
.pv{position:fixed;inset:0;z-index:50;display:grid;place-items:center;background:rgba(0,0,0,.72);padding:16px}
.pv[hidden]{display:none}
.pvbox{position:relative;max-width:min(1000px,100%);max-height:100%;display:flex;flex-direction:column;background:var(--card);border-radius:12px;overflow:hidden}
.pvhead{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 12px;font-size:13px;border-bottom:1px solid var(--line)}
.pvhead span{overflow-wrap:anywhere}.pvclose{font-size:20px;line-height:1;color:var(--bright);background:transparent;border:0;padding:0 4px;cursor:pointer}
.pvbody{overflow:auto;min-height:0}.pvbody img,.pvbody video{display:block;max-width:100%;max-height:80vh;margin:auto}
.pvbody pre{margin:0;padding:12px;font:13px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:80vh}
.pvbody iframe{display:block;width:min(1000px,92vw);height:80vh;border:0;background:#fff}.pvbody audio{display:block;margin:20px}
.e img{max-width:100%;max-height:320px;border-radius:8px;margin-top:6px;display:block}
.tools{display:flex;gap:8px;margin:14px 2px;flex-wrap:wrap}.tools button,.tools a{font-size:13px;background:transparent;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:6px 10px;text-decoration:none;font-weight:500}
/* three columns: equal sides keep the middle link centered whatever the dates say */
.nav{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px;margin:0 2px 12px;font-size:14px}
.nav>:last-child{justify-self:end}
.nav .today{font-weight:600;color:var(--bright);text-align:center}
.title{font-size:28px;margin:4px 2px 12px;letter-spacing:-.01em}
</style></head><body><main>
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
<h1 class="title">Drop a line.</h1>
<div class="nav">{prev}{today}{next}</div>
<div class="cols">
<aside class="compose">{form}
{flash}</aside>
<section class="list">
<h2><span>{title}</span><span>{count} <button type="button" id="selectall" class="selall" hidden>Select all</button></span></h2>
{entries}
<div id="selbar" class="del" hidden>
  <b id="delcount"></b>
  <button type="button" id="selcopytext" class="plain" title="Just the notes">Copy text</button>
  <button type="button" id="selcopy" class="plain" title="Notes with time, source, and attachment links">Copy entry</button>
  <button type="button" id="selexport" class="plain">Export .zip</button>
  <button type="button" id="seldelete">Delete…</button>
  <button type="button" id="delcancel" class="plain">Cancel</button>
  <form id="delform" method="post" action="{base}delete/{day}" hidden>
    <input name="username" placeholder="Username" autocomplete="username" autocapitalize="none" required>
    <input type="password" name="password" placeholder="Password" autocomplete="current-password" required>
    <button>Delete</button>
  </form>
</div>
<script>
// Multi-select delete: tick entries (shift-click ticks a range, "Select all" ticks
// everything), then confirm with username + password.
(() => {
  const bar = document.getElementById("selbar"), form = document.getElementById("delform");
  const picks = [...document.querySelectorAll(".pick")];
  const ENTRIES = {entries_json};  // entry head (number, time, note, source) per position
  const FILES = {files_json};      // per position: file name -> its attachment line
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
    document.getElementById("selcopytext").hidden = n !== 1;  // just one note: copy its text
    all.textContent = n === picks.length && n ? "Select none" : "Select all";
    picks.forEach((p) => p.closest(".e").classList.toggle("sel", p.checked));
    apicks.flat().forEach((a) => a.closest(".att") && a.closest(".att").classList.toggle("asel", a.checked));
    const files = apicks.flat().filter((a) => a.checked).length;
    bar.hidden = n === 0 && files === 0;
    document.getElementById("delcount").textContent =
      `${n} entr${n === 1 ? "y" : "ies"}` + (files ? `, ${files} file${files === 1 ? "" : "s"}` : "") + " selected";
  };
  all.hidden = picks.length === 0;
  // Outlook-style: click an entry to select it (Ctrl/Cmd-click adds or removes one,
  // Shift-click selects a range). The round checkbox on the right ticks just that entry.
  const rows = picks.map((p) => p.closest(".e"));
  // Attachment circles: independent, except that changing an entry's selection sets all of its
  // attachments to match (select entry -> all its files; deselect entry -> none of them).
  const apicks = rows.map((r) => (r && r.querySelectorAll ? [...r.querySelectorAll(".apick")] : []));
  let before = picks.map((p) => p.checked);
  var syncFiles = () => {  // entries whose selection changed: their files follow
    picks.forEach((p, i) => {
      if (p.checked !== before[i]) apicks[i].forEach((a) => (a.checked = p.checked));
    });
    before = picks.map((p) => p.checked);
  };
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
  const busy = (t) => t.closest("a, button, input, textarea, select, form, video, audio, .details");
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
      if (picks[i].checked && apicks[i].some((a) => !a.checked) && !e.shiftKey) {
        picks[i].checked = false; apicks[i].forEach((a) => (a.checked = false)); last = i; update(); return;
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
  const clearAll = () => { picks.forEach((p) => (p.checked = false)); apicks.flat().forEach((a) => (a.checked = false)); last = null; update(); };
  document.getElementById("delcancel").onclick = clearAll;
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
    if (!picks.some((p) => p.checked) && !apicks.flat().some((a) => a.checked)) return;
    clearAll();
  });
  document.getElementById("seldelete").onclick = () => { form.hidden = false; form.querySelector("input").focus(); };
  // Copy-text icon on each entry: copies just that entry's note.
  document.querySelectorAll(".copynote").forEach((btn) => btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    const icon = btn.innerHTML, ok = await copyText(NOTES[Number(btn.dataset.i)] || "");
    btn.innerHTML = ok ? CHECK : icon; btn.classList.toggle("ok", ok); btn.title = ok ? "Copied" : "Couldn't copy";
    setTimeout(() => { btn.innerHTML = icon; btn.classList.remove("ok"); btn.title = "Copy text"; }, 1500);
  }));
  // What's selected, entry by entry: selected entries with only their ticked files; files
  // ticked on their own come under their entry's number marked "(files only)".
  const ticked = (i) => apicks[i].filter((a) => a.checked).map((a) => a.value);
  document.getElementById("selcopy").onclick = async (e) => {
    const blocks = [];
    picks.forEach((p, k) => {
      const i = Number(p.value), files = ticked(k).map((f) => FILES[i][f]).filter(Boolean);
      if (p.checked) blocks.push([ENTRIES[i], ...files].join("\\n"));
      else if (files.length) blocks.push([(ENTRIES[i].match(/^\\[[^\\]]*\\]/) || [""])[0] + " (files only)", ...files].join("\\n"));
    });
    const text = [`From my inbox for {day}:`, ...blocks.reverse()].join("\\n\\n");  // oldest first
    copyOut(e.target, text, "Copy entry");
  };
  document.getElementById("selcopytext").onclick = (e) => {
    copyOut(e.target, chosen().map((i) => NOTES[i]).filter(Boolean).join("\\n"), "Copy text");
  };
  async function copyOut(btn, text, label) {
    btn.textContent = (await copyText(text)) ? "Copied" : "Couldn't copy";
    setTimeout(() => (btn.textContent = label), 1500);
  }
  document.getElementById("selexport").onclick = () => {
    const files = apicks.flat().filter((a) => a.checked).map((a) => "f=" + encodeURIComponent(a.value));
    location.href = "{base}export/{day}?" + [...chosen().map((i) => "i=" + i), ...(files.length ? files : ["f="])].join("&");
  };
})();
</script>
<div class="pv" id="pv" hidden role="dialog" aria-modal="true" aria-labelledby="pvname">
  <div class="pvbox"><div class="pvhead"><span id="pvname"></span><button type="button" class="pvclose" id="pvclose" aria-label="Close">×</button></div>
  <div class="pvbody" id="pvbody"></div></div>
</div>
<div class="tools">
  <button type="button" id="copy">Copy for Claude</button>
  <a href="{base}day/{day}.md">inbox.md</a>
  {send}
</div>
</section>
</div>
</main>
<script>
const text = {plain};
const CHECK = {check_icon};
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
</body></html>"""

FORM = """<form method="post" action="{base}add" enctype="multipart/form-data">
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
// Picked files build up in a list (each with an x to remove it); the input is kept in sync so
// a normal form post sends exactly the listed files. Total is checked against MAX_MB before
// uploading: Cloudflare rejects anything over 100 MB with an error page.
(() => {
  const MAX_MB = {max_mb};
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
    out.textContent = !files.length ? "" : tooBig
      ? `${mb(total)} MB is over the ${MAX_MB} MB limit. Remove some files (your text stays), or save a link instead.`
      : `${files.length} file${files.length > 1 ? "s" : ""}, ${mb(total)} MB`;
  };
  // Clearing the input's value un-picks everything (works even without DataTransfer).
  clearAll.addEventListener("click", () => { picked = []; input.value = ""; render(); });
  input.addEventListener("change", () => {
    if (canEdit) { picked = picked.concat([...input.files]); sync(); }
    render();
  });
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
ICON_CHECK = _SVG.format(
    d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"
)


def attachment_card(day: str, f: str) -> str:
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
    return (
        f'<div class="att" data-kind="{kind}" data-url="{url}">'
        f'<a class="attname" href="{url}" target="_blank" rel="noopener">{name}</a>'
        f'<span class="atticons">'
        f'<a class="attbtn" href="{url}?download=1" title="Download" aria-label="Download {name}">{ICON_DOWNLOAD}</a>'
        f'<button type="button" class="attbtn copyatt" title="Copy" aria-label="Copy {name}">{ICON_COPY}</button>'
        f'<button type="button" class="attbtn delatt" data-file="{name}" title="Delete" aria-label="Delete {name}">{ICON_TRASH}</button>'
        f'<input type="checkbox" class="apick" name="dfile" value="{name}" form="delform" aria-label="Select {name}">'
        f"</span></div>"
    )


def js_json(value) -> str:
    """JSON safe to drop into an inline <script>: no "</script>", and nothing shaped like one of
    this page's {placeholders} (so user text can never be substituted). JSON's own braces stay."""
    out = json.dumps(value).replace("</", "<\\/")
    return re.sub(r"\{([A-Za-z_]+)\}", r"\\u007b\1\\u007d", out)


def render(day: str, flash: str = "", session: dict | None = None) -> bytes:
    base = "/inbox/"
    entries = read_day(day)
    today = date.today().isoformat()
    items = []
    for i, e in reversed(
        list(enumerate(entries))
    ):  # newest first; i = position in inbox.md
        body = [
            f'<div class="ehead"><span class="t"><b class="num">{day}.{e["n"]}</b>'
            # Time + metadata live in a tooltip on "details" (hover, or tap/focus on phones).
            f'<span class="details" tabindex="0">details<span class="tip" role="tooltip">'
            f"{html.escape(e['time'])}"
            + (f"<br>{html.escape(e['meta'])}" if e.get("meta") else "")
            + "</span></span></span>"
            + (
                f'<button type="button" class="attbtn copynote" data-i="{i}" title="Copy text" '
                f'aria-label="Copy the note of entry {day}.{e["n"]}">{ICON_COPY}</button>'
                if e["text"]
                else ""
            )
            + f'<input type="checkbox" class="pick" name="del" value="{i}" form="delform" '
            f'aria-label="Select entry from {html.escape(e["time"])}"></div>'
        ]
        if e["text"]:
            body.append(f"<p>{linkify(e['text'])}</p>")
        if e["files"]:
            cards = "".join(attachment_card(day, f) for f in e["files"])
            body.append(f'<div class="atts">{cards}</div>')
        items.append('<div class="e">' + "".join(body) + "</div>")
    d = date.fromisoformat(day)
    prev_day, next_day = (
        (d - timedelta(days=1)).isoformat(),
        (d + timedelta(days=1)).isoformat(),
    )
    sent = (day_dir(day) / ".digest-sent").exists()
    send = (
        f'<form method="post" action="{base}send/{day}" style="display:contents"><button>'
        f"{'Email again' if sent else 'Email this day now'}</button></form>"
        if entries
        else ""
    )
    # Fill the template's own placeholders first, then insert user content (which may contain
    # anything, including "{day}").
    page = (
        PAGE.replace(
            "{logout}", LOGOUT.replace("{tag}", session["tag"]) if session else ""
        )
        .replace("{base}", base)
        .replace("{day}", day)
        .replace(
            "{form}",
            FORM.replace("{base}", base).replace("{max_mb}", str(MAX_UPLOAD_MB))
            if day == today
            else "",
        )
        .replace(
            "{flash}", f'<div class="ok">{html.escape(flash)}</div>' if flash else ""
        )
        .replace("{title}", "Today" if day == today else day)
        .replace("{count}", f"{len(entries)} saved" + (" · emailed" if sent else ""))
        .replace("{entries}", "".join(items) or '<div class="e t">Nothing yet.</div>')
        .replace("{send}", send)
        .replace("{prev}", f'<a href="{base}day/{prev_day}">← {prev_day}</a>')
        .replace(
            "{today}",
            f'<a class="today" href="{base}">Go to today ({date.today():%a %b %-d})</a>'
            if day != today
            else f'<span class="today">Today · {date.today():%a %b %-d}</span>',
        )
        .replace(
            "{next}",
            f'<a href="{base}day/{next_day}">{next_day} →</a>'
            if day < today
            else "<span></span>",
        )
        .replace("{check_icon}", js_json(ICON_CHECK))
        .replace("{plain}", js_json(plain_text(day, entries)))
        .replace("{entries_json}", js_json([entry_head(day, e) for e in entries]))
        .replace(
            "{files_json}",
            js_json([{f: attach_line(day, f) for f in e["files"]} for e in entries]),
        )
        .replace("{notes_json}", js_json([e["text"] for e in entries]))
    )
    return page.encode()


# ------------------------------------------------------------------- http


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
            page = render(date.today().isoformat(), flash, session)
            self._send(200, page, "text/html; charset=utf-8")
        elif m := re.fullmatch(r"/inbox/day/(\d{4}-\d{2}-\d{2})", path):
            self._send(200, render(m[1], flash, session), "text/html; charset=utf-8")
        elif m := re.fullmatch(r"/inbox/day/(\d{4}-\d{2}-\d{2})\.md", path):
            md = day_dir(m[1]) / "inbox.md"
            body = (
                md.read_bytes()
                if md.exists()
                else f"# Inbox {m[1]}\n\n(nothing saved)\n".encode()
            )
            self._send(200, body, "text/markdown; charset=utf-8")
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
            name = f"inbox-{m[1]}-selected.zip"
            self._send(
                200,
                export_zip(m[1], picks, files),
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
        if length > MAX_UPLOAD:
            self._send(
                413,
                f"too big ({MAX_UPLOAD_MB} MB max per entry)".encode(),
                "text/plain",
            )
            return
        body = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")
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
            user, pw = (f.get("username") or [""])[0], (f.get("password") or [""])[0]
            if too_many_fails(ip) or not (PASSWORD_HASH and check_login(user, pw)):
                with _auth_lock:
                    _fails.setdefault(ip, []).append(time.time())
                self._redirect(
                    f"/inbox/day/{m[1]}?sent={quote('Not deleted: wrong username or password.')}"
                )
                return
            if f.get("file"):  # one attachment (trash icon on its line)
                ok = delete_file(m[1], f["file"][0])
                msg = "Deleted the file." if ok else "That file wasn't found."
                self._redirect(f"/inbox/day/{m[1]}?sent={quote(msg)}")
                return
            picks = {int(v) for v in f.get("del", []) if v.isdigit()}
            whole, nfiles = delete_selection(m[1], picks, set(f.get("dfile", [])))
            msg = (
                f"Deleted {whole} entr{'y' if whole == 1 else 'ies'}"
                + (f" and {nfiles} file{'' if nfiles == 1 else 's'}" if nfiles else "")
                + "."
            )
            self._redirect(f"/inbox/day/{m[1]}?sent={quote(msg)}")
            return
        if path == "/inbox/add":
            text, files = "", []
            if ctype.startswith("multipart/form-data"):
                msg = BytesParser(policy=email_policy).parsebytes(
                    f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode()
                    + body
                )
                for part in msg.iter_parts():
                    name = part.get_param("name", header="content-disposition")
                    if name == "text":
                        text = (
                            part.get_content()
                            if part.get_content_maintype() == "text"
                            else part.get_payload(decode=True).decode(
                                "utf-8", "replace"
                            )
                        )
                    elif name == "file" and part.get_filename():
                        data = part.get_payload(decode=True) or b""
                        if data:
                            files.append((part.get_filename(), data))
            if not text.strip() and not files:
                self._redirect("/inbox/")
                return
            add_entry(text, files, describe_source(self.headers))
            self._redirect("/inbox/?saved")
        elif m := re.fullmatch(r"/inbox/send/(\d{4}-\d{2}-\d{2})", path):
            try:
                result = send_digest(m[1])
            except Exception as e:
                result = f"email failed: {e.__class__.__name__}: {e}"
            self._redirect(f"/inbox/day/{m[1]}?sent={quote(result)}")
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
