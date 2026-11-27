#!/usr/bin/env python3
"""Import a Notion "Tasks Tracker" export (Markdown + CSV) into tasks.json.

    python3 import_notion.py <export folder> --dry-run      # summary only, writes nothing
    python3 import_notion.py <export folder>                # write TASKS_DIR/tasks.json
    python3 import_notion.py <export folder> --replace      # overwrite an existing tasks.json

Mapping (decided 2026-11-26):
- Groups = Notion Category (School, Music, Personal, Chores, Nerd, ...). A task lives in its top
  ancestor's group (children follow the parent); top-level tasks with no category: Unsorted.
- Nesting kept as is (unlimited), matched by Notion page id, not title (titles repeat).
- Containers (course/project headers): every top-level item that has children, plus these
  nested ones: Cesium Heart/Brains/Body/Nerves/GNC, Sun sensor Project, PROJECT, Room, Bathroom.
- Status: Cancelled -> cancelled; Done -> done; In progress, or Working = Yes -> doing (the
  Working checkbox counts as In progress); otherwise todo. Priority: High/Medium/Low.
- Due date: "Due date", else "Date"; time and zone dropped. "Late submission deadline" goes
  into the notes. Notes = the page body. Task type: dropped. The journal tree: not imported.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

NESTED_CONTAINERS = {
    "Cesium Heart",
    "Cesium Brains",
    "Cesium Body",
    "Cesium Nerves",
    "Cesium GNC",
    "Sun sensor Project",
    "PROJECT",
    "Room",
    "Bathroom",
}
DROP_TREES = {"journal"}  # top-level items whose whole tree is not imported
PROP_RE = re.compile(r"^([A-Za-z][A-Za-z -]*): (.*)$")
ID_RE = re.compile(r"([0-9a-f]{32})\.md$")
MONTHS = {
    m: i
    for i, m in enumerate(
        "January February March April May June July August September October November December".split(),
        1,
    )
}


def parse_date(s: str) -> str | None:
    s = s.strip()
    if m := re.match(r"(\d{2})/(\d{2})/(\d{4})", s):  # 10/27/2026 13:30 (PDT)
        return f"{m[3]}-{m[1]}-{m[2]}"
    if m := re.match(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", s):  # June 12, 2026
        if m[1] in MONTHS:
            return f"{m[3]}-{MONTHS[m[1]]:02d}-{int(m[2]):02d}"
    return None


def read_page(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    title = lines[0][2:].strip() if lines and lines[0].startswith("# ") else path.stem
    props, i = {}, 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines) and (m := PROP_RE.match(lines[i])):
        props[m[1]] = m[2].strip()
        i += 1
    body = "\n".join(lines[i:]).strip()
    parent = None
    if pl := props.get("Parent item"):
        if m := re.search(r"([0-9a-f]{32})\.md\)", unquote(pl)):
            parent = m[1]
    return {
        "id": ID_RE.search(path.name)[1],
        "title": title,
        "props": props,
        "body": body,
        "parent": parent,
    }


def build(export: Path) -> tuple[dict, dict]:
    pages = {p["id"]: p for p in map(read_page, sorted(export.rglob("*.md"))) if p}
    kids: dict[str, list[str]] = {}
    for p in pages.values():
        if p["parent"] in pages:
            kids.setdefault(p["parent"], []).append(p["id"])

    def root(pid: str) -> str:
        seen = set()
        while pages[pid]["parent"] in pages and pid not in seen:
            seen.add(pid)
            pid = pages[pid]["parent"]
        return pid

    dropped = {pid for pid in pages if pages[root(pid)]["title"] in DROP_TREES}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    groups: dict[str, dict] = {}
    tasks = []
    new_id = {pid: secrets.token_hex(5) for pid in pages}
    for pid, p in pages.items():
        if pid in dropped:
            continue
        pr = p["props"]
        top = pages[root(pid)]
        cat = (top["props"].get("Category") or "").strip()
        gid = None
        if cat:
            g = groups.setdefault(
                cat, {"id": secrets.token_hex(4), "name": cat, "archived": False}
            )
            gid = g["id"]
        is_top = p["parent"] not in pages
        container = (is_top and pid in kids) or p["title"] in NESTED_CONTAINERS
        st = pr.get("Status", "")
        if st == "Cancelled":
            status = "cancelled"
        elif pr.get("Done") == "Yes" or st == "Done":
            status = "done"
        elif st == "In progress" or pr.get("Working") == "Yes":
            status = "doing"
        else:
            status = "todo"
        notes = []
        if pr.get("Late submission deadline"):
            notes.append(f"Late submission deadline: {pr['Late submission deadline']}")
        if p["body"]:
            notes.append(p["body"])
        tasks.append(
            {
                "id": new_id[pid],
                "title": p["title"][:300],
                "group": gid,
                "parent": new_id[p["parent"]]
                if p["parent"] in pages and p["parent"] not in dropped
                else None,
                "container": bool(container),
                "archived": False,
                "due": parse_date(pr.get("Due date", ""))
                or parse_date(pr.get("Date", "")),
                "priority": {"High": "high", "Medium": "medium", "Low": "low"}.get(
                    pr.get("Priority", ""), "normal"
                ),
                "status": status,
                "notes": "\n\n".join(notes)[:20000],
                "created": now,
                "updated": now,
                "completed": now if status == "done" else None,
                "notion_id": pid,
            }
        )
    order = [
        "School",
        "Music",
        "Nerd",
        "Personal",
        "Chores",
        "Professional",
        "Financial",
        "People",
        "Health",
    ]
    gl = sorted(
        groups.values(),
        key=lambda g: (order.index(g["name"]) if g["name"] in order else 99, g["name"]),
    )
    stats = {
        "pages": len(pages),
        "dropped (journal)": len(dropped),
        "imported": len(tasks),
        "containers": sum(t["container"] for t in tasks),
        "open": sum(
            t["status"] in ("todo", "doing") and not t["container"] for t in tasks
        ),
        "cancelled": sum(t["status"] == "cancelled" for t in tasks),
        "done": sum(t["status"] == "done" and not t["container"] for t in tasks),
        "unsorted top-level": sum(
            1 for t in tasks if t["group"] is None and t["parent"] is None
        ),
    }
    return {"version": 1, "groups": gl, "tasks": tasks}, stats


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    data, stats = build(Path(args[0]))
    for k, v in stats.items():
        print(f"{k:>20}: {v}")
    for g in data["groups"]:
        ts = [t for t in data["tasks"] if t["group"] == g["id"]]
        print(
            f"  {g['name']:<14} {len(ts):3} tasks, containers: "
            + ", ".join(
                t["title"] for t in ts if t["container"] and t["parent"] is None
            )
        )
    if "--dry-run" in sys.argv:
        return
    out = Path(os.getenv("TASKS_DIR", "/srv/state/tasks")) / "tasks.json"
    if out.exists() and "--replace" not in sys.argv:
        sys.exit(
            f"{out} already exists; add --replace to overwrite it (back it up first)."
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
