#!/usr/bin/env python3
"""Pre-generate SDXL images for the static opening steps.

Run once after downloading the model:
    python scripts/generate_opening_assets.py
"""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def main():
    from app.config import settings
    from app.content import get_world
    from app.agents.scripted import ScriptedNarrator
    from app.agents.visual import VisualAgent
    from app.domain.state import GameSession, WorldState, PlayerProfile, CharacterState
    from app.runtime import build_runtime
    import logging
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("generate_opening_assets")

    # Force image generation enabled and SDXL backend for pregeneration
    settings.IMAGE_GENERATION_ENABLED = True
    settings.IMAGE_BACKEND = "sdxl"
    settings.SDXL_OFFLINE_MODE = True

    logger.info("Building runtime and initializing SDXL pipeline...")
    runtime = await build_runtime(settings)
    world = runtime.world
    narrator = ScriptedNarrator(world)
    visual_agent = VisualAgent(world)

    session = GameSession(
        id="static-opening-preview",
        world_id=world.id,
        player=PlayerProfile(name="Player"),
        world=WorldState(
            location="classroom",
            time_of_day="morning",
            present_characters=[c.id for c in world.characters],
            arc=world.arcs[0] if world.arcs else "prologue",
        ),
        characters={
            c.id: CharacterState(
                id=c.id,
                name=c.name,
                relationship=dict(c.starting_relationship),
                current_emotion=c.default_emotion,
            )
            for c in world.characters
        },
    )
    
    logger.info("Extracting opening steps...")
    run = narrator.opening(session)
    steps = run.steps
    logger.info(f"Generated {len(steps)} steps.")
    
    unique_specs = {}
    for step in steps:
        if step.visual:
            visual_spec = visual_agent.normalise(step, session)
            asset_specs = visual_agent.specs_for(visual_spec)
            for spec in asset_specs:
                if spec.cache_key not in unique_specs:
                    unique_specs[spec.cache_key] = spec

    logger.info(f"Found {len(unique_specs)} unique visual assets to generate.")

    for i, (key, spec) in enumerate(unique_specs.items(), 1):
        logger.info(f"Generating [{i}/{len(unique_specs)}] {spec.kind}: {key} …")
        ref = await runtime.asset_service.ensure(spec, world.id)
        logger.info(f"  -> AssetRef: status={ref.status.value}, asset_id={ref.asset_id}, url={ref.url}")

    await runtime.close()
    logger.info("Pre-generation complete! All opening assets are ready.")

if __name__ == "__main__":
    asyncio.run(main())
