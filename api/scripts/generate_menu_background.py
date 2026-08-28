#!/usr/bin/env python3
"""Generate the main menu background for Decalove visual novel."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("generate_menu_background")


async def main() -> None:
    from app.config import settings
    from app.llm.sdxl_image import SDXLImageProvider
    from app.runtime import build_runtime

    settings.IMAGE_GENERATION_ENABLED = True
    settings.IMAGE_BACKEND = "sdxl"
    settings.SDXL_OFFLINE_MODE = True

    runtime = await build_runtime(settings)
    
    prompt = (
        "anime visual novel title screen key art, japanese high school entrance and cherry blossom trees at sunset golden hour, "
        "falling sakura petals drifting in the wind, glowing warm rim light, empty stone pathway leading through the iron gate, "
        "wide sky with soft orange and violet clouds, cinematic nostalgic romantic mood, Makoto Shinkai style, "
        "soft cel shading, high quality 4k wallpaper, no people, no text"
    )
    negative_prompt = "blurry, low quality, deformed, text, watermark, logo, characters, humans, ugly, artifacts"

    logger.info("Generating main menu background with SDXL...")
    image_provider = SDXLImageProvider(
        model_id=settings.SDXL_MODEL_ID,
        model_dir=settings.SDXL_MODEL_DIR,
        device=settings.SDXL_DEVICE,
        torch_dtype=settings.SDXL_TORCH_DTYPE,
        num_inference_steps=35,
        guidance_scale=8.0,
        negative_prompt=negative_prompt,
        enable_attention_slicing=settings.SDXL_ATTENTION_SLICING,
        enable_vae_tiling=settings.SDXL_VAE_TILING,
        offline_mode=True,
    )

    image_bytes, content_type = await image_provider.generate(
        prompt, width=1024, height=576
    )

    # Save to MinIO
    object_key = "ui/main_menu.png"
    await runtime.store.put(object_key, image_bytes, "image/png")
    logger.info("Saved to MinIO: %s", object_key)

    # Save to local directory
    out_dir = Path(__file__).resolve().parent.parent / "var" / "assets" / "ui"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "main_menu.png"
    with open(out_path, "wb") as f:
        f.write(image_bytes)
    logger.info("Saved local copy to %s", out_path)

    # Save to game folder (Ren'Py gui)
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        # 1280x720 matches default Ren'Py resolution
        img_resized = img.resize((1280, 720), Image.Resampling.LANCZOS)
        game_gui_dir = Path(__file__).resolve().parent.parent.parent / "game" / "gui"
        if game_gui_dir.exists():
            game_main_menu = game_gui_dir / "main_menu.png"
            game_game_menu = game_gui_dir / "game_menu.png"
            img_resized.save(game_main_menu, "PNG")
            img_resized.save(game_game_menu, "PNG")
            logger.info("Saved game copy to %s and %s", game_main_menu, game_game_menu)
    except Exception as e:
        logger.warning("Could not write to game folder: %s", e)

    await runtime.close()
    await image_provider.aclose()
    logger.info("Main menu background generation complete!")


if __name__ == "__main__":
    asyncio.run(main())
