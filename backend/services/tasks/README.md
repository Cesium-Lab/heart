# Tasks

A personal task tracker at **https://cesiumlab.net/tasks/** (replaces the Notion task list).
Laptop and phone friendly; standard-library Python, no database server.

- **Two tabs, one filter**: **Board** (a column per category, cards tinted in its color; drag a
  card to another column to change its category, phone: press and hold; "+ New task" per
  column; containers list their children as chips) and **Table** (click Status / Priority pills,
  the date, or the box to edit in place; click a column header to sort). Both share the status
  checkboxes above them, remembered on the device: **Focus** = tick In progress, **Undone** =
  Not started + In progress, **Full** = all four. **Pinned tabs** (any category or container,
  "Pin as tab" on its page; saved on the server) use the same checkboxes.
- **Groups** = categories (School, Music, Nerd, ...), each with a color (defaults match Notion's;
  manage them with the **Categories** button: create, rename, color, pin as a tab, archive, delete).
- **Containers** = courses and projects (AA 274A, Cesium, Gig Tracker): progress instead of a
  checkbox; on the board their children show as chips. Archive one when the quarter ends.
- **Tasks**: title (only required field), status (Not started / In progress / Done / Cancelled),
  due date (red when overdue, amber within 3 days), priority (Low / Medium / High), notes in
  light **Markdown** (bullets, `- [ ]` checklists you can tick on the page, links, headings,
  bold, code; click the notes to edit the text). Nesting is unlimited.
- **New**: the New button adds a task with just a title; set its category or parent later.
- Always dark, Notion-style.

## Access

Same rule and login as the inbox: no password at home or on Tailscale; from anywhere else, the
inbox username and password (`INBOX_USERNAME` / `INBOX_PASSWORD_HASH` in
`/etc/cesium/inbox.env`, which the unit loads). Writes need the page's own `X-Tasks` header, so
other sites can't post into it.

## Data, backup, restore

- **Live data**: `/srv/state/tasks/tasks.json` (internal drive), one JSON file, written atomically
  (temp file + rename), so a crash never leaves it half-written.
- **Automatic backups**: once a day the service copies it to
  `/srv/data/backups/tasks/tasks-YYYY-MM-DD.json` on the data drive (last 30 kept). Skipped while
  the data drive isn't mounted.
- **Manual backup** (any time):
  ```bash
  cp /srv/state/tasks/tasks.json ~/tasks-$(date +%F).json
  ```
- **Restore**:
  ```bash
  sudo systemctl stop tasks
  cp /srv/data/backups/tasks/tasks-2026-11-26.json /srv/state/tasks/tasks.json
  sudo systemctl start tasks
  ```
  The file is plain JSON (`groups` + `tasks`), so it can also be read or fixed by hand.

## Run / deploy

- Unit `deploy/systemd/tasks.service`, port `127.0.0.1:42906`, Apache route `/tasks/`
  (`deploy/apache/includes/api-proxies.conf`). Installed by `scripts/deploy/backends.sh`.
- After code changes: `sudo systemctl restart tasks`. Logs: `journalctl -u tasks -n 50`.
- Dev run: `TASKS_DIR=/tmp/tasks TASKS_PORT=42977 python3 server.py`, then send
  `X-Forwarded-For: 192.168.0.5` to act as the home network.

## Importing from Notion

`import_notion.py` reads a Notion "Tasks Tracker" export (the folder with `Tasks Tracker/*.md`):
Category → group, parent links (by Notion page id) → nesting, top items with children (plus the
Cesium subprojects, Room, Bathroom...) → containers, Done/Cancelled → done (cancelled noted),
In progress/Working → doing; the journal tree and Task type are left out. See the docstring.

```bash
cd backend/services/tasks
python3 import_notion.py <export folder> --dry-run          # summary only
sudo systemctl stop tasks
TASKS_DIR=/srv/state/tasks python3 import_notion.py <export folder>   # --replace to overwrite
sudo systemctl start tasks
```
Export folders are git-ignored (`*_ExportBlock-*/`); delete them once imported.

## API (what the page uses)

`GET /tasks/api/state` · `POST /tasks/api/groups` `{name}` · `PATCH|DELETE /tasks/api/groups/<id>`
· `POST /tasks/api/tasks` `{title, group?, parent?, container?, due?, priority?, status?, notes?}` ·
`PATCH|DELETE /tasks/api/tasks/<id>`. JSON in and out; writes need `X-Tasks: 1`.

Links: `/tasks/board`, `/tasks/table`, `/tasks/categories`, pinned tabs `/tasks/g/<id>` and
`/tasks/t/<id>`, plus `?open=<task id>` for an open task. Back/forward work.
