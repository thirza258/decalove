"""Composition root.

Every external dependency is probed once at startup and either used or replaced with its
offline equivalent. The result is reported by ``/health``, so "why is my save not
persisting?" has a one-request answer instead of being a mystery.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.context import ContextAssembler
from app.agents.director import DirectorAgent
from app.agents.knowledge import CharacterKnowledgeManager
from app.agents.memory_agent import MemoryAgent, MemoryWeights
from app.agents.narrative import NarrativeAgent
from app.agents.planner import NarrativePlanner
from app.agents.quality import NarrativeQualityEvaluator
from app.agents.safety import SafetyFilter
from app.agents.scripted import ScriptedNarrator
from app.agents.validator import Validator
from app.agents.visual import VisualAgent
from app.assets.base import AssetStore
from app.assets.local_store import LocalAssetStore
from app.assets.minio_store import MinioAssetStore
from app.config import Settings
from app.content import get_world
from app.content.world import World
from app.database import close_mongo_connection, get_db, try_connect
from app.llm.base import ChatProvider, EmbeddingProvider, ImageProvider
from app.llm.embeddings import HashingEmbedding, HttpEmbedding
from app.llm.fallback_image import FallbackImageProvider
from app.llm.openrouter import (
    FREE_OPENROUTER_MODELS,
    OpenRouterChat,
    OpenRouterImage,
    discover_free_models,
    pick_primary_model,
)
from app.llm.placeholder_image import PlaceholderImageProvider
from app.llm.sdxl_image import SDXLImageProvider
from app.repositories.base import (
    AssetRepository,
    ChronicleRepository,
    GameRepository,
    KnowledgeRepository,
    MemoryRepository,
    ThreadRepository,
    TraceRepository,
)
from app.repositories.memory_repo import (
    InMemoryAssetRepository,
    InMemoryChronicleRepository,
    InMemoryGameRepository,
    InMemoryKnowledgeRepository,
    InMemoryMemoryRepository,
    InMemoryThreadRepository,
    InMemoryTraceRepository,
)
from app.repositories.mongo_repo import (
    MongoAssetRepository,
    MongoChronicleRepository,
    MongoGameRepository,
    MongoKnowledgeRepository,
    MongoMemoryRepository,
    MongoThreadRepository,
    MongoTraceRepository,
)
from app.services.asset_service import AssetService
from app.services.game_service import GameService
from app.services.generation import GenerationService
from app.services.maintenance import MaintenanceService
from app.services.tracing import TraceRecorder
from app.services.writing_service import WritingService
from app.services.writing_storage import WritingStorage
from app.repositories.writing_repo import InMemoryWritingRepository, MongoWritingRepository
from app.storage import init_minio

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    settings: Settings
    world: World
    model_chain: list[str]
    games: GameRepository
    memories: MemoryRepository
    chronicle: ChronicleRepository
    knowledge: KnowledgeRepository
    threads: ThreadRepository
    traces: TraceRepository
    knowledge_manager: CharacterKnowledgeManager
    planner: NarrativePlanner
    tracer: TraceRecorder
    assets_repo: AssetRepository
    store: AssetStore
    chat: ChatProvider | None
    quality_judge: ChatProvider | None
    image: ImageProvider | None
    embedder: EmbeddingProvider
    generation: GenerationService
    game_service: GameService
    asset_service: AssetService
    maintenance: MaintenanceService
    writing: WritingService
    writing_storage: WritingStorage
    storage_backend: str
    asset_backend: str

    def describe(self) -> dict[str, Any]:
        return {
            "world": self.world.id,
            "web_mode": self.settings.WEB_MODE,
            "storage": self.storage_backend,
            "task_queue": self.generation.task_backend,
            "assets": self.asset_backend,
            "narrative": self.chat.name if self.chat else (
                "unavailable (no OPENROUTER_API_KEY)" if self.settings.WEB_MODE
                else "scripted (no OPENROUTER_API_KEY)"
            ),
            "quality_judge": (
                getattr(self.quality_judge, "model", self.quality_judge.name)
                if self.quality_judge else "off"
            ),
            "model_chain": list(self.model_chain),
            "images": (
                self.image.name
                if (self.image and self.settings.IMAGE_GENERATION_ENABLED)
                else "disabled"
            ),
            "embeddings": self.embedder.name,
            "intelligence": {
                "knowledge": self.settings.KNOWLEDGE_ENABLED,
                "threads": self.settings.THREAD_TRACKING_ENABLED,
                "behavior": self.settings.BEHAVIOR_MODELING_ENABLED,
                "consolidation": self.settings.MEMORY_CONSOLIDATION_ENABLED,
                "quality_evaluation": self.settings.QUALITY_EVALUATION_ENABLED,
                "traces": self.settings.NARRATIVE_TRACE_ENABLED,
            },
            "steps_per_batch": self.settings.STEPS_PER_BATCH,
            "speculative_branches": self.settings.SPECULATIVE_PREFETCH_MAX_BRANCHES,
            "ending_after_steps": self.settings.ENDING_MIN_STEPS,
            "session_gc": self.maintenance.describe(),
        }

    async def close(self) -> None:
        await self.maintenance.stop()
        await self.generation.shutdown()
        providers = [self.chat, self.image, self.embedder,
                     *self.generation.narrative.fallback_chats]
        if self.quality_judge is not None and self.quality_judge is not self.chat:
            providers.append(self.quality_judge)
        for provider in providers:
            closer = getattr(provider, "aclose", None)
            if closer is not None:
                await closer()
        if self.storage_backend == "mongo":
            await close_mongo_connection()


async def _build_persistence(
    settings: Settings,
) -> tuple[GameRepository, MemoryRepository, ChronicleRepository, AssetRepository, str]:
    wanted = settings.STORAGE_BACKEND
    if wanted != "memory":
        connected = await try_connect()
        if connected:
            db = get_db()
            games = MongoGameRepository(db)
            memories = MongoMemoryRepository(db)
            chronicle = MongoChronicleRepository(db)
            assets = MongoAssetRepository(db)
            for repository in (games, memories, chronicle, assets):
                await repository.ensure_indexes()
            return games, memories, chronicle, assets, "mongo"
        if wanted == "mongo":
            raise RuntimeError(
                "STORAGE_BACKEND=mongo but MongoDB is unreachable. "
                "Start it with `docker compose up -d`, or set STORAGE_BACKEND=memory."
            )
        log.warning(
            "MongoDB unreachable - falling back to in-memory storage. "
            "SAVES WILL NOT SURVIVE A RESTART. Start it with `docker compose up -d`."
        )
    return (
        InMemoryGameRepository(),
        InMemoryMemoryRepository(),
        InMemoryChronicleRepository(),
        InMemoryAssetRepository(),
        "memory",
    )


async def _resolve_story_models(settings: Settings) -> tuple[str, list[str]]:
    """Pick the primary story model and a freshly shuffled free fallback chain.

    The primary is the configured id (the default is hand-verified), or a verified model
    from the live catalogue when ``OPENROUTER_MODEL=auto``. Alternates are explicit
    configuration first, then the shuffled live free catalogue, capped so one turn can
    still give each attempt enough time. Discovery is fail-open: no key, no network or a
    malformed catalogue leaves the verified static ids in charge.
    """
    configured_primary = settings.OPENROUTER_MODEL.strip()
    configured_fallbacks = [
        model.strip() for model in settings.OPENROUTER_FALLBACK_MODELS.split(",")
        if model.strip()
    ]

    discovered: list[str] = []
    wants_discovery = settings.WEB_MODE or configured_primary.lower() in ("", "auto")
    if settings.has_llm and settings.OPENROUTER_DISCOVER_FREE_MODELS and wants_discovery:
        discovered = await discover_free_models(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            timeout=settings.OPENROUTER_MODEL_DISCOVERY_TIMEOUT_S,
        )

    if configured_primary.lower() in ("", "auto"):
        primary = pick_primary_model(discovered)
    else:
        primary = configured_primary

    pool = configured_fallbacks + list(discovered)
    if not pool:
        # Offline or discovery failure: a known-good chain beats no alternates at all.
        pool = [model for model in FREE_OPENROUTER_MODELS if model != primary]
    limit = max(1, settings.OPENROUTER_FALLBACK_MODEL_LIMIT)
    fallbacks = [
        model for model in dict.fromkeys(pool) if model != primary
    ][:limit]
    return primary, fallbacks


async def _build_intel(
    settings: Settings, storage_backend: str
) -> tuple[KnowledgeRepository, ThreadRepository, TraceRepository]:
    """The intelligence layer's per-game records.

    Split from ``_build_persistence`` so the existing tuple its callers unpack stays
    stable. Mongo uses the connection already established above; the offline seam gets
    in-memory equivalents with identical behaviour.
    """
    if storage_backend == "mongo":
        db = get_db()
        knowledge = MongoKnowledgeRepository(db)
        threads = MongoThreadRepository(db)
        traces = MongoTraceRepository(db)
        for repository in (knowledge, threads, traces):
            await repository.ensure_indexes()
        return knowledge, threads, traces
    return (
        InMemoryKnowledgeRepository(),
        InMemoryThreadRepository(),
        InMemoryTraceRepository(),
    )


def _build_asset_store(settings: Settings) -> tuple[AssetStore, str]:
    wanted = settings.ASSET_BACKEND
    if wanted != "local":
        if init_minio():
            return MinioAssetStore(), "minio"
        if wanted == "minio":
            raise RuntimeError(
                "ASSET_BACKEND=minio but MinIO is unreachable. "
                "Start it with `docker compose up -d`, or set ASSET_BACKEND=local."
            )
        log.warning("MinIO unreachable - storing generated art on the local filesystem instead.")
    root = Path(settings.LOCAL_ASSET_DIR)
    if not root.is_absolute():
        root = Path(__file__).resolve().parent.parent / root
    return LocalAssetStore(root), "local"


def _sdxl_installed() -> bool:
    """Whether this image carries the SDXL extras at all.

    find_spec rather than import: torch costs seconds and hundreds of megabytes of RSS to
    import, and the point of asking is that we are probably about to decide not to.

    Only the GPU image has them (see Dockerfile.gpu), so on the default image this is the
    difference between 'sdxl' being dropped at boot with a warning and every picture
    failing on an ImportError the chain was never given a chance to route around.
    """
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "diffusers"))


def _build_image_chain(settings: Settings, openrouter: dict[str, Any]) -> ImageProvider:
    """Assemble ``IMAGE_BACKEND`` into one provider.

    Entries this deployment cannot serve are dropped here, at boot, with a warning --
    an ``openrouter`` link with no API key would otherwise cost a round-trip per image to
    discover, on every image, forever. A chain of one is returned unwrapped so ``/health``
    keeps naming the backend rather than a wrapper.
    """
    providers: list[ImageProvider] = []
    for backend in settings.image_backends:
        if backend == "openrouter":
            if not settings.has_llm:
                log.warning(
                    "IMAGE_BACKEND lists 'openrouter' but OPENROUTER_API_KEY is unset - "
                    "dropping it from the chain."
                )
                continue
            providers.append(OpenRouterImage(model=settings.OPENROUTER_IMAGE_MODEL, **openrouter))
        elif backend == "sdxl":
            if not _sdxl_installed():
                log.warning(
                    "IMAGE_BACKEND lists 'sdxl' but torch/diffusers are not installed - "
                    "dropping it from the chain. This is the default image; rebuild with "
                    "Dockerfile.gpu (COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml) "
                    "to render locally."
                )
                continue
            # Runs locally: no API key, and the weights load lazily on the first image, so
            # a chain that never reaches this link costs nothing to have declared.
            providers.append(
                SDXLImageProvider(
                    model_id=settings.SDXL_MODEL_ID,
                    model_dir=settings.SDXL_MODEL_DIR,
                    device=settings.SDXL_DEVICE,
                    torch_dtype=settings.SDXL_TORCH_DTYPE,
                    num_inference_steps=settings.SDXL_NUM_INFERENCE_STEPS,
                    guidance_scale=settings.SDXL_GUIDANCE_SCALE,
                    negative_prompt=settings.SDXL_NEGATIVE_PROMPT,
                    enable_attention_slicing=settings.SDXL_ATTENTION_SLICING,
                    enable_vae_tiling=settings.SDXL_VAE_TILING,
                    offline_mode=settings.SDXL_OFFLINE_MODE,
                )
            )
        elif backend == "placeholder":
            providers.append(PlaceholderImageProvider())

    if not providers:
        log.warning(
            "no usable image backend in IMAGE_BACKEND=%r - falling back to the placeholder "
            "generator, which keeps the whole asset pipeline exercisable offline.",
            settings.IMAGE_BACKEND,
        )
        return PlaceholderImageProvider()
    if len(providers) == 1:
        return providers[0]
    return FallbackImageProvider(providers)


def _openrouter_options(settings: Settings) -> dict[str, Any]:
    return {
        "api_key": settings.OPENROUTER_API_KEY,
        "base_url": settings.OPENROUTER_BASE_URL,
        "timeout": settings.OPENROUTER_TIMEOUT_S,
        "max_retries": settings.OPENROUTER_MAX_RETRIES,
        "referer": settings.OPENROUTER_SITE_URL,
        "title": settings.OPENROUTER_APP_NAME,
    }


def _build_providers(
    settings: Settings,
    *,
    chat_model: str | None = None,
) -> tuple[ChatProvider | None, ImageProvider | None, EmbeddingProvider]:
    chat: ChatProvider | None = None
    openrouter: dict[str, Any] = {}

    if settings.has_llm:
        openrouter = _openrouter_options(settings)
        chat = OpenRouterChat(
            model=chat_model or settings.OPENROUTER_MODEL,
            require_parameters=settings.OPENROUTER_REQUIRE_PARAMETERS,
            **openrouter,
        )
    elif settings.WEB_MODE:
        log.warning("No OPENROUTER_API_KEY set - web stories cannot continue beyond the opening.")
    else:
        log.warning(
            "No OPENROUTER_API_KEY set - running on the scripted narrator. "
            "The game is fully playable; the prose is authored, not generated."
        )

    image: ImageProvider = (
        _build_image_chain(settings, openrouter)
        if settings.IMAGE_GENERATION_ENABLED
        # Constructed either way so the seam is never None, but nothing calls it:
        # AssetService.enabled is what gates generation.
        else PlaceholderImageProvider()
    )

    if settings.EMBEDDING_BACKEND == "http" and settings.EMBEDDING_API_KEY:
        embedder: EmbeddingProvider = HttpEmbedding(
            base_url=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY,
            model=settings.EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
    else:
        embedder = HashingEmbedding(settings.EMBEDDING_DIMENSIONS)

    return chat, image, embedder


async def build_runtime(settings: Settings) -> Runtime:
    world = get_world(None)
    games, memories, chronicle, assets_repo, storage_backend = await _build_persistence(settings)
    knowledge_repo, thread_repo, trace_repo = await _build_intel(settings, storage_backend)
    store, asset_backend = _build_asset_store(settings)
    story_model, fallback_models = await _resolve_story_models(settings)
    chat, image, embedder = _build_providers(settings, chat_model=story_model)
    fallback_chats = []
    seen = {story_model}
    if settings.WEB_MODE and settings.has_llm:
        for model in fallback_models:
            if not model or model in seen:
                continue
            seen.add(model)
            fallback_chats.append(OpenRouterChat(
                model=model,
                require_parameters=settings.OPENROUTER_REQUIRE_PARAMETERS,
                **_openrouter_options(settings),
            ))
    model_chain = [story_model, *[model for model in fallback_models if model in seen]]

    # A separate judge model (free by default) rather than the story model, so the
    # evaluator's taste does not share the writer's blind spots -- and so judging does
    # not interrupt the story model's rate limit.
    quality_judge: ChatProvider | None = None
    if settings.QUALITY_EVALUATION_ENABLED and settings.QUALITY_JUDGE_ENABLED and settings.has_llm:
        quality_judge = OpenRouterChat(
            model=settings.QUALITY_JUDGE_MODEL.strip() or settings.OPENROUTER_MODEL,
            require_parameters=settings.OPENROUTER_REQUIRE_PARAMETERS,
            **_openrouter_options(settings),
        )

    safety = SafetyFilter(settings.CONTENT_RATING)
    validator = Validator(
        world=world,
        safety=safety,
        max_delta=settings.MAX_RELATIONSHIP_DELTA,
        max_steps=settings.STEPS_PER_BATCH,
        min_choices=settings.MIN_CHOICES,
        max_choices=settings.MAX_CHOICES,
    )
    scripted = ScriptedNarrator(world)
    director = DirectorAgent(
        world, chat=chat, safety=safety, ending_min_steps=settings.ENDING_MIN_STEPS,
        steps_per_arc=settings.STEPS_PER_ARC,
    )
    narrative = NarrativeAgent(
        world,
        validator,
        scripted,
        chat=chat,
        max_steps=settings.STEPS_PER_BATCH,
        max_delta=settings.MAX_RELATIONSHIP_DELTA,
        temperature=settings.TEMPERATURE,
        max_tokens=settings.MAX_OUTPUT_TOKENS,
        history_steps=settings.HISTORY_STEPS,
        rating=settings.CONTENT_RATING,
        min_choices=settings.MIN_CHOICES,
        max_choices=settings.MAX_CHOICES,
        web_mode=settings.WEB_MODE,
        fallback_chats=fallback_chats,
        # Leave time for every model, even when the primary hangs.
        attempt_timeout_s=max(0.01, min(
            settings.WEB_AI_ATTEMPT_TIMEOUT_S,
            (settings.GENERATION_TIMEOUT_S - 5) / (1 + len(fallback_chats)),
        )),
    )
    visual = VisualAgent(
        world,
        deterministic_seed=settings.IMAGE_DETERMINISTIC_SEED,
        seed_salt=settings.IMAGE_SEED_SALT,
        style_prompt=settings.IMAGE_STYLE_PROMPT,
        negative_prompt=settings.IMAGE_NEGATIVE_PROMPT,
        character_scene_context=settings.IMAGE_CHARACTER_SCENE_CONTEXT,
        character_pose_variants=settings.IMAGE_CHARACTER_POSE_VARIANTS,
    )
    memory_agent = MemoryAgent(
        embedder,
        memories,
        top_k=settings.MEMORY_TOP_K,
        weights=MemoryWeights(
            semantic=settings.MEMORY_WEIGHT_SEMANTIC,
            importance=settings.MEMORY_WEIGHT_IMPORTANCE,
            recency=settings.MEMORY_WEIGHT_RECENCY,
            relationship=settings.MEMORY_WEIGHT_RELATIONSHIP,
            unresolved=settings.MEMORY_WEIGHT_UNRESOLVED,
        ),
        token_budget=settings.MEMORY_CONTEXT_BUDGET,
    )
    knowledge_manager = CharacterKnowledgeManager(knowledge_repo, world=world)
    planner = NarrativePlanner(
        thread_repo, world=world,
        dormant_after_steps=max(1, settings.STEPS_PER_ARC // 3),
    )
    tracer = TraceRecorder(trace_repo, enabled=settings.NARRATIVE_TRACE_ENABLED)
    context_assembler = ContextAssembler(
        memory=memory_agent,
        knowledge=knowledge_manager if settings.KNOWLEDGE_ENABLED else None,
        planner=planner if settings.THREAD_TRACKING_ENABLED else None,
        chronicle=chronicle,
        max_chars=settings.CONTEXT_MAX_CHARS,
        history_steps=settings.HISTORY_STEPS,
    )
    quality = (
        NarrativeQualityEvaluator(
            min_overall=settings.QUALITY_MIN_OVERALL,
            max_repairs=settings.QUALITY_MAX_REPAIRS,
            judge=quality_judge,
            judge_timeout_s=settings.QUALITY_JUDGE_TIMEOUT_S,
        )
        if settings.QUALITY_EVALUATION_ENABLED
        else None
    )
    narrative.quality = quality
    narrative.choice_repair_enabled = settings.QUALITY_CHOICE_REPAIR_ENABLED
    narrative.choice_repair_timeout_s = settings.QUALITY_CHOICE_REPAIR_TIMEOUT_S
    image_generation_enabled = settings.IMAGE_GENERATION_ENABLED and not settings.WEB_MODE
    if settings.WEB_MODE and settings.IMAGE_GENERATION_ENABLED:
        log.info(
            "WEB_MODE is on — image generation disabled. "
            "Only pre-existing images in the asset store will be served."
        )
    asset_service = AssetService(
        assets_repo,
        store,
        image,
        api_prefix=settings.API_PREFIX,
        enabled=image_generation_enabled,
        generation_probability=settings.IMAGE_GENERATION_PROBABILITY,
        width=settings.IMAGE_WIDTH,
        height=settings.IMAGE_HEIGHT,
    )
    generation = GenerationService(
        games=games,
        narrative=narrative,
        director=director,
        memory=memory_agent,
        chronicle=chronicle,
        visual=visual,
        assets=asset_service,
        timeout_s=settings.GENERATION_TIMEOUT_S,
        speculative_branches=settings.SPECULATIVE_PREFETCH_MAX_BRANCHES,
        task_backend=(
            settings.TASK_QUEUE_BACKEND if storage_backend == "mongo" else "asyncio"
        ),
        context=context_assembler,
        planner=planner if settings.THREAD_TRACKING_ENABLED else None,
        tracer=tracer,
    )
    game_service = GameService(
        world=world,
        games=games,
        director=director,
        narrative=narrative,
        memory=memory_agent,
        chronicle=chronicle,
        visual=visual,
        assets=asset_service,
        generation=generation,
        max_wait_ms=settings.NEXT_STEP_MAX_WAIT_MS,
        steps_per_arc=settings.STEPS_PER_ARC,
        knowledge=knowledge_manager if settings.KNOWLEDGE_ENABLED else None,
        planner=planner if settings.THREAD_TRACKING_ENABLED else None,
        tracer=tracer,
        consolidation_enabled=settings.MEMORY_CONSOLIDATION_ENABLED,
        behavior_enabled=settings.BEHAVIOR_MODELING_ENABLED,
    )

    maintenance = MaintenanceService(
        games=games,
        memories=memories,
        chronicle=chronicle,
        generation=generation,
        game_service=game_service,
        ttl_days=settings.SESSION_TTL_DAYS,
        interval_s=settings.SESSION_GC_INTERVAL_MINUTES * 60,
        batch_limit=settings.SESSION_GC_BATCH_LIMIT,
        enabled=settings.SESSION_GC_ENABLED,
        knowledge=knowledge_repo,
        threads=thread_repo,
        traces=trace_repo,
    )

    runtime = Runtime(
        settings=settings,
        model_chain=model_chain if settings.has_llm else [],
        world=world,
        games=games,
        memories=memories,
        chronicle=chronicle,
        knowledge=knowledge_repo,
        threads=thread_repo,
        traces=trace_repo,
        knowledge_manager=knowledge_manager,
        planner=planner,
        tracer=tracer,
        assets_repo=assets_repo,
        store=store,
        chat=chat,
        quality_judge=quality_judge,
        image=image,
        embedder=embedder,
        generation=generation,
        game_service=game_service,
        asset_service=asset_service,
        maintenance=maintenance,
        writing=WritingService(
            ([chat] if chat else []) + fallback_chats,
            attempt_timeout_s=settings.WEB_AI_ATTEMPT_TIMEOUT_S,
            total_timeout_s=settings.GENERATION_TIMEOUT_S,
            max_tokens=settings.MAX_OUTPUT_TOKENS,
        ),
        writing_storage=WritingStorage(
            MongoWritingRepository(get_db()) if storage_backend == "mongo" else InMemoryWritingRepository(),
            store, backend=storage_backend,
        ),
        storage_backend=storage_backend,
        asset_backend=asset_backend,
    )
    log.info("Decalove runtime ready: %s", runtime.describe())
    return runtime
