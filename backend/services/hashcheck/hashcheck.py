#!/usr/bin/env python3
"""hashcheck: weekly SHA-256 check of every file on the data drive, to catch silent corruption
(bit rot, a failing USB drive) before the only copy of something is gone.

Each run re-hashes every file under HASHCHECK_DATA_DIR and compares with the last run's list
(kept on the internal drive, HASHCHECK_STATE_DIR/manifest.tsv):

  - CORRUPT:     same size and modified time as last time, but different contents. Nothing
                 should change a file without touching its modified time, so this is the alarm.
  - UNREADABLE:  the file couldn't be read (I/O error): often the first sign of a dying drive.
  - MISSING:     was there last time, gone now (could be a normal delete; listed so you can tell).
  - changed/new: modified normally, or added. Counted, not alarmed.

Emails only when something is CORRUPT, UNREADABLE, or MISSING (Gmail settings shared with the
inbox: INBOX_SMTP_USER / INBOX_SMTP_PASS / INBOX_TO). Every run also writes a report file in
the state dir. If a large share of files is suddenly missing (drive not mounted properly), it
emails and keeps the old list instead of replacing it.

    python3 hashcheck.py            # run a check (what the weekly timer does)
    python3 hashcheck.py --dry-run  # check and print, but don't save the list or email

Standard library only.
"""

from __future__ import annotations

import hashlib
import os
import smtplib
import ssl
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

DATA = Path(os.getenv("HASHCHECK_DATA_DIR", "/srv/data"))
STATE = Path(os.getenv("HASHCHECK_STATE_DIR", "/srv/state/hashcheck"))
SMTP_HOST = os.getenv("INBOX_SMTP_HOST", "smtp.gmail.com")
SMTP_USER = os.getenv("INBOX_SMTP_USER", "")
SMTP_PASS = os.getenv("INBOX_SMTP_PASS", "")
MAIL_TO = os.getenv("HASHCHECK_TO") or os.getenv("INBOX_TO") or SMTP_USER
# Refuse to replace the list when more than this share of known files vanished at once.
MASS_MISSING = float(os.getenv("HASHCHECK_MASS_MISSING", "0.2"))
KEEP_REPORTS = 12
# How often an unfinished run saves its progress (and logs a line), in seconds.
CHECKPOINT_SECS = int(os.getenv("HASHCHECK_CHECKPOINT_SECS", "300"))

# macOS / system clutter that comes and goes on its own; skipping it keeps MISSING meaningful.
SKIP_DIRS = {
    ".Spotlight-V100",
    ".fseventsd",
    ".Trashes",
    ".TemporaryItems",
    ".DocumentRevisions-V100",
    "$RECYCLE.BIN",
    "System Volume Information",
    ".uploading",  # the inbox's in-progress uploads
}
SKIP_FILES = {".DS_Store", "Thumbs.db"}
# Folders (relative to the data dir) whose files rotate on purpose, e.g. the tasks service's
# daily backups: old copies get deleted, which would otherwise be reported as MISSING.
SKIP_PATHS = {
    p.strip().strip("/")
    for p in os.getenv("HASHCHECK_SKIP_PATHS", "backups/tasks").split(",")
    if p.strip()
}


def log(msg: str) -> None:
    print(msg, flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def walk(root: Path):
    """Every regular file under root (relative path string, Path), skipping clutter."""
    for dirpath, dirnames, filenames in os.walk(root):
        here = os.path.relpath(dirpath, root)
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in SKIP_DIRS
            and os.path.normpath(os.path.join(here, d)) not in SKIP_PATHS
        )
        for name in sorted(filenames):
            if name in SKIP_FILES or name.startswith("._"):
                continue
            p = Path(dirpath) / name
            if p.is_symlink() or not p.is_file():
                continue
            yield str(p.relative_to(root)), p


def load_manifest(path: Path) -> dict[str, tuple[str, int, int]]:
    """path -> (sha256, size, mtime_ns). One file per line: sha, size, mtime_ns, path (tabs)."""
    out: dict[str, tuple[str, int, int]] = {}
    if path.exists():
        for line in path.read_text(
            encoding="utf-8", errors="surrogateescape"
        ).splitlines():
            parts = line.split("\t", 3)
            if len(parts) == 4:
                out[parts[3]] = (parts[0], int(parts[1]), int(parts[2]))
    return out


def save_manifest(path: Path, rows: dict[str, tuple[str, int, int]]) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", errors="surrogateescape") as f:
        for rel in sorted(rows):
            sha, size, mtime = rows[rel]
            f.write(f"{sha}\t{size}\t{mtime}\t{rel}\n")
    os.replace(tmp, path)  # all or nothing: a crash mid-write keeps the old list


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def check(dry_run: bool = False) -> int:
    if not DATA.is_dir() or not any(DATA.iterdir()):
        return alarm_only(
            f"{DATA} is missing or empty (drive not mounted?). Nothing checked."
        )
    STATE.mkdir(parents=True, exist_ok=True)
    old = load_manifest(STATE / "manifest.tsv")
    # Resume: hashes an interrupted run already computed (reused only if the file's size and
    # modified time still match, and the checkpoint is from the last 8 days).
    ckpt = STATE / "progress.tsv"
    done = {}
    if ckpt.exists() and time.time() - ckpt.stat().st_mtime < 8 * 86400:
        done = load_manifest(ckpt)
        log(f"resuming: {len(done)} files already hashed by the interrupted run")
    expected = sum(v[1] for v in old.values())  # last run's total, for a percentage
    new: dict[str, tuple[str, int, int]] = {}
    seen: dict[
        str, tuple[str, int, int]
    ] = {}  # what this run actually found (checkpointed)
    corrupt, unreadable, odd_names = [], [], []
    changed = added = total_bytes = fresh_bytes = 0
    start = time.monotonic()
    last_log = last_status = start

    def tick(final: bool = False) -> None:
        """Status line for status.sh every 30 s; journal line + checkpoint every 5 min."""
        nonlocal last_log, last_status
        now = time.monotonic()
        if dry_run or (now - last_status < min(30, CHECKPOINT_SECS) and not final):
            return
        last_status = now
        line = f"{total_bytes / 1e9:.1f} GB, {len(seen)} files"
        if expected:
            pct = min(99, int(100 * total_bytes / expected))
            line = f"{pct}%, {total_bytes / 1e9:.1f} / {expected / 1e9:.1f} GB"
            rate = fresh_bytes / max(now - start, 1)  # bytes/s actually read this run
            if rate > 0 and expected > total_bytes:
                line += f", ~{(expected - total_bytes) / rate / 60:.0f} min left"
        write_atomic(STATE / "status.txt", line + "\n")
        if now - last_log >= CHECKPOINT_SECS:
            last_log = now
            log("... " + line)
            save_manifest(ckpt, seen)

    for rel, p in walk(DATA):
        if "\n" in rel or "\t" in rel:
            odd_names.append(rel)  # can't be stored one-per-line; listed in the report
            continue
        try:
            st = p.stat()
            hit = done.get(rel)
            if hit and hit[1:] == (st.st_size, st.st_mtime_ns):
                digest = hit[0]  # hashed before the interruption, unchanged since
            else:
                digest = sha256(p)
                fresh_bytes += st.st_size
        except OSError as e:
            unreadable.append(f"{rel}  ({e.strerror or e})")
            if rel in old:
                new[rel] = old[rel]  # keep its last good hash for next time
            continue
        seen[rel] = new[rel] = (digest, st.st_size, st.st_mtime_ns)
        total_bytes += st.st_size
        prev = old.get(rel)
        if prev is None:
            added += 1
        elif prev[1:] == (st.st_size, st.st_mtime_ns) and prev[0] != digest:
            corrupt.append(rel)
            new[rel] = prev  # keep the good hash: it alarms every week until dealt with
        elif prev[0] != digest:
            changed += 1
        tick()

    missing = sorted(set(old) - set(new))
    mins = (time.monotonic() - start) / 60
    mass = old and len(missing) > max(100, MASS_MISSING * len(old))
    summary = [
        f"hashcheck {datetime.now():%Y-%m-%d %H:%M} on {DATA}",
        f"{len(new)} files, {total_bytes / 1e9:.1f} GB, {mins:.0f} min",
        f"new {added} · changed normally {changed} · missing {len(missing)} · "
        f"CORRUPT {len(corrupt)} · UNREADABLE {len(unreadable)}",
    ]
    if not old:
        summary.append(
            "First run: this is the baseline list; problems show from next week on."
        )
    if mass:
        summary.append(
            f"{len(missing)} of {len(old)} known files are missing at once: kept the old list "
            "(not replaced). Check the drive is mounted and intact."
        )
    sections = [
        ("CORRUPT (same size and time, different contents)", corrupt),
        ("UNREADABLE (read errors)", unreadable),
        ("MISSING since last run", missing),
        ("Skipped (tab or newline in the name)", odd_names),
    ]
    report = "\n".join(summary) + "\n"
    for title, items in sections:
        if items:
            report += (
                f"\n{title}: {len(items)}\n" + "\n".join(f"  {x}" for x in items) + "\n"
            )
    log(report)
    if dry_run:
        return 1 if (corrupt or unreadable) else 0

    if not mass:
        save_manifest(STATE / "manifest.tsv", new)
    # Finished: no resume next time; status.sh shows the last result instead of a percentage.
    ckpt.unlink(missing_ok=True)
    problems = len(corrupt) + len(unreadable)
    write_atomic(
        STATE / "status.txt",
        f"last run {datetime.now():%a %b %-d %H:%M}: {len(new)} files, "
        + (f"{problems} PROBLEM(S)" if problems else "all good")
        + (f", {len(missing)} missing" if missing else "")
        + "\n",
    )
    out = STATE / f"report-{datetime.now():%Y-%m-%d}.txt"
    out.write_text(report, encoding="utf-8", errors="surrogateescape")
    for old_report in sorted(STATE.glob("report-*.txt"))[:-KEEP_REPORTS]:
        old_report.unlink()
    if corrupt or unreadable or missing:
        # Keep the email readable: the first 200 lines per section; the full list is on disk.
        body = "\n".join(summary) + "\n"
        for title, items in sections:
            if items:
                body += f"\n{title}: {len(items)}\n" + "\n".join(
                    f"  {x}" for x in items[:200]
                )
                body += (
                    f"\n  … and {len(items) - 200} more\n" if len(items) > 200 else "\n"
                )
        body += f"\nFull report on mr-ray: {out}\n"
        bad = "CORRUPT/UNREADABLE files" if (corrupt or unreadable) else "files missing"
        send(f"hashcheck: {bad} on {DATA}", body)
    return 1 if (corrupt or unreadable or mass) else 0


def alarm_only(text: str) -> int:
    log(text)
    send(f"hashcheck: couldn't check {DATA}", text)
    return 1


def send(subject: str, body: str) -> None:
    if not (SMTP_USER and SMTP_PASS and MAIL_TO):
        log("(no Gmail settings: not emailed; see the report file)")
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, SMTP_USER, MAIL_TO
    msg.set_content(body)
    with smtplib.SMTP_SSL(
        SMTP_HOST, 465, context=ssl.create_default_context(), timeout=30
    ) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    log(f"emailed {MAIL_TO}")


if __name__ == "__main__":
    sys.exit(check(dry_run="--dry-run" in sys.argv[1:]))
