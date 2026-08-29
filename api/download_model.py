#!/usr/bin/env python3
"""Pre-download the SDXL model weights into the local models/ directory.

Run this once before starting the API so the first image request doesn't block
while downloading ~6.5 GB of weights:

    python download_model.py            # uses defaults from .env / config
    python download_model.py --dir models/sdxl --model stabilityai/stable-diffusion-xl-base-1.0

The script stores weights in api/models/sdxl/ (or wherever SDXL_MODEL_DIR points).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# So that `from app.config import settings` works when run from the api/ dir.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Download SDXL model weights into the local models/ directory.")
    parser.add_argument(
        "--model",
        default=None,
        help="Hugging Face model ID (default: from SDXL_MODEL_ID env / config)",
    )
    parser.add_argument(
        "--dir",
        default=None,
        help="Local directory to store weights (default: from SDXL_MODEL_DIR env / config)",
    )
    args = parser.parse_args()

    # Load project settings (reads .env automatically).
    from app.config import settings

    model_id = args.model or settings.SDXL_MODEL_ID
    model_dir = args.dir or settings.SDXL_MODEL_DIR

    # Resolve relative paths against api/ root.
    model_path = Path(model_dir)
    if not model_path.is_absolute():
        model_path = Path(__file__).resolve().parent / model_path
    model_path.mkdir(parents=True, exist_ok=True)

    print(f"Model:     {model_id}")
    print(f"Cache dir: {model_path}")
    print()

    # Prevent HF from also writing to ~/.cache/huggingface.
    os.environ["HF_HOME"] = str(model_path)
    os.environ["TRANSFORMERS_CACHE"] = str(model_path)

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

    from diffusers import StableDiffusionXLPipeline

    dtype = getattr(torch, settings.SDXL_TORCH_DTYPE, torch.float16)

    print(f"Downloading {model_id} (fp16 safetensors) …")
    StableDiffusionXLPipeline.from_pretrained(
        model_id,
        torch_dtype=dtype,
        use_safetensors=True,
        variant="fp16",
        cache_dir=str(model_path),
    )
    print()
    print(f"✓ Model downloaded to {model_path}")
    print("  You can now start the API — it will load from this directory without re-downloading.")


if __name__ == "__main__":
    main()
