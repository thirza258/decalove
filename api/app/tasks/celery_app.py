"""Celery application instance — for distributed background batch and asset generation."""

from __future__ import annotations

import os
from app.config import settings

try:
    from celery import Celery

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
        task_time_limit=300,
        worker_prefetch_multiplier=1,
    )
except ImportError:
    celery_app = None
