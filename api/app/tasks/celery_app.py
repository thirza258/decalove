"""Celery application instance — for distributed background batch and asset generation.

Two queues, deliberately. Story generation is one structured-output HTTP call to a hosted
model and takes seconds; image generation is an SDXL pass on a local GPU and takes tens of
seconds, or minutes on a cold pipeline. Sharing one queue means the pictures head-of-line
block the prose: with ``worker_prefetch_multiplier=1`` and ``--concurrency=2``, two
in-flight image jobs stall *every* player's next line behind art nobody has asked to see
yet. Routed apart they are consumed by separate workers (see ``docker-compose.yml``), so
the story path never queues behind the GPU.
"""

from __future__ import annotations

import os

from app.config import settings

#: Queue names. Imported by the tasks and named in the worker ``-Q`` flags, so the routing
#: table and the deployment cannot drift apart in a typo.
STORY_QUEUE = "story"
IMAGE_QUEUE = "images"

#: Per-queue ceilings, because the two workloads have nothing in common. Anything past the
#: story limit is a hung connection rather than a slow model, and the player is better
#: served by the scripted fallback than by a worker slot held open.
STORY_TIME_LIMIT_S = 180
STORY_SOFT_TIME_LIMIT_S = 150

#: Generous by comparison: the ceiling has to cover a first-run SDXL weight load (~6.5 GB
#: onto the GPU) on top of the inference itself.
IMAGE_TIME_LIMIT_S = 900
IMAGE_SOFT_TIME_LIMIT_S = 840

try:
    from celery import Celery
    from kombu import Queue

    broker_url = os.getenv("CELERY_BROKER_URL", settings.CELERY_BROKER_URL)
    result_backend = os.getenv("CELERY_RESULT_BACKEND", settings.CELERY_RESULT_BACKEND)

    celery_app = Celery(
        "decalove",
        broker=broker_url,
        backend=result_backend,
        include=["app.tasks.generation_tasks"],
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        worker_prefetch_multiplier=1,
        # Unrouted work is story work: a new task added without a routing entry should land
        # on the cheap queue, never in front of the GPU.
        task_default_queue=STORY_QUEUE,
        task_queues=(Queue(STORY_QUEUE), Queue(IMAGE_QUEUE)),
        task_routes={
            "app.tasks.generation_tasks.generate_batch_task": {"queue": STORY_QUEUE},
            "app.tasks.generation_tasks.generate_assets_task": {"queue": IMAGE_QUEUE},
        },
        # A backstop only. Each task declares its own limit, which takes precedence; this
        # is what a future task gets if it forgets to.
        task_time_limit=STORY_TIME_LIMIT_S,
    )
except ImportError:
    celery_app = None
