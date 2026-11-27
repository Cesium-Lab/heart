"""HQ: Colin's private home base for people, organizations, projects, and songs (and later
social media / creator work), at cesiumlab.net/hq/.

Schema-driven: every collection is a field list in SCHEMA below; the server validates against
it and the page (app.html) draws tables and forms from the same schema (GET /hq/api/state).
Adding a collection later (e.g. "content") means adding an entry to SCHEMA.

Links: a person links to organizations and projects, each link with a short role
("MONARCH: drummer"). Projects nest (parent) and can belong to an organization; songs belong
to a project. Deleting something clears every reference to it.

Storage: HQ_DIR/hq.json (default /srv/state/hq, internal drive), written atomically; a dated
copy goes to HQ_BACKUP_DIR once a day (default /srv/data/backups/hq, last 30 kept).

Access: a login is ALWAYS required (contacts are private), even on the home network, with the
inbox's credentials (INBOX_USERNAME / INBOX_PASSWORD_HASH from /etc/cesium/inbox.env).

    python3 server.py            # serve on 127.0.0.1:42907 (HQ_PORT)

Standard library only.
"""

from __future__ import annotations

import hashlib
import hmac
import html
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
PORT = int(os.getenv("HQ_PORT", "42907"))
DIR = Path(os.getenv("HQ_DIR", "/srv/state/hq"))
BACKUP_DIR = Path(os.getenv("HQ_BACKUP_DIR", "/srv/data/backups/hq"))
BACKUP_NEEDS = Path(
    os.getenv("HQ_BACKUP_NEEDS", "/srv/data")
)  # only back up while it's there
KEEP_BACKUPS = 30
DB = DIR / "hq.json"
USERNAME = os.getenv("INBOX_USERNAME", "colin")
PASSWORD_HASH = os.getenv("INBOX_PASSWORD_HASH", "")

# ------------------------------------------------------------------ schema
# type: str (one line) | text (multi-line) | lines (one item per line) | enum | multi
#       | bool | date | ref (id in another collection)
SCHEMA: dict[str, dict] = {
    "people": {
        "label": "People",
        "one": "Person",
        "fields": [
            ("name", "str", {"label": "Name", "required": True}),
            (
                "areas",
                "multi",
                {
                    "label": "Area",
                    "options": ["Music", "Aerospace", "Personal", "Other"],
                },
            ),
            (
                "strength",
                "enum",
                {
                    "label": "Relationship",
                    "options": ["New", "Familiar", "Strong", "Super close"],
                },
            ),
            ("org_text", "str", {"label": "Organization"}),
            ("role", "str", {"label": "Role"}),
            ("known_from", "str", {"label": "Where I know them from"}),
            ("location", "str", {"label": "Location"}),
            ("phones", "lines", {"label": "Phone"}),
            ("emails", "lines", {"label": "Email"}),
            ("socials", "lines", {"label": "Social links"}),
            ("cares", "text", {"label": "What they care about"}),
            ("offer", "text", {"label": "What I can offer"}),
            ("ask", "text", {"label": "What I might ask for"}),
            ("current", "text", {"label": "Current projects / opportunities"}),
            ("plans", "text", {"label": "Plans"}),
            ("notes", "text", {"label": "Notes"}),
        ],
    },
    "orgs": {
        "label": "Organizations",
        "one": "Organization",
        "fields": [
            ("name", "str", {"label": "Name", "required": True}),
            (
                "type",
                "enum",
                {
                    "label": "Type",
                    "options": [
                        "Band",
                        "Artist project",
                        "Venue",
                        "Promoter",
                        "Label",
                        "Collective",
                        "Studio",
                        "Company",
                        "School",
                        "Other",
                    ],
                },
            ),
            ("location", "str", {"label": "Location"}),
            ("website", "str", {"label": "Website"}),
            ("socials", "lines", {"label": "Socials"}),
            ("context", "text", {"label": "Connection / context"}),
            ("notes", "text", {"label": "Notes"}),
        ],
    },
    "projects": {
        "label": "Projects",
        "one": "Project",
        "fields": [
            ("name", "str", {"label": "Name", "required": True}),
            ("icon", "str", {"label": "Icon (emoji)"}),
            (
                "type",
                "enum",
                {
                    "label": "Type",
                    "options": [
                        "Band",
                        "Artist project",
                        "Release",
                        "Show",
                        "Content",
                        "Collaboration",
                        "Other",
                    ],
                },
            ),
            (
                "status",
                "enum",
                {"label": "Status", "options": ["Idea", "Active", "Paused", "Done"]},
            ),
            ("parent", "ref", {"label": "Inside project", "to": "projects"}),
            ("org", "ref", {"label": "Organization", "to": "orgs"}),
            ("objective", "text", {"label": "Objective"}),
            ("next_action", "str", {"label": "Next action"}),
            ("next_action_date", "date", {"label": "Next action date"}),
            ("notes", "text", {"label": "Notes"}),
        ],
    },
    "songs": {
        "label": "Songs",
        "one": "Song",
        "fields": [
            ("name", "str", {"label": "Title", "required": True}),
            (
                "kind",
                "enum",
                {
                    "label": "Kind",
                    "options": ["Idea", "Original", "Cover", "almost", "stub"],
                },
            ),
            (
                "status",
                "enum",
                {
                    "label": "Status",
                    "options": [
                        "Idea",
                        "Writing",
                        "Demo",
                        "Arranging",
                        "Rehearsing",
                        "Recording",
                        "Ready",
                        "Released",
                    ],
                },
            ),
            ("project", "ref", {"label": "Project", "to": "projects"}),
            ("performance_ready", "bool", {"label": "Performance ready"}),
            ("links", "lines", {"label": "Links"}),
            ("references", "text", {"label": "References"}),
            ("folder", "str", {"label": "Folder (on the data drive)"}),
            ("notes", "text", {"label": "Notes"}),
        ],
    },
}
LINK_KINDS = {
    "org": "orgs",
    "project": "projects",
}  # what a person's links can point at

# ------------------------------------------------------------------ storage
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty() -> dict:
    return {"version": 1, **{c: [] for c in SCHEMA}}


def load() -> dict:
    data = json.loads(DB.read_text(encoding="utf-8")) if DB.exists() else empty()
    for c in SCHEMA:
        data.setdefault(c, [])
    return data


def save(data: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = DB.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)  # contacts: owner-only
    os.replace(tmp, DB)


def backup_once() -> str | None:
    if not DB.exists() or not BACKUP_NEEDS.is_dir() or not any(BACKUP_NEEDS.iterdir()):
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out = BACKUP_DIR / f"hq-{date.today()}.json"
    if not out.exists():
        with _lock:
            shutil.copyfile(DB, out)
        os.chmod(out, 0o600)
        for old in sorted(BACKUP_DIR.glob("hq-*.json"))[:-KEEP_BACKUPS]:
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
    """Invalid fields (-> 400 with the message)."""


def _clean(
    coll: str, body: dict, data: dict, partial: bool, self_id: str | None = None
) -> dict:
    out = {}
    for key, kind, opt in SCHEMA[coll]["fields"]:
        if key not in body:
            if not partial and opt.get("required"):
                raise Bad(f"{opt['label']} is required.")
            continue
        v = body[key]
        if kind == "str":
            v = " ".join(str(v or "").split())[:500]
            if opt.get("required") and not v:
                raise Bad(f"{opt['label']} is required.")
        elif kind == "text":
            v = str(v or "")[:50000]
        elif kind == "lines":
            if isinstance(v, str):
                v = v.splitlines()
            v = [" ".join(str(x).split())[:500] for x in (v or []) if str(x).strip()][
                :50
            ]
        elif kind == "enum":
            v = v or None
            if v is not None and v not in opt["options"]:
                raise Bad(f"{opt['label']}: unknown value {v!r}.")
        elif kind == "multi":
            v = [x for x in (v or []) if x in opt["options"]]
        elif kind == "bool":
            v = bool(v)
        elif kind == "date":
            v = v or None
            if v is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v)):
                raise Bad(f"{opt['label']} must be YYYY-MM-DD.")
        elif kind == "ref":
            v = v or None
            if v is not None and not any(x["id"] == v for x in data[opt["to"]]):
                raise Bad(f"{opt['label']}: not found.")
            if v is not None and opt["to"] == coll and self_id is not None:
                if v == self_id or v in _descendant_ids(data, coll, key, self_id):
                    raise Bad("A project can't go inside itself.")
        out[key] = v
    if coll == "people" and "links" in body:
        out["links"] = _clean_links(body["links"], data)
    return out


def _clean_links(links, data: dict) -> list[dict]:
    out, seen = [], set()
    for ln in links or []:
        kind, lid = ln.get("kind"), ln.get("id")
        if kind not in LINK_KINDS or not any(
            x["id"] == lid for x in data[LINK_KINDS[kind]]
        ):
            raise Bad("A link points at something that doesn't exist.")
        if (kind, lid) in seen:
            continue
        seen.add((kind, lid))
        out.append(
            {
                "kind": kind,
                "id": lid,
                "role": " ".join(str(ln.get("role") or "").split())[:120],
            }
        )
    return out


def _descendant_ids(data: dict, coll: str, key: str, rid: str) -> set[str]:
    out, todo = set(), [rid]
    while todo:
        cur = todo.pop()
        for x in data[coll]:
            if x.get(key) == cur and x["id"] not in out:
                out.add(x["id"])
                todo.append(x["id"])
    return out


def create(coll: str, body: dict) -> dict:
    with _lock:
        data = load()
        rec = {
            "id": secrets.token_hex(5),
            **_defaults(coll),
            **_clean(coll, body, data, partial=False),
        }
        rec["created"] = rec["updated"] = _now()
        data[coll].append(rec)
        save(data)
    return rec


def _defaults(coll: str) -> dict:
    d = {}
    for key, kind, _ in SCHEMA[coll]["fields"]:
        d[key] = (
            []
            if kind in ("lines", "multi")
            else (
                False if kind == "bool" else ("" if kind in ("str", "text") else None)
            )
        )
    if coll == "people":
        d["links"] = []
    return d


def update(coll: str, rid: str, body: dict) -> dict:
    with _lock:
        data = load()
        rec = next((x for x in data[coll] if x["id"] == rid), None)
        if rec is None:
            raise KeyError(rid)
        rec.update(_clean(coll, body, data, partial=True, self_id=rid))
        rec["updated"] = _now()
        save(data)
    return rec


def delete(coll: str, rid: str) -> None:
    """Delete one record and clear every reference to it (refs -> empty, person links removed,
    subprojects move up to the deleted project's parent)."""
    with _lock:
        data = load()
        rec = next((x for x in data[coll] if x["id"] == rid), None)
        if rec is None:
            raise KeyError(rid)
        data[coll] = [x for x in data[coll] if x["id"] != rid]
        for c, spec in SCHEMA.items():
            for key, kind, opt in spec["fields"]:
                if kind == "ref" and opt["to"] == coll:
                    for x in data[c]:
                        if x.get(key) == rid:
                            x[key] = (
                                rec.get("parent")
                                if (c == coll and key == "parent")
                                else None
                            )
        kind = next((k for k, v in LINK_KINDS.items() if v == coll), None)
        if kind:
            for p in data["people"]:
                p["links"] = [
                    ln
                    for ln in p.get("links", [])
                    if not (ln["kind"] == kind and ln["id"] == rid)
                ]
        save(data)


# --------------------------------------------------------------------- auth
# Always a login (no home-network bypass): contacts are private. Same credentials as the inbox.

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
    return xff.split(",")[-1].strip() if xff else "?"


def safe_next(form: dict, default: str) -> str:
    """Where to go after logging in: the app link the login page was opened at (same app only)."""
    nxt = (form.get("next") or [""])[0]
    return nxt if re.fullmatch(default + r"[A-Za-z0-9/?=&:_-]*", nxt) else default


def logged_in(headers) -> bool:
    return session.valid(headers)  # the shared login (common/session.py)


def too_many_fails(ip: str) -> bool:
    now = time.time()
    with _auth_lock:
        recent = [t for t in _fails.get(ip, []) if now - t < 300]
        _fails[ip] = recent
        return len(recent) >= 5


LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>HQ</title>
<meta name="robots" content="noindex"><meta name="color-scheme" content="dark">
<link rel="icon" href="/favicon.svg?v=5" type="image/svg+xml">
<style>
body{margin:0;background:#191919;color:#e9e9e7;font:15px/1.45 ui-sans-serif,-apple-system,Helvetica,Arial,sans-serif}
form{max-width:320px;margin:18vh auto 0;padding:22px;background:#202020;border:1px solid #2f2f2f;border-radius:12px;display:grid;gap:12px}
h1{font-size:20px;margin:0}input{font:inherit;padding:10px;border:1px solid #2f2f2f;border-radius:8px;background:#252525;color:inherit}
button{font:inherit;font-weight:600;color:#fff;background:#2383e2;border:0;border-radius:8px;padding:10px;cursor:pointer}
.msg{color:#e0645a;font-size:13px;min-height:1em}
</style></head><body>
<form method="post" action="/hq/login"><input type="hidden" name="next" id="next"><script>document.getElementById("next").value = location.pathname + location.search;</script>
  <h1>HQ</h1>
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
    server_version = "hq"

    def _send(
        self, code: int, body: bytes, ctype: str, extra: dict | None = None
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
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

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 500_000:
            raise Bad("Request too large.")
        try:
            obj = json.loads(self.rfile.read(n) if n else b"{}")
        except ValueError:
            raise Bad("Body must be JSON.") from None
        if not isinstance(obj, dict):
            raise Bad("Body must be a JSON object.")
        return obj

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/hq/health":
            return self._json(200, {"ok": True, "db": str(DB), "exists": DB.exists()})
        if path in ("/hq", "/hq/") or re.fullmatch(
            r"/hq(?:/[a-z]+)?", path
        ):  # app links, e.g. /hq/songs
            if not logged_in(self.headers):
                return self._send(200, login_page(), "text/html; charset=utf-8")
            return self._send(200, APP.encode(), "text/html; charset=utf-8")
        if path == "/hq/api/state":
            if not logged_in(self.headers):
                return self._json(401, {"error": "login"})
            with _lock:
                data = load()
            schema = {
                c: {
                    **{k: v for k, v in s.items() if k != "fields"},
                    "fields": [{"key": k, "type": t, **o} for k, t, o in s["fields"]],
                }
                for c, s in SCHEMA.items()
            }
            return self._json(200, {"schema": schema, **{c: data[c] for c in SCHEMA}})
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/hq/login":
            return self._login()
        if path == "/hq/logout":
            return self._send(
                303,
                b"",
                "text/plain",
                {"Location": "/hq/", "Set-Cookie": session.clear(self.headers)},
            )
        self._api("POST", path)

    def do_PATCH(self) -> None:  # noqa: N802
        self._api("PATCH", self.path.split("?", 1)[0])

    def do_DELETE(self) -> None:  # noqa: N802
        self._api("DELETE", self.path.split("?", 1)[0])

    def _api(self, method: str, path: str) -> None:
        if not logged_in(self.headers):
            return self._json(401, {"error": "login"})
        if self.headers.get("X-HQ") != "1":  # only the page's own script sends this
            return self._json(403, {"error": "missing X-HQ header"})
        m = re.fullmatch(r"/hq/api/([a-z]+)(?:/([0-9a-f]{10}))?", path)
        if not m or m[1] not in SCHEMA:
            return self._json(404, {"error": "not found"})
        coll, rid = m[1], m[2]
        try:
            if method == "POST" and rid is None:
                return self._json(201, create(coll, self._body()))
            if method == "PATCH" and rid:
                return self._json(200, update(coll, rid, self._body()))
            if method == "DELETE" and rid:
                delete(coll, rid)
                return self._json(200, {"ok": True})
        except Bad as e:
            return self._json(400, {"error": str(e)})
        except KeyError:
            return self._json(404, {"error": "not found"})
        self._json(404, {"error": "not found"})

    def _login(self) -> None:
        ip = visitor_ip(self.headers)
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
                303,
                b"",
                "text/plain",
                {"Location": safe_next(f, "/hq/"), "Set-Cookie": cookie},
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
    os.chmod(DIR, 0o700)
    threading.Thread(target=backup_worker, daemon=True).start()
    print(f"hq on http://{HOST}:{PORT}/hq/ -> {DB} (backups: {BACKUP_DIR})", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
