"""Composition root.

Every external dependency is probed once at startup and either used or replaced with its
offline equivalent. The result is reported by ``/health``, so "why is my save not
persisting?" has a one-request answer instead of being a mystery.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.director import DirectorAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.narrative import NarrativeAgent
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
from app.llm.openrouter import OpenRouterChat, OpenRouterImage
from app.llm.placeholder_image import PlaceholderImageProvider
from app.llm.sdxl_image import SDXLImageProvider
from app.repositories.base import AssetRepository, GameRepository, MemoryRepository
from app.repositories.memory_repo import (
    InMemoryAssetRepository,
    InMemoryGameRepository,
    InMemoryMemoryRepository,
)
from app.repositories.mongo_repo import (
    MongoAssetRepository,
    MongoGameRepository,
    MongoMemoryRepository,
)
from app.services.asset_service import AssetService
from app.services.game_service import GameService
from app.services.generation import GenerationService
from app.services.maintenance import MaintenanceService
from app.storage import init_minio

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    settings: Settings
    world: World
    games: GameRepository
    memories: MemoryRepository
    assets_repo: AssetRepository
    store: AssetStore
    chat: ChatProvider | None
    image: ImageProvider | None
    embedder: EmbeddingProvider
    generation: GenerationService
    game_service: GameService
    asset_service: AssetService
    maintenance: MaintenanceService
    storage_backend: str
    asset_backend: str

    def describe(self) -> dict[str, Any]:
        return {
            "world": self.world.id,
            "storage": self.storage_backend,
            "assets": self.asset_backend,
            "narrative": self.chat.name if self.chat else "scripted (no OPENROUTER_API_KEY)",
            "images": (
                self.image.name
                if (self.image and self.settings.IMAGE_GENERATION_ENABLED)
                else "disabled"
            ),
            "embeddings": self.embedder.name,
            "steps_per_batch": self.settings.STEPS_PER_BATCH,
            "speculative_branches": self.settings.SPECULATIVE_PREFETCH_MAX_BRANCHES,
            "ending_after_steps": self.settings.ENDING_MIN_STEPS,
            "session_gc": self.maintenance.describe(),
        }

    async def close(self) -> None:
        await self.maintenance.stop()
        await self.generation.shutdown()
        for provider in (self.chat, self.image, self.embedder):
            closer = getattr(provider, "aclose", None)
            if closer is not None:
                await closer()
        if self.storage_backend == "mongo":
            await close_mongo_connection()


async def _build_persistence(
    settings: Settings,
) -> tuple[GameRepository, MemoryRepository, AssetRepository, str]:
    wanted = settings.STORAGE_BACKEND
    if wanted != "memory":
        connected = await try_connect()
        if connected:
            db = get_db()
            games = MongoGameRepository(db)
            memories = MongoMemoryRepository(db)
            assets = MongoAssetRepository(db)
            for repository in (games, memories, assets):
                await repository.ensure_indexes()
            return games, memories, assets, "mongo"
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
        InMemoryAssetRepository(),
        "memory",
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


def _build_providers(
    settings: Settings,
) -> tuple[ChatProvider | None, ImageProvider | None, EmbeddingProvider]:
    chat: ChatProvider | None = None
    openrouter: dict[str, Any] = {}

    if settings.has_llm:
        openrouter = {
            "api_key": settings.OPENROUTER_API_KEY,
            "base_url": settings.OPENROUTER_BASE_URL,
            "timeout": settings.OPENROUTER_TIMEOUT_S,
            "max_retries": settings.OPENROUTER_MAX_RETRIES,
            "referer": settings.OPENROUTER_SITE_URL,
            "title": settings.OPENROUTER_APP_NAME,
        }
        chat = OpenRouterChat(
            model=settings.OPENROUTER_MODEL,
            require_parameters=settings.OPENROUTER_REQUIRE_PARAMETERS,
            **openrouter,
        )
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
    games, memories, assets_repo, storage_backend = await _build_persistence(settings)
    store, asset_backend = _build_asset_store(settings)
    chat, image, embedder = _build_providers(settings)

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
        world, chat=chat, safety=safety, ending_min_steps=settings.ENDING_MIN_STEPS
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
    memory_agent = MemoryAgent(embedder, memories, top_k=settings.MEMORY_TOP_K)
    asset_service = AssetService(
        assets_repo,
        store,
        image,
        api_prefix=settings.API_PREFIX,
        enabled=settings.IMAGE_GENERATION_ENABLED,
        generation_probability=settings.IMAGE_GENERATION_PROBABILITY,
        width=settings.IMAGE_WIDTH,
        height=settings.IMAGE_HEIGHT,
    )
    generation = GenerationService(
        games=games,
        narrative=narrative,
        director=director,
        memory=memory_agent,
        visual=visual,
        assets=asset_service,
        timeout_s=settings.GENERATION_TIMEOUT_S,
        speculative_branches=settings.SPECULATIVE_PREFETCH_MAX_BRANCHES,
        task_backend=settings.TASK_QUEUE_BACKEND,
    )
    game_service = GameService(
        world=world,
        games=games,
        director=director,
        narrative=narrative,
        memory=memory_agent,
        visual=visual,
        assets=asset_service,
        generation=generation,
        max_wait_ms=settings.NEXT_STEP_MAX_WAIT_MS,
        steps_per_arc=settings.STEPS_PER_ARC,
    )

    maintenance = MaintenanceService(
        games=games,
        memories=memories,
        generation=generation,
        game_service=game_service,
        ttl_days=settings.SESSION_TTL_DAYS,
        interval_s=settings.SESSION_GC_INTERVAL_MINUTES * 60,
        batch_limit=settings.SESSION_GC_BATCH_LIMIT,
        enabled=settings.SESSION_GC_ENABLED,
    )

    runtime = Runtime(
        settings=settings,
        world=world,
        games=games,
        memories=memories,
        assets_repo=assets_repo,
        store=store,
        chat=chat,
        image=image,
        embedder=embedder,
        generation=generation,
        game_service=game_service,
        asset_service=asset_service,
        maintenance=maintenance,
        storage_backend=storage_backend,
        asset_backend=asset_backend,
    )
    log.info("Decalove runtime ready: %s", runtime.describe())
    return runtime
