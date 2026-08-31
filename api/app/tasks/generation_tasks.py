"""Celery background tasks for Decalove story and asset generation.

The two tasks live on different queues (see ``celery_app``) and are consumed by different
workers, because they are different workloads wearing the same shape: story generation is
an API call measured in seconds, image generation is a GPU pass measured in minutes. Their
retry policies and time limits differ for the same reason.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from app.domain.direction import DecisionContext
from app.domain.intent import PlayerIntent
from app.domain.state import BatchState
from app.runtime import build_runtime
from app.tasks.celery_app import (
    IMAGE_QUEUE,
    IMAGE_SOFT_TIME_LIMIT_S,
    IMAGE_TIME_LIMIT_S,
    STORY_QUEUE,
    STORY_SOFT_TIME_LIMIT_S,
    STORY_TIME_LIMIT_S,
    celery_app,
)

log = logging.getLogger(__name__)

if celery_app is not None:
    _task_decorator = celery_app.task
else:
    def _task_decorator(*args, **kwargs):
        def _wrapper(fn):
            fn.delay = lambda *a, **kw: None
            return fn
        return _wrapper


@_task_decorator(
    name="app.tasks.generation_tasks.generate_batch_task",
    bind=True,
    max_retries=2,
    queue=STORY_QUEUE,
    time_limit=STORY_TIME_LIMIT_S,
    soft_time_limit=STORY_SOFT_TIME_LIMIT_S,
)
def generate_batch_task(
    self=None,
    game_id: str = "",
    batch_id: str = "",
    intent_dict: dict[str, Any] | None = None,
    decision_dict: dict[str, Any] | None = None,
    speculative_key: str | None = None,
    refine_input: str | None = None,
) -> dict[str, Any]:
    """Run batch generation in a Celery background worker process.

    Consumed off the ``story`` queue only, so this never waits behind an image.
    """
    log.info("Starting Celery batch generation for game %s, batch %s", game_id, batch_id)

    async def _run():
        runtime = await build_runtime(settings)
        try:
            intent = PlayerIntent.model_validate(intent_dict)
            decision = DecisionContext.model_validate(decision_dict)
            session = await runtime.games.get(game_id)
            if session is None or session.ended:
                return {"status": "skipped", "game_id": game_id}

            batch = BatchState(batch_id=batch_id, source=decision.kind.value)
            await runtime.generation._run_batch(
                game_id,
                batch,
                intent,
                decision,
                session.model_copy(deep=True),
                prepared=None,
                refine_input=refine_input,
            )
            return {"status": "success", "game_id": game_id, "batch_id": batch_id}
        finally:
            # Closes this task's HTTP clients and MongoDB connection, which really are
            # per-runtime. The SDXL pipeline is not: it stays loaded in the process (see
            # llm/sdxl_image.py), which is why the second image job in a worker is fast.
            await runtime.close()

    try:
        return asyncio.run(_run())
    except Exception as exc:
        log.exception("Celery batch generation task failed for game %s: %s", game_id, exc)
        raise self.retry(exc=exc, countdown=2)


@_task_decorator(
    name="app.tasks.generation_tasks.generate_assets_task",
    bind=True,
    max_retries=1,
    queue=IMAGE_QUEUE,
    time_limit=IMAGE_TIME_LIMIT_S,
    soft_time_limit=IMAGE_SOFT_TIME_LIMIT_S,
)
def generate_assets_task(
    self=None,
    game_id: str = "",
    specs_dicts: list[dict[str, Any]] | None = None,
    world_id: str = "",
) -> dict[str, Any]:
    """Run image generation in a Celery background worker process.

    Consumed off the ``images`` queue by a worker that owns the GPU. Slow by nature, and
    that is fine: nothing a player is reading is behind it.
    """
    from app.agents.visual import AssetSpec

    async def _run():
        runtime = await build_runtime(settings)
        try:
            specs = [AssetSpec.from_payload(d) for d in specs_dicts]
            await runtime.generation._fill_assets(game_id, specs)
            return {"status": "success", "game_id": game_id, "count": len(specs)}
        finally:
            await runtime.close()

    try:
        return asyncio.run(_run())
    except Exception as exc:
        log.exception("Celery asset generation task failed for game %s: %s", game_id, exc)
        return {"status": "failed", "error": str(exc)}
