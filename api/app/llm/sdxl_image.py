"""Hugging Face Stable Diffusion XL image provider.

Runs ``stabilityai/stable-diffusion-xl-base-1.0`` locally on a CUDA GPU using the
``diffusers`` library.  The pipeline is loaded lazily on first ``generate()`` call so
the API boots instantly even when image generation is enabled.

``SDXL_DEVICE`` is a requirement rather than a preference: asking for ``cuda`` on a host
without it raises ``ImageError`` instead of rendering on the CPU, which lets the next
backend in an ``IMAGE_BACKEND`` chain take over (see ``llm/fallback_image.py``).

Model weights are stored in a local ``models/`` directory (configurable via
``SDXL_MODEL_DIR``) so they stay inside the project tree instead of landing in
``~/.cache/huggingface``.

Heavy inference is dispatched to a thread-pool executor so the async event loop stays
responsive.

The loaded pipeline is cached per *process*, not per provider instance.  Under Celery each
task builds and closes its own ``Runtime`` on a fresh event loop, so a pipeline owned by
the provider would be loaded -- ~6.5 GB onto the GPU -- and thrown away once per image.
"""

from __future__ import annotations

import asyncio
import io
import logging
import threading
from functools import partial
from pathlib import Path
from typing import Any

from app.llm.base import ImageError

log = logging.getLogger(__name__)

#: Loaded pipelines, keyed by the settings that decide what was loaded.  Process-wide and
#: deliberately never evicted: the point is that the *second* image job in a worker starts
#: generating immediately instead of loading SDXL again.
_PIPELINES: dict[tuple[Any, ...], Any] = {}

#: A threading lock rather than an asyncio one.  The loading happens in an executor thread,
#: and an asyncio lock would belong to an event loop that dies with the task that made it.
_PIPELINE_LOCK = threading.Lock()

#: One diffusion pass at a time per process.  Diffusers pipelines are not thread-safe, and
#: now that the pipeline is shared across tasks two of them really can land in the default
#: executor together -- on one GPU that is VRAM thrash, not throughput.
_INFERENCE_LOCK = threading.Lock()


def _resolve_model_dir(model_dir: str) -> Path:
    """Turn a possibly-relative *model_dir* into an absolute path.

    Relative paths are resolved against the ``api/`` directory (two levels up
    from this file: ``api/app/llm/sdxl_image.py``).
    """
    p = Path(model_dir)
    if not p.is_absolute():
        api_root = Path(__file__).resolve().parent.parent.parent
        p = api_root / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def _patch_torch_compat() -> None:
    try:
        import torch
        if not hasattr(torch, "xpu"):
            class _DummyXPU:
                @staticmethod
                def is_available() -> bool:
                    return False
                @staticmethod
                def device_count() -> int:
                    return 0
                @staticmethod
                def current_device() -> int:
                    return 0
            torch.xpu = _DummyXPU()
    except Exception:
        pass


def _load_pipeline(
    model_id: str,
    model_dir: str,
    device: str,
    torch_dtype_name: str,
    enable_attention_slicing: bool,
    enable_vae_tiling: bool,
    offline_mode: bool = False,
) -> Any:
    """Load the SDXL pipeline.  Called once, inside a worker thread."""
    _patch_torch_compat()
    import torch

    # Before the diffusers import, which is not cheap: a host that cannot serve this
    # backend should find that out for the price of one torch.cuda.is_available().
    dtype = getattr(torch, torch_dtype_name, torch.float16)
    if device == "cuda" and not torch.cuda.is_available():
        # Raise rather than quietly dropping to CPU. An SDXL pass on CPU is minutes per
        # image -- indistinguishable from a hang, and past the image queue's time limit --
        # and with a chain (IMAGE_BACKEND=sdxl,openrouter) failing here is exactly what
        # lets the next backend serve the request. SDXL_DEVICE=cpu asks for CPU on purpose.
        #
        # Checked before from_pretrained, so a GPU-less host pays one
        # torch.cuda.is_available() per image rather than a 6.5 GB load attempt. Nothing is
        # cached on this path either, so the pipeline still loads the moment a GPU appears.
        raise ImageError(
            "SDXL_DEVICE=cuda but torch.cuda.is_available() is False. Set SDXL_DEVICE=cpu "
            "to render on the CPU anyway, or list another backend after 'sdxl' in "
            "IMAGE_BACKEND."
        )

    from diffusers import StableDiffusionXLPipeline

    cache_dir = _resolve_model_dir(model_dir)
    log.info(
        "Loading SDXL pipeline %s on %s (%s), cache_dir=%s, offline=%s …",
        model_id, device, dtype, cache_dir, offline_mode,
    )

    pipe = StableDiffusionXLPipeline.from_pretrained(
        model_id,
        torch_dtype=dtype,
        use_safetensors=True,
        variant="fp16" if dtype == torch.float16 else None,
        cache_dir=str(cache_dir),
        local_files_only=offline_mode,
    )
    pipe = pipe.to(device)

    if enable_attention_slicing:
        pipe.enable_attention_slicing()
    if enable_vae_tiling:
        pipe.enable_vae_tiling()

    log.info("SDXL pipeline ready.")
    return pipe


def _get_or_load_pipeline(cache_key: tuple[Any, ...], *load_args: Any) -> Any:
    """Return the process-wide pipeline for *cache_key*, loading it on first use.

    Runs inside a worker thread and holds ``_PIPELINE_LOCK`` across the load, so two first
    calls arriving together cannot both push a copy of the weights onto the GPU.
    """
    with _PIPELINE_LOCK:
        pipe = _PIPELINES.get(cache_key)
        if pipe is None:
            pipe = _load_pipeline(*load_args)
            _PIPELINES[cache_key] = pipe
        return pipe


def unload_pipelines() -> None:
    """Release every cached pipeline and its GPU memory.

    Not called on provider close -- see ``SDXLImageProvider.aclose``.  This is for explicit
    teardown: a script that is done with the GPU, or a test.
    """
    with _PIPELINE_LOCK:
        if not _PIPELINES:
            return
        _PIPELINES.clear()

    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # pragma: no cover - torch may not be installed at all
        pass
    log.info("SDXL pipeline(s) unloaded, GPU memory released.")


def _generate_sync(
    pipe: Any,
    prompt: str,
    width: int,
    height: int,
    num_inference_steps: int,
    guidance_scale: float,
    negative_prompt: str,
) -> bytes:
    """Run inference synchronously (called inside a worker thread)."""
    import torch

    with _INFERENCE_LOCK, torch.no_grad():
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt or None,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
        )
    image = result.images[0]

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class SDXLImageProvider:
    """``ImageProvider`` backed by a local SDXL pipeline on GPU."""

    name = "sdxl-local"

    def __init__(
        self,
        *,
        model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
        model_dir: str = "models/sdxl",
        device: str = "cuda",
        torch_dtype: str = "float16",
        num_inference_steps: int = 30,
        guidance_scale: float = 7.5,
        negative_prompt: str = "",
        enable_attention_slicing: bool = True,
        enable_vae_tiling: bool = False,
        offline_mode: bool = False,
    ) -> None:
        self._model_id = model_id
        self._model_dir = model_dir
        self._device = device
        self._torch_dtype = torch_dtype
        self._num_inference_steps = num_inference_steps
        self._guidance_scale = guidance_scale
        self._negative_prompt = negative_prompt
        self._enable_attention_slicing = enable_attention_slicing
        self._enable_vae_tiling = enable_vae_tiling
        self._offline_mode = offline_mode
        self._pipe: Any = None

    def _cache_key(self) -> tuple[Any, ...]:
        """Everything that changes *which* pipeline gets loaded."""
        return (
            self._model_id,
            self._model_dir,
            self._device,
            self._torch_dtype,
            self._enable_attention_slicing,
            self._enable_vae_tiling,
            self._offline_mode,
        )

    async def _ensure_pipeline(self) -> Any:
        if self._pipe is not None:
            return self._pipe

        key = self._cache_key()
        cached = _PIPELINES.get(key)
        if cached is not None:
            # Loaded by an earlier task in this process. No GPU work, no executor hop.
            self._pipe = cached
            return cached

        loop = asyncio.get_running_loop()
        self._pipe = await loop.run_in_executor(
            None,
            partial(
                _get_or_load_pipeline,
                key,
                self._model_id,
                self._model_dir,
                self._device,
                self._torch_dtype,
                self._enable_attention_slicing,
                self._enable_vae_tiling,
                self._offline_mode,
            ),
        )
        return self._pipe

    async def generate(
        self, prompt: str, *, width: int = 1024, height: int = 576
    ) -> tuple[bytes, str]:
        """Return ``(png_bytes, 'image/png')`` or raise ``ImageError``."""
        try:
            pipe = await self._ensure_pipeline()
        except Exception as exc:
            raise ImageError(f"Failed to load SDXL pipeline: {exc}") from exc

        # SDXL requires dimensions divisible by 8.
        width = (width // 8) * 8
        height = (height // 8) * 8

        loop = asyncio.get_running_loop()
        try:
            png_bytes = await loop.run_in_executor(
                None,
                partial(
                    _generate_sync,
                    pipe,
                    prompt,
                    width,
                    height,
                    self._num_inference_steps,
                    self._guidance_scale,
                    self._negative_prompt,
                ),
            )
        except Exception as exc:
            raise ImageError(f"SDXL generation failed: {exc}") from exc

        return png_bytes, "image/png"

    async def aclose(self) -> None:
        """Drop this provider's handle on the pipeline, without unloading it.

        Deliberately not a teardown.  The pipeline belongs to the process, not to the
        ``Runtime`` that happens to hold this provider, and under Celery a runtime is built
        and closed *per task* -- so unloading here made every single image job pay a cold
        ~6.5 GB load.  Use ``unload_pipelines()`` when the GPU really should be released.
        """
        self._pipe = None
