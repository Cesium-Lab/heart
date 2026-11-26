# hashcheck

A weekly SHA-256 check of every file on the data drive (`/srv/data`), to catch silent corruption
(bit rot, a failing USB drive) while there's still a good copy somewhere. No server, no port:
a systemd timer runs `hashcheck.py` every **Sunday at 02:00** (or at the next boot if mr-ray was
off then), at low CPU and disk priority.

## What it reports

Each run re-hashes everything and compares with last week's list:

| Result         | Meaning                                                              | Email? |
| -------------- | -------------------------------------------------------------------- | ------ |
| **CORRUPT**    | same size and modified time as last week, different contents         | yes    |
| **UNREADABLE** | read error: often the first sign of a dying drive                    | yes    |
| **MISSING**    | was there last week, gone now (a normal delete looks like this too)  | yes    |
| changed / new  | edited normally (modified time moved) or added                       | no     |

- The email goes to `INBOX_TO` using the inbox's Gmail settings (`/etc/cesium/inbox.env`);
  `HASHCHECK_TO` in `/etc/cesium/hashcheck.env` overrides the address. Without Gmail settings
  it only writes the report.
- A CORRUPT file keeps its last good hash, so it's reported every week until you deal with it:
  restore it from another copy, or, if the change is fine, `touch` it (a new modified time makes
  it a normal change).
- If the drive is missing or empty, or more than 20% of known files vanish at once
  (`HASHCHECK_MASS_MISSING`), it emails and **keeps the old list** instead of recording
  everything as deleted.
- Skipped: macOS/Windows clutter (`.DS_Store`, `._*`, `.Spotlight-V100`, `.Trashes`, …) and the
  inbox's in-progress uploads.

## Progress and interruptions

- **While it runs:** `./scripts/status.sh` shows `hashcheck  running  30%, 112.4 / 371.0 GB,
  ~45 min left` (updated every 30 s), and the journal gets the same line every 5 min
  (`journalctl -u hashcheck -f`). The total comes from last run's list, so the first run shows
  GB so far only. Between runs, status.sh shows the last result (`all good` or `N PROBLEM(S)`).
- **If it stops partway** (reboot, power cut, drive unplugged, `systemctl stop`), it has saved
  what it hashed so far every 5 min (`progress.tsv`). The next run reuses those hashes for files
  whose size and modified time haven't changed, and hashes the rest; a checkpoint older than
  8 days is ignored. The real list is still only replaced when a run finishes, so an
  interruption never damages it. Because `Persistent=true`, a run missed while mr-ray was off
  happens at the next boot; to finish an interrupted one sooner, `sudo systemctl start hashcheck`.

## Files

- `/srv/state/hashcheck/manifest.tsv`: the list (hash, size, modified time, path), on the
  internal NVMe so it isn't on the drive being checked.
- `/srv/state/hashcheck/report-YYYY-MM-DD.txt`: each run's full report (last 12 kept).
- `/srv/state/hashcheck/progress.tsv`: an unfinished run's checkpoint (deleted when a run ends).
- `/srv/state/hashcheck/status.txt`: one line for status.sh (progress, or the last result).
- The first run builds the baseline (~371 GB over USB: expect an hour or more).

## Run it

```bash
sudo systemctl start hashcheck          # a full check now (takes a while)
journalctl -u hashcheck -n 50 --no-pager # progress every 5 min, then the summary
systemctl list-timers hashcheck          # when it runs next
python3 hashcheck.py --dry-run           # check and print only: no list saved, no email
```

`./scripts/status.sh` shows `hashcheck` as **FAILED** after a run that found CORRUPT or
UNREADABLE files (or couldn't check), and `stopped` otherwise (normal between runs).

Installed by `./scripts/deploy/backends.sh` (enables `hashcheck.timer`; the service itself only
runs from the timer). Standard library only, runs on the system `python3`.
