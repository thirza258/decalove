"""Generation traces — the intelligence PRD's FR-08 observability.

One row per generation attempt: what context went in, what came back, what validation
and quality said, how long it took and whether the player ever read it. Writes are
best-effort and bounded; a trace store outage must never cost a turn. Full prose is
deliberately not stored -- the step id, summary and counts are enough to reproduce a
complaint from the save itself.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.agents.context import NarrativeContext
from app.agents.narrative import RunResult
from app.domain.direction import Directive
from app.domain.intent import PlayerIntent
from app.domain.state import BatchState, GameSession
from app.domain.trace import NarrativeTrace
from app.repositories.base import TraceRepository

log = logging.getLogger(__name__)

TRACE_TIMEOUT_S = 1.5


class TraceRecorder:
    def __init__(self, repository: TraceRepository | None, *, enabled: bool = True) -> None:
        self.repository = repository
        self.enabled = enabled and repository is not None

    async def record(
        self,
        *,
        session: GameSession,
        batch: BatchState,
        intent: PlayerIntent,
        directive: Directive | None,
        result: RunResult | None,
        context: NarrativeContext | None,
        latency_ms: float,
        error: str = "",
        step_index: int = 0,
    ) -> NarrativeTrace | None:
        if not self.enabled or (result is None and not error):
            return None

        trace = NarrativeTrace(
            id=uuid.uuid4().hex,
            game_id=session.id,
            batch_id=batch.batch_id,
            step_index=step_index or session.next_index,
            player_input=(intent.raw or "")[:600],
            intent=intent.model_dump(mode="json"),
            memory_ids=context.memory_ids if context else [],
            memory_count=len(context.memories) if context else 0,
            knowledge_facts=context.knowledge_counts if context else {},
            knowledge_fact_ids=context.fact_ids()[:60] if context else [],
            thread_ids=context.thread_ids if context else [],
            context_sections=context.included if context else [],
            prompt_version=result.prompt_version if result else "",
            provider=result.provider if result else "",
            model=result.model if result else "",
            director=(
                {
                    "pacing": directive.pacing.value,
                    "tension": directive.tension,
                    "focus": list(directive.focus),
                    "is_finale": directive.is_finale,
                    "thread_note": directive.thread_note,
                }
                if directive is not None
                else {}
            ),
            output_steps=len(result.steps) if result else 0,
            output_summary=(result.summary or "")[:600],
            validator_rules=(
                [violation.rule for violation in result.report.violations] if result else []
            ),
            used_fallback=result.used_fallback if result else False,
            quality=(
                result.quality.model_dump(mode="json") if result and result.quality else {}
            ),
            repair_attempts=result.repair_attempts if result else 0,
            prompt_chars=result.prompt_chars if result else 0,
            output_chars=result.output_chars if result else 0,
            prompt_tokens=result.prompt_tokens if result else 0,
            completion_tokens=result.completion_tokens if result else 0,
            total_tokens=result.total_tokens if result else 0,
            latency_ms=round(latency_ms, 1),
            error=error[:300],
        )
        await self._write(trace)
        return trace

    async def mark_committed(self, trace: NarrativeTrace | None) -> None:
        if trace is None or not self.enabled:
            return
        trace.committed = True
        trace.updated_at = datetime.now(timezone.utc)
        await self._write(trace)

    async def mark_delivered(self, game_id: str, batch_id: str, step_index: int) -> None:
        if not self.enabled or not batch_id:
            return
        try:
            await asyncio.wait_for(
                self.repository.mark_delivered(game_id, batch_id, step_index),
                timeout=TRACE_TIMEOUT_S,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("trace delivery mark failed for %s/%s", game_id, batch_id, exc_info=True)

    async def _write(self, trace: NarrativeTrace) -> None:
        try:
            await asyncio.wait_for(
                self.repository.upsert(trace), timeout=TRACE_TIMEOUT_S
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("trace write failed for %s", trace.game_id, exc_info=True)
