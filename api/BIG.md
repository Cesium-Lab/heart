# Cesium Lab Web Platform Architecture Plan

## Goal

Evolve Cesium Lab into a personal web platform with:

- a lightweight web frontend
- a private contacts/people database
- music-network data
- projects and other structured personal data
- a reusable API for scripts, tools, and future AI agents
- secure remote access
- a clean separation between frontend, backend, and persistent data

Breaking the current Apache-based implementation during the migration is acceptable. The priority is a clean final architecture rather than preserving the existing server throughout the transition.

---

## 1. Final Architecture

The target stack is:

- **Astro** — frontend
- **FastAPI** — backend/API
- **PostgreSQL** — relational database
- **Cloudflare Pages** — production frontend hosting
- **Cloudflare Tunnel** — secure route to the backend on the home server
- **Cloudflare Access** — authentication for private services

```text
                         INTERNET
                            │
                            ▼
                       Cloudflare
                      /          \
                     /            \
                    ▼              ▼
             Frontend             API
          Cloudflare Pages   Cloudflare Access
                 │                 │
                 │                 ▼
                 │          Cloudflare Tunnel
                 │                 │
                 │                 ▼
                 │          FastAPI :8000
                 │                 │
                 │                 ▼
                 │         PostgreSQL :5432
                 │
                 └──── HTTP API requests ────┘
```

Apache is not required in the final architecture.

---

## 2. Responsibilities

Each component should have one clear job.

### Astro

Astro is responsible for what the user sees:

- pages
- layouts
- navigation
- dashboards
- contact views
- project views
- static content
- interactive frontend components

### FastAPI

FastAPI is responsible for what the application does:

- API routes
- authentication/authorization checks where needed
- validation
- database access
- business logic
- search
- imports
- integrations
- future agent/tool interfaces

### PostgreSQL

PostgreSQL is responsible for what the application knows:

- people
- organizations
- relationships
- interactions
- events
- opportunities
- projects
- songs
- other structured Cesium Lab data

### Cloudflare

Cloudflare is responsible for how the application is reached:

- DNS
- static frontend hosting
- CDN
- HTTPS
- authentication
- secure tunneling to the home server

A useful mental model is:

```text
Astro       = what you see
FastAPI     = what things do
PostgreSQL  = what things know
Cloudflare  = how you securely reach it
```

---

## 3. Development Ports

During local development:

| Port | Service | Purpose |
| ---: | --- | --- |
| `4321` | Astro | Frontend development server |
| `8000` | FastAPI | Backend/API |
| `5432` | PostgreSQL | Relational database |
| `22` | SSH | Server administration |

Astro uses port `4321` by default.

The development architecture is:

```text
Browser
   │
   ▼
Astro :4321
   │
   │ API requests
   ▼
FastAPI :8000
   │
   ▼
PostgreSQL :5432
```

PostgreSQL should not be directly accessible from the Internet.

---

## 4. Repository Structure

Keep the platform inside `heart/`.

```text
heart/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── layouts/
│   │   └── styles/
│   ├── public/
│   ├── astro.config.mjs
│   ├── package.json
│   └── tsconfig.json
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── people.py
│   │   │   ├── organizations.py
│   │   │   ├── interactions.py
│   │   │   ├── events.py
│   │   │   ├── opportunities.py
│   │   │   ├── projects.py
│   │   │   └── songs.py
│   │   ├── models/
│   │   ├── database/
│   │   ├── services/
│   │   └── auth/
│   ├── migrations/
│   └── requirements.txt
│
├── services/
│   ├── cesium-api.service
│   └── cloudflared.service
│
├── scripts/
│   ├── backup-db.sh
│   ├── import-contacts.py
│   └── import-notion.py
│
├── docs/
│   └── api/
│       └── BIG.md
│
└── README.md
```

The existing `apache2/` directory can be archived or deleted once its contents have been migrated.

---

## 5. Frontend — Astro

Astro is the frontend framework.

It is a good fit because Cesium Lab is primarily page-, dashboard-, and tool-oriented rather than requiring the entire site to be a large single-page application.

Astro can generate lightweight static pages while still allowing interactive components where needed.

### Interactive Components

Use client-side components only where they provide value, such as:

- instant contact search
- filters
- editable forms
- sortable tables
- dashboards
- network graphs
- interactive project tools

React can be added as an Astro integration for these components without making the entire application React.

Conceptually:

```text
Astro page
├── static layout
├── static navigation
├── static content
│
├── React search component
├── React contacts table
└── React network visualization
```

---

## 6. Frontend Development

Run Astro locally:

```bash
npm run dev
```

Default address:

```text
http://localhost:4321
```

During development, the frontend communicates with:

```text
http://localhost:8000
```

for API requests.

For example:

```text
Astro
   │
   │ GET /api/people
   ▼
FastAPI
   │
   ▼
PostgreSQL
```

A development proxy can later make the API appear under `/api` without hardcoding backend URLs throughout the frontend.

---

## 7. Frontend Production Hosting

Astro can build the frontend into static files:

```bash
npm run build
```

producing:

```text
frontend/dist/
```

Deploy that build to Cloudflare Pages.

Production therefore does **not** require:

- Apache
- nginx
- a permanent Node server
- Astro running on the home machine

Static assets are served by Cloudflare's infrastructure.

```text
Browser
   ↓
cesiumlab.net
   ↓
Cloudflare Pages
   ↓
Astro static build
```

The home server only needs to handle dynamic backend requests.

---

## 8. Backend — FastAPI

Run FastAPI on the home server:

```text
127.0.0.1:8000
```

FastAPI should handle:

- CRUD operations
- search
- filtering
- validation
- relationships
- database transactions
- imports
- exports
- future agent/API access

Example request:

```text
Browser
   ↓
GET https://api.cesiumlab.net/people
   ↓
Cloudflare
   ↓
FastAPI
   ↓
PostgreSQL
```

---

## 9. API Structure

Potential initial endpoints:

```http
GET    /people
GET    /people/{id}
POST   /people
PATCH  /people/{id}
DELETE /people/{id}

GET    /organizations
GET    /organizations/{id}

GET    /interactions
GET    /events
GET    /opportunities
GET    /projects
GET    /songs
```

Later:

```http
GET /people?q=alex
GET /people?location=los-angeles
GET /people/{id}/interactions
GET /people/{id}/network
GET /opportunities?status=contacted
```

The API becomes the common interface for Cesium Lab data.

```text
Astro frontend ─────┐
                    │
CLI tools ──────────┤
                    │
AI tools ───────────┼── FastAPI ── PostgreSQL
                    │
scripts ────────────┤
                    │
future apps ────────┘
```

Clients should not directly access PostgreSQL.

---

## 10. Database — PostgreSQL

PostgreSQL is the canonical structured datastore.

Initial schema:

```text
people
organizations
people_organizations
interactions

events
event_people
event_organizations

opportunities
opportunity_people
opportunity_organizations

projects
project_people
project_organizations

songs
song_people
song_projects
```

### Example `people`

```text
people
------------------------------------------------
id                  UUID PRIMARY KEY
first_name
last_name
display_name
email
phone
instagram
website
location
notes
created_at
updated_at
```

Use UUIDs as canonical identifiers.

For example:

```text
person_id = 29be1fe9-2e9b-4cbc-8b82-...
```

Names can change or collide. IDs should not.

---

## 11. Database Security

PostgreSQL should remain private.

Desired path:

```text
FastAPI
   ↓
127.0.0.1:5432
   ↓
PostgreSQL
```

Not:

```text
Internet → PostgreSQL
```

The public API should be the controlled interface to the data.

A connection string could look like:

```text
postgresql://cesium@127.0.0.1:5432/cesium
```

Credentials should live outside Git.

For example:

```text
/etc/cesium/api.env
```

with values such as:

```dotenv
DATABASE_URL=...
CESIUM_API_TOKEN=...
```

---

## 12. Backend `systemd` Service

Create:

```text
heart/services/cesium-api.service
```

Conceptually:

```ini
[Unit]
Description=Cesium Lab API
After=network.target postgresql.service

[Service]
User=colin
WorkingDirectory=/path/to/heart/backend
EnvironmentFile=/etc/cesium/api.env
ExecStart=/path/to/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
sudo systemctl enable cesium-api
sudo systemctl start cesium-api
```

Verify:

```bash
systemctl status cesium-api
```

and:

```bash
curl http://127.0.0.1:8000/
```

---

## 13. Cloudflare Tunnel

Cloudflare Tunnel exposes FastAPI without opening the API port directly to the Internet.

Conceptually:

```text
api.cesiumlab.net
        ↓
Cloudflare
        ↓
Cloudflare Tunnel
        ↓
127.0.0.1:8000
        ↓
FastAPI
```

The home router does not need to publicly expose port `8000`.

`cloudflared` maintains the outbound tunnel.

---

## 14. Authentication

Contact and personal data must not be publicly browseable.

Use Cloudflare Access in front of private services.

Recommended domains:

```text
cesiumlab.net
    public

app.cesiumlab.net
    private

api.cesiumlab.net
    private
```

### Browser Access

For the private application:

```text
Browser
   ↓
app.cesiumlab.net
   ↓
Cloudflare Access
   ↓
allowed identity
   ↓
application
```

Only approved identities should pass the Access policy.

### Programmatic API Access

Scripts and future tools can additionally authenticate to FastAPI using a bearer token:

```http
Authorization: Bearer <token>
```

Store the token in:

```text
/etc/cesium/api.env
```

Do not:

- commit tokens
- put tokens in URLs
- hardcode private API tokens into browser JavaScript

---

## 15. Domain Structure

Recommended:

```text
cesiumlab.net
    public Astro site

app.cesiumlab.net
    private Cesium Lab interface

api.cesiumlab.net
    private FastAPI backend
```

### `cesiumlab.net`

Hosted on Cloudflare Pages.

Contains public Cesium Lab content.

### `app.cesiumlab.net`

Private frontend interface.

Can also be an Astro static deployment protected by Cloudflare Access.

### `api.cesiumlab.net`

Cloudflare Access + Cloudflare Tunnel to:

```text
127.0.0.1:8000
```

---

## 16. Public and Private Frontends

The public and private interfaces do not necessarily need separate frameworks.

Both can use Astro.

Possible approaches:

### One Astro Project

```text
frontend/
├── public pages
└── application pages
```

Deploy different routes/domains as appropriate.

### Two Astro Projects

```text
frontend-public/
frontend-app/
```

This provides stronger conceptual separation but introduces more duplicated tooling.

Start with one frontend unless separation becomes useful.

---

## 17. Contacts Interface

The first high-value private frontend should be a fast contacts interface.

Example:

```text
┌──────────────────────────────────────────────────────┐
│ Cesium Lab                                     Colin │
├──────────────────────────────────────────────────────┤
│ Search people...                                     │
├──────────────┬───────────────────────────────────────┤
│ Filters      │                                       │
│              │ Alex Smith                            │
│ Musicians    │ Guitarist · Los Angeles               │
│ Engineers    │ Some Band / Organization              │
│ LA           │                                       │
│ Seattle      │ Last interaction: Aug 12              │
│ Stanford     │                                       │
│ UCLA         │ [Open profile]                        │
│              │                                       │
│              │ Sarah Jones                           │
│              │ Photographer · Seattle                │
└──────────────┴───────────────────────────────────────┘
```

Prioritize instant search across:

- names
- organizations
- roles
- locations
- social handles
- notes

Useful filters could include:

- musicians
- engineers
- city
- school
- organization
- relationship type
- project
- last interaction

---

## 18. Person Page

A person page can aggregate relational information.

```text
Alex Smith
Los Angeles

Guitarist · Producer

Organizations
-------------
Some Band
Some Studio

Contact
-------
Instagram: @...
Email: ...

Interactions
------------
Aug 14, 2026
Met at backyard release show

Jul 22, 2026
Instagram conversation

Opportunities
-------------
Possible co-bill
Status: Explore

Events
------
Backyard Release Party

Projects
--------
...

Connections
-----------
Sarah Jones
John Smith
Some Band
```

This is where the relational database becomes substantially more useful than a flat contact list.

---

## 19. Other Frontend Pages

Cesium Lab can gradually grow into:

```text
/
├── /contacts
├── /people/:id
├── /organizations
├── /interactions
├── /events
├── /opportunities
├── /projects
├── /music
├── /songs
└── /network
```

Do not build all of these before the basic People workflow works.

---

## 20. Network Graph

Eventually `/network` can visualize relationships among:

- people
- organizations
- bands
- venues
- events
- projects

Example:

```text
                 Artist A
                    │
                Person A
                 /     \
                /       \
          MONARCH       Venue
              │           │
             Colin ─── Promoter
              │
            Person B
```

A client-side library such as Cytoscape.js or React Flow can be embedded into an Astro page.

The graph should complement search and tables rather than replace them.

Useful questions include:

- Who connects me to this person?
- Which organizations contain the most people I know?
- Where are clusters forming?
- Who bridges two scenes?
- Which people have I interacted with repeatedly?

---

## 21. Notion Migration

Do not immediately destroy the existing Notion databases.

Migration flow:

```text
Notion
   ↓
import script
   ↓
normalize
   ↓
deduplicate
   ↓
PostgreSQL
```

Start with:

1. People
2. Organizations
3. Interactions

Then:

4. Events
5. Opportunities
6. Projects
7. Songs

Once PostgreSQL is reliable, decide whether structured Notion databases are still useful.

Long-form information can remain in Notion if useful.

For example:

```text
PostgreSQL
├── people
├── relationships
├── organizations
├── events
└── opportunities

Notion
├── Artistic Identity
├── Music Strategy
├── Songwriting Lessons
├── City Notes
└── long-form project notes
```

---

## 22. File Locations

Keep source code, persistent data, and secrets separate.

### Source Code

```text
~/heart/
```

Contains:

- Astro frontend
- FastAPI backend
- migrations
- scripts
- service definitions
- documentation

### Persistent Application Data

```text
/var/lib/cesium/
```

Potential contents:

```text
uploads/
backups/
exports/
```

PostgreSQL should normally manage its own database files.

### Secrets

```text
/etc/cesium/
```

For example:

```text
/etc/cesium/api.env
```

Never commit this directory to Git.

---

## 23. Backups

Once PostgreSQL becomes valuable, automate backups.

```text
PostgreSQL
   ↓
pg_dump
   ↓
/var/lib/cesium/backups/
```

Target:

```text
nightly local backup
weekly second-machine/cloud backup
```

A backup is not trustworthy until restoration has been tested.

Do not let the home server become the only copy of years of contact and network information.

---

## 24. Migration from Apache

Because preserving the current implementation is not a requirement, the migration can target the final architecture directly.

### Phase 1 — Backend Foundation

- [ ] Create `heart/backend/`
- [ ] Create Python virtual environment
- [ ] Install FastAPI
- [ ] Install SQLAlchemy
- [ ] Install Alembic
- [ ] Install PostgreSQL driver
- [ ] Create minimal API
- [ ] Verify FastAPI on `127.0.0.1:8000`

### Phase 2 — PostgreSQL

- [ ] Install PostgreSQL
- [ ] Create `cesium` database
- [ ] Create dedicated `cesium` user
- [ ] Restrict PostgreSQL to local/private access
- [ ] Configure FastAPI connection
- [ ] Create first migration
- [ ] Create `people` table
- [ ] Verify FastAPI can read/write PostgreSQL

### Phase 3 — Backend Service

- [ ] Create `cesium-api.service`
- [ ] Load secrets from `/etc/cesium/api.env`
- [ ] Start FastAPI through `systemd`
- [ ] Enable at boot
- [ ] Verify automatic restart

### Phase 4 — Cloudflare API

- [ ] Create `api.cesiumlab.net`
- [ ] Configure Cloudflare Tunnel
- [ ] Route it to `127.0.0.1:8000`
- [ ] Configure Cloudflare Access
- [ ] Restrict Access to approved identity
- [ ] Add API bearer authentication if needed
- [ ] Verify PostgreSQL remains inaccessible externally

### Phase 5 — Astro Frontend

- [ ] Create `heart/frontend/`
- [ ] Initialize Astro
- [ ] Add TypeScript
- [ ] Configure local API URL
- [ ] Build basic layout/navigation
- [ ] Build `/contacts`
- [ ] Build `/people/:id`
- [ ] Add instant search
- [ ] Add filters
- [ ] Add create/edit functionality

### Phase 6 — Cloudflare Pages

- [ ] Connect frontend repository/build to Cloudflare Pages
- [ ] Configure Astro build command
- [ ] Configure output directory
- [ ] Point `cesiumlab.net` to the public frontend
- [ ] Configure `app.cesiumlab.net` if using a private frontend
- [ ] Protect private app with Cloudflare Access

### Phase 7 — Import Data

- [ ] Write `scripts/import-notion.py`
- [ ] Import People
- [ ] Deduplicate
- [ ] Validate
- [ ] Import Organizations
- [ ] Import Interactions
- [ ] Preserve Notion data during validation

### Phase 8 — Expand Data Model

- [ ] Events
- [ ] Opportunities
- [ ] Projects
- [ ] Songs
- [ ] Relationship queries
- [ ] Network graph

### Phase 9 — Backups

- [ ] Configure `pg_dump`
- [ ] Schedule local backups
- [ ] Configure off-machine backup
- [ ] Test restore

### Phase 10 — Retire Apache

Once the Astro deployment and FastAPI backend work:

- [ ] Confirm no required content remains under `apache2/`
- [ ] Archive anything worth keeping
- [ ] Disable `apache2.service`
- [ ] Remove Apache from Cloudflare Tunnel configuration
- [ ] Delete/archive `heart/apache2/`

---

## 25. Final Production Architecture

The desired final state is:

```text
                              Internet
                                  │
                              Cloudflare
                         ┌────────┴────────┐
                         │                 │
                         ▼                 ▼
                  Cloudflare Pages   Cloudflare Access
                         │                 │
                         │                 ▼
                         │          Cloudflare Tunnel
                         │                 │
                         │                 ▼
                         │          FastAPI :8000
                         │                 │
                         │                 ▼
                         │        PostgreSQL :5432
                         │
                         └──── API requests ─────┘
```

More concretely:

```text
cesiumlab.net
    ↓
Cloudflare Pages
    ↓
Astro public frontend

app.cesiumlab.net
    ↓
Cloudflare Access
    ↓
Astro private frontend

api.cesiumlab.net
    ↓
Cloudflare Access
    ↓
Cloudflare Tunnel
    ↓
FastAPI :8000
    ↓
PostgreSQL :5432
```

Home-server services:

```text
cloudflared.service
cesium-api.service
postgresql.service
```

Development-only frontend service:

```text
Astro :4321
```

No Apache service and no permanent Node frontend server are required in production.

---

## Immediate Next Steps

- [ ] Create `heart/backend/`
- [ ] Install PostgreSQL
- [ ] Create the `cesium` database
- [ ] Create a minimal FastAPI application
- [ ] Connect FastAPI to PostgreSQL
- [ ] Create the first `people` migration/table
- [ ] Add `cesium-api.service`
- [ ] Create `api.cesiumlab.net`
- [ ] Tunnel it to `127.0.0.1:8000`
- [ ] Protect the API with Cloudflare Access
- [ ] Create `heart/frontend/`
- [ ] Initialize Astro + TypeScript
- [ ] Build the contacts and person views
- [ ] Deploy the Astro build to Cloudflare Pages
- [ ] Import People from Notion
- [ ] Add Organizations and Interactions
- [ ] Configure backups
- [ ] Retire Apache