#!/usr/bin/env python3
"""One-time import of the Notion "People" export (1984 + Music HQ) into hq.json.

    python3 import_notion.py <export>/People --dry-run    # summary only, writes nothing
    python3 import_notion.py <export>/People              # write HQ_DIR/hq.json
    python3 import_notion.py <export>/People --replace    # overwrite an existing hq.json

Mapping (decided 2026-11-27):
- 1984 -> people: core fields, contact info (phones / emails / socials, one per line), and the
  networking fields. Dropped: hashes, Source ID, vCard order/UID, identifier history, last
  checked, next follow-up, talked, last talked, and the empty Music Organizations/Projects
  relations. The free-text Organization stays text (org_text); links are made by hand later.
- Music HQ Organizations -> orgs; Projects -> projects (a project and an org with the same name,
  e.g. MONARCH, are linked); Songs -> songs, linked to their project by name.
- Events, Interactions, Opportunities (empty) and Career HQ are not imported.
"""

from __future__ import annotations

import csv
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from server import SCHEMA, empty  # noqa: E402

MONTHS = {
    m: i
    for i, m in enumerate(
        "January February March April May June July August September October November December".split(),
        1,
    )
}


def table(root: Path, prefix: str) -> list[dict]:
    hits = sorted(root.glob(f"{prefix} *_all.csv")) or sorted(
        root.glob(f"{prefix} *.csv")
    )
    if not hits:
        return []
    with open(hits[0], encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def split(v: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,;\n]+", v or "") if x.strip()]


def date_of(v: str) -> str | None:
    v = (v or "").strip()
    if m := re.match(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", v):
        return f"{m[3]}-{MONTHS[m[1]]:02d}-{int(m[2]):02d}" if m[1] in MONTHS else None
    if m := re.match(r"(\d{2})/(\d{2})/(\d{4})", v):
        return f"{m[3]}-{m[1]}-{m[2]}"
    return None


def pick(value: str, coll: str, key: str) -> str | None:
    """First comma-separated value that's a valid option for an enum field."""
    opts = next(o for k, _, o in SCHEMA[coll]["fields"] if k == key)["options"]
    for v in split(value):
        if v in opts:
            return v
    return None


def rel_name(v: str) -> str:
    return re.sub(r"\s*\([^()]*\.(md|csv)\)\s*$", "", v or "").strip()


def build(root: Path) -> tuple[dict, dict]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data = empty()
    new = lambda: {"id": secrets.token_hex(5), "created": now, "updated": now}  # noqa: E731
    mh = root / "Music HQ"

    for r in table(mh, "Organizations"):
        data["orgs"].append(
            {
                **new(),
                "name": r["Name"].strip(),
                "type": pick(r.get("Type", ""), "orgs", "type"),
                "location": r.get("Location", "").strip(),
                "website": r.get("Website", "").strip(),
                "socials": split(r.get("Socials", "")),
                "context": r.get("Connection / context", "").strip(),
                "notes": r.get("Notes", "").strip(),
            }
        )
    org_by_name = {o["name"].lower(): o["id"] for o in data["orgs"]}

    for r in table(mh, "Projects"):
        name = r["Name"].strip()
        data["projects"].append(
            {
                **new(),
                "name": name,
                "type": pick(r.get("Type", ""), "projects", "type"),
                "status": pick(r.get("Status", ""), "projects", "status"),
                "parent": None,
                "org": org_by_name.get(name.lower()),
                "objective": r.get("Objective", "").strip(),
                "next_action": r.get("Next action", "").strip(),
                "next_action_date": date_of(r.get("Next action date", "")),
                "notes": r.get("Notes", "").strip(),
            }
        )
    proj_by_name = {p["name"].lower(): p["id"] for p in data["projects"]}

    unknown_projects = set()
    for r in table(mh, "Songs"):
        title = r.get("Title", "").strip()
        if not title:
            continue
        pname = rel_name(r.get("Project", ""))
        pid = proj_by_name.get(pname.lower()) if pname else None
        if pname and not pid:
            unknown_projects.add(pname)
        data["songs"].append(
            {
                **new(),
                "name": title,
                "kind": pick(r.get("Kind", ""), "songs", "kind"),
                "status": pick(r.get("Status", ""), "songs", "status"),
                "project": pid,
                "performance_ready": r.get("Performance ready", "").strip() == "Yes",
                "links": split(r.get("Links", "")),
                "references": r.get("References", "").strip(),
                "folder": "",
                "notes": r.get("Notes", "").strip(),
            }
        )

    bodies = {}  # the few person pages with text beyond their properties
    for md in (root / "1984").glob("*.md"):
        lines = md.read_text(encoding="utf-8").splitlines()
        body = [
            ln
            for ln in lines[1:]
            if ln.strip() and not re.match(r"^[A-Za-z][A-Za-z /?()-]*: ", ln)
        ]
        if body:
            bodies[lines[0][2:].strip()] = "\n".join(body)
    for r in table(root, "1984"):
        name = r["Name"].strip()
        if not name:
            continue
        notes = r.get("notes", "").strip()
        if name in bodies:
            notes = (notes + "\n\n" + bodies[name]).strip()
        data["people"].append(
            {
                **new(),
                "name": name,
                "areas": [
                    a
                    for a in split(r.get("Area", ""))
                    if a in ("Music", "Aerospace", "Personal", "Other")
                ],
                "strength": pick(
                    r.get("Relationship strength", ""), "people", "strength"
                ),
                "org_text": r.get("Organization", "").strip(),
                "role": r.get("Role", "").strip(),
                "known_from": r.get("Where I know them from", "").strip(),
                "location": r.get("Location", "").strip(),
                "phones": split(r.get("Phone", "")),
                "emails": split(r.get("Email", "")),
                "socials": split(r.get("Social links", "")),
                "cares": r.get("What they care about", "").strip(),
                "offer": r.get("What I can offer", "").strip(),
                "ask": r.get("What I might ask for", "").strip(),
                "current": r.get("Current projects / opportunities", "").strip(),
                "plans": r.get("plans", "").strip(),
                "notes": notes,
                "links": [],
            }
        )

    stats = {c: len(data[c]) for c in SCHEMA}
    stats["songs with a project"] = sum(1 for s in data["songs"] if s["project"])
    stats["projects linked to an org"] = sum(1 for p in data["projects"] if p["org"])
    stats["people with phone / email"] = (
        f"{sum(1 for p in data['people'] if p['phones'])} / {sum(1 for p in data['people'] if p['emails'])}"
    )
    if unknown_projects:
        stats["song projects not found"] = ", ".join(sorted(unknown_projects))
    return data, stats


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    data, stats = build(Path(args[0]))
    for k, v in stats.items():
        print(f"{k:>26}: {v}")
    if "--dry-run" in sys.argv:
        return
    out = Path(os.getenv("HQ_DIR", "/srv/state/hq")) / "hq.json"
    if out.exists() and "--replace" not in sys.argv:
        sys.exit(
            f"{out} already exists; add --replace to overwrite it (back it up first)."
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
