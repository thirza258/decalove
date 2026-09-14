# Working on Decalove

Decalove has a FastAPI story engine (`api/`), a React/Vite client (`frontend/`), and a
Ren'Py client (`game/`). Read `docs/STORY.md` before changing story direction.

## Story and state invariants

- The engine owns relationships, world state and endings. Model output is a proposal;
  validate it before queueing and apply its effects only on delivery.
- Ordinary runs have one decision. Any buffered tail stays in the same scene and has
  no relationship changes, emotions, flags or memories. It must work for every answer.
- Finales have no choice or prompt anywhere. The Director authorises the finale; the
  validator and commit path create the ending marker.
- Chapter briefs and character secrets are writer guidance, not completed events or
  shared character knowledge. Ground callbacks in delivered dialogue and memories.
- Preserve the player's exact free text and the accepted decision across retries.
  Cancellation must propagate; provider and memory outages must have bounded waits.
- Web deployments use AI failover and an explicit retry of the same turn on exhaustion.
  Offline deployments use the scripted narrator. Preserve both behaviours.
- Keep the static opening aligned in `api/app/agents/scripted.py`,
  `frontend/src/game/opening.ts`, and `game/decalove/60_static_opening.rpy`.
  The choice is server index 14; handoff ends at index 19. Its tail stays in the library.
- Keep character-memory inserts idempotent. Memory indexing is secondary to the story
  ledger and must not block delivery when its provider is unavailable.

## Verification

From `api/`, run `.venv/bin/python -m pytest -q`. The tests use offline providers;
MongoDB/MinIO integration tests skip when those services are absent. Use
`tests/test_story_stability.py` for failure-path and chapter regressions and
`tests/test_long_playthrough.py` for relationship balance through an ending.

For client changes, from `frontend/` run `npm test`, `npm run build`, and `npm run lint`.
New dependencies are not needed for ordinary story or agent changes. Run
`git diff --check` before handing changes back.
