#!/usr/bin/env python3
"""Pre-generate a wide variety of background and character assets using SDXL.

Usage:
    python scripts/generate_asset_variations.py [--category all|backgrounds|characters] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("generate_asset_variations")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-generate SDXL visual assets across world locations & character emotions.")
    parser.add_argument("--category", choices=["all", "backgrounds", "characters"], default="all")
    parser.add_argument("--limit", type=int, default=0, help="Max number of assets to generate (0 = all)")
    args = parser.parse_args()

    from app.agents.visual import AssetSpec, VisualAgent
    from app.config import settings
    from app.domain.story import VisualSpec
    from app.runtime import build_runtime

    settings.IMAGE_GENERATION_ENABLED = True
    settings.IMAGE_BACKEND = "sdxl"
    settings.SDXL_OFFLINE_MODE = True

    logger.info("Initializing Decalove runtime and SDXL pipeline...")
    runtime = await build_runtime(settings)
    world = runtime.world
    visual_agent = VisualAgent(world)

    unique_specs: dict[str, AssetSpec] = {}

    # 1. Background variations (all locations x supported times of day)
    if args.category in ("all", "backgrounds"):
        for loc in world.locations:
            for time_of_day in loc.times:
                spec = VisualSpec(
                    background=loc.id,
                    time_of_day=time_of_day,
                    weather="clear",
                )
                bg_spec = visual_agent.background_spec(spec)
                if bg_spec and bg_spec.cache_key not in unique_specs:
                    unique_specs[bg_spec.cache_key] = bg_spec

    # 2. Character variations (all characters x all expressions at common locations)
    if args.category in ("all", "characters"):
        key_locations = ["classroom", "rooftop", "library", "school_gate", "park"]
        for character in world.characters:
            for expression in character.expressions:
                for loc_id in key_locations:
                    loc = world.location(loc_id)
                    time_of_day = loc.times[0] if loc and loc.times else "afternoon"
                    spec = VisualSpec(
                        background=loc_id,
                        character=character.id,
                        expression=expression,
                        time_of_day=time_of_day,
                    )
                    ch_spec = visual_agent.character_spec(spec)
                    if ch_spec and ch_spec.cache_key not in unique_specs:
                        unique_specs[ch_spec.cache_key] = ch_spec

    total_count = len(unique_specs)
    logger.info("Total asset variations planned: %d", total_count)

    # Filter out already existing assets in the repository
    specs_to_generate = []
    for key, spec in unique_specs.items():
        existing = await runtime.assets_repo.by_cache_key(key)
        if existing is not None:
            logger.debug("Already cached: %s (%s)", key, spec.kind)
        else:
            specs_to_generate.append(spec)

    logger.info("New assets to generate (uncached): %d", len(specs_to_generate))

    if args.limit > 0:
        specs_to_generate = specs_to_generate[: args.limit]
        logger.info("Limiting generation to first %d assets", args.limit)

    for i, spec in enumerate(specs_to_generate, 1):
        logger.info("Generating [%d/%d] %s: %s", i, len(specs_to_generate), spec.kind, spec.cache_key)
        ref = await runtime.asset_service.ensure(spec, world.id)
        logger.info("  -> Status: %s, Asset ID: %s", ref.status.value, ref.asset_id)

    await runtime.close()
    logger.info("Finished generation run!")


if __name__ == "__main__":
    asyncio.run(main())
