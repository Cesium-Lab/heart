# Cesium Lab Architecture

## Goal

Turn Cesium Lab from a static Apache-served website into a personal software platform supporting:

- existing Cesium Lab pages
- contacts and people
- organizations and relationships
- music data
- projects
- APIs for scripts and AI tools
- a private web application

## Current Architecture

```text
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

Apache currently serves the static website and is the endpoint used by Cloudflare Tunnel.

## Target Architecture

```text
                    Internet
                       │
                       ▼
                   Cloudflare
                       │
                       ▼
                  cloudflared
                       │
                       ▼
                   Apache :80
                  /          \
                 ▼            ▼
          Static frontend    /api/*
                                │
                                ▼
                         FastAPI :8000
                                │
                                ▼
                        PostgreSQL :5432
```

Apache remains the main HTTP entrypoint while the platform is developed.

## Components

| Port | Service | Purpose |
|---|---|---|
| `80` | Apache | Main HTTP entrypoint |
| `3000` | Vite | Frontend development |
| `8000` | FastAPI | Cesium API |
| `5432` | PostgreSQL | Database |
| `22` | SSH | Server administration |

Ports `8000` and `5432` should normally listen only locally.

Port `3000` is primarily for development.

## Repository

```text
heart/
├── docs/
├── apache2/
├── backend/
├── frontend/
├── services/
└── scripts/
```

## Responsibility

### Apache
Routing and production static-file serving.

### FastAPI
Application and data logic.

### PostgreSQL
Canonical structured data.

### React
Human interface to Cesium Lab.

### Cloudflare
Secure Internet ingress and authentication where appropriate.

## Long-Term Direction

Eventually Apache may become unnecessary:

```text
Cloudflare
    ↓
Cesium application
    ├── frontend
    └── API
         ↓
     PostgreSQL
```

There is no need to remove Apache until it actually becomes redundant.
