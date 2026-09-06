# Decalove — web client

A self-hosted browser build of the Decalove client, for deploying the game yourself
instead of shipping a Ren'Py package. It is the same game: same API, same config
names, same static-art layout, same 1280×720 presentation as `game/`.

The backend owns the story; this owns presentation (PRD §20).

## Running it

```bash
cp .env.example .env      # point VITE_API_BASE at your API
npm install
npm run dev               # http://localhost:5173
```

The API must be running:

```bash
cd ../api && uvicorn app.main:app --reload --port 8000
```

`npm run build` produces a static `dist/` — plain files, no server-side rendering, so
any static host will do. The API sends `access-control-allow-origin: *`, so the client
can live on a different port or host; serve both over the *same scheme*, since a
browser blocks an https page calling an http API whatever CORS says.

| | |
|---|---|
| `npm run dev` | dev server with HMR |
| `npm run build` | typecheck + production bundle into `dist/` |
| `npm test` | the playback-machine tests |
| `npm run lint` | oxlint |

## Self-hosting

```bash
cd api && docker compose up -d      # game on :3000, API on :8000
```

That brings up MongoDB, MinIO, Redis, the API, both workers, and this client. The web
container serves the static bundle and proxies `/api/` to the API, so the browser sees
one origin — no CORS to satisfy, and no way to end up with an https page calling an http
API. `DECALOVE_WEB_PORT` in `api/.env` changes the published port.

Standalone, without the rest of the stack:

```bash
docker build -t decalove-web frontend/
docker run -p 3000:80 -e DECALOVE_API_BASE=https://api.example.com decalove-web
```

**The bundle is built once and configured where it runs.** Vite substitutes
`import.meta.env.VITE_*` at build time, which is the wrong lifetime for a self-hosted
image — it would mean one build per environment. So the container writes `/config.js`
from its own environment at start-up and the bundle reads that first, falling back to
the build-time value and then to a local default. `src/config.ts` holds the resolution
order; `docker-entrypoint.d/40-decalove-config.sh` writes the file.

Only what differs per deployment is runtime-configurable — `DECALOVE_API_BASE` and
`DECALOVE_API_PREFIX`. The tuning knobs (`WAIT_MS`, `AMBIENT_LIMIT`, `TEXT_SPEED_CPS`)
stay with the build: each runtime knob is another thing the entrypoint can get wrong and
another way to drift from `00_config.rpy`. See `.env.example` for the full list.

Two things in `nginx.conf.template` are load-bearing rather than decoration. The upstream
goes through a *variable*, because nginx resolves a literal `proxy_pass` host once at
start-up and refuses to boot if it cannot — so the standalone case above, where the proxy
is unused, would have failed on a DNS name it never needed. And `proxy_buffering off`
with a generous `proxy_read_timeout`, because `/steps/batch?wait_ms=` holds the
connection open on purpose (PRD §11) and a buffering proxy turns that into a timeout the
client reads as an outage.

## How it maps to the Ren'Py client

Every file here is a port of one there, and the names are kept so a change in one is
findable in the other.

| Ren'Py | Web | |
|---|---|---|
| `game/decalove/00_config.rpy` | `src/config.ts` | same knobs, same defaults, same reasons |
| `game/decalove/10_api.rpy` | `src/api/client.ts` | never throws; `null` + `lastError` |
| `game/decalove/20_art.rpy` | `src/game/art.ts` | palette gradients, static-file probing |
| `game/decalove/30_state.rpy` | `src/game/machine.ts` | session state |
| `game/decalove/40_screens.rpy` | `src/components/` | choice menu, offline, expired |
| `game/decalove/50_player.rpy` | `src/game/machine.ts` + `src/hooks/useDecalove.ts` | the playback loop |
| `game/decalove/60_static_opening.rpy` | `src/game/opening.ts` | authored opening, as data |
| `game/script.rpy` | `src/App.tsx` | boot → intro → setup → opening → play |
| `game/gui.rpy` | `src/index.css` `@theme` | palette, type scale, box geometry |

Two things are shaped differently on purpose:

**The loop is a state machine.** `decalove_play` is a `while True` whose blocking calls
(`renpy.say`, `renpy.input`, `renpy.call_screen`) *are* the waiting. A browser has no
equivalent, so the loop is turned inside out: the player's click is the iteration and
`reduce()` is one step of it. Every rule the loop encoded survives as a transition, and
`machine.test.ts` asserts them.

**The opening is data, not script.** `60_static_opening.rpy` is imperative Ren'Py;
`opening.ts` is a list of step-shaped objects. That means it plays through the same
renderer and the same decision handling as anything the API sends — the only thing
special about those beats is that they need no network.

## What is deliberately not here

Save/load slots, the history backlog, the preferences screen, skip and auto-forward.
Rollback is absent for the reason `00_config.rpy` gives for disabling it: the server's
step cursor only moves forward, so a rewind would quietly desynchronise the transcript
from the world state. A save is a bookmark, not a rewind point.

## Art

`public/images/` mirrors `game/images/`, and the same pre-generation scripts fill it:

```
public/images/bg/<location_id>.png
public/images/characters/<character_id>.png
public/images/characters/<character_id>/<expression>.png
```

Its contents are gitignored, exactly as `game/images/` is. Resolution order per beat is
the Ren'Py one: a generated image from the API, then a static file, then a gradient
built from the palette the API serves with `/worlds`. The gradient is not an error
state — it is keyed to the palette, so a place looks the same every time you are in it
(PRD §26), and the game stays playable with image generation switched off entirely.
