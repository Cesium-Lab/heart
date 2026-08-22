# Cesium Lab Migration Plan

## Phase 1 — Preserve Current Site

Keep:

```text
Cloudflare
 ↓
Apache :80
 ↓
existing Cesium Lab
```

working throughout development.

## Phase 2 — PostgreSQL

- [ ] Install PostgreSQL
- [ ] Create `cesium` database
- [ ] Create dedicated database user
- [ ] Restrict database to local/private access
- [ ] Create first migration
- [ ] Create `people` table

## Phase 3 — Backend

- [ ] Create `heart/backend/`
- [ ] Create Python virtual environment
- [ ] Install FastAPI
- [ ] Install SQLAlchemy
- [ ] Install Alembic
- [ ] Configure PostgreSQL connection
- [ ] Implement `GET /people`
- [ ] Implement `GET /people/{id}`
- [ ] Implement `POST /people`
- [ ] Implement `PATCH /people/{id}`
- [ ] Test on `localhost:8000`

## Phase 4 — Production API

- [ ] Create `cesium-api.service`
- [ ] Start API through systemd
- [ ] Enable API at boot
- [ ] Configure Apache reverse proxy
- [ ] Route `/api/*` to port `8000`
- [ ] Test API through Cesium Lab

## Phase 5 — Authentication

Before importing real contacts:

- [ ] Protect private routes
- [ ] Configure Cloudflare Access or equivalent
- [ ] Verify unauthenticated users cannot access contacts
- [ ] Verify PostgreSQL itself is not Internet accessible

## Phase 6 — Frontend

- [ ] Create `heart/frontend/`
- [ ] Initialize React + TypeScript + Vite
- [ ] Build `/contacts`
- [ ] Add instant search
- [ ] Build `/people/:id`
- [ ] Add create/edit person functionality
- [ ] Add interaction timeline
- [ ] Build production frontend
- [ ] Serve build through Apache

## Phase 7 — Data Migration

Start with:

1. People
2. Organizations
3. Interactions

Create:

```text
scripts/import-notion.py
```

Flow:

```text
Notion
 ↓
import script
 ↓
normalize/deduplicate
 ↓
PostgreSQL
```

Do not delete the Notion data during migration.

## Phase 8 — Expand

After the People system proves useful:

- [ ] Organizations
- [ ] Interactions
- [ ] Events
- [ ] Opportunities
- [ ] Projects
- [ ] Songs
- [ ] Network visualization

## Phase 9 — Backups

Before treating PostgreSQL as the source of truth:

- [ ] Configure automatic `pg_dump`
- [ ] Store local backups
- [ ] Maintain a second backup outside the home server
- [ ] Test restoring a backup

## Phase 10 — Reevaluate Apache

Once the platform is mature, determine whether Apache is still useful.

If not:

```text
Cloudflare
 ↓
Cesium application
 ↓
PostgreSQL
```

Then Cloudflare Tunnel can point directly to the application server and `apache2.service` can be retired.

Removing Apache is an optimization, not a prerequisite.
