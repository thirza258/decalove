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
import gc
import os
import shutil
import sys
import time
from pathlib import Path

# Patch PyTorch 3.14 compatibility before diffusers imports
try:
    import torch
    if not hasattr(torch, "xpu"):
        class _DummyXPU:
            @staticmethod
            def is_available() -> bool: return False
            @staticmethod
            def device_count() -> int: return 0
            @staticmethod
            def current_device() -> int: return 0
        torch.xpu = _DummyXPU()
except Exception:
    pass

from PIL import Image
from minio import Minio

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
FRONTEND_IMAGES = ROOT / "frontend" / "public" / "images"
GAME_IMAGES = ROOT / "game" / "images"
MODEL_DIR = ROOT / "api" / "models" / "sdxl"

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
# Character sprites: tall portrait
CHAR_WIDTH, CHAR_HEIGHT = 512, 768
DEFAULT_STEPS = 20
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
    # 1. Classroom (morning, noon, afternoon)
    "classroom.png": "japanese high school classroom interior, wooden desks and chairs, chalkboard, large windows with sunlight streaming in, morning light, warm atmosphere",
    "classroom_morning.png": "japanese high school classroom interior, wooden desks and chairs, chalkboard, large windows with bright morning sunlight, golden hour morning light, dust motes in sunbeams",
    "classroom_noon.png": "japanese high school classroom interior, bright midday sun through large windows, empty desks, clean chalkboard, vivid colors",
    "classroom_afternoon.png": "japanese high school classroom interior, empty desks in rows, warm late afternoon sunlight, dust motes in golden sunbeams, peaceful quiet classroom",

    # 2. Cafeteria (noon)
    "cafeteria.png": "japanese high school cafeteria interior, long wooden tables and benches, food trays, large windows, industrial ceiling, warm sunlight",
    "cafeteria_noon.png": "japanese high school cafeteria interior, long wooden tables and benches, food trays, large windows, bright noon sunlight, lively atmosphere",

    # 3. Library (noon, afternoon, evening)
    "library.png": "japanese high school library interior, tall wooden bookshelves filled with books, reading tables with desk lamps, wooden floor, warm afternoon light through windows",
    "library_noon.png": "japanese high school library interior, tall wooden bookshelves filled with books, reading tables with desk lamps, wooden floor, afternoon sunlight streaming through windows",
    "library_afternoon.png": "japanese high school library interior, long shadows between tall wooden bookshelves, warm golden hour sunlight, quiet study carrels",
    "library_evening.png": "japanese high school library interior, tall wooden bookshelves, warm glowing reading desk lamps, dusk outside windows, quiet cozy atmosphere",

    # 4. Rooftop (noon, afternoon, sunset, evening)
    "rooftop.png": "japanese high school rooftop, chain-link fence, metal door, pipes and ventilation, city skyline view, dramatic sunset sky, orange and purple clouds",
    "rooftop_noon.png": "japanese high school rooftop, chain-link fence, panoramic city skyline view, clear blue midday sky with white fluffy clouds, bright sunlight",
    "rooftop_afternoon.png": "japanese high school rooftop, chain-link fence overlooking town, warm afternoon sunlight, wide sky with light clouds",
    "rooftop_sunset.png": "japanese high school rooftop, chain-link fence overlooking city skyline, dramatic sunset, golden hour, orange and purple sky, city lights beginning to glow",
    "rooftop_evening.png": "japanese high school rooftop, chain-link fence overlooking town skyline at twilight, deep blue and purple sky, glowing city lights in distance, serene mood",

    # 5. School Gate (morning, noon, afternoon, sunset)
    "school_gate.png": "japanese high school entrance front gate, iron gates, bicycle racks, cherry blossom trees, sidewalk, peaceful campus entrance",
    "school_gate_morning.png": "japanese high school front gate, bright fresh morning light, cherry blossom trees, bicycle parking racks, school building entrance",
    "school_gate_noon.png": "japanese high school front gate, bright midday sun, paved entrance road, cherry trees, open iron gate",
    "school_gate_afternoon.png": "japanese high school front gate, warm afternoon sunlight, cherry blossom trees along path, bicycle racks, gate open",
    "school_gate_sunset.png": "japanese high school front gate at golden sunset hour, long warm shadows, glowing orange sky, cherry trees, end of school day",

    # 6. Riverside Park (afternoon, sunset, evening)
    "park.png": "riverside park, grassy bank sloping down to water, single wooden park bench, vending machine, peaceful afternoon scenery",
    "park_afternoon.png": "riverside park, green grassy riverbank, single bench, vending machine, bright afternoon sun reflecting on sparkling river water",
    "park_sunset.png": "riverside park at sunset, grassy slope down to river, single bench, softly glowing vending machine, golden orange reflection on water surface",
    "park_evening.png": "riverside park at evening twilight, dusk sky, single bench beside river, warm streetlight glow, quiet tranquil riverside",

    # 7. Train Station (afternoon, sunset, evening, night)
    "train_station.png": "small japanese train station platform, departure schedule board, empty wooden benches, railway tracks, suburban station",
    "train_station_afternoon.png": "small suburban train station platform, warm afternoon sunlight, overhead canopy, empty wooden benches, railway tracks",
    "train_station_sunset.png": "small japanese train station platform at sunset, glowing departure board, dramatic orange and purple sunset sky over tracks",
    "train_station_evening.png": "suburban japanese train platform at twilight, glowing station platform lamps, departure board illuminated, dusk sky",
    "train_station_night.png": "quiet japanese train station platform at night, overhead fluorescent lights glowing, empty platform, dark clear night sky",

    # 8. Player's Bedroom (morning, afternoon, evening, night)
    "player_home.png": "cozy japanese teenager bedroom, wooden study desk, bookshelf, unmade bed, window, warm interior lighting",
    "player_home_morning.png": "cozy teenager bedroom interior, bright morning sunlight streaming through curtains onto wooden desk and unmade bed",
    "player_home_afternoon.png": "cozy teenager bedroom interior, afternoon sunlight through window, study desk with lamp, books on shelves",
    "player_home_evening.png": "cozy bedroom interior at twilight, warm desk lamp glowing, quiet evening room atmosphere, dusk through window",
    "player_home_night.png": "cozy bedroom interior at night, warm yellow bedside lamp light, dark starry night sky outside window, quiet peaceful room",
}

# Character descriptions derived from the actual game sprites
CHARACTERS = {
    "aiko": {
        "base": "anime girl, black hair in high ponytail with dark red ribbon, brown eyes, serious composed expression, navy blue school blazer uniform, white dress shirt, dark red bow tie, pleated navy skirt, school crest on blazer",
        "expressions": {
            "neutral": "neutral calm expression, standing straight",
            "composed": "composed dignified expression, hands clasped together in front",
            "thoughtful": "thoughtful pensive expression, looking slightly down, hands together",
            "happy": "happy gentle smile, warm affectionate expression, slight blush on cheeks",
            "embarrassed": "flustered shy expression, blushing cheeks, looking slightly away, hands fidgeting",
            "surprised": "wide brown eyes, slightly parted lips, surprised taken aback expression",
            "sad": "downcast gaze, subtle melancholic expression, subdued gentle frown",
            "annoyed": "slight pout, furrowed brows, arms crossed, mildly irritated expression",
        },
    },
    "haruto": {
        "base": "anime boy, messy black hair, glasses, calm intellectual expression, white dress shirt with sleeves rolled up, dark navy tie, navy dress pants, black belt, holding a book, school logo on shirt pocket",
        "expressions": {
            "neutral": "neutral calm expression, holding a book",
            "composed": "composed focused expression, adjusting glasses",
            "serious": "serious stern expression, arms crossed",
            "reserved": "quiet introverted expression, looking slightly aside, adjusting glasses calmly",
            "faint_smile": "rare subtle gentle smile, warm eyes behind glasses, relaxed posture",
            "surprised": "widened eyes behind glasses, head tilted slightly, caught off guard",
            "troubled": "conflicted thoughtful expression, hand touching chin, furrowed brow",
            "sad": "quiet downcast expression, looking down at his book, gentle sorrow",
            "annoyed": "exasperated sigh expression, tired eyes, slight scowl",
            "thoughtful": "deep in thought, finger on glasses frame, reflective expression",
        },
    },
    "mika": {
        "base": "anime girl, short messy auburn red hair with ahoge cowlick, bright green eyes, energetic cheerful expression, green track jacket over navy school blazer, striped tie, navy skirt, athletic bracelet on wrist",
        "expressions": {
            "neutral": "neutral relaxed expression, hand on hip",
            "happy": "happy bright smile, cheerful expression",
            "excited": "excited enthusiastic expression, wide grin, leaning forward",
            "cheerful": "radiant beaming grin, sparkling green eyes, enthusiastic energetic stance",
            "laughing": "hearty open laughter, eyes crinkled with joy, one hand waving",
            "surprised": "wide open eyes, mouth in 'o' shape, shocked playful reaction",
            "pouting": "childish cute pout, puffed cheeks, arms crossed",
            "sad": "subdued downcast look, cowlick drooping, quiet regretful expression",
            "determined": "fierce determined grin, clenched fist in front, resolute eyes",
            "embarrassed": "blushing bright red, sheepish grin, scratching back of head",
        },
    },
    "ren": {
        "base": "anime boy, messy silver gray hair, golden amber eyes, confident smirk, navy school blazer with pins and patches, white shirt, navy tie loosened, headphones around neck, backpack on one shoulder",
        "expressions": {
            "neutral": "neutral cool expression, one hand in pocket",
            "amused": "amused playful smirk, hand behind head, relaxed pose",
            "grinning": "wide playful toothy grin, winking playfully, carefree confident pose",
            "surprised": "widened amber eyes, eyebrow raised in sudden surprise, slightly tilted head",
            "serious": "rare sincere earnest expression, focused attentive gaze, no smirk",
            "sad": "quiet wistful gaze, gentle somber look, hands in pockets",
            "embarrassed": "faint blush across cheeks, looking to the side, tugging lightly at headphones",
            "thoughtful": "sketching in a sketchbook, pensive artistic expression, lost in thought",
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
    """Load SDXL pipeline with memory optimizations for RTX 5050 (8 GB VRAM)."""
    from diffusers import StableDiffusionXLPipeline

    print(f"Loading model {MODEL_ID}...")
    print(f"  Device: {DEVICE}")
    total_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    print(f"  VRAM:   {total_mem:.2f} GB")

    kwargs = {
        "torch_dtype": DTYPE,
        "use_safetensors": True,
        "variant": "fp16",
    }
    if MODEL_DIR.exists():
        kwargs["cache_dir"] = str(MODEL_DIR)
        kwargs["local_files_only"] = True

    pipe = StableDiffusionXLPipeline.from_pretrained(MODEL_ID, **kwargs)
    try:
        pipe.enable_model_cpu_offload()
        print("  model cpu offload: enabled")
    except Exception as e:
        print(f"  falling back to pipe.to({DEVICE}): {e}")
        pipe.to(DEVICE)
    pipe.enable_attention_slicing()
    try:
        pipe.vae.enable_slicing()
        pipe.vae.enable_tiling()
        print("  VAE slicing & tiling: enabled")
    except Exception:
        pass

    try:
        pipe.enable_xformers_memory_efficient_attention()
        print("  xformers: enabled")
    except Exception:
        pass

    return pipe


def clean_vram():
    """Clean CUDA cache and garbage collection."""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def sync_file_to_game(src_path: Path, rel_subpath: str):
    """Mirror generated image into game/images/ so Ren'Py has it as well."""
    dest_path = GAME_IMAGES / rel_subpath
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dest_path)


def upload_single_to_minio(file_path: Path, object_key: str, bucket_name="decalove-assets"):
    """Immediately upload a generated image to MinIO so it is live right away."""
    try:
        client = Minio("127.0.0.1:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)
        content_type = "image/jpeg" if str(file_path).endswith(".jpg") else "image/png"
        client.fput_object(bucket_name, object_key, str(file_path), content_type=content_type)
        print(f"           Uploaded to MinIO: {object_key}")
    except Exception as e:
        print(f"           MinIO upload warning for {object_key}: {e}")


def generate_backgrounds(pipe, filter_location=None, limit=0, steps=DEFAULT_STEPS, force=False):
    """Generate background images for all locations."""
    BG_DIR.mkdir(parents=True, exist_ok=True)
    
    items = list(BACKGROUNDS.items())
    if filter_location:
        items = [(k, v) for k, v in items if k.startswith(filter_location)]

    generated_count = 0
    total = len(items)

    print(f"\n--- Processing {total} Backgrounds (filter: {filter_location or 'all'}) ---")

    for i, (filename, description) in enumerate(items, 1):
        output_path = BG_DIR / filename
        if output_path.exists() and not force:
            print(f"  [{i}/{total}] SKIP {filename} (already exists)")
            sync_file_to_game(output_path, f"bg/{filename}")
            continue

        if limit > 0 and generated_count >= limit:
            print(f"Reached generation limit ({limit}). Stopping backgrounds.")
            break

        prompt = f"{STYLE_BG}, {description}"
        print(f"  [{i}/{total}] Generating {filename} ({steps} steps)...")
        start = time.time()

        image = pipe(
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT_BG,
            width=BG_WIDTH,
            height=BG_HEIGHT,
            num_inference_steps=steps,
            guidance_scale=GUIDANCE_SCALE,
            generator=torch.Generator(device=DEVICE).manual_seed(42 + i),
        ).images[0]

        image.save(output_path, "PNG")
        sync_file_to_game(output_path, f"bg/{filename}")
        upload_single_to_minio(output_path, f"static/images/bg/{filename}")
        elapsed = time.time() - start
        print(f"           Saved to frontend & game ({elapsed:.1f}s)")
        generated_count += 1
        clean_vram()

    return generated_count


def generate_characters(pipe, filter_char=None, limit=0, steps=DEFAULT_STEPS, force=False):
    """Generate character sprites and expression variants."""
    CHAR_DIR.mkdir(parents=True, exist_ok=True)
    generated_count = 0

    chars = CHARACTERS.items()
    if filter_char:
        chars = [(k, v) for k, v in chars if k == filter_char]

    for char_id, char_data in chars:
        char_dir = CHAR_DIR / char_id
        char_dir.mkdir(parents=True, exist_ok=True)
        base_desc = char_data["base"]
        expressions = char_data["expressions"]

        # 1. Base sprite
        base_path = CHAR_DIR / f"{char_id}.png"
        if not base_path.exists() or force:
            if limit > 0 and generated_count >= limit:
                return generated_count
            prompt = f"{STYLE_CHAR}, {base_desc}, standing pose, full body"
            print(f"  Generating base {char_id}.png ({steps} steps)...")
            start = time.time()
            image = pipe(
                prompt=prompt,
                negative_prompt=NEGATIVE_PROMPT_CHAR,
                width=CHAR_WIDTH,
                height=CHAR_HEIGHT,
                num_inference_steps=steps,
                guidance_scale=GUIDANCE_SCALE,
                generator=torch.Generator(device=DEVICE).manual_seed(hash(char_id) % 2**32),
            ).images[0]
            image.save(base_path, "PNG")
            sync_file_to_game(base_path, f"characters/{char_id}.png")
            upload_single_to_minio(base_path, f"static/images/characters/{char_id}.png")
            print(f"           Saved ({time.time() - start:.1f}s)")
            generated_count += 1
            clean_vram()
        else:
            print(f"  SKIP {char_id}.png (already exists)")
            sync_file_to_game(base_path, f"characters/{char_id}.png")

        # 2. Expression variants
        for expr_name, expr_desc in expressions.items():
            expr_path = char_dir / f"{expr_name}.png"
            if expr_path.exists() and not force:
                print(f"  SKIP {char_id}/{expr_name}.png (already exists)")
                sync_file_to_game(expr_path, f"characters/{char_id}/{expr_name}.png")
                continue

            if limit > 0 and generated_count >= limit:
                return generated_count

            prompt = f"{STYLE_CHAR}, {base_desc}, {expr_desc}, full body"
            print(f"  Generating {char_id}/{expr_name}.png ({steps} steps)...")
            start = time.time()

            image = pipe(
                prompt=prompt,
                negative_prompt=NEGATIVE_PROMPT_CHAR,
                width=CHAR_WIDTH,
                height=CHAR_HEIGHT,
                num_inference_steps=steps,
                guidance_scale=GUIDANCE_SCALE,
                generator=torch.Generator(device=DEVICE).manual_seed(
                    abs(hash(f"{char_id}_{expr_name}")) % 2**32
                ),
            ).images[0]

            image.save(expr_path, "PNG")
            sync_file_to_game(expr_path, f"characters/{char_id}/{expr_name}.png")
            upload_single_to_minio(expr_path, f"static/images/characters/{char_id}/{expr_name}.png")
            elapsed = time.time() - start
            print(f"           Saved ({elapsed:.1f}s)")
            generated_count += 1
            clean_vram()

    return generated_count


def generate_previews(pipe, limit=0, steps=DEFAULT_STEPS, force=False):
    """Generate small preview/thumbnail images for character selection."""
    CHAR_DIR.mkdir(parents=True, exist_ok=True)
    generated_count = 0

    for filename, (char_id, extra) in PREVIEWS.items():
        output_path = CHAR_DIR / filename
        if output_path.exists() and not force:
            print(f"  SKIP {filename} (already exists)")
            sync_file_to_game(output_path, f"characters/{filename}")
            continue

        if limit > 0 and generated_count >= limit:
            break

        char_desc = CHARACTERS[char_id]["base"]
        prompt = f"{STYLE_CHAR}, {char_desc}, {extra}"
        print(f"  Generating {filename}...")
        start = time.time()

        image = pipe(
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT_CHAR,
            width=512,
            height=512,
            num_inference_steps=steps,
            guidance_scale=GUIDANCE_SCALE,
            generator=torch.Generator(device=DEVICE).manual_seed(
                abs(hash(f"preview_{char_id}")) % 2**32
            ),
        ).images[0]

        if filename.endswith(".jpg"):
            image.save(output_path, "JPEG", quality=90)
        else:
            if "small" in filename:
                image = image.resize((128, 128), Image.LANCZOS)
            image.save(output_path, "PNG")

        sync_file_to_game(output_path, f"characters/{filename}")
        print(f"           Saved ({time.time() - start:.1f}s)")
        generated_count += 1
        clean_vram()

    return generated_count


def upload_to_minio(source_dir, bucket_name="decalove-assets", force_upload=False):
    """Upload all images from source_dir to MinIO decalove-assets bucket."""
    print(f"\n--- Uploading images from {source_dir} to MinIO ({bucket_name}) ---")
    
    endpoint = "127.0.0.1:9000"
    access_key = "minioadmin"
    secret_key = "minioadmin"
    secure = False
    
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

        uploaded = 0
        skipped = 0

        for ext in ("*.png", "*.jpg"):
            for file_path in source_path.rglob(ext):
                rel_path = file_path.relative_to(source_path)
                object_key = f"static/images/{rel_path.as_posix()}"
                
                if not force_upload:
                    try:
                        client.stat_object(bucket_name, object_key)
                        skipped += 1
                        continue
                    except Exception:
                        pass
                
                print(f"  Uploading {object_key}...")
                content_type = "image/jpeg" if ext == "*.jpg" else "image/png"
                client.fput_object(bucket_name, object_key, str(file_path), content_type=content_type)
                uploaded += 1
                
        print(f"MinIO Upload complete! Uploaded: {uploaded}, Already in MinIO: {skipped}")
    except Exception as e:
        print(f"ERROR: Failed to upload to MinIO: {e}")


def main():
    parser = argparse.ArgumentParser(description="Decalove All Locations & Characters Image Generator/Uploader")
    parser.add_argument("--upload-only", action="store_true", help="Skip generation, just upload to MinIO")
    parser.add_argument("--source", type=str, help="Source directory for images (default: frontend/public/images)")
    parser.add_argument("--category", choices=["all", "backgrounds", "characters", "previews"], default="all")
    parser.add_argument("--location", type=str, default=None, help="Filter to specific location (e.g. school_gate, park, train_station, player_home)")
    parser.add_argument("--character", type=str, default=None, help="Filter to specific character (aiko, haruto, mika, ren)")
    parser.add_argument("--limit", type=int, default=0, help="Max number of new images to generate (0 = all)")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS, help=f"Inference steps (default: {DEFAULT_STEPS})")
    parser.add_argument("--force", action="store_true", help="Force regenerate even if file exists locally")
    parser.add_argument("--force-upload", action="store_true", help="Force upload to MinIO even if object exists")
    args = parser.parse_args()

    print("=" * 65)
    print("Decalove GPU Visual Novel Art Generator & MinIO Uploader")
    print("=" * 65)

    source_dir = Path(args.source) if args.source else FRONTEND_IMAGES

    if not args.upload_only:
        if not torch.cuda.is_available():
            print("ERROR: CUDA is not available. PyTorch with CUDA required.")
            sys.exit(1)

        print(f"GPU:       {torch.cuda.get_device_name(0)}")
        print(f"Output:    {FRONTEND_IMAGES}")
        print(f"Category:  {args.category}")
        print(f"Steps:     {args.steps}")
        if args.location:
            print(f"Location:  {args.location}")
        if args.character:
            print(f"Character: {args.character}")
        print()

        pipe = load_pipeline()

        remaining_limit = args.limit
        if args.category in ("all", "backgrounds"):
            gen = generate_backgrounds(
                pipe, filter_location=args.location, limit=remaining_limit, steps=args.steps, force=args.force
            )
            if remaining_limit > 0:
                remaining_limit = max(0, remaining_limit - gen)

        if args.category in ("all", "characters") and (remaining_limit > 0 or args.limit == 0):
            gen = generate_characters(
                pipe, filter_char=args.character, limit=remaining_limit, steps=args.steps, force=args.force
            )
            if remaining_limit > 0:
                remaining_limit = max(0, remaining_limit - gen)

        if args.category in ("all", "previews") and (remaining_limit > 0 or args.limit == 0):
            generate_previews(pipe, limit=remaining_limit, steps=args.steps, force=args.force)

        # Count total
        total_png = sum(1 for _ in FRONTEND_IMAGES.rglob("*.png"))
        total_jpg = sum(1 for _ in FRONTEND_IMAGES.rglob("*.jpg"))
        print(f"\n{'=' * 65}")
        print(f"Generation phase finished! Total images on disk: {total_png + total_jpg}")
        print(f"{'=' * 65}")

    upload_to_minio(source_dir, force_upload=args.force_upload)


if __name__ == "__main__":
    main()
