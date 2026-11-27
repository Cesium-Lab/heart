"""One login for Inbox, Notes, Status, Tasks and HQ.

A stateless signed cookie `cl_s` (Path=/), so a login in one app works in the others and
survives service restarts. Token = "<issued epoch>.<hmac>", keyed from INBOX_PASSWORD_HASH, so
changing the password logs everyone out. Valid until IDLE_S unused: every authenticated
response re-issues it (at most once a minute), so the hour slides while you use it.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time

NAME = "cl_s"
IDLE_S = 3600
_RE = re.compile(r"(?:^|;\s*)cl_s=(\d+)\.([0-9a-f]{64})")


def _key() -> bytes:
    return hashlib.sha256(
        b"cesiumlab-session:" + os.getenv("INBOX_PASSWORD_HASH", "").encode()
    ).digest()


def _sig(ts: str) -> str:
    return hmac.new(_key(), ts.encode(), hashlib.sha256).hexdigest()


def age(headers) -> float | None:
    """Seconds since the cookie was (re)issued, or None if missing/invalid/expired."""
    if not os.getenv("INBOX_PASSWORD_HASH"):
        return None
    m = _RE.search(headers.get("Cookie", ""))
    if not m or not hmac.compare_digest(_sig(m[1]), m[2]):
        return None
    a = time.time() - int(m[1])
    return a if -60 < a < IDLE_S else None


def valid(headers) -> bool:
    return age(headers) is not None


def _attrs(headers) -> str:
    secure = "; Secure" if headers.get("X-Forwarded-Proto") == "https" else ""
    return f"Path=/; HttpOnly; SameSite=Strict{secure}"


def issue(headers) -> str:
    """Set-Cookie value for a fresh login."""
    ts = str(int(time.time()))
    return f"{NAME}={ts}.{_sig(ts)}; Max-Age={IDLE_S}; {_attrs(headers)}"


def refresh(headers) -> str | None:
    """Set-Cookie value to slide the hour, if the request is logged in and the cookie is >60 s old."""
    a = age(headers)
    return issue(headers) if a is not None and a > 60 else None


def clear(headers) -> str:
    return f"{NAME}=; Max-Age=0; {_attrs(headers)}"
