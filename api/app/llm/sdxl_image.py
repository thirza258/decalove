"""Hugging Face Stable Diffusion XL image provider.

Runs ``stabilityai/stable-diffusion-xl-base-1.0`` locally on a CUDA GPU using the
``diffusers`` library.  The pipeline is loaded lazily on first ``generate()`` call so
the API boots instantly even when image generation is enabled.

Model weights are stored in a local ``models/`` directory (configurable via
``SDXL_MODEL_DIR``) so they stay inside the project tree instead of landing in
``~/.cache/huggingface``.

Heavy inference is dispatched to a thread-pool executor so the async event loop stays
responsive.
"""

from __future__ import annotations

import asyncio
import io
import logging
from functools import partial
from pathlib import Path
from typing import Any

from app.llm.base import ImageError

log = logging.getLogger(__name__)

# These are imported lazily inside _load_pipeline() so that the module can be
# imported even when torch / diffusers are not installed (e.g. during tests or
# when the provider is not selected).
_pipeline: Any = None
_device: str = "cuda"


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


def _load_pipeline(
    model_id: str,
    model_dir: str,
    device: str,
    torch_dtype_name: str,
    enable_attention_slicing: bool,
    enable_vae_tiling: bool,
) -> Any:
    """Load the SDXL pipeline.  Called once, inside a worker thread."""
    import torch
    from diffusers import StableDiffusionXLPipeline

    cache_dir = _resolve_model_dir(model_dir)
    dtype = getattr(torch, torch_dtype_name, torch.float16)
    log.info(
        "Loading SDXL pipeline %s on %s (%s), cache_dir=%s …",
        model_id, device, dtype, cache_dir,
    )

    pipe = StableDiffusionXLPipeline.from_pretrained(
        model_id,
        torch_dtype=dtype,
        use_safetensors=True,
        variant="fp16",
        cache_dir=str(cache_dir),
    )
    pipe = pipe.to(device)

    if enable_attention_slicing:
        pipe.enable_attention_slicing()
    if enable_vae_tiling:
        pipe.enable_vae_tiling()

    log.info("SDXL pipeline ready.")
    return pipe


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

    with torch.no_grad():
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
        self._pipe: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_pipeline(self) -> Any:
        if self._pipe is not None:
            return self._pipe
        async with self._lock:
            if self._pipe is not None:
                return self._pipe
            loop = asyncio.get_running_loop()
            self._pipe = await loop.run_in_executor(
                None,
                partial(
                    _load_pipeline,
                    self._model_id,
                    self._model_dir,
                    self._device,
                    self._torch_dtype,
                    self._enable_attention_slicing,
                    self._enable_vae_tiling,
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
        """Release GPU memory."""
        if self._pipe is not None:
            import torch

            del self._pipe
            self._pipe = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            log.info("SDXL pipeline unloaded, GPU memory released.")
