"""Celery background tasks for Decalove story and asset generation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from app.domain.direction import DecisionContext
from app.domain.intent import PlayerIntent
from app.domain.state import BatchState
from app.runtime import build_runtime
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)

if celery_app is not None:
    _task_decorator = celery_app.task
else:
    def _task_decorator(*args, **kwargs):
        def _wrapper(fn):
            fn.delay = lambda *a, **kw: None
            return fn
        return _wrapper


@_task_decorator(name="app.tasks.generation_tasks.generate_batch_task", bind=True, max_retries=2)
def generate_batch_task(
    self=None,
    game_id: str = "",
    batch_id: str = "",
    intent_dict: dict[str, Any] | None = None,
    decision_dict: dict[str, Any] | None = None,
    speculative_key: str | None = None,
) -> dict[str, Any]:
    """Run batch generation in a Celery background worker process."""
    log.info("Starting Celery batch generation for game %s, batch %s", game_id, batch_id)

    async def _run():
        runtime = await build_runtime(settings)
        try:
            intent = PlayerIntent.model_validate(intent_dict)
            decision = DecisionContext.model_validate(decision_dict)
            session = await runtime.games.get(game_id)
            if session is None or session.ended:
                return {"status": "skipped", "game_id": game_id}

            batch = BatchState(batch_id=batch_id, source="action")
            await runtime.generation._run_batch(
                game_id,
                batch,
                intent,
                decision,
                session.model_copy(deep=True),
                prepared=None,
            )
            return {"status": "success", "game_id": game_id, "batch_id": batch_id}
        finally:
            await runtime.close()

    try:
        return asyncio.run(_run())
    except Exception as exc:
        log.exception("Celery batch generation task failed for game %s: %s", game_id, exc)
        raise self.retry(exc=exc, countdown=2)


@_task_decorator(name="app.tasks.generation_tasks.generate_assets_task", bind=True, max_retries=1)
def generate_assets_task(
    self=None,
    game_id: str = "",
    specs_dicts: list[dict[str, Any]] | None = None,
    world_id: str = "",
) -> dict[str, Any]:
    """Run image generation in a Celery background worker process."""
    from app.agents.visual import AssetSpec

    async def _run():
        runtime = await build_runtime(settings)
        try:
            specs = [AssetSpec(**d) for d in specs_dicts]
            await runtime.generation._fill_assets(game_id, specs)
            return {"status": "success", "game_id": game_id, "count": len(specs)}
        finally:
            await runtime.close()

    try:
        return asyncio.run(_run())
    except Exception as exc:
        log.exception("Celery asset generation task failed for game %s: %s", game_id, exc)
        return {"status": "failed", "error": str(exc)}
