"""
Generate visual novel art for the Decalove frontend using local GPU (Stable Diffusion).

Generates backgrounds and character sprites matching the anime VN art style
already present in game/images/, saving them to frontend/public/images/ where
the frontend's art.ts probes for static assets.

Requirements:
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
    pip install diffusers transformers accelerate safetensors
"""

import argparse
import os
import sys
import time
from pathlib import Path

import torch
from diffusers import StableDiffusionXLPipeline, AutoPipelineForText2Image
from PIL import Image
from minio import Minio

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
FRONTEND_IMAGES = ROOT / "frontend" / "public" / "images"
BG_DIR = FRONTEND_IMAGES / "bg"
CHAR_DIR = FRONTEND_IMAGES / "characters"

# ---------------------------------------------------------------------------
# Quality / perf settings for RTX 5050 (8 GB VRAM)
# ---------------------------------------------------------------------------
MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"
DEVICE = "cuda"
DTYPE = torch.float16
# Background: 1280x720 (VN standard 16:9)
BG_WIDTH, BG_HEIGHT = 1280, 720
# Character sprites: tall portrait, transparent-friendly
CHAR_WIDTH, CHAR_HEIGHT = 512, 768
NUM_INFERENCE_STEPS = 30
GUIDANCE_SCALE = 7.5

# ---------------------------------------------------------------------------
# Common style prefix — anime VN backgrounds with warm lighting
# ---------------------------------------------------------------------------
STYLE_BG = (
    "anime visual novel background, high quality, detailed, "
    "no people, no characters, empty scene, "
    "beautiful lighting, makoto shinkai style, "
    "sharp details, concept art, digital painting"
)

STYLE_CHAR = (
    "anime visual novel character sprite, full body portrait, "
    "high quality, detailed, clean lineart, "
    "japanese high school student, school uniform, "
    "white background, simple background, "
    "character design sheet, digital art"
)

NEGATIVE_PROMPT_BG = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, "
    "extra digit, fewer digits, cropped, worst quality, low quality, "
    "normal quality, jpeg artifacts, signature, watermark, username, "
    "blurry, people, characters, person, figure, humans"
)

NEGATIVE_PROMPT_CHAR = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, "
    "extra digit, fewer digits, cropped, worst quality, low quality, "
    "normal quality, jpeg artifacts, signature, watermark, username, "
    "blurry, deformed, disfigured, multiple views, multiple angles"
)

# ---------------------------------------------------------------------------
# Image definitions — matched to game/images/ structure
# ---------------------------------------------------------------------------
BACKGROUNDS = {
    "classroom.png": "japanese high school classroom interior, wooden desks and chairs, chalkboard, large windows with sunlight streaming in, morning light, warm atmosphere",
    "classroom_morning.png": "japanese high school classroom interior, wooden desks and chairs, chalkboard, large windows with bright morning sunlight, golden hour morning light, dust motes in sunbeams",
    "cafeteria.png": "japanese high school cafeteria interior, long wooden tables and benches, food trays, large windows, industrial ceiling, warm sunlight",
    "cafeteria_noon.png": "japanese high school cafeteria interior, long wooden tables and benches, food trays, large windows, bright noon sunlight, lively atmosphere",
    "library.png": "japanese high school library interior, tall wooden bookshelves filled with books, reading tables with desk lamps, wooden floor, warm afternoon light through windows",
    "library_noon.png": "japanese high school library interior, tall wooden bookshelves filled with books, reading tables with desk lamps, wooden floor, afternoon sunlight streaming through windows",
    "rooftop.png": "japanese high school rooftop, chain-link fence, metal door, pipes and ventilation, city skyline view, dramatic sunset sky, orange and purple clouds",
    "rooftop_sunset.png": "japanese high school rooftop, chain-link fence overlooking city skyline, dramatic sunset, golden hour, orange and purple sky, city lights beginning to glow",
}

# Character descriptions derived from the actual game sprites
CHARACTERS = {
    "aiko": {
        "base": "anime girl, black hair in high ponytail with dark red ribbon, brown eyes, serious composed expression, navy blue school blazer uniform, white dress shirt, dark red bow tie, pleated navy skirt, school crest on blazer",
        "expressions": {
            "neutral": "neutral calm expression, standing straight",
            "composed": "composed dignified expression, hands clasped together in front",
            "thoughtful": "thoughtful pensive expression, looking slightly down, hands together",
        },
    },
    "haruto": {
        "base": "anime boy, messy black hair, glasses, calm intellectual expression, white dress shirt with sleeves rolled up, dark navy tie, navy dress pants, black belt, holding a book, school logo on shirt pocket",
        "expressions": {
            "neutral": "neutral calm expression, holding a book",
            "composed": "composed focused expression, adjusting glasses",
            "serious": "serious stern expression, arms crossed",
        },
    },
    "mika": {
        "base": "anime girl, short messy auburn red hair with ahoge cowlick, bright green eyes, energetic cheerful expression, green track jacket over navy school blazer, striped tie, navy skirt, athletic bracelet on wrist",
        "expressions": {
            "neutral": "neutral relaxed expression, hand on hip",
            "happy": "happy bright smile, cheerful expression",
            "excited": "excited enthusiastic expression, wide grin, leaning forward",
        },
    },
    "ren": {
        "base": "anime boy, messy silver gray hair, golden amber eyes, confident smirk, navy school blazer with pins and patches, white shirt, navy tie loosened, headphones around neck, backpack on one shoulder",
        "expressions": {
            "neutral": "neutral cool expression, one hand in pocket",
            "amused": "amused playful smirk, hand behind head, relaxed pose",
        },
    },
}

# Preview images (small thumbnails for character selection)
PREVIEWS = {
    "_preview_aiko.jpg": ("aiko", "face closeup portrait"),
    "_preview_haruto.jpg": ("haruto", "face closeup portrait"),
    "_preview_mika.jpg": ("mika", "face closeup portrait"),
    "_preview_ren.jpg": ("ren", "face closeup portrait"),
    "_preview_aiko_small.png": ("aiko", "face closeup portrait, small icon"),
}


def load_pipeline():
    """Load the SDXL pipeline with memory optimizations for 8GB VRAM."""
    print(f"Loading model {MODEL_ID}...")
    print(f"  Device: {DEVICE}")
    print(f"  VRAM: {torch.cuda.get_device_properties(0).total_mem / 1024**3:.1f} GB")

    pipe = StableDiffusionXLPipeline.from_pretrained(
        MODEL_ID,
        torch_dtype=DTYPE,
        use_safetensors=True,
        variant="fp16",
    )

    # Memory optimizations for 8GB VRAM
    pipe.to(DEVICE)
    pipe.enable_attention_slicing()

    # Try to enable xformers if available for extra speed
    try:
        pipe.enable_xformers_memory_efficient_attention()
        print("  xformers: enabled")
    except Exception:
        print("  xformers: not available (using default attention)")

    return pipe


def generate_backgrounds(pipe):
    """Generate all background images."""
    BG_DIR.mkdir(parents=True, exist_ok=True)
    total = len(BACKGROUNDS)

    for i, (filename, description) in enumerate(BACKGROUNDS.items(), 1):
        output_path = BG_DIR / filename
        if output_path.exists():
            print(f"  [{i}/{total}] SKIP {filename} (already exists)")
            continue

        prompt = f"{STYLE_BG}, {description}"
        print(f"  [{i}/{total}] Generating {filename}...")
        start = time.time()

        image = pipe(
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT_BG,
            width=BG_WIDTH,
            height=BG_HEIGHT,
            num_inference_steps=NUM_INFERENCE_STEPS,
            guidance_scale=GUIDANCE_SCALE,
            generator=torch.Generator(device=DEVICE).manual_seed(42 + i),
        ).images[0]

        image.save(output_path, "PNG")
        elapsed = time.time() - start
        print(f"           Saved ({elapsed:.1f}s)")


def generate_characters(pipe):
    """Generate character sprites and expression variants."""
    CHAR_DIR.mkdir(parents=True, exist_ok=True)

    for char_id, char_data in CHARACTERS.items():
        char_dir = CHAR_DIR / char_id
        char_dir.mkdir(parents=True, exist_ok=True)
        base_desc = char_data["base"]
        expressions = char_data["expressions"]

        # Generate base sprite (default / neutral)
        base_path = CHAR_DIR / f"{char_id}.png"
        if not base_path.exists():
            prompt = f"{STYLE_CHAR}, {base_desc}, standing pose, full body"
            print(f"  Generating {char_id}.png (base sprite)...")
            start = time.time()

            image = pipe(
                prompt=prompt,
                negative_prompt=NEGATIVE_PROMPT_CHAR,
                width=CHAR_WIDTH,
                height=CHAR_HEIGHT,
                num_inference_steps=NUM_INFERENCE_STEPS,
                guidance_scale=GUIDANCE_SCALE,
                generator=torch.Generator(device=DEVICE).manual_seed(
                    hash(char_id) % 2**32
                ),
            ).images[0]

            image.save(base_path, "PNG")
            elapsed = time.time() - start
            print(f"           Saved ({elapsed:.1f}s)")
        else:
            print(f"  SKIP {char_id}.png (already exists)")

        # Generate expression variants
        for expr_name, expr_desc in expressions.items():
            expr_path = char_dir / f"{expr_name}.png"
            if expr_path.exists():
                print(f"  SKIP {char_id}/{expr_name}.png (already exists)")
                continue

            prompt = f"{STYLE_CHAR}, {base_desc}, {expr_desc}, full body"
            print(f"  Generating {char_id}/{expr_name}.png...")
            start = time.time()

            image = pipe(
                prompt=prompt,
                negative_prompt=NEGATIVE_PROMPT_CHAR,
                width=CHAR_WIDTH,
                height=CHAR_HEIGHT,
                num_inference_steps=NUM_INFERENCE_STEPS,
                guidance_scale=GUIDANCE_SCALE,
                generator=torch.Generator(device=DEVICE).manual_seed(
                    hash(f"{char_id}_{expr_name}") % 2**32
                ),
            ).images[0]

            image.save(expr_path, "PNG")
            elapsed = time.time() - start
            print(f"           Saved ({elapsed:.1f}s)")


def generate_previews(pipe):
    """Generate small preview/thumbnail images for character selection."""
    CHAR_DIR.mkdir(parents=True, exist_ok=True)

    for filename, (char_id, extra) in PREVIEWS.items():
        output_path = CHAR_DIR / filename
        if output_path.exists():
            print(f"  SKIP {filename} (already exists)")
            continue

        char_desc = CHARACTERS[char_id]["base"]
        prompt = f"{STYLE_CHAR}, {char_desc}, {extra}"
        print(f"  Generating {filename}...")
        start = time.time()

        image = pipe(
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT_CHAR,
            width=512,
            height=512,
            num_inference_steps=NUM_INFERENCE_STEPS,
            guidance_scale=GUIDANCE_SCALE,
            generator=torch.Generator(device=DEVICE).manual_seed(
                hash(f"preview_{char_id}") % 2**32
            ),
        ).images[0]

        # Save as appropriate format
        if filename.endswith(".jpg"):
            image.save(output_path, "JPEG", quality=90)
        else:
            # Resize for small variant
            if "small" in filename:
                image = image.resize((128, 128), Image.LANCZOS)
            image.save(output_path, "PNG")

        elapsed = time.time() - start
        print(f"           Saved ({elapsed:.1f}s)")


def upload_to_minio(source_dir):
    """Upload images from the source directory to MinIO."""
    print(f"\n--- Uploading images from {source_dir} to MinIO ---")
    
    endpoint = "localhost:9000"
    access_key = "minioadmin"
    secret_key = "minioadmin"
    secure = False
    bucket_name = "decalove-assets"
    
    try:
        client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            print(f"Created bucket '{bucket_name}'")
            
        source_path = Path(source_dir)
        if not source_path.exists():
            print(f"ERROR: Source directory {source_path} does not exist.")
            return

        for ext in ("*.png", "*.jpg"):
            for file_path in source_path.rglob(ext):
                rel_path = file_path.relative_to(source_path)
                object_key = f"static/images/{rel_path.as_posix()}"
                
                try:
                    client.stat_object(bucket_name, object_key)
                    print(f"  SKIP {object_key} (already exists in MinIO)")
                    continue
                except Exception:
                    pass
                
                print(f"  Uploading {object_key}...")
                client.fput_object(bucket_name, object_key, str(file_path))
                
        print("Upload complete!")
    except Exception as e:
        print(f"ERROR: Failed to upload to MinIO: {e}")


def main():
    parser = argparse.ArgumentParser(description="Decalove Image Generator/Uploader")
    parser.add_argument("--upload-only", action="store_true", help="Skip generation, just upload to MinIO")
    parser.add_argument("--source", type=str, help="Source directory for images (default: frontend/public/images)")
    args = parser.parse_args()

    print("=" * 60)
    print("Decalove Frontend Image Generator & Uploader")
    print("=" * 60)

    source_dir = Path(args.source) if args.source else FRONTEND_IMAGES

    if not args.upload_only:
        if not torch.cuda.is_available():
            print("ERROR: CUDA is not available. Install PyTorch with CUDA:")
            print("  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128")
            sys.exit(1)

        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"Output: {FRONTEND_IMAGES}")
        print()

        pipe = load_pipeline()

        print("\n--- Generating Backgrounds ---")
        generate_backgrounds(pipe)

        print("\n--- Generating Character Sprites ---")
        generate_characters(pipe)

        print("\n--- Generating Preview Thumbnails ---")
        generate_previews(pipe)

        # Count generated files
        total_files = sum(1 for _ in FRONTEND_IMAGES.rglob("*.png")) + sum(
            1 for _ in FRONTEND_IMAGES.rglob("*.jpg")
        )
        print(f"\n{'=' * 60}")
        print(f"Done! Generated {total_files} images in {FRONTEND_IMAGES}")
        print(f"The frontend will automatically pick them up via art.ts probing.")
        print(f"{'=' * 60}")
        
        # Default upload source to FRONTEND_IMAGES after generation if not overridden
        if not args.source:
            source_dir = FRONTEND_IMAGES

    upload_to_minio(source_dir)


if __name__ == "__main__":
    main()
