# HQ

Colin's private home base at **https://cesiumlab.net/hq/**: people, organizations, projects,
and songs (social media / creator work to come). Replaces the Notion "1984" + Music HQ pages.
Same dark Notion-like look as Tasks; standard-library Python, no database server.

- **People**: one record per person (name, area, relationship, organization text, role, where
  you know them from, location, phones, emails, socials, what they care about / what you can
  offer / might ask, current projects, plans, notes). Search + filters (area, relationship);
  **Table** or **Cards** (grouped by area, where you know them from, or relationship).
  Link a person to organizations and projects with a short role ("MONARCH: drummer").
- **Organizations**: bands, venues, promoters, labels, companies... Their page lists the linked
  people (with roles) and the projects that belong to them.
- **Projects**: nest without limit (subprojects); each can belong to an organization (the
  MONARCH project ↔ the MONARCH org). Their page lists subprojects, songs, and people.
- **Songs**: title, kind, status (Idea → Writing → Demo → Arranging → Rehearsing → Recording →
  Ready → Released), project, performance ready, links, references, a Folder field for its
  folder on the data drive (filled in by hand once the music layout is decided), notes.

Schema-driven: every collection is a field list in `SCHEMA` (`server.py`); the page draws its
tables and forms from it. A new collection (e.g. content / social accounts) is a new entry there
(plus its table columns and filters at the top of `app.html`).

## Access

**Login always**, even at home (contacts are private), with the inbox's username and password
(`INBOX_USERNAME` / `INBOX_PASSWORD_HASH` in `/etc/cesium/inbox.env`). Sessions end after 60 min
unused or with **Log out**. Writes need the page's own `X-HQ` header.

## Data, backup, restore

- **Live data**: `/srv/state/hq/hq.json` (internal drive), owner-only (`0600`, folder `0700`),
  written atomically.
- **Automatic backups**: once a day to `/srv/data/backups/hq/hq-YYYY-MM-DD.json` (last 30). The
  data drive is exFAT, which can't keep owner-only permissions, so those copies are readable by
  any local user on mr-ray (not from the network).
- **Restore**: `sudo systemctl stop hq`, copy a backup to `/srv/state/hq/hq.json`,
  `sudo systemctl start hq`.

## Importing from Notion (one time)

```bash
cd backend/services/hq
python3 import_notion.py <export>/People --dry-run
HQ_DIR=/srv/state/hq python3 import_notion.py <export>/People
```
Mapping in the script's docstring (unused fields, empty databases and Career HQ are left out).
The export folder is git-ignored; delete it once imported.

## Run / deploy

Unit `deploy/systemd/hq.service`, port `127.0.0.1:42907`, Apache route `/hq/`. Installed by
`scripts/deploy/backends.sh`. After code changes: `sudo systemctl restart hq`.

API: `GET /hq/api/state` (schema + all records) · `POST /hq/api/<collection>` ·
`PATCH|DELETE /hq/api/<collection>/<id>` with collections `people`, `orgs`, `projects`, `songs`.

Links: every tab and view has its own address, e.g. `/hq/songs?view=table`, `/hq/songs?view=status`,
`/hq/people?view=cards`, `/hq/orgs`, plus `&open=<id>` for an open record. Back/forward work.
