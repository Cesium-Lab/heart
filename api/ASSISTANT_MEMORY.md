# Personal Assistant Memory Integration

## Goal

Use the Cesium Lab backend as the persistent memory layer for a personal assistant AI.

The assistant should not maintain a completely separate infrastructure stack. It should use the same:

- FastAPI backend
- PostgreSQL database
- authentication
- Cloudflare Tunnel
- backup system

as the rest of Cesium Lab.

```text
Personal Assistant
       │
       ▼
Cesium API
       │
       ▼
PostgreSQL
```

---

## Architecture

```text
                         PostgreSQL
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
           People         Memories       Projects
              │              │              │
              └──────────────┼──────────────┘
                             │
                             ▼
                       FastAPI :8000
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
          Cesium Lab UI           Personal Assistant
```

The assistant becomes another client of the Cesium API rather than owning the database itself.

---

## Memory Table

Start with a general `memories` table.

```text
memories
------------------------------------------------
id                  UUID PRIMARY KEY
content             TEXT
memory_type
importance
source
created_at
updated_at
last_accessed_at
```

Possible `memory_type` values:

```text
fact
preference
goal
decision
lesson
context
```

Examples:

```text
"Colin prefers..."
"Current goal is..."
"Decided to use Astro for..."
"Project X is currently..."
```

---

## Link Memories to Existing Data

Memories should be relational when possible rather than isolated text blobs.

```text
memory_people
memory_projects
memory_organizations
memory_events
memory_songs
```

For example:

```text
Memory
"Met Alex at the release show and discussed collaborating."
   │
   ├── Person → Alex
   ├── Event → Release Show
   └── Opportunity → Collaboration
```

This allows the assistant to retrieve context through actual relationships.

---

## Structured Data vs Memory

Avoid duplicating structured information into the memory system.

For example:

```text
people.location = "Los Angeles"
```

should live in `people`, not as a memory saying:

```text
"Alex lives in Los Angeles."
```

Use `memories` for information that does not naturally belong in an existing structured field.

The assistant can retrieve both:

```text
structured database records
+
relevant memories
=
assistant context
```

---

## Assistant API

Add assistant-oriented endpoints to FastAPI.

```http
GET  /assistant/context
GET  /assistant/memories
POST /assistant/memories
GET  /assistant/search?q=...
```

Eventually:

```http
GET /assistant/context?person={id}
GET /assistant/context?project={id}
GET /assistant/context?topic=music
```

The context endpoint can gather related information from multiple tables before returning it to the AI.

---

## Retrieval

A request could work like:

```text
User
 ↓
Personal Assistant
 ↓
"What context is relevant to this?"
 ↓
FastAPI
 ↓
PostgreSQL
 ↓
People + Projects + Memories + Interactions + Events
 ↓
Relevant context
 ↓
Personal Assistant
 ↓
Response
```

Start with normal PostgreSQL queries and full-text search.

Semantic/vector retrieval can be added later if the memory collection becomes large enough to justify it.

---

## Writing Memories

The assistant should be able to propose or create memories through the API.

```text
Conversation
    ↓
Assistant identifies durable information
    ↓
POST /assistant/memories
    ↓
PostgreSQL
```

Not every message should become a memory.

Prefer information that is:

- durable
- useful in future conversations
- connected to a goal, person, project, or decision
- difficult to reconstruct later

---

## Cesium Lab Frontend

Add a private memory interface to the Astro application:

```text
app.cesiumlab.net/
├── /memory
├── /memory/:id
└── /assistant
```

Useful tools:

- search memories
- inspect what the assistant knows
- edit incorrect memories
- delete memories
- see linked people/projects
- see memory source
- filter by memory type

The user should be able to inspect and control the assistant's persistent memory.

---

## Security

Assistant memory is private data.

Use the same security model as the rest of the private Cesium Lab system:

```text
Assistant / Private UI
        ↓
Cloudflare Access / API authentication
        ↓
Cloudflare Tunnel
        ↓
FastAPI
        ↓
PostgreSQL
```

Do not expose PostgreSQL directly.

---

## Initial Implementation

- [ ] Add `memories` table
- [ ] Add `memory_people`
- [ ] Add `memory_projects`
- [ ] Add other relationship tables as needed
- [ ] Add `/assistant/memories` API
- [ ] Add `/assistant/search`
- [ ] Add `/assistant/context`
- [ ] Build `/memory` in the Astro frontend
- [ ] Allow memories to be inspected/edited/deleted
- [ ] Connect the personal assistant to the Cesium API
- [ ] Add semantic/vector retrieval later only if useful

## Principle

Cesium Lab should become the shared knowledge layer:

```text
People
Organizations
Interactions
Events
Projects
Songs
Memories
     │
     ▼
PostgreSQL
     │
     ▼
FastAPI
     │
     ├── Cesium Lab
     ├── Personal Assistant
     ├── scripts
     └── future agents
```

The personal assistant is therefore not a separate database system. It is an intelligent interface over the same personal knowledge graph used by the rest of Cesium Lab.