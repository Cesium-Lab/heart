# SilverBullet (docs.cesiumlab.net)

> **Live at https://docs.cesiumlab.net/docs/ (2026-11-26), login required.** SilverBullet 3 runs
> in multi-space mode, set up through its first-run wizard (the `SB_USER` line in
> `/etc/cesium/silverbullet.env` is ignored). Layout of `/srv/data/docs` (= `/space` in the container):
>
> - `server.json` (server address `https://docs.cesiumlab.net`), `spaces.json`, `users.json`
>   (admin `cskin`, hashed password), `.silverbullet.*.json` sessions: server config, kept out of
>   the space so they can't be opened as pages. SilverBullet warns they're world-readable; exFAT
>   can't change that (only local users on mr-ray could read them).
> - `spaces/<space id>/`: the `docs` space's pages (`index.md`, `Journal/`, `Library/`), served
>   at `/docs/`. An empty `folder` in `spaces.json` means this default location.
>
> Unauthenticated requests get the app shell at `/docs/` and 401 for every page and file.
>
> Spaces (made in `/.dashboard`, listed in `spaces.json`): **`docs`** at `/docs/` (home, Content,
> MONARCH, Engineering hubs) in `spaces/<id>/`, and **`music`** at `/music/` (songs, practice,
> gear) in `spaces/music/`. Both require the login.

A browser editor for the Markdown files in **`/srv/data/docs`**: pages, links between pages,
search, checklists, live preview, on phone or desktop. The files stay plain `.md` on the data
drive (files are the truth), so they're also covered by hashcheck and open fine in Obsidian or
any editor (for example over the Samba share).

- Docker (`docker-compose.yaml`), `127.0.0.1:42905`, behind Apache's `docs.cesiumlab.net`
  vhost (`deploy/apache/sites-available/docs.conf`) and the Cloudflare tunnel.
- **Login always**, everywhere: the admin account made in the first-run setup (stored hashed in
  `users.json`). Manage users and spaces at `/.dashboard`.
- `/srv/data/notes` (the inbox's Notes buckets) is deliberately **not** in here, so hand edits
  can't break the Notes page format.

## Set up (once)

1. Login file:
   ```bash
   sudo install -m 0640 -o root -g cskin /dev/null /etc/cesium/silverbullet.env
   sudoedit /etc/cesium/silverbullet.env     # SB_USER=colin:<long password>
   ```
2. Start it and add the Apache site:
   ```bash
   ./scripts/deploy/docs.sh       # creates /srv/data/docs, pulls and starts the container
   ./scripts/deploy/apache.sh     # installs + enables docs.conf, reloads Apache
   ```
3. Cloudflare (dashboard, since the tunnel is token-managed): Zero Trust → Networks → Tunnels →
   this tunnel → **Public hostname** → add `docs.cesiumlab.net` → service `http://localhost:80`
   (same as `dataviz.cesiumlab.net`). Cloudflare creates the DNS record.

Check: `curl -sI http://127.0.0.1:42905/` (a redirect to the login page), then open
https://docs.cesiumlab.net.

## Day to day

- Update: `docker compose -f backend/services/silverbullet/docker-compose.yaml pull && ./scripts/deploy/docs.sh`
- Logs: `docker compose -f backend/services/silverbullet/docker-compose.yaml logs --tail 50`
- If the data drive is unplugged, `docs.sh` refuses to start it (nothing lands on the system disk).
