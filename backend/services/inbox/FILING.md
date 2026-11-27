# Filing the inbox

The inbox is the raw log. Filing copies what's worth keeping into a few Markdown lists, so
they can be read on the phone and handed to Claude/ChatGPT. Claude Code does the sorting;
**Colin approves every change** (batch approval is fine).

## Buckets

One file per bucket in `/srv/data/notes/` (`NOTES_DIR`):

| File              | What goes in                                                     |
| ----------------- | ---------------------------------------------------------------- |
| `song-ideas.md`   | Lyrics, hooks, chord ideas, arrangements: a loose pile           |
| `licks.md`        | Guitar/piano things to learn (needs a video, audio, or tab link) |
| `music-tools.md`  | Tools and references: tab makers, stem splitters, songwriting guides, MONARCH links |
| `listen.md`       | Videos/songs to listen to or watch (the /music/ checklist; `done:` when checked off) |
| `content-tips.md` | Reels, hooks, posting times/habits, trial reels, editing         |
| `business.md`     | Business _and_ production: funding, shows, mixing, recording     |
| `later.md`        | Anything not about music that's worth keeping                    |

Once a song has a name, its ideas go to `/srv/data/music/<song>/lyrics/` instead of the pile.

## Item format

```markdown
## 3 lead guitar lines (newellshreds)

- from: [2026-11-25#4](/inbox/2026-11-25#4)
- filed: 2026-11-26
- link: https://www.instagram.com/reel/DgJpiXOyev4/
- caption: 3 lead guitar lines to add to your vocabulary! …
- file: /srv/data/inbox/2026-11-25/083552-tab.png
- note: Colin's own words, as written (can run over several lines: the lines
  after "- note:" are part of it; web addresses in it become links, bare ones like krillion.io too)
- thumb: thumbs/DgJpiXOyev4.jpg
```

- No status: delete an item from the Notes page once it's learned or done.
- **Links stay as-is** (the video is the point). The caption is scraped from Instagram's embed
  page or YouTube's oEmbed and cached in `/srv/data/inbox/.captions.json`. The thumbnail is
  saved to `notes/thumbs/` when filed (Instagram's image links expire); `filing.py thumbs`
  fills in any that are missing.
- The title is short and descriptive. Base it on Colin's words plus the caption; never invent
  what a video shows.
- One entry can become several items: each reel in its replies gets its own item.

## A sorting session

1. `.venv/bin/python backend/services/inbox/filing.py unfiled` lists every entry without a
   filed mark, with captions.
2. Show a table: id, what it is, and the proposed action: `file → bucket` (with title),
   `delete` (only entries with no real content: tests, "hm", "ok new"), or `ask` when unsure.
3. After Colin approves (all, or with changes), write the plan as JSON and run
   `filing.py apply plan.json`:
   ```json
   [
     {
       "id": "2026-11-25#4",
       "action": "file",
       "bucket": "licks",
       "title": "…",
       "links": ["…"],
       "caption": "…",
       "files": [],
       "note": "licks"
     },
     { "id": "2026-11-23#5", "action": "delete" }
   ]
   ```
4. Filed entries get a `_filed → licks.md_` line and show "filed → licks.md" in the inbox.
   Deleted ones move to that day's `.deleted/`. `filing.py unmark <id>` clears a mark.

## The Notes page

`/inbox/notes/` (same access as the inbox; linked as "Notes" next to "Pinned") lists the
buckets; each bucket page shows its items with thumbnail, caption (tap to expand), note, files,
and a link back to the inbox entry. On any device:

- **+ Add**: a link, optional title (otherwise from the caption), note. Fetches caption + thumb.
- **Edit**: title and note in place.
- **Select** items, then **Move to…** another bucket or **Delete** (a confirm, no password;
  deleted items are appended to `notes/.deleted.md`).
- Every form carries the list's version, so if the file changed meanwhile (another tab, a
  filing run) nothing happens and the page says to try again.

## File ▾ (one entry at a time, from the inbox)

Each entry's actions row has **File ▾**: the five buckets, with a ★ on the likely one (a
keyword guess from the note, replies, and any cached reel caption: `notes.GUESS`; no hits →
Later). Picking a bucket writes the item in the same format as `filing.py` (title from the reel
caption, or the note's first line), saves the thumbnail, and marks the entry `filed → …`.
Buckets it's already in show ✓; picking another adds it there too, and picking a ✓ one
takes it back out (after a confirm; the note goes to `notes/.deleted.md`). The ★ is only a guess:
nothing is filed until you pick. Claude Code's batch filing (below) still works for writing
better titles over many entries at once.

## Links both ways

- A note's "from 2026-11-25#4" opens the inbox entry it came from.
- An inbox entry's "filed → licks.md" opens that note on its bucket page (scrolled to and
  highlighted). It goes through `/inbox/notes/find/<day>/<n>`, which looks in the bucket it was
  filed to first, then all buckets, so it still works after a note is moved. If the note was
  deleted, it says so.

## On /music/

Licks to learn, Song ideas, and Music tools are shown **publicly, read-only** on `/music/`
(`notes.PUBLIC_BUCKETS`, served by `GET /inbox/music.json`): titles, links, notes, captions only;
never files, thumbnails, or the inbox "from" links. Listen & watch is the checklist there. Edit
everything in `/inbox/notes/`; the page shows "Edit in Notes" links when you're home or logged in.
