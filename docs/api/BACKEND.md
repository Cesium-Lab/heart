# Cesium Lab Backend

## Stack

Initial backend:

```text
Python
FastAPI
SQLAlchemy
Alembic
PostgreSQL
```

Run the API on:

```text
127.0.0.1:8000
```

Run PostgreSQL on:

```text
127.0.0.1:5432
```

## Data Model

Start with:

```text
people
organizations
people_organizations
interactions
```

Later add:

```text
events
opportunities
projects
songs
```

and their relationship tables.

## People

Example fields:

```text
id              UUID
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

## API

Initial endpoints:

```text
GET    /people
GET    /people/{id}

POST   /people
PATCH  /people/{id}
DELETE /people/{id}
```

Then:

```text
GET /organizations
GET /interactions
GET /events
GET /opportunities
GET /projects
GET /songs
```

Eventually useful queries could include:

```text
GET /people?q=alex
GET /people?location=los-angeles
GET /people/{id}/interactions
GET /people/{id}/network
GET /opportunities?status=contacted
```

## API Principle

Clients should not directly access PostgreSQL.

Use:

```text
Frontend
    ↓
FastAPI
    ↓
PostgreSQL
```

This means the same backend can eventually support:

```text
Web frontend ─────┐
AI tools ─────────┤
CLI ──────────────┼── API ── PostgreSQL
scripts ──────────┤
mobile app ───────┘
```

## Secrets

Do not commit database credentials.

Store them somewhere such as:

```text
/etc/cesium/api.env
```

and load that environment file from the API's systemd service.
