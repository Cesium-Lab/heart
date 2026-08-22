# Cesium Lab Music Storage Schema

## Goal

Use the mounted hard drive as the canonical store for large music files, while PostgreSQL stores searchable metadata and relationships.

The system should make it easy to answer questions like:

- What is the latest recording of this song?
- Where is the master file?
- Which files belong to this recording session?
- Which songs have live videos?
- Which recordings include a specific collaborator?
- Which files are missing or moved?
- Which project/session created this file?

The core principle is:

```text
Mounted hard drive = actual files
PostgreSQL         = catalog + metadata + relationships
FastAPI            = controlled interface to both
```

---

## 1. Storage Layout

Example mounted path:

```text
/mnt/music/
```

Possible directory structure:

```text
/mnt/music/
├── originals/
├── covers/
├── live/
├── demos/
├── sessions/
├── stems/
├── masters/
├── video/
├── artwork/
└── projects/
```

The database should not depend on this exact folder hierarchy.

Files should be identified by stable database IDs and checksums, while `path` records where the file currently lives.

---

## 2. Core Tables

Recommended initial tables:

```text
songs
recordings
music_files
recording_files
sessions
session_people
song_people
performances
performance_songs
projects
project_songs
```

The most important relationships are:

```text
Song
 ├── Recording
 │    └── Files
 │
 ├── Performance
 │    └── Files
 │
 ├── Collaborators
 └── Projects
```

---

## 3. `songs`

Represents the conceptual song, independent of any specific recording.

```sql
songs
------------------------------------------------------------
id                  UUID PRIMARY KEY
title               TEXT NOT NULL
slug                TEXT UNIQUE
song_type            TEXT
status               TEXT
project_id           UUID NULL
key                   TEXT NULL
bpm                   NUMERIC NULL
performance_ready     BOOLEAN DEFAULT FALSE
notes                 TEXT NULL
created_at            TIMESTAMPTZ NOT NULL
updated_at            TIMESTAMPTZ NOT NULL
```

Suggested `song_type` values:

```text
original
cover
idea
```

Suggested `status` values:

```text
idea
writing
demo
arranging
rehearsing
recording
ready
released
```

---

## 4. `recordings`

Represents a specific version, take, demo, mix, or master of a song.

A recording can have multiple files.

```sql
recordings
------------------------------------------------------------
id                  UUID PRIMARY KEY
song_id             UUID REFERENCES songs(id)
title               TEXT NULL
recording_type      TEXT
version_label       TEXT NULL
recorded_at         TIMESTAMPTZ NULL
session_id          UUID NULL
is_primary          BOOLEAN DEFAULT FALSE
notes               TEXT NULL
created_at          TIMESTAMPTZ NOT NULL
updated_at          TIMESTAMPTZ NOT NULL
```

Suggested `recording_type` values:

```text
voice_memo
demo
rehearsal
live
tracking
rough_mix
mix
master
alternate
```

Example:

```text
Song: FOMO

Recording 1
type: voice_memo
version: first chorus idea

Recording 2
type: demo
version: acoustic demo

Recording 3
type: master
version: release master
```

---

## 5. `music_files`

Represents an actual file on the mounted hard drive.

Do not store the file contents in PostgreSQL.

```sql
music_files
------------------------------------------------------------
id                  UUID PRIMARY KEY

path                TEXT NOT NULL UNIQUE
filename            TEXT NOT NULL
extension           TEXT NULL
mime_type           TEXT NULL

file_type           TEXT NULL

size_bytes          BIGINT NULL
modified_at_fs      TIMESTAMPTZ NULL

checksum_sha256     TEXT NULL

duration_seconds    NUMERIC NULL
sample_rate_hz      INTEGER NULL
bit_depth           INTEGER NULL
channels            INTEGER NULL

video_width         INTEGER NULL
video_height        INTEGER NULL
frame_rate          NUMERIC NULL

exists_on_disk      BOOLEAN DEFAULT TRUE

indexed_at          TIMESTAMPTZ NULL
created_at          TIMESTAMPTZ NOT NULL
updated_at          TIMESTAMPTZ NOT NULL
```

Suggested `file_type` values:

```text
audio
video
project
stem
midi
lyrics
chord_chart
image
artwork
document
other
```

Example:

```text
id:
    8eae...

path:
    /mnt/music/originals/fomo/mixes/fomo-master.wav

filename:
    fomo-master.wav

file_type:
    audio

checksum_sha256:
    ...
```

---

## 6. `recording_files`

Join table connecting recordings to their physical files.

```sql
recording_files
------------------------------------------------------------
recording_id        UUID REFERENCES recordings(id)
file_id             UUID REFERENCES music_files(id)

role                TEXT NULL
track_name          TEXT NULL
track_number        INTEGER NULL

PRIMARY KEY (recording_id, file_id)
```

Suggested `role` values:

```text
master
mix
rough_mix
instrumental
acapella
stem
multitrack
reference
project_file
bounce
video
artwork
lyrics
```

This allows one recording to contain:

```text
Recording: FOMO final

├── master.wav
├── instrumental.wav
├── vocal.wav
├── guitar-left.wav
├── guitar-right.wav
├── session.logicx
└── cover-art.png
```

---

## 7. `sessions`

Represents a recording, rehearsal, writing, or production session.

```sql
sessions
------------------------------------------------------------
id                  UUID PRIMARY KEY
name                TEXT
session_type        TEXT
started_at          TIMESTAMPTZ NULL
ended_at            TIMESTAMPTZ NULL
location            TEXT NULL
project_id          UUID NULL
notes               TEXT NULL
created_at          TIMESTAMPTZ NOT NULL
updated_at          TIMESTAMPTZ NOT NULL
```

Suggested `session_type` values:

```text
writing
recording
rehearsal
production
mixing
mastering
jam
```

---

## 8. `session_people`

Links people to sessions.

```sql
session_people
------------------------------------------------------------
session_id          UUID REFERENCES sessions(id)
person_id           UUID REFERENCES people(id)
role                TEXT NULL

PRIMARY KEY (session_id, person_id)
```

Example roles:

```text
artist
guitar
vocals
producer
engineer
photographer
guest
```

---

## 9. `song_people`

Links collaborators and contributors directly to songs.

```sql
song_people
------------------------------------------------------------
song_id             UUID REFERENCES songs(id)
person_id           UUID REFERENCES people(id)
role                TEXT NULL
notes               TEXT NULL

PRIMARY KEY (song_id, person_id, role)
```

Possible roles:

```text
writer
composer
performer
producer
engineer
featured_artist
arranger
```

---

## 10. `performances`

Represents an actual live performance.

```sql
performances
------------------------------------------------------------
id                  UUID PRIMARY KEY
event_id            UUID NULL
project_id          UUID NULL
performed_at        TIMESTAMPTZ NULL
venue               TEXT NULL
notes               TEXT NULL
created_at          TIMESTAMPTZ NOT NULL
updated_at          TIMESTAMPTZ NOT NULL
```

If an `events` table already exists, `event_id` should reference it.

---

## 11. `performance_songs`

Represents the setlist and ordering.

```sql
performance_songs
------------------------------------------------------------
performance_id      UUID REFERENCES performances(id)
song_id             UUID REFERENCES songs(id)

set_order           INTEGER NULL
notes               TEXT NULL

PRIMARY KEY (performance_id, song_id)
```

Later, if the same song may appear twice in a performance, replace this composite primary key with a UUID row ID.

---

## 12. Performance Files

Live photos, board recordings, and videos can use the same `music_files` table.

Add a join table:

```sql
performance_files
------------------------------------------------------------
performance_id      UUID REFERENCES performances(id)
file_id             UUID REFERENCES music_files(id)

role                TEXT NULL

PRIMARY KEY (performance_id, file_id)
```

Suggested roles:

```text
board_audio
room_audio
video
photo
multicam
social_clip
```

---

## 13. `projects`

If Cesium already has a general `projects` table, reuse it.

Examples:

```text
MONARCH
Colin After Hours
Knockoff
EP 1
Recording Project — FOMO
```

Connect songs through:

```sql
project_songs
------------------------------------------------------------
project_id          UUID REFERENCES projects(id)
song_id             UUID REFERENCES songs(id)

PRIMARY KEY (project_id, song_id)
```

---

## 14. File Indexing

Create a background script that scans the mounted drive.

Example:

```text
/mnt/music/
    ↓
music indexer
    ↓
stat file
    ↓
calculate checksum if needed
    ↓
read audio/video metadata
    ↓
update music_files
```

Possible script:

```text
heart/scripts/index-music.py
```

The indexer should:

- discover new files
- update paths
- update modified times
- detect deleted/missing files
- calculate checksums
- extract audio metadata
- extract video metadata
- avoid creating duplicate rows for identical files

---

## 15. File Identity

Do not rely only on file paths.

Files can move.

Use:

```text
database UUID
+
checksum
+
current path
```

Example:

```text
music_file.id
    = stable Cesium identity

music_file.checksum_sha256
    = content identity

music_file.path
    = current filesystem location
```

If:

```text
/mnt/music/demos/fomo.wav
```

moves to:

```text
/mnt/music/originals/fomo/demos/fomo.wav
```

the indexer should ideally update the existing file record rather than creating a new one.

---

## 16. Recommended Filesystem Rules

The database should tolerate messy folders, but a predictable structure will still help.

Suggested pattern:

```text
/mnt/music/
├── projects/
│   ├── monarch/
│   ├── colin-after-hours/
│   └── knockoff/
│
├── songs/
│   └── fomo/
│       ├── demos/
│       ├── sessions/
│       ├── stems/
│       ├── mixes/
│       └── masters/
│
├── live/
│   └── 2026-08-22-show-name/
│
└── archive/
```

Do not make folder organization the source of truth.

PostgreSQL should remain the authoritative catalog.

---

## 17. FastAPI Endpoints

Useful initial endpoints:

```http
GET /songs
GET /songs/{id}

GET /songs/{id}/recordings
GET /songs/{id}/files
GET /songs/{id}/performances

GET /recordings/{id}
GET /recordings/{id}/files

GET /files/{id}
GET /files/search?q=...

GET /performances/{id}
GET /performances/{id}/files
```

Administrative/indexing endpoints could include:

```http
POST /admin/music/reindex
GET  /admin/music/index-status
```

Keep these private.

---

## 18. File Access

FastAPI can optionally expose protected file access.

Example:

```http
GET /files/{id}/download
GET /files/{id}/stream
```

Flow:

```text
Client
  ↓
FastAPI auth
  ↓
lookup music_files.path
  ↓
read mounted drive
  ↓
stream file
```

Do not expose `/mnt/music/` as a raw public directory.

---

## 19. Search

Useful music search should combine structured metadata and file metadata.

Examples:

```text
"FOMO"
"latest master"
"MONARCH rehearsal"
"live video UCLA"
"files involving Alex"
"all demos from August"
```

FastAPI can query:

```text
songs
recordings
sessions
people
performances
music_files
```

together.

---

## 20. Example Relationship

```text
Song
FOMO
│
├── Collaborator
│   └── Person A
│
├── Recording
│   ├── Acoustic Demo
│   │   ├── fomo-demo.wav
│   │   └── fomo-demo.logicx
│   │
│   └── Final Master
│       ├── fomo-master.wav
│       ├── instrumental.wav
│       └── artwork.png
│
└── Performance
    └── Aug 22 Show
        ├── board.wav
        ├── camera-1.mov
        └── social-clip.mp4
```

The files remain on disk.

The relationships live in PostgreSQL.

---

## 21. Initial Implementation Order

- [ ] Create `songs`
- [ ] Create `recordings`
- [ ] Create `music_files`
- [ ] Create `recording_files`
- [ ] Create `sessions`
- [ ] Link sessions to People
- [ ] Create `performances`
- [ ] Create `performance_songs`
- [ ] Create `performance_files`
- [ ] Write `index-music.py`
- [ ] Scan `/mnt/music/`
- [ ] Extract basic file metadata
- [ ] Add checksums
- [ ] Add FastAPI read endpoints
- [ ] Add protected stream/download endpoints if useful
- [ ] Build music browser UI in Astro
- [ ] Add automatic/repeated indexing later

---

## Final Model

```text
Mounted Hard Drive
      │
      │ files
      ▼
 /mnt/music/
      │
      │ indexed by
      ▼
PostgreSQL
├── songs
├── recordings
├── sessions
├── performances
├── music_files
└── relationships
      │
      ▼
FastAPI
      │
      ├── Astro frontend
      ├── personal assistant
      ├── MCP tools
      └── scripts
```

The hard drive stores the media.

PostgreSQL explains what the media is.

Cesium Lab makes it searchable, relational, and usable by both humans and AI.
