Cesium Lab Web Platform Architecture Plan

Goal

Evolve the current Cesium Lab setup from a static Apache-hosted directory into a small personal web platform that can support:

* the existing Cesium Lab website
* a private contacts/people database
* music-network data
* projects and other structured personal data
* a reusable API for scripts and future AI agents
* a richer web frontend
* eventual removal of Apache if it becomes unnecessary

The migration should happen incrementally so the current website keeps working throughout.

⸻

1. Current Architecture

Right now:

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

This is a perfectly reasonable starting point. Apache currently acts as both:

1. the web server
2. the entrypoint Cloudflare sends traffic to

The goal is initially to keep Apache doing this job while adding new services behind it.

⸻

2. Target Intermediate Architecture

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
                    /            \
                   /              \
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

The important rule is:

Only Apache should initially be exposed to Cloudflare.

The other services should listen only locally.

⸻

3. Port Allocation

Port	Service	Exposure	Purpose
80	Apache	Cloudflare Tunnel	Main HTTP entrypoint
3000	Frontend	localhost	React/Next/Vite development or application server
8000	Backend API	localhost	API for people, music, projects, etc.
5432	PostgreSQL	localhost	Main relational database
6379	Redis	localhost	Optional future cache/job queue
22	SSH	private/Tailscale	Server administration

The three main new services are therefore:

:3000  frontend
:8000  API
:5432  database

⸻

4. Repository Structure

Expand heart/ rather than making the database system an unrelated project.

heart/
├── apache2/
│   ├── html/
│   │   ├── index.html
│   │   ├── css/
│   │   ├── js/
│   │   └── assets/
│   │
│   └── config/
│       └── cesiumlab.conf
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   │
│   │   ├── api/
│   │   │   ├── people.py
│   │   │   ├── organizations.py
│   │   │   ├── interactions.py
│   │   │   ├── events.py
│   │   │   ├── opportunities.py
│   │   │   ├── projects.py
│   │   │   └── songs.py
│   │   │
│   │   ├── models/
│   │   ├── database/
│   │   ├── services/
│   │   └── auth/
│   │
│   ├── migrations/
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── ...
│
├── services/
│   ├── cesium-api.service
│   ├── cesium-web.service
│   └── cloudflared.service
│
├── scripts/
│   ├── deploy.sh
│   ├── backup-db.sh
│   ├── import-contacts.py
│   └── import-notion.py
│
└── README.md

Initially, only these need to exist:

heart/
├── apache2/
└── backend/

The frontend can come after the API works.

⸻

5. Database

Use PostgreSQL for the primary database.

PostgreSQL is a good fit because the data is highly relational.

For example:

Person
 ├── belongs to Organization
 ├── attended Event
 ├── had Interaction
 ├── involved in Opportunity
 └── participates in Project

Initial schema:

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

Example people

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

Use UUIDs instead of names as identifiers.

For example:

person_id = 29be1fe9-2e9b-4cbc-8b82-...

Names can change or collide. UUIDs do not.

⸻

6. PostgreSQL Security

PostgreSQL should not be Internet accessible.

Desired connection:

API
 ↓
127.0.0.1:5432
 ↓
PostgreSQL

Not:

Internet → PostgreSQL

Configure PostgreSQL to listen locally where possible.

The database URL could look like:

postgresql://cesium@127.0.0.1:5432/cesium

Credentials should live outside Git.

For example:

/etc/cesium/api.env

containing:

DATABASE_URL=...
DATABASE_PASSWORD=...
API_SECRET=...

Do not commit that file.

⸻

7. Backend API

A good backend choice is FastAPI.

Run it on:

127.0.0.1:8000

Conceptually:

Browser
   ↓
GET /api/people
   ↓
FastAPI
   ↓
PostgreSQL

Potential endpoints:

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

Later:

GET /api/people?q=alex
GET /api/people?location=los-angeles
GET /api/people/{id}/interactions
GET /api/people/{id}/network
GET /api/opportunities?status=contacted

The API becomes the common interface for everything.

Web frontend ───────┐
                    │
CLI tools ──────────┤
                    │
AI tools ───────────┼── API ── PostgreSQL
                    │
scripts ────────────┤
                    │
future mobile app ──┘

⸻

8. Backend systemd Service

Create:

heart/services/cesium-api.service

Conceptually:

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

Then:

sudo systemctl enable cesium-api
sudo systemctl start cesium-api

Now:

curl http://127.0.0.1:8000/

should reach the backend.

⸻

9. Apache as Reverse Proxy

Keep Cloudflare pointing to:

http://localhost:80

Apache can route different paths to different services.

Example conceptual configuration:

DocumentRoot /path/to/heart/apache2/html
ProxyPass        /api/ http://127.0.0.1:8000/
ProxyPassReverse /api/ http://127.0.0.1:8000/

Now:

https://cesiumlab.net/api/people

travels:

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

Meanwhile:

https://cesiumlab.net/

still goes to the existing Apache website.

That means the backend can be built without breaking the existing site.

⸻

10. Frontend

There are several reasonable approaches.

Recommended Approach: React + Vite

For Cesium Lab, I would probably start with:

React
+
TypeScript
+
Vite

rather than immediately introducing a large full-stack framework.

Why:

* fast
* relatively simple
* excellent ecosystem
* easy API integration
* good for dashboards
* good for tables
* good for network visualization
* frontend remains separate from backend
* FastAPI remains responsible for data

The architecture becomes:

React frontend
     │
     │ fetch("/api/people")
     ▼
FastAPI
     │
     ▼
PostgreSQL

⸻

11. Possible Frontend Pages

Cesium Lab could gradually become your personal control panel.

cesiumlab.net/
│
├── /
│   Cesium Lab homepage
│
├── /contacts
│   People search
│
├── /people/:id
│   Person profile
│
├── /organizations
│
├── /network
│   Relationship graph
│
├── /interactions
│
├── /events
│
├── /opportunities
│
├── /music
│   Music HQ
│
├── /songs
│
└── /projects

⸻

12. Contacts UI

The first useful frontend could simply be a very fast contacts interface.

Something like:

┌──────────────────────────────────────────────────────┐
│ Cesium Lab                                     Colin │
├──────────────────────────────────────────────────────┤
│ Search people...                                     │
├──────────────┬───────────────────────────────────────┤
│ Filters      │                                       │
│              │ Alex Smith                            │
│ Musicians    │ Guitarist · Los Angeles               │
│ Engineers    │ MONARCH / Handmade Records            │
│ LA           │                                       │
│ Seattle      │ Last interaction: Aug 12              │
│ Stanford     │                                       │
│ UCLA         │ [Open profile]                        │
│              │                                       │
│              │ Sarah Jones                           │
│              │ Photographer · Seattle                │
└──────────────┴───────────────────────────────────────┘

The most valuable feature initially is probably simply:

instant search

Type:

nat

and immediately search:

* names
* organizations
* notes
* locations
* roles
* social handles

That alone may make the SQL system substantially more useful than searching through Notion manually.

⸻

13. Individual Person Page

A person page could combine everything that currently gets scattered around.

Alex Smith
Los Angeles
Guitarist · Producer
Organizations
------------
Some Band
Handmade Records
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
Connections
-----------
Sarah Jones
John Smith
Some Band

That is where having relational SQL becomes particularly valuable.

⸻

14. Network Graph

Eventually /network could visualize:

                 Artist A
                    │
                    │
                Person A
                 /     \
                /       \
          MONARCH       Venue
              │           │
             Colin ─── Promoter
              │
              │
            Person B

Libraries such as Cytoscape.js or React Flow can make this practical.

The graph shouldn’t replace normal tables. It should answer questions like:

* Who connects me to this artist?
* Which organizations contain the most people I know?
* Where are clusters forming?
* Who bridges two scenes?
* Which people have I met repeatedly?

⸻

15. Frontend Port

During development:

React/Vite
127.0.0.1:3000

You could have Apache proxy:

/app/
    ↓
localhost:3000

But this is mainly useful during development.

For production, Vite builds ordinary static files:

npm run build

producing something like:

frontend/dist/

Apache can serve that directly.

Therefore production could actually be:

Apache :80
├── frontend/dist/
└── /api → FastAPI :8000

No frontend server needs to run continuously.

That’s especially attractive for your setup.

⸻

16. Recommended Production Architecture

This is probably the architecture I would target first:

                      Cloudflare
                           │
                           ▼
                    cloudflared
                           │
                           ▼
                       Apache :80
                      /          \
                     /            \
                    ▼              ▼
          React static build     /api/*
          frontend/dist/            │
                                    ▼
                              FastAPI :8000
                                    │
                                    ▼
                             PostgreSQL :5432

Services running:

apache2.service
cloudflared.service
cesium-api.service
postgresql.service

No permanent Node server required.

⸻

17. Authentication

Contacts should not simply become publicly browseable because they’re hosted at cesiumlab.net.

Separate:

PUBLIC
cesiumlab.net/

from:

PRIVATE
cesiumlab.net/app/
cesiumlab.net/contacts/
cesiumlab.net/api/

Cloudflare Access is a strong option for putting authentication in front of the private portion.

For example:

contacts.cesiumlab.net
        ↓
Cloudflare Access
        ↓
Google login / allowed identity
        ↓
Apache

Another clean setup could be:

cesiumlab.net           public
app.cesiumlab.net       private
api.cesiumlab.net       private

I actually prefer that separation.

⸻

18. Suggested Domain Structure

cesiumlab.net
    Public site
app.cesiumlab.net
    Private Cesium Lab interface
api.cesiumlab.net
    API

Cloudflare Tunnel could route:

cesiumlab.net
    → localhost:80
app.cesiumlab.net
    → localhost:80
api.cesiumlab.net
    → localhost:8000

However, initially I would keep:

api.cesiumlab.net

behind Cloudflare Access rather than publicly exposing unrestricted API access.

⸻

19. Notion Migration

Do not immediately delete the Notion databases.

Instead:

Notion
 ↓
migration/import script
 ↓
PostgreSQL

Start with:

1. People
2. Organizations
3. Interactions

Then validate the data.

Later:

4. Events
5. Opportunities
6. Projects
7. Songs

Once PostgreSQL becomes reliable, decide which Notion components remain useful.

Long-form information can still live in Notion even if structured entities move to SQL.

For example:

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

⸻

20. File Locations

Keep code, data, and secrets separate.

Git repository

~/heart/

Contains:

source code
frontend
API
Apache config
database migrations
scripts
systemd templates

Persistent application data

/var/lib/cesium/

Could contain:

uploads/
backups/
exports/

PostgreSQL should normally manage its own database directory.

Secrets

/etc/cesium/

For example:

/etc/cesium/api.env

⸻

21. Backups

Once the contact database becomes valuable, automate backups.

Example:

PostgreSQL
 ↓
pg_dump
 ↓
/var/lib/cesium/backups/

Potential schedule:

nightly local backup
weekly second-machine/cloud backup

Do not allow the home server to become the only copy of years of contact/network information.

⸻

22. Implementation Sequence

Phase 1 — Preserve Existing System

Do not modify how the existing Cesium Lab site works yet.

Verify:

Cloudflare → Apache :80 → static files

is stable.

⸻

Phase 2 — Install PostgreSQL

Install PostgreSQL.

Create:

database: cesium
user: cesium

Configure local access.

Test:

psql

Create an initial people table manually or through migrations.

⸻

Phase 3 — Create Backend

Create:

heart/backend/

Set up:

Python
FastAPI
SQLAlchemy
Alembic
PostgreSQL driver

Implement:

GET /people
GET /people/{id}
POST /people
PATCH /people/{id}

Test locally:

localhost:8000

⸻

Phase 4 — Create systemd API Service

Create:

cesium-api.service

Run FastAPI automatically at boot.

Verify:

systemctl status cesium-api

⸻

Phase 5 — Connect Apache to API

Enable Apache proxy modules if necessary.

Add:

/api/
    → localhost:8000

Now test:

https://cesiumlab.net/api/people

At this point you have your first remotely accessible database-backed endpoint.

⸻

Phase 6 — Add Authentication

Before adding real contact data:

Protect either:

/api/*

or preferably:

app.cesiumlab.net
api.cesiumlab.net

using Cloudflare Access or another authentication mechanism.

⸻

Phase 7 — Build Contacts Frontend

Create:

heart/frontend/

Use:

React
TypeScript
Vite

Start with only:

/contacts
/people/:id

Implement:

* search
* filters
* profile view
* create person
* edit person
* interaction timeline

Do not initially try to reproduce all of Notion.

⸻

Phase 8 — Build Production Frontend

Run:

npm run build

Serve:

frontend/dist/

from Apache.

Production no longer requires port 3000.

Port 3000 remains useful only during development.

⸻

Phase 9 — Import People

Export or retrieve People data from Notion.

Write:

scripts/import-notion.py

Map:

Notion person
 ↓
normalize
 ↓
SQL person

Avoid duplicates using:

* email
* phone
* social handles
* existing external IDs

⸻

Phase 10 — Add Relationships

After People works well, add:

organizations
interactions
events
opportunities
projects
songs

Build the UI only as these become useful.

⸻

23. Future Apache Removal

Apache does not need to be permanent.

Eventually you might have:

Cloudflare
   ↓
FastAPI :8000
   ├── /api
   └── static React build

At that point:

cloudflared
    → localhost:8000

and Apache could be disabled.

But there is little reason to do this early.

Apache currently gives you:

* static file serving
* reverse proxying
* routing
* mature HTTP handling
* separation between frontend and backend

It remains useful until it becomes redundant.

⸻

24. Final Initial Architecture

The first stable version should therefore be:

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
                     /            \
                    ▼              ▼
           React static UI       /api/*
                                      │
                                      ▼
                               FastAPI :8000
                                      │
                                      ▼
                              PostgreSQL :5432

With:

heart/
├── apache2/
├── backend/
├── frontend/
├── services/
└── scripts/

and services:

apache2.service
cloudflared.service
postgresql.service
cesium-api.service

This gives Cesium Lab a path from being a locally stored website into an actual personal software platform without requiring a large rewrite.

Immediate Next Steps

* Create heart/backend/
* Install PostgreSQL
* Create the cesium database
* Create the first people table
* Create a minimal FastAPI application
* Run FastAPI on 127.0.0.1:8000
* Add cesium-api.service
* Configure Apache /api/ proxying
* Verify cesiumlab.net/api/... works
* Add authentication before importing real contacts
* Create heart/frontend/
* Build a React + TypeScript + Vite contacts interface
* Add search and person profile pages
* Import People from Notion
* Add Organizations and Interactions
* Expand into Events, Opportunities, Projects, and Songs
* Reevaluate whether Apache is still useful