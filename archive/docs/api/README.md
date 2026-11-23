# Retired: the Aug 2026 "personal platform" plan

These docs planned to turn cesiumlab.net into a platform: FastAPI at `api.cesiumlab.net`,
PostgreSQL as the source of truth, login, a private app, a React or Astro frontend, and
eventually retiring Apache for Cloudflare Pages.

None of that was built, and the direction changed: files are the truth, small services, Astro
build served by Apache. The current architecture is in `architecture/`. Ideas that survived
(contacts, Coda, Juice) are in `architecture/ideas.md`.

Kept for history and for the people/contacts data model in `BIG.md` and `BACKEND.md`.
