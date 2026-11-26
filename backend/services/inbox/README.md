# Inbox

Drop anything into **`/inbox/`** through the day: a note, a link (an Instagram reel, a recipe), a
photo of something you want to make or buy, and a line about what it's for ("for reminding me to
get flowers later"). Every evening the day's entries arrive in your email, ready to sort through
with Claude or ChatGPT.

```text
phone / laptop → https://cesiumlab.net/inbox/   (login page)    ┐
                 http://mr-ray/inbox/           (home WiFi)     ├→ Apache → inbox :42904
                 http://mr-ray/inbox/           (Tailscale)     ┘     → /srv/data/inbox/<day>/
9 pm daily → Gmail → you@gmail.com (entries, photo thumbnails, a block to paste into Claude)
```

## Using it

- **Save:** one text box plus an optional file picker (on a phone it offers the camera). Save,
  and the entry shows under "Today". Text-only and file-only entries are both fine. The upload
  limit per entry or reply (all its files together) shows under the box ("Files up to …"):
  **95 MB from the web** (Cloudflare's free plan refuses anything over 100 MB) and **1 GB at home
  or on Tailscale** (tentative; `INBOX_HOME_UPLOAD_MB`). Uploads stream straight to disk
  (`.uploading/` in the inbox folder, then renamed into the day), so big files don't sit in RAM.
- **Each entry records** its local time with zone (`14:54:32 PST`), UTC, Unix time, and where it
  was sent from: `home network 192.168.0.42`, `Tailscale 100.120.196.52`, or
  `internet 203.0.113.5 (via cesiumlab.net)`.
- **IDs, Jira-style:** each entry is `2026-11-23#5`, its replies `#5.1`, `#5.2` (fixed numbers, never
  reused after deletes). `/inbox/2026-11-23#5` opens that day and selects entry 5; `#5.1` highlights
  that reply.
- **References:** type `#5` (same day), `#5.2` (a reply), or `2026-11-20#3` (another day) in a note
  and it becomes a link. `#` + digits only, so `#flowers` stays plain text.
- **Listen & watch** (`listen.py`): the checklist on the public `/music/` page, stored in
  `/srv/data/notes/listen.md`. `GET /inbox/listen.json` is public (read-only);
  `POST /inbox/listen/add|toggle|delete` need home/Tailscale or the inbox login. Titles come from
  the link: YouTube and Shorts (title + channel), Spotify (title), Instagram reels (the caption).
- **Status page** (`/inbox/status`): runs `scripts/status.sh` (read-only, ~2 s) and shows its
  output with its colors: services, APIs, upstream, docker, disks, hashcheck progress. Checks when
  opened; **Refresh** checks again. Same access as the inbox (open at home / on Tailscale, login
  elsewhere).
- **Day buttons** (← · Today · →) switch days in place, without a full reload, so fast clicks
  all register (Chrome ignores clicks during a reload).
- **Pin**: click the 📌 at an entry's top right (entries only, not replies or files) to pin or
  unpin it; gray and faint when unpinned, full color when pinned. Pinned entries show on the **Pinned page**
  (`/inbox/pins`, linked as "Pinned (N)" under the title), which lists them from every day.
  Hovering a pinned 📌 shows "go to pinned", to its left, linking to `/inbox/pins/<day>/<n>` (that
  card highlighted). The Pinned page has the same entry actions as a day page (📌, Reply,
  Edit, Copy, Raw, replies), plus Delete… per entry, an add box ("pencil pencil.") that saves to
  today **and pins** the new entry, and "Email pinned…" (a To box, then Send) for the whole list
  (no SMTP set: saves `pins-preview.eml` in the inbox folder). Delete… on the Pinned
  page is the same real delete (password; the entry with all its files and replies). Stored as a
  `_pinned_` line in the entry's block; the 9pm email ends with the list of pinned entries.
- **Reply** (arrow icon on an entry): a note and/or files, shown indented under the entry, with
  its own copy/edit/delete icons (delete asks for the password). Stored in the entry's day file as
  `### 5.1 · time`. Deleting an entry whole takes its replies with it.
- **Edit** (pencil icon): change an entry's or reply's note in place (overwrites; no history). It
  then shows "edited"; hover for the time.
- **Open as text** (box-arrow icon): the note alone as plain text in a new tab
  (`/inbox/2026-11-23/5.1.txt`).
- **Select entries** with their checkboxes: shift-click ticks a range, **Select all** (top of the
  list) ticks everything. A bar then offers:
  - **Copy**: the selected entries as text, ready to paste into Claude/ChatGPT.
  - **Export .zip**: `selected.md` (same format as `inbox.md`) plus their photos and files.
  - **Delete…**: confirm with your username and password (always, even at home).
    - An entry selected with all its files ticked is deleted whole.
    - An entry selected with some files unticked loses its note and the ticked files; the
      unticked files stay, as an entry without text.
    - Files ticked on their own are deleted alone; their entry's note stays.
    - Replies have selection circles too (click anywhere on a reply). Ticked replies are deleted
      alone. An entry is never deleted without all of its replies: if a selected entry has an
      unticked reply, Delete is blocked until you tick them all (or untick the entry). When an
      entry's note is deleted (even if some of its files are kept), all its replies go too.
    - Once an entry has no note and no files left, it disappears from the list (its number
      isn't reused). Everything deleted moves to the day's `.deleted/` folder (`deleted.md` plus
      the files), so a mistake can be undone by hand.
- **Adding files:** each pick adds to a list under the box, each with an × to remove it, plus
  **Remove all files**. Over the limit, Save (and ⌘/Ctrl+Enter) turns off until you remove some.
- **Days:** `← yesterday` / `→` links browse past days; each day has **Copy for Claude** (the whole
  day as text), its raw `inbox.md`, and **Email this day…** (opens a To box with your address filled in; Send sends it, to anyone).
- **Tip:** add it to your iPhone home screen (Share → Add to Home Screen) so it opens like an app.

## Filing

Claude Code sorts entries into bucket lists in `/srv/data/notes/` (song ideas, licks, content
tips, business/production, later) with `filing.py`, after you approve its plan. Filed entries
stay here, marked "filed → licks.md". The lists are on the **Notes page** (`/inbox/notes/`,
linked next to Pinned): add, edit, move between lists, and delete, from the phone too. How it
works: [FILING.md](FILING.md).

## Files are the truth

```text
/srv/data/inbox/2026-11-23/inbox.md              # the day's entries, readable and pasteable
/srv/data/inbox/2026-11-23/143728-flowers.jpg    # files, prefixed with the time saved
/srv/data/inbox/2026-11-23/.digest-sent          # marker: today's email went out
```

`inbox.md` is plain Markdown: one `## HH:MM:SS` section per entry, the note as a `>` quote, and
links to its files. Nothing else stores state, so you can edit or delete entries by hand.

## Access

Apache only proxies `/inbox/`; the service decides who must log in.

- **No login** from the home LAN (`192.168.0.0/24`) and Tailscale (`100.64.0.0/10`), set by
  `INBOX_HOME_NETS`.
- **Login page** (username + password) from everywhere else, including everything through
  cesiumlab.net and mr-ray's second, shared WiFi (`10.27.150.x`).
  - A login lasts only for that tab: a new tab, reopening the home-screen app, or restarting the
    browser asks again. It also expires after `INBOX_IDLE_MIN` (10) minutes unused.
  - **Log out** (top right) appears only when you're logged in.
  - 5 wrong passwords from one address in 5 minutes lock it out for a while.
  - The session cookie is `HttpOnly`, `SameSite=Strict`, and `Secure` over https.
- **How it knows where you are:** mod_proxy appends the real visitor address to
  `X-Forwarded-For`; the service reads the _last_ entry, which visitors can't fake. Tunnel
  visitors arrive as `127.0.0.1` (never "home"); their real address comes from Cloudflare's
  `CF-Connecting-IP`, used only for the record. Keep Apache's `mod_remoteip` off (it is).
- The password is stored only as a PBKDF2 hash in `/etc/cesium/inbox.env`
  (`INBOX_PASSWORD_HASH`). Pages and files send `noindex`; the inbox isn't in the sitemap.

## Email

Through Gmail with an **app password** (Google Account → Security → 2-Step Verification → App
passwords; not your normal password), in `/etc/cesium/inbox.env` (template:
[`.env.example`](.env.example)). At `INBOX_DIGEST_HOUR` (default 21:00) the day's entries are sent
once (a restart won't resend); days with nothing saved send nothing. Without a password set, the
digest is written to the day folder as `digest-preview.eml` instead, so you can check it.

## Setup (changes the machine, so ask first)

```bash
.venv/bin/python backend/services/inbox/server.py hash-password    # type a password; copy the line
sudo install -m 0640 -o root -g cskin backend/services/inbox/.env.example /etc/cesium/inbox.env
sudoedit /etc/cesium/inbox.env      # username, the INBOX_PASSWORD_HASH line, Gmail + app password
./scripts/deploy/backends.sh        # venv (Pillow) + inbox.service
sudo systemctl restart inbox        # load the new code and settings
./scripts/deploy/apache.sh          # plain /inbox/ proxy (the service handles login)
./scripts/status.sh                 # inbox should show ok
```

To change the password later: run `hash-password` again, replace the line, restart `inbox`.

## Run locally

```bash
INBOX_DIR=/tmp/inbox .venv/bin/python backend/services/inbox/server.py   # http://127.0.0.1:42904/inbox/
# Run by hand there's no Apache in front, so it shows the login page (set INBOX_PASSWORD_HASH).
```

Config (env vars): `INBOX_USERNAME` (colin), `INBOX_PASSWORD_HASH`, `INBOX_IDLE_MIN` (10),
`INBOX_HOME_NETS`, `INBOX_SMTP_USER`, `INBOX_SMTP_PASS`, `INBOX_TO`, `INBOX_DIGEST_HOUR` (21),
`INBOX_DIR` (`/srv/data/inbox`), `INBOX_PORT` (42904), `INBOX_PUBLIC_URL`
(`https://cesiumlab.net/inbox/`, used for links in the email).
