# Cesium Lab Frontend

## Recommended Stack

Start with:

```text
React
TypeScript
Vite
```

The frontend communicates with FastAPI:

```text
React
   ↓
fetch("/api/...")
   ↓
FastAPI
   ↓
PostgreSQL
```

## Development

Run Vite on:

```text
127.0.0.1:3000
```

This is primarily a development server.

## Production

Build with:

```bash
npm run build
```

Vite generates static files in:

```text
frontend/dist/
```

Apache can serve these directly.

Therefore production does not need a Node process running continuously.

## Initial UI

Do not build an enormous Music HQ immediately.

Start with:

```text
/contacts
/people/:id
```

### Contacts

The first interface should prioritize extremely fast search.

Search across:

- name
- organization
- role
- location
- social handle
- notes

Useful filters:

- musician
- engineering
- LA
- Seattle
- Stanford
- UCLA
- organization
- relationship type

### Person Page

```text
Name

Roles
Location
Contact information

Organizations

Interactions
------------
Aug 14
Met at show

Jul 22
Instagram conversation

Opportunities
-------------
Possible collaboration

Events
------

Projects
--------

Connections
-----------
```

## Expansion

Once contacts work well:

```text
/organizations
/interactions
/events
/opportunities
/projects
/music
/songs
/network
```

## Network Graph

Eventually `/network` can visualize relationships between:

```text
people
organizations
bands
venues
events
projects
```

A graph library such as Cytoscape.js could sit on top of the same API.

The graph should complement normal search and tables rather than replace them.
