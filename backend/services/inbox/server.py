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
        block = [f"## {now:%H:%M:%S %Z}", f"_{meta}_", ""]
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
            [f"## {e['time']}"] + ([f"_{e['meta']}_"] if e.get("meta") else []) + [""]
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
                fh.write(f"## {e['time']} (deleted {datetime.now():%H:%M:%S})\n\n")
                fh.write("".join(f"> {ln}\n" for ln in e["text"].splitlines()))
                fh.write("".join(f"- {f}\n" for f in e["files"]) + "\n")
                for f in e["files"]:
                    src = day_dir(day) / safe_name(f)
                    if src.is_file():
                        src.rename(trash / src.name)
        write_day(day, keep)
        return len(gone)


def read_day(day: str) -> list[dict]:
    """Parse a day's inbox.md back into entries: [{time, text, files}]."""
    md = day_dir(day) / "inbox.md"
    if not md.exists():
        return []
    entries: list[dict] = []
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            entries.append(
                {"time": line[3:].strip(), "meta": "", "text": [], "files": []}
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


def entry_text(day: str, e: dict) -> str:
    """One entry as plain text (for Claude/ChatGPT)."""
    lines = [f"[{e['time']}] {e['text'] or '(no note)'}"]
    if e.get("meta"):
        lines.append(f"  ({e['meta']})")
    for f in e["files"]:
        lines.append(f"  attachment: {f} ({PUBLIC_URL}files/{day}/{quote(f)})")
    return "\n".join(lines)


def plain_text(day: str, entries: list[dict]) -> str:
    """The block meant for pasting into Claude/ChatGPT."""
    head = f"My inbox for {day} ({len(entries)} entries). Each is something I saved to deal with later."
    return "\n\n".join([head] + [entry_text(day, e) for e in entries])


def export_zip(day: str, indexes: set[int]) -> bytes:
    """Selected entries as a zip: selected.md (same format as inbox.md) plus their files."""
    entries = [e for i, e in enumerate(read_day(day)) if i in indexes]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        md = [f"# Inbox {day} (selected)", ""]
        for e in entries:
            md += (
                [f"## {e['time']}"]
                + ([f"_{e['meta']}_"] if e.get("meta") else [])
                + [""]
            )
            md += [f"> {ln}" if ln else ">" for ln in e["text"].splitlines()]
            md += [f"- [{f}]({quote(f)})" for f in e["files"]] + [""]
            for f in e["files"]:
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
:root{--bg:#fafaf7;--card:#fff;--ink:#1a1a1a;--muted:#6b6b66;--line:#e5e3dc;--accent:#c4541c}
@media(prefers-color-scheme:dark){:root{--bg:#14140f;--card:#1c1c17;--ink:#f5f3ec;--muted:#8a8a82;--line:#2a2a23;--accent:#f0997b}}
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
:root{--bg:#fafaf7;--card:#fff;--ink:#1a1a1a;--muted:#6b6b66;--line:#e5e3dc;--accent:#c4541c}
@media(prefers-color-scheme:dark){:root{--bg:#14140f;--card:#1c1c17;--ink:#f5f3ec;--muted:#8a8a82;--line:#2a2a23;--accent:#f0997b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,Helvetica,Arial,sans-serif}
main{max-width:640px;margin:0 auto;padding:20px 16px 60px}
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
.pick{width:16px;height:16px;vertical-align:-3px;margin-right:4px;accent-color:var(--accent)}
label.t{cursor:pointer;user-select:none}
.selall{font-size:11px;font-weight:500;letter-spacing:0;text-transform:none;color:var(--muted);background:transparent;border:1px solid var(--line);border-radius:6px;padding:2px 8px;margin-left:8px}.meta{font-size:11px;opacity:.8}
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
.e img{max-width:100%;max-height:320px;border-radius:8px;margin-top:6px;display:block}
.tools{display:flex;gap:8px;margin:14px 2px;flex-wrap:wrap}.tools button,.tools a{font-size:13px;background:transparent;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:6px 10px;text-decoration:none;font-weight:500}
.nav{display:flex;justify-content:space-between;margin:20px 2px;font-size:14px}
</style></head><body><main>
{logout}
{form}
{flash}
<h2><span>{title}</span><span>{count} <button type="button" id="selectall" class="selall" hidden>Select all</button></span></h2>
{entries}
<div id="selbar" class="del" hidden>
  <b id="delcount"></b>
  <button type="button" id="selcopy" class="plain">Copy</button>
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
  const ENTRIES = {entries_json};  // plain text per entry position, for Copy
  const chosen = () => picks.filter((p) => p.checked).map((p) => Number(p.value)).sort((a, b) => a - b);
  const all = document.getElementById("selectall");
  let last = null;
  const update = () => {
    const n = picks.filter((p) => p.checked).length;
    bar.hidden = n === 0;
    if (n === 0) form.hidden = true;
    document.getElementById("delcount").textContent = `${n} selected`;
    all.textContent = n === picks.length && n ? "Select none" : "Select all";
  };
  all.hidden = picks.length === 0;
  picks.forEach((p, i) => p.addEventListener("click", (e) => {
    if (e.shiftKey && last !== null && last !== i) {
      const [a, b] = last < i ? [last, i] : [i, last];
      for (let k = a; k <= b; k++) picks[k].checked = p.checked; // match the box just clicked
    }
    last = i;
    update();
  }));
  all.onclick = () => {
    const on = !picks.every((p) => p.checked);
    picks.forEach((p) => (p.checked = on));
    last = null;
    update();
  };
  document.getElementById("delcancel").onclick = () => { picks.forEach((p) => (p.checked = false)); last = null; update(); };
  document.getElementById("seldelete").onclick = () => { form.hidden = false; form.querySelector("input").focus(); };
  document.getElementById("selcopy").onclick = async (e) => {
    const ids = chosen();
    const text = [`From my inbox for {day} (${ids.length} of ${ENTRIES.length} entries):`, ...ids.map((i) => ENTRIES[i])].join("\\n\\n");
    try { await navigator.clipboard.writeText(text); e.target.textContent = "Copied"; setTimeout(() => (e.target.textContent = "Copy"), 1500); }
    catch { prompt("Copy:", text); }
  };
  document.getElementById("selexport").onclick = () => {
    location.href = "{base}export/{day}?" + chosen().map((i) => "i=" + i).join("&");
  };
})();
</script>
<div class="tools">
  <button type="button" id="copy">Copy for Claude</button>
  <a href="{base}day/{day}.md">inbox.md</a>
  {send}
</div>
<div class="nav">{prev}<span></span>{next}</div>
</main>
<script>
const text = {plain};
document.getElementById("copy").onclick = async (e) => {
  try { await navigator.clipboard.writeText(text); e.target.textContent = "Copied"; } catch { prompt("Copy:", text); }
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


def js_json(value) -> str:
    """JSON safe to drop into an inline <script>: no "</script>", and no braces, so user text
    can never look like one of this page's {placeholders}."""
    return (
        json.dumps(value)
        .replace("</", "<\\/")
        .replace("{", "\\u007b")
        .replace("}", "\\u007d")
    )


def render(day: str, flash: str = "", session: dict | None = None) -> bytes:
    base = "/inbox/"
    entries = read_day(day)
    today = date.today().isoformat()
    items = []
    for i, e in reversed(
        list(enumerate(entries))
    ):  # newest first; i = position in inbox.md
        body = [
            f'<label class="t"><input type="checkbox" class="pick" name="del" value="{i}" '
            f'form="delform"> {html.escape(e["time"])}</label>'
        ]
        if e.get("meta"):
            body.append(f'<div class="t meta">{html.escape(e["meta"])}</div>')
        if e["text"]:
            body.append(f"<p>{linkify(e['text'])}</p>")
        for f in e["files"]:
            url = f"{base}files/{day}/{quote(f)}"
            if Path(f).suffix.lower() in IMAGE_EXT - {".heic", ".heif"}:
                body.append(
                    f'<a href="{url}"><img src="{url}" alt="" loading="lazy"></a>'
                )
            else:
                body.append(f'<p><a href="{url}">{html.escape(f)}</a></p>')
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
            "{next}",
            f'<a href="{base}day/{next_day}">{next_day} →</a>' if day < today else "",
        )
        .replace("{plain}", js_json(plain_text(day, entries)))
        .replace("{entries_json}", js_json([entry_text(day, e) for e in entries]))
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
                self._send(200, f.read_bytes(), ctype)
            else:
                self._send(404, b"not found", "text/plain")
        elif m := re.fullmatch(r"/inbox/export/(\d{4}-\d{2}-\d{2})", path):
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            picks = {int(v) for v in parse_qs(query).get("i", []) if v.isdigit()}
            name = f"inbox-{m[1]}-selected.zip"
            self._send(
                200,
                export_zip(m[1], picks),
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
            picks = {int(v) for v in f.get("del", []) if v.isdigit()}
            n = delete_entries(m[1], picks)
            self._redirect(f"/inbox/day/{m[1]}?deleted={n}")
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
