"""Tasks: a small personal task tracker (courses, projects, ideas) at cesiumlab.net/tasks/.

Groups are categories (School, Music, Nerd, Chores...). Inside a group, tasks nest without
limit; a task marked as a container is a course or project header (AA 274A, Cesium, Gig
Tracker) that shows progress instead of a checkbox. Tasks have a title, due date, priority,
status, and notes; a title alone is enough to add one. Everything lives in its parent's group.

Storage: one JSON file, TASKS_DIR/tasks.json (default /srv/state/tasks, the internal drive),
written atomically. A dated copy goes to TASKS_BACKUP_DIR once a day (default
/srv/data/backups/tasks, the data drive; last 30 kept). See README.md for backup/restore.

Access: same rule and credentials as the inbox. Home LAN and Tailscale need no login; everyone
else (including everything through the Cloudflare tunnel) logs in with INBOX_USERNAME /
INBOX_PASSWORD_HASH from /etc/cesium/inbox.env.

    python3 server.py            # serve on 127.0.0.1:42906 (TASKS_PORT)

Standard library only.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import ipaddress
import json
import os
import re
import secrets
import shutil
import threading
import time
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import session  # noqa: E402

HOST = "127.0.0.1"
PORT = int(os.getenv("TASKS_PORT", "42906"))
DIR = Path(os.getenv("TASKS_DIR", "/srv/state/tasks"))
BACKUP_DIR = Path(os.getenv("TASKS_BACKUP_DIR", "/srv/data/backups/tasks"))
# Backups only happen while this (the data drive) is there, so nothing lands on the system disk.
BACKUP_NEEDS = Path(os.getenv("TASKS_BACKUP_NEEDS", "/srv/data"))
KEEP_BACKUPS = 30
DB = DIR / "tasks.json"

USERNAME = os.getenv("INBOX_USERNAME", "colin")
PASSWORD_HASH = os.getenv("INBOX_PASSWORD_HASH", "")
HOME_NETS = [
    ipaddress.ip_network(n)
    for n in os.getenv(
        "INBOX_HOME_NETS", "192.168.0.0/24,100.64.0.0/10,fd7a:115c:a1e0::/48"
    ).split(",")
    if n.strip()
]

PRIORITIES = ("low", "normal", "medium", "high")  # normal = no priority set
STATUSES = (
    "todo",
    "doing",
    "done",
    "cancelled",
)  # Not started / In progress / Done / Cancelled
CLOSED = ("done", "cancelled")
COLORS = (
    "gray",
    "brown",
    "orange",
    "yellow",
    "green",
    "blue",
    "darkblue",
    "purple",
    "pink",
    "red",
)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# ------------------------------------------------------------------ storage

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> dict:
    if not DB.exists():
        return {"version": 1, "groups": [], "tasks": []}
    data = json.loads(DB.read_text(encoding="utf-8"))
    for t in data[
        "tasks"
    ]:  # older imports stored Cancelled as done + a "(cancelled)" note
        if t.get("status") == "done" and t.get("notes", "").startswith("(cancelled)"):
            t["status"] = "cancelled"
            t["notes"] = t["notes"][len("(cancelled)") :].lstrip()
    return data


def save(data: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = DB.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, DB)  # all or nothing: a crash mid-write keeps the previous file


def backup_once() -> str | None:
    """Copy tasks.json to BACKUP_DIR/tasks-YYYY-MM-DD.json if today's copy is missing.
    Skipped (returns None) when the data drive isn't there."""
    if not DB.exists() or not BACKUP_NEEDS.is_dir() or not any(BACKUP_NEEDS.iterdir()):
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out = BACKUP_DIR / f"tasks-{date.today()}.json"
    if not out.exists():
        with _lock:
            shutil.copyfile(DB, out)
        for old in sorted(BACKUP_DIR.glob("tasks-*.json"))[:-KEEP_BACKUPS]:
            old.unlink()
    return str(out)


def backup_worker() -> None:
    while True:
        try:
            backup_once()
        except OSError as e:
            print(f"backup failed: {e}", flush=True)
        time.sleep(3600)


class Bad(Exception):
    """A request with invalid fields (-> 400 with the message)."""


def _descendants(data: dict, tid: str) -> list[dict]:
    out, todo = [], [tid]
    while todo:
        cur = todo.pop()
        kids = [t for t in data["tasks"] if t.get("parent") == cur]
        out += kids
        todo += [k["id"] for k in kids]
    return out


def _clean_task_fields(body: dict, data: dict, partial: bool) -> dict:
    out = {}
    if "title" in body or not partial:
        title = " ".join(str(body.get("title", "")).split())
        if not title:
            raise Bad("A task needs a title.")
        out["title"] = title[:300]
    if "group" in body:
        g = body["group"] or None
        if g is not None and not any(x["id"] == g for x in data["groups"]):
            raise Bad("No such group.")
        out["group"] = g
    if "due" in body:
        d = body["due"] or None
        if d is not None and not DATE_RE.fullmatch(str(d)):
            raise Bad("Due date must be YYYY-MM-DD.")
        out["due"] = d
    if "priority" in body:
        if body["priority"] not in PRIORITIES:
            raise Bad("Priority must be low, normal, medium, or high.")
        out["priority"] = body["priority"]
    if "status" in body:
        if body["status"] not in STATUSES:
            raise Bad("Status must be todo, doing, done, or cancelled.")
        out["status"] = body["status"]
    if "notes" in body:
        out["notes"] = str(body["notes"] or "")[:20000]
    for flag in ("container", "archived", "pinned"):
        if flag in body:
            out[flag] = bool(body[flag])
    return out


def create_group(body: dict) -> dict:
    """A group is a category: School, Music, Nerd, Chores..."""
    name = " ".join(str(body.get("name", "")).split())[:120]
    if not name:
        raise Bad("A group needs a name.")
    with _lock:
        data = load()
        if any(g["name"].lower() == name.lower() for g in data["groups"]):
            raise Bad(f"{name} already exists.")
        g = {"id": secrets.token_hex(4), "name": name, "archived": False}
        data["groups"].append(g)
        save(data)
    return g


def update_group(gid: str, body: dict) -> dict:
    with _lock:
        data = load()
        g = next((x for x in data["groups"] if x["id"] == gid), None)
        if g is None:
            raise KeyError(gid)
        if "name" in body:
            name = " ".join(str(body["name"]).split())[:120]
            if not name:
                raise Bad("A group needs a name.")
            g["name"] = name
        if "archived" in body:
            g["archived"] = bool(body["archived"])
        if "pinned" in body:
            g["pinned"] = bool(body["pinned"])
        if "color" in body:
            if body["color"] not in COLORS:
                raise Bad("Unknown color.")
            g["color"] = body["color"]
        save(data)
    return g


def delete_group(gid: str) -> None:
    """Remove a group; its tasks are kept, as unsorted."""
    with _lock:
        data = load()
        if not any(x["id"] == gid for x in data["groups"]):
            raise KeyError(gid)
        data["groups"] = [x for x in data["groups"] if x["id"] != gid]
        for t in data["tasks"]:
            if t.get("group") == gid:
                t["group"] = None
        save(data)


def _new_task(fields: dict, parent: str | None) -> dict:
    t = {
        "id": secrets.token_hex(5),
        "title": fields["title"],
        "group": fields.get("group"),
        "parent": parent,
        "container": fields.get("container", False),
        "archived": fields.get("archived", False),
        "pinned": fields.get("pinned", False),
        "due": fields.get("due"),
        "priority": fields.get("priority", "normal"),
        "status": fields.get("status", "todo"),
        "notes": fields.get("notes", ""),
        "created": _now(),
        "updated": _now(),
        "completed": None,
    }
    if t["status"] in CLOSED:
        t["completed"] = _now()
    return t


def create_task(body: dict) -> dict:
    with _lock:
        data = load()
        fields = _clean_task_fields(body, data, partial=False)
        parent = body.get("parent") or None
        if parent is not None:
            p = next((x for x in data["tasks"] if x["id"] == parent), None)
            if p is None:
                raise Bad("No such parent task.")
            fields["group"] = p.get("group")  # everything lives in its parent's group
        t = _new_task(fields, parent)
        data["tasks"].append(t)
        save(data)
    return t


def update_task(tid: str, body: dict) -> dict:
    with _lock:
        data = load()
        t = next((x for x in data["tasks"] if x["id"] == tid), None)
        if t is None:
            raise KeyError(tid)
        fields = _clean_task_fields(body, data, partial=True)
        if (
            "parent" in body
        ):  # move under another task (or to the top of its group: null)
            np = body["parent"] or None
            if np is not None:
                p = next((x for x in data["tasks"] if x["id"] == np), None)
                if p is None:
                    raise Bad("No such parent task.")
                if np == tid or any(d["id"] == np for d in _descendants(data, tid)):
                    raise Bad("A task can't go inside itself.")
                fields["group"] = p.get("group")
            t["parent"] = np
        if "status" in fields and fields["status"] != t["status"]:
            t["completed"] = _now() if fields["status"] in CLOSED else None
        t.update(fields)
        t["updated"] = _now()
        if "group" in fields:  # a task's whole subtree moves with it
            for d in _descendants(data, tid):
                d["group"] = t["group"]
        save(data)
    return t


def delete_task(tid: str) -> int:
    """Delete a task and everything under it. Returns how many were removed."""
    with _lock:
        data = load()
        if not any(x["id"] == tid for x in data["tasks"]):
            raise KeyError(tid)
        gone = {tid} | {d["id"] for d in _descendants(data, tid)}
        data["tasks"] = [x for x in data["tasks"] if x["id"] not in gone]
        save(data)
    return len(gone)


# --------------------------------------------------------------------- auth
# Same rule as the inbox (see backend/services/inbox/server.py, "auth"): Apache appends the real
# visitor address as the last X-Forwarded-For entry; home LAN and Tailscale need no login.

_fails: dict[str, list[float]] = {}
_auth_lock = threading.Lock()


def check_login(user: str, pw: str) -> bool:
    try:
        algo, iters, salt, want = PASSWORD_HASH.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(iters))
    ok_pw = hmac.compare_digest(dk.hex(), want)
    return hmac.compare_digest(user.strip().lower(), USERNAME.lower()) and ok_pw


def visitor_ip(headers) -> str:
    xff = headers.get("X-Forwarded-For", "")
    return xff.split(",")[-1].strip() if xff else ""


def is_home(headers) -> bool:
    try:
        ip = ipaddress.ip_address(visitor_ip(headers))
    except ValueError:
        return False
    return any(ip in net for net in HOME_NETS)


def logged_in(headers) -> bool:
    return session.valid(headers)  # the shared login (common/session.py)


def too_many_fails(ip: str) -> bool:
    now = time.time()
    with _auth_lock:
        recent = [t for t in _fails.get(ip, []) if now - t < 300]
        _fails[ip] = recent
        return len(recent) >= 5


LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Tasks</title>
<meta name="robots" content="noindex"><link rel="icon" href="/favicon.svg?v=5" type="image/svg+xml">
<style>
:root{--bg:#fafaf7;--card:#fff;--ink:#111;--line:#e5e3dc;--accent:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#14140f;--card:#1c1c17;--ink:#fff;--line:#3a3a32;--accent:#60a5fa}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 -apple-system,Helvetica,Arial,sans-serif}
form{max-width:320px;margin:18vh auto 0;padding:20px;background:var(--card);border:1px solid var(--line);border-radius:12px;display:grid;gap:12px}
h1{font-size:18px;margin:0}input{font:inherit;padding:10px;border:1px solid var(--line);border-radius:8px;background:transparent;color:inherit}
button{font:inherit;font-weight:600;color:#fff;background:var(--accent);border:0;border-radius:8px;padding:10px;cursor:pointer}
.msg{color:#dc2626;font-size:13px;min-height:1em}
</style></head><body>
<form method="post" action="/tasks/login">
  <h1>Tasks</h1>
  <input name="username" placeholder="Username" autocomplete="username" autocapitalize="none" autofocus required>
  <input type="password" name="password" placeholder="Password" autocomplete="current-password" required>
  <button>Log in</button>
  <div class="msg">{msg}</div>
</form></body></html>"""


def login_page(msg: str = "") -> bytes:
    return LOGIN_PAGE.replace("{msg}", html.escape(msg)).encode()


# --------------------------------------------------------------------- http

APP = (Path(__file__).parent / "app.html").read_text(encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "tasks"

    def _send(
        self, code: int, body: bytes, ctype: str, extra: dict | None = None
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        extra = dict(extra or {})
        if "Set-Cookie" not in extra and (c := session.refresh(self.headers)):
            extra["Set-Cookie"] = c  # slide the shared login's hour
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(
            code, json.dumps(obj, ensure_ascii=False).encode(), "application/json"
        )

    def _allowed(self) -> bool:
        return is_home(self.headers) or logged_in(self.headers)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 100_000:
            raise Bad("Request too large.")
        raw = self.rfile.read(n) if n else b"{}"
        try:
            obj = json.loads(raw or b"{}")
        except ValueError:
            raise Bad("Body must be JSON.") from None
        if not isinstance(obj, dict):
            raise Bad("Body must be a JSON object.")
        return obj

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/tasks/health":
            return self._json(200, {"ok": True, "db": str(DB), "exists": DB.exists()})
        if path in ("/tasks", "/tasks/"):
            if not self._allowed():
                return self._send(200, login_page(), "text/html; charset=utf-8")
            return self._send(200, APP.encode(), "text/html; charset=utf-8")
        if path == "/tasks/api/state":
            if not self._allowed():
                return self._json(401, {"error": "login"})
            with _lock:
                data = load()
            return self._json(200, data)
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/tasks/login":
            return self._login()
        self._api("POST", path)

    def do_PATCH(self) -> None:  # noqa: N802
        self._api("PATCH", self.path.split("?", 1)[0])

    def do_DELETE(self) -> None:  # noqa: N802
        self._api("DELETE", self.path.split("?", 1)[0])

    def _api(self, method: str, path: str) -> None:
        if not self._allowed():
            return self._json(401, {"error": "login"})
        # Only the page's own script sends this header; a form or link on another site can't
        # (a custom header forces a CORS preflight, which this server never answers).
        if self.headers.get("X-Tasks") != "1":
            return self._json(403, {"error": "missing X-Tasks header"})
        try:
            if method == "POST" and path == "/tasks/api/groups":
                return self._json(201, create_group(self._body()))
            if method == "POST" and path == "/tasks/api/tasks":
                return self._json(201, create_task(self._body()))
            if m := re.fullmatch(r"/tasks/api/groups/([0-9a-f]{8})", path):
                if method == "PATCH":
                    return self._json(200, update_group(m[1], self._body()))
                if method == "DELETE":
                    delete_group(m[1])
                    return self._json(200, {"ok": True})
            if m := re.fullmatch(r"/tasks/api/tasks/([0-9a-f]{10})", path):
                if method == "PATCH":
                    return self._json(200, update_task(m[1], self._body()))
                if method == "DELETE":
                    return self._json(200, {"deleted": delete_task(m[1])})
        except Bad as e:
            return self._json(400, {"error": str(e)})
        except KeyError:
            return self._json(404, {"error": "not found"})
        self._json(404, {"error": "not found"})

    def _login(self) -> None:
        ip = visitor_ip(self.headers) or "?"
        n = int(self.headers.get("Content-Length") or 0)
        f = parse_qs(self.rfile.read(min(n, 10_000)).decode("utf-8", "replace"))
        if too_many_fails(ip):
            return self._send(
                429,
                login_page("Too many tries. Wait a few minutes."),
                "text/html; charset=utf-8",
            )
        if PASSWORD_HASH and check_login(
            (f.get("username") or [""])[0], (f.get("password") or [""])[0]
        ):
            cookie = session.issue(self.headers)
            return self._send(
                303, b"", "text/plain", {"Location": "/tasks/", "Set-Cookie": cookie}
            )
        with _auth_lock:
            _fails.setdefault(ip, []).append(time.time())
        msg = (
            "Wrong username or password."
            if PASSWORD_HASH
            else "No password is set up on the server yet."
        )
        self._send(401, login_page(msg), "text/html; charset=utf-8")

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=backup_worker, daemon=True).start()
    print(
        f"tasks on http://{HOST}:{PORT}/tasks/ -> {DB} (backups: {BACKUP_DIR})",
        flush=True,
    )
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
