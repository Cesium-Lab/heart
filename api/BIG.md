# Cesium Lab Web Platform Architecture Plan

## Goal

Evolve the current Cesium Lab setup from a static Apache-hosted directory into a small personal web platform that can support:

- the existing Cesium Lab website
- a private contacts/people database
- music-network data
- projects and other structured personal data
- a reusable API for scripts and future AI agents
- a richer web frontend
- eventual removal of Apache if it becomes unnecessary

The migration should happen incrementally so the current website keeps working throughout.

## 1. Current Architecture

```text
GitHub
└── heart/
    └── apache2/
        └── static website files

Home server
├── apache2.service
│   └── listens on :80
│
└── cloudflared.service
    └── cesiumlab.net → http://localhost:80

Internet
    ↓
Cloudflare
    ↓
Cloudflare Tunnel
    ↓
Apache :80
    ↓
heart/apache2/
```

Apache currently acts as both the web server and the entrypoint Cloudflare sends traffic to.

## 2. Target Intermediate Architecture

```text
                         INTERNET
                            │
                            ▼
                       Cloudflare
                            │
                            ▼
                    Cloudflare Tunnel
                            │
                            ▼
                      Apache :80
                    /            \\
                   /              \\
                  ▼                ▼
          Static website      Reverse proxy
          heart/apache2/          │
                                  │
                       ┌──────────┴──────────┐
                       ▼                     ▼
                 Frontend :3000        API :8000
                                          │
                                          ▼
                                   PostgreSQL :5432
```

Only Apache should initially be exposed to Cloudflare. Other services should listen locally.

## 3. Port Allocation

| Port | Service | Exposure | Purpose |
|---|---|---|---|
| `80` | Apache | Cloudflare Tunnel | Main HTTP entrypoint |
| `3000` | Frontend | localhost | React/Vite development server |
| `8000` | Backend API | localhost | API for people, music, projects, etc. |
| `5432` | PostgreSQL | localhost | Main relational database |
| `6379` | Redis | localhost | Optional future cache/job queue |
| `22` | SSH | private/Tailscale | Server administration |

## 4. Repository Structure

```text
heart/
├── apache2/
│   ├── html/
│   └── config/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── models/
│   │   ├── database/
│   │   ├── services/
│   │   └── auth/
│   ├── migrations/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── public/
│   └── package.json
├── services/
├── scripts/
└── README.md
```

Initially, only `apache2/` and `backend/` need to exist.

## 5. Database

Use PostgreSQL as the primary relational database.

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

Example `people` fields:

```text
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

Use UUIDs instead of names as identifiers.

## 6. PostgreSQL Security

PostgreSQL should not be Internet accessible.

```text
API
 ↓
127.0.0.1:5432
 ↓
PostgreSQL
```

Credentials should live outside Git, for example:

```text
/etc/cesium/api.env
```

## 7. Backend API

Use FastAPI on:

```text
127.0.0.1:8000
```

Potential endpoints:

```text
GET    /api/people
GET    /api/people/{id}
POST   /api/people
PATCH  /api/people/{id}
DELETE /api/people/{id}

GET    /api/organizations
GET    /api/interactions
GET    /api/events
GET    /api/opportunities
GET    /api/projects
GET    /api/songs
```

The API becomes the common interface for the web frontend, CLI tools, AI tools, scripts, and future apps.

## 8. Backend systemd Service

Create `cesium-api.service` to run FastAPI automatically:

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

## 9. Apache as Reverse Proxy

Keep Cloudflare pointing to `http://localhost:80`.

Apache can route `/api/` to FastAPI:

```apache
DocumentRoot /path/to/heart/apache2/html

ProxyPass        /api/ http://127.0.0.1:8000/
ProxyPassReverse /api/ http://127.0.0.1:8000/
```

Request path:

```text
Internet
 ↓
Cloudflare
 ↓
cloudflared
 ↓
Apache :80
 ↓
FastAPI :8000
 ↓
PostgreSQL :5432
```

## 10. Frontend

Recommended stack:

```text
React
TypeScript
Vite
```

The frontend calls FastAPI rather than accessing PostgreSQL directly.

## 11. Possible Frontend Pages

```text
/
├── /contacts
├── /people/:id
├── /organizations
├── /network
├── /interactions
├── /events
├── /opportunities
├── /music
├── /songs
└── /projects
```

## 12. Contacts UI

Prioritize instant search across:

- names
- organizations
- notes
- locations
- roles
- social handles

Useful filters could include musician, engineering, LA, Seattle, Stanford, UCLA, organization, and relationship type.

## 13. Individual Person Page

A person page can combine roles, location, contact information, organizations, interactions, opportunities, events, projects, and connections.

## 14. Network Graph

Eventually `/network` can visualize relationships among people, organizations, bands, venues, events, and projects. Cytoscape.js or React Flow could be used.

## 15. Frontend Port

During development:

```text
React/Vite → 127.0.0.1:3000
```

For production:

```bash
npm run build
```

produces `frontend/dist/`, which can be served as static files. A permanent Node process is not required.

## 16. Recommended Production Architecture

```text
                      Cloudflare
                           │
                           ▼
                    cloudflared
                           │
                           ▼
                       Apache :80
                      /          \\
                     /            \\
                    ▼              ▼
          React static build     /api/*
          frontend/dist/            │
                                    ▼
                              FastAPI :8000
                                    │
                                    ▼
                             PostgreSQL :5432
```

## 17. Authentication

Keep private contacts and API data protected. A useful split is:

```text
cesiumlab.net
    public

app.cesiumlab.net
    private

api.cesiumlab.net
    private
```

Cloudflare Access can protect the private application and API. Programmatic API access can additionally use a bearer token stored outside the repository.

## 18. Suggested Domain Structure

```text
cesiumlab.net       → public site
app.cesiumlab.net   → private Cesium Lab interface
api.cesiumlab.net   → authenticated API
```

## 19. Notion Migration

Do not immediately delete the Notion databases.

Start by migrating:

1. People
2. Organizations
3. Interactions

Then later:

4. Events
5. Opportunities
6. Projects
7. Songs

Structured entities can move to PostgreSQL while long-form strategy and knowledge can remain in Notion if useful.

## 20. File Locations

Code:

```text
~/heart/
```

Persistent application data:

```text
/var/lib/cesium/
```

Secrets:

```text
/etc/cesium/
```

Do not commit secrets or private database contents.

## 21. Backups

Automate PostgreSQL backups with `pg_dump`.

Target:

```text
nightly local backup
weekly second-machine/cloud backup
```

Test restoration before treating PostgreSQL as the sole source of truth.

## 22. Implementation Sequence

### Phase 1 — Preserve Existing System

Verify:

```text
Cloudflare → Apache :80 → static files
```

### Phase 2 — Install PostgreSQL

- Install PostgreSQL
- Create database `cesium`
- Create user `cesium`
- Configure local access
- Create the first `people` table/migration

### Phase 3 — Create Backend

Create `heart/backend/` and set up:

```text
Python
FastAPI
SQLAlchemy
Alembic
PostgreSQL driver
```

Implement the initial People CRUD endpoints and test on `localhost:8000`.

### Phase 4 — Create systemd API Service

Create and enable `cesium-api.service`.

### Phase 5 — Connect Apache to API

Enable Apache proxy modules and route:

```text
/api/ → localhost:8000
```

### Phase 6 — Add Authentication

Before adding real contact data, protect the private application/API using Cloudflare Access and API credentials where appropriate.

### Phase 7 — Build Contacts Frontend

Create `heart/frontend/` using React + TypeScript + Vite.

Start with:

```text
/contacts
/people/:id
```

Implement search, filters, profile view, create/edit person, and interaction timeline.

### Phase 8 — Build Production Frontend

Run `npm run build` and deploy `frontend/dist/` as static files.

### Phase 9 — Import People

Create:

```text
scripts/import-notion.py
```

Normalize and deduplicate People data before inserting into PostgreSQL.

### Phase 10 — Add Relationships

Add Organizations, Interactions, Events, Opportunities, Projects, and Songs as the core system proves useful.

## 23. Future Apache Removal

Apache does not need to be permanent.

Eventually:

```text
Cloudflare
   ↓
FastAPI/application
   ├── /api
   └── static React build
```

Cloudflare Tunnel could point directly to the application server and Apache could be disabled. There is little reason to do this early.

## 24. Immediate Next Steps

- [ ] Create `heart/backend/`
- [ ] Install PostgreSQL
- [ ] Create the `cesium` database
- [ ] Create the first `people` table
- [ ] Create a minimal FastAPI application
- [ ] Run FastAPI on `127.0.0.1:8000`
- [ ] Add `cesium-api.service`
- [ ] Configure Apache `/api/` proxying
- [ ] Verify the API works through the intended domain
- [ ] Add authentication before importing real contacts
- [ ] Create `heart/frontend/`
- [ ] Build a React + TypeScript + Vite contacts interface
- [ ] Add search and person profile pages
- [ ] Import People from Notion
- [ ] Add Organizations and Interactions
- [ ] Expand into Events, Opportunities, Projects, and Songs
- [ ] Configure backups
- [ ] Reevaluate whether Apache is still useful