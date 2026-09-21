# Writing courses and the Writing Studio

Open **Writing courses** (`#/courses`) or **Script & novel studio** (`#/studio`)
from the landing page. These are authoring tools separate from the playable visual
novel; writing a draft never changes a game, character relationship, or ending.

## Learn and practise

Six courses cover story structure, dialogue, theme, book planning, narration, and
revision. Each of the 18 lessons includes an explanation, deeper reading, an annotated
before/after example, common mistakes, a five-pass exercise, a concrete deliverable,
a review checklist, and a targeted AI revision brief. Practice notes and completion
progress save with the workspace. **Practice in the studio** creates a new document
with the exercise, craft guidance, and the learner's notes in its instructions.

The final project develops a 50-line scene through an encounter, resistance, a change
in understanding, a costly choice, and its consequence. Its review rubric checks
intention, causality, character voice, narration, theme, and continuity.

## Write and revise

The studio fills the window: the brief, the page and the side panel each scroll on their
own, and the toolbars stay above the paper they act on. The centre switches between the
**Manuscript** and the **Storyboard**; the side panel switches between the **AI partner**
and **Notes & comments**, and a request in flight survives that switch.

- Choose script or novel presentation; both keep editable dialogue, narration, and
  heading passages. The default AI scene target is **50 dialogue lines plus narration**.
- Start from a theme suggestion or write a custom premise, genre, and character notes.
  Paste an existing story or continuity summary into the reference notes.
- Select words to apply bold, italic, underline, one of eight **text colours** or one of
  eight **highlights**. With no text range selected, those buttons format the active
  passage. Fonts, size, alignment, and lists apply to a passage. A second colour over the
  same words replaces the first; the ⌀ swatch removes colour. A document stores the
  colour's name, never a value, so nothing a writer picks can reach a style attribute.
- Add, reorder, change the type of, and remove passages. Use undo/redo, find/replace,
  browser spelling assistance, focus mode, page zoom, word counts, and reading time.
- Use Ctrl/Cmd+B, I, or U for formatting, Ctrl/Cmd+F for find/replace inside the
  editor, Ctrl/Cmd+Z and Shift+Z for undo/redo, and Ctrl/Cmd+S to save the workspace.
- Import plain text, Markdown as plain text, or a Decalove JSON backup as a new document.
  Export `.txt` for portable prose or a JSON backup to retain notes and formatting.
  **Print** also supports the browser's Save as PDF destination.

AI can draft a scene, continue the manuscript, write a conversation, add narration,
or rewrite the selected passage. The request includes the current draft, exact author
instructions, brief, characters, and reference notes. Suggestions remain separate until
the writer inserts or replaces them; their text is editable in the review panel.
Changes typed during generation are preserved. A rewrite cannot replace a passage
whose text, type, or speaker changed while it was running.

## Pictures

**+ Image** puts an illustration in the manuscript, from the writer's own machine or from
the deployment's shared library. A picture is a passage: it can be captioned, described,
reordered, aligned, sized between a quarter and the full page width, replaced, and
removed. Its description is what an export writes and what a reader hears.

Bytes never travel inside the workspace. An upload is stored in the existing object store
under `writing/<workspace-id>/images/<sha256>.<ext>` and the document keeps the
identifier, so a repeated upload of the same picture is one object and an interrupted one
is safe to retry. Uploads are PNG, JPEG, WebP or GIF up to 5 MB, and the file's first
bytes must match the type it claims. Pictures are served back inline through a
workspace-scoped route with `nosniff`, not through the public game-art endpoint.

Anything an operator places under `writing/library/` is offered to every writer, inserted
by reference rather than copied. [docs/IMAGES.md](IMAGES.md) is the tutorial: the folder
layout of the bucket, and how to upload into it.

## Notes, comments and the storyboard

**Notes & comments** is the margin of the manuscript. A comment holds onto a passage but
never depends on it: rewriting or deleting the passage keeps the remark, shown
unanchored with the words it was left on, because losing a note with a paragraph is the
worse failure. Comments carry an optional name — the browser remembers the last one —
and are resolved, reopened, or deleted. A passage with open comments shows a marker that
opens them. Notes are free-standing cards with an optional colour from the same palette.

The **Storyboard** is the same scene told in frames. Each panel has a shot size, a title,
what the camera sees, one line heard over it, staging notes, and a picture chosen the
same way as an illustration. **Build from manuscript** drafts a first pass locally — a
heading opens a panel, narration describes it, the first spoken line tightens the shot —
and **Draft panels with AI** asks for an exact number of panels from the same author
context the writing partner uses. Both only ever add panels; nothing on the board edits
the manuscript. A storyboard prints on its own, and an exported `.txt` ends with the
shot list.

Each document holds up to 30 notes, 100 comments and 40 panels, inside the same 2 MB
workspace budget as everything else.

## Existing MongoDB and MinIO storage

The feature uses the same runtime connections and configuration as the rest of Decalove:

- MongoDB's **existing database** gains `writing_workspaces` and `writing_files`.
  Workspaces contain manuscripts, formatting, story notes, active document, course
  exercises, and completion progress. A revision guard prevents a stale tab from
  overwriting a newer save. Retrying an already committed identical save is idempotent.
- MinIO's **existing bucket** stores exported manuscripts, JSON backups and inserted
  pictures beneath `writing/<workspace-id>/…`, and the shared picture library under
  `writing/library/`. Content-derived object keys make retries safe. File metadata is
  published in MongoDB only after the object write succeeds. Downloads and pictures go
  through workspace-scoped API routes, not the public game-art endpoint.
- Autosave waits briefly after editing and serialises saves. Save failures retain the
  editable draft and expose retry and recovery download controls. The browser keeps
  a recovery cache and workspace identifier; it is not the primary storage system.

There is no new account system. The random workspace identifier is a capability:
anyone with its private link can open and edit that workspace. The browser remembers
it, and the **private workspace link** can open the same work on another device.
Clearing browser storage loses the remembered link, so retain the link or a backup.
When two tabs conflict, download a recovery copy before choosing **Load server version**.

In Docker, the existing `STORAGE_BACKEND=mongo` and `ASSET_BACKEND=minio` settings
provide persistent storage. To start just those services:

```bash
cd api
docker compose up -d mongodb minio
```

The MinIO image is `minio/minio` from Docker Hub, and its root credentials come from
`MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` in `api/.env` -- the same pair the API
authenticates with, so the server and the client cannot drift apart. See the
[upstream container documentation](https://github.com/minio/minio/blob/master/docs/docker/README.md).

For the local server, `auto` uses MongoDB and MinIO when reachable. The existing offline
memory/local seams still work; the writing UI labels those saves as temporary. No new
database, bucket, credentials, packages, or AI API keys are required beyond existing
Decalove configuration.

## API and failure handling

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/v1/writing/status` | AI availability and the default dialogue and panel counts |
| POST | `/api/v1/writing/assist` | A validated writing proposal |
| POST | `/api/v1/writing/storyboard` | A validated shot list of exactly the requested panels |
| GET | `/api/v1/writing/library` | Pictures an operator placed under `writing/library/` |
| POST | `/api/v1/writing/workspaces/{uuid}` | Open or idempotently create a workspace |
| PUT | `/api/v1/writing/workspaces/{uuid}` | Save with an expected revision |
| POST | `/api/v1/writing/workspaces/{uuid}/files` | Save a text export or JSON backup |
| GET | `/api/v1/writing/workspaces/{uuid}/files/{id}` | Download that workspace's file |
| POST | `/api/v1/writing/workspaces/{uuid}/images` | Store an uploaded picture |
| POST | `/api/v1/writing/workspaces/{uuid}/images/library` | Use a shared library picture |
| GET | `/api/v1/writing/workspaces/{uuid}/images/{id}` | That workspace's picture, inline |

Assistance reuses OpenRouter and the configured web-mode fallback providers. Attempts
are bounded to at most 45 seconds each and 110 seconds overall. Invalid counts, empty
passages, unsupported types, and invalid rewrites fail validation and try the next
provider. Exhaustion returns a retryable 503; **Retry same request** preserves the
original request even if the draft or prompt has since changed. Client cancellation
and disconnection cancel the pending provider call. Without an AI provider, manual
editing and courses remain available; authored game narration keeps its offline path.

Drafts are bounded to 1,000 passages and 120,000 characters each. Workspaces allow 50
documents and a 2 MB JSON library, so long books can be worked on chapter by chapter.
Reference notes allow 30,000 characters. Storage requests have a 12-second server
deadline and 20-second client deadline; a picture upload is allowed 45 seconds by the
client. The nginx API proxy accepts bounded workspace payloads including escaped Unicode
and a 5 MB picture as base64.

An illustration travels to the AI as context — so passage numbers still line up, and the
model can read its caption — but a proposal containing one is rejected, and an
illustration cannot be the target of a rewrite. Pictures are the author's to choose.

## Verification

```bash
cd api && .venv/bin/python -m pytest -q
cd ../frontend && npm test && npm run build && npm run lint
```

`test_writing.py` covers author context, exact dialogue and panel counts, failover,
timeouts, cancellation, illustrations as context but never as proposals, and isolation
from gameplay. `test_writing_storage.py` covers persistence, version conflicts,
idempotency, file and picture scoping, raster-only uploads, the shared library, and
object-store failure. The real MongoDB and MinIO round trip is in
`test_integration_writing.py` and skips when services are absent. Frontend tests cover
rich-text round trips, escaping, selection, colour by name, picture insertion, comments
that outlive their passage, notes, the storyboard, AI review, retry snapshots,
cancellation, concurrent edits, autosave recovery, and course progress. `document.test.ts`
pins the exported manuscript to the same bytes the server writes.

Provider responses in automated tests are deterministic fakes. Live model prose still
needs editorial review for coherence, repetition, voice, and continuity.
