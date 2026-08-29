from pathlib import Path
from typing import List, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # -- Application -----------------------------------------------------------------
    PROJECT_NAME: str = "Decalove AI Backend"
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["*"]

    # -- MongoDB ---------------------------------------------------------------------
    MONGODB_URL: str = "mongodb://root:rootpassword@localhost:27017"
    MONGODB_DB_NAME: str = "decalove_db"

    # -- MinIO -----------------------------------------------------------------------
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    MINIO_BUCKET_NAME: str = "decalove-assets"

    # -- Redis & Celery --------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    TASK_QUEUE_BACKEND: Literal["asyncio", "celery"] = "asyncio"

    # -- Backend selection -----------------------------------------------------------
    # "auto" probes the service on startup and falls back to the offline implementation
    # with a loud warning, so the game runs with no Docker at all.
    STORAGE_BACKEND: Literal["auto", "mongo", "memory"] = "auto"
    ASSET_BACKEND: Literal["auto", "minio", "local"] = "auto"
    LOCAL_ASSET_DIR: str = "var/assets"
    STORAGE_PROBE_TIMEOUT_MS: int = 1500

    # -- OpenRouter ------------------------------------------------------------------
    # With no key the engine runs on the scripted narrator (see agents/scripted.py).
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    # Must support structured outputs. Verify at:
    #   https://openrouter.ai/models?supported_parameters=structured_outputs
    OPENROUTER_MODEL: str = "google/gemini-3.7-flash"
    # Verify at: https://openrouter.ai/models?output_modalities=image
    OPENROUTER_IMAGE_MODEL: str = "google/gemini-3.1-flash-image"
    # Keeps the request off provider endpoints that would ignore response_format.
    OPENROUTER_REQUIRE_PARAMETERS: bool = True
    OPENROUTER_TIMEOUT_S: float = 120.0
    OPENROUTER_MAX_RETRIES: int = 2
    OPENROUTER_SITE_URL: str = ""
    OPENROUTER_APP_NAME: str = "Decalove"

    # -- Generation ------------------------------------------------------------------
    #: Hard ceiling on one run. Batches are 20 steps with a decision point placed
    #: at step 10-15 (e.g. step 14/15) to pipeline generation and eliminate perceived latency.
    STEPS_PER_BATCH: int = 20
    #: Options offered at a decision point. The validator guarantees this range: it caps
    #: an over-long list and tops up a short one rather than dropping to free text.
    MIN_CHOICES: int = 3
    MAX_CHOICES: int = 5
    TEMPERATURE: float = 0.85
    MAX_OUTPUT_TOKENS: int = 12000
    GENERATION_TIMEOUT_S: float = 120.0
    #: PRD §24 Rule 4 — the most any single step may move a relationship axis.
    MAX_RELATIONSHIP_DELTA: int = 5
    #: Upper bound for long-polling GET /steps/next.
    NEXT_STEP_MAX_WAIT_MS: int = 10000
    #: Generate a run per branch *before* the player chooses. Costs one LLM call per
    #: branch; see docs/ARCHITECTURE.md §1.2. 0 disables.
    SPECULATIVE_PREFETCH_MAX_BRANCHES: int = 0
    #: How many recent steps are replayed into the prompt as immediate context.
    HISTORY_STEPS: int = 20
    #: Delivered steps per story arc. The arc advances through World.arcs on this
    #: cadence, which is what keeps a long save from staying in the prologue forever.
    STEPS_PER_ARC: int = 60
    #: Delivered steps the player must get through before the story may end. With five
    #: arcs at STEPS_PER_ARC=60 the final arc opens at step 240, so the ending lands
    #: roughly 60 steps into it.
    ENDING_MIN_STEPS: int = 300
    MEMORY_TOP_K: int = 6

    # -- Images ----------------------------------------------------------------------
    #: Off by default: image models cost real money per scene.
    IMAGE_GENERATION_ENABLED: bool = False
    #: "openrouter" uses the cloud API; "sdxl" runs stabilityai/stable-diffusion-xl-base-1.0
    #: locally on GPU via Hugging Face diffusers + PyTorch.
    IMAGE_BACKEND: Literal["openrouter", "sdxl"] = "openrouter"
    IMAGE_WIDTH: int = 1024
    IMAGE_HEIGHT: int = 576
    #: Very low generation probability for new unseen images (5%); mostly generates text and reuses existing art.
    IMAGE_GENERATION_PROBABILITY: float = 0.05

    # -- SDXL local GPU settings (only used when IMAGE_BACKEND=sdxl) ----------------
    SDXL_MODEL_ID: str = "stabilityai/stable-diffusion-xl-base-1.0"
    #: Local directory where the SDXL weights are stored. Relative paths resolve
    #: against the api/ directory (i.e. the repo's api/ folder).
    SDXL_MODEL_DIR: str = "models/sdxl"
    SDXL_DEVICE: str = "cuda"
    SDXL_TORCH_DTYPE: str = "float16"
    SDXL_NUM_INFERENCE_STEPS: int = 30
    SDXL_GUIDANCE_SCALE: float = 7.5
    SDXL_NEGATIVE_PROMPT: str = ""
    SDXL_ATTENTION_SLICING: bool = True
    SDXL_VAE_TILING: bool = False
    #: When True, skip HuggingFace Hub HTTP requests and load entirely from
    #: the local cache.  Requires that weights have been downloaded at least once
    #: (via ``download_model.py`` or a previous online run).
    SDXL_OFFLINE_MODE: bool = True

    # -- Embeddings ------------------------------------------------------------------
    EMBEDDING_BACKEND: Literal["hashing", "http"] = "hashing"
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 256

    # -- Garbage collection ------------------------------------------------------------
    #: Delete games the player has not continued for this long. Finished stories are
    #: never collected, whatever this is set to.
    SESSION_TTL_DAYS: int = 7
    SESSION_GC_ENABLED: bool = True
    SESSION_GC_INTERVAL_MINUTES: float = 60.0
    #: Games examined per sweep, so one pass cannot stall the event loop.
    SESSION_GC_BATCH_LIMIT: int = 200

    # -- Safety ----------------------------------------------------------------------
    CONTENT_RATING: str = "teen"

    model_config = SettingsConfigDict(
        env_file=(_API_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def has_llm(self) -> bool:
        return bool(self.OPENROUTER_API_KEY.strip())


settings = Settings()
