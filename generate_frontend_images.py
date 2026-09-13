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
    # 1. Classroom (morning, noon, afternoon, sunset, evening, night, rain)
    "classroom.png": "japanese high school classroom interior, wooden desks and chairs, chalkboard, large windows with sunlight streaming in, morning light, warm atmosphere",
    "classroom_morning.png": "japanese high school classroom interior, wooden desks and chairs, chalkboard, large windows with bright morning sunlight, golden hour morning light, dust motes in sunbeams",
    "classroom_noon.png": "japanese high school classroom interior, bright midday sun through large windows, empty desks, clean chalkboard, vivid colors",
    "classroom_afternoon.png": "japanese high school classroom interior, empty desks in rows, warm late afternoon sunlight, dust motes in golden sunbeams, peaceful quiet classroom",
    "classroom_sunset.png": "japanese high school classroom interior at sunset, long golden amber shadows stretching across wooden desks, chalkboard glowing in orange sunset rays, melancholic twilight atmosphere",
    "classroom_evening.png": "japanese high school classroom interior at evening dusk, deep blue sky outside large windows, soft warm classroom ceiling lights turned on, quiet empty classroom after school",
    "classroom_night.png": "japanese high school classroom interior at night, dark starry night sky outside large windows, city lights glowing in distance, quiet shadows across wooden desks",
    "classroom_rain.png": "japanese high school classroom interior on a rainy day, rain streaks on large windows, overcast soft cool blue ambient light, wet courtyard outside, quiet peaceful classroom",

    # 2. Cafeteria (morning, noon, afternoon, sunset, evening)
    "cafeteria.png": "japanese high school cafeteria interior, long wooden tables and benches, food trays, large windows, industrial ceiling, warm sunlight",
    "cafeteria_morning.png": "japanese high school cafeteria interior in early morning, soft morning sunlight streaming across empty wooden tables, clean food counters, quiet serene start of day",
    "cafeteria_noon.png": "japanese high school cafeteria interior, long wooden tables and benches, food trays, large windows, bright noon sunlight, lively atmosphere",
    "cafeteria_afternoon.png": "japanese high school cafeteria interior in late afternoon, quiet empty cafeteria, warm slanting sunlight across long tables and benches, serene atmosphere",
    "cafeteria_sunset.png": "japanese high school cafeteria interior at sunset, orange and golden sunset glow reflecting on polished floor, empty long tables and vending machines",
    "cafeteria_evening.png": "japanese high school cafeteria interior at evening, warm interior cafeteria lamps, dim outside windows, empty tables, peaceful quiet mood",

    # 3. Library (morning, noon, afternoon, sunset, evening, night, rain)
    "library.png": "japanese high school library interior, tall wooden bookshelves filled with books, reading tables with desk lamps, wooden floor, warm afternoon light through windows",
    "library_morning.png": "japanese high school library interior in bright fresh morning sunlight, sunbeams streaming between tall wooden bookshelves, sparkling dust motes, quiet wooden study tables",
    "library_noon.png": "japanese high school library interior, tall wooden bookshelves filled with books, reading tables with desk lamps, wooden floor, afternoon sunlight streaming through windows",
    "library_afternoon.png": "japanese high school library interior, long shadows between tall wooden bookshelves, warm golden hour sunlight, quiet study carrels",
    "library_sunset.png": "japanese high school library interior at golden sunset, warm amber sunlight illuminating tall bookshelves, long shadows between book aisles, cozy quiet reading atmosphere",
    "library_evening.png": "japanese high school library interior, tall wooden bookshelves, warm glowing reading desk lamps, dusk outside windows, quiet cozy atmosphere",
    "library_night.png": "japanese high school library interior late at night, warm glowing brass desk lamps on wooden study tables, deep dark night outside tall windows, quiet peaceful solitude",
    "library_rain.png": "japanese high school library interior on a rainy afternoon, raindrops on tall arched windows, cozy warm desk lamps, bookshelves, peaceful gentle sound of rain",

    # 4. Rooftop (morning, noon, afternoon, sunset, evening, night, rain)
    "rooftop.png": "japanese high school rooftop, chain-link fence, metal door, pipes and ventilation, city skyline view, dramatic sunset sky, orange and purple clouds",
    "rooftop_morning.png": "japanese high school rooftop at early sunrise, pale pastel pink and gold morning sky over city skyline, fresh dawn breeze, chain-link fence, empty metal benches",
    "rooftop_noon.png": "japanese high school rooftop, chain-link fence, panoramic city skyline view, clear blue midday sky with white fluffy clouds, bright sunlight",
    "rooftop_afternoon.png": "japanese high school rooftop, chain-link fence overlooking town, warm afternoon sunlight, wide sky with light clouds",
    "rooftop_sunset.png": "japanese high school rooftop, chain-link fence overlooking city skyline, dramatic sunset, golden hour, orange and purple sky, city lights beginning to glow",
    "rooftop_evening.png": "japanese high school rooftop, chain-link fence overlooking town skyline at twilight, deep blue and purple sky, glowing city lights in distance, serene mood",
    "rooftop_night.png": "japanese high school rooftop under starry night sky, crescent moon, glittering city lights sprawling below, chain-link fence silhouette, quiet romantic atmosphere",
    "rooftop_rain.png": "japanese high school rooftop in light rain, overcast cloudy sky, puddle reflections on concrete rooftop floor, rain droplets on chain-link fence, town skyline in mist",

    # 5. School Gate (morning, noon, afternoon, sunset, evening, night, rain)
    "school_gate.png": "japanese high school entrance front gate, iron gates, bicycle racks, cherry blossom trees, sidewalk, peaceful campus entrance",
    "school_gate_morning.png": "japanese high school front gate, bright fresh morning light, cherry blossom trees, bicycle parking racks, school building entrance",
    "school_gate_noon.png": "japanese high school front gate, bright midday sun, paved entrance road, cherry trees, open iron gate",
    "school_gate_afternoon.png": "japanese high school front gate, warm afternoon sunlight, cherry blossom trees along path, bicycle racks, gate open",
    "school_gate_sunset.png": "japanese high school front gate at golden sunset hour, long warm shadows, glowing orange sky, cherry trees, end of school day",
    "school_gate_evening.png": "japanese high school entrance front gate at evening dusk, warm streetlamp glowing softly, deep indigo sky, silhouettes of cherry blossom trees, quiet empty street",
    "school_gate_night.png": "japanese high school front gate at night, closed iron gates under warm streetlights, quiet residential street, starry night sky above school building",
    "school_gate_rain.png": "japanese high school front gate in gentle rain, puddle reflections on asphalt, cherry blossom petals on wet ground, bicycle racks, umbrellas by gate",

    # 6. Riverside Park (morning, noon, afternoon, sunset, evening, night, rain)
    "park.png": "riverside park, grassy bank sloping down to water, single wooden park bench, vending machine, peaceful afternoon scenery",
    "park_morning.png": "riverside park in early morning mist, fresh morning sunlight reflecting on sparkling river, dew on green grassy bank, single wooden bench, peaceful quiet dawn",
    "park_noon.png": "riverside park at bright noon, lush green grassy riverbank, clear blue sky with fluffy summer clouds, sparkling river water, single wooden bench, vending machine",
    "park_afternoon.png": "riverside park, green grassy riverbank, single bench, vending machine, bright afternoon sun reflecting on sparkling river water",
    "park_sunset.png": "riverside park at sunset, grassy slope down to river, single bench, softly glowing vending machine, golden orange reflection on water surface",
    "park_evening.png": "riverside park at evening twilight, dusk sky, single bench beside river, warm streetlight glow, quiet tranquil riverside",
    "park_night.png": "riverside park at night, full moon reflecting on calm river water, starry sky, warm glow from vending machine, lone wooden bench, peaceful serene night scenery",
    "park_rain.png": "riverside park in gentle rain, raindrops rippling on river surface, glistening wet grass on bank, lone wooden bench under cloudy grey sky",

    # 7. Train Station (morning, noon, afternoon, sunset, evening, night, rain)
    "train_station.png": "small japanese train station platform, departure schedule board, empty wooden benches, railway tracks, suburban station",
    "train_station_morning.png": "small suburban japanese train station platform in crisp morning sunlight, clear blue sky, overhead canopy, empty wooden benches, polished railway tracks",
    "train_station_noon.png": "suburban japanese train station platform at bright midday, strong summer sun casting sharp shadows under canopy, empty benches, sun-baked tracks stretching into distance",
    "train_station_afternoon.png": "small suburban train station platform, warm afternoon sunlight, overhead canopy, empty wooden benches, railway tracks",
    "train_station_sunset.png": "small japanese train station platform at sunset, glowing departure board, dramatic orange and purple sunset sky over tracks",
    "train_station_evening.png": "suburban japanese train platform at twilight, glowing station platform lamps, departure board illuminated, dusk sky",
    "train_station_night.png": "quiet japanese train station platform at night, overhead fluorescent lights glowing, empty platform, dark clear night sky",
    "train_station_rain.png": "japanese train station platform in gentle rain, wet platform reflecting overhead lights, raindrops falling from canopy edge, railway tracks glistening in rain",

    # 8. Player's Bedroom (morning, noon, afternoon, sunset, evening, night, rain)
    "player_home.png": "cozy japanese teenager bedroom, wooden study desk, bookshelf, unmade bed, window, warm interior lighting",
    "player_home_morning.png": "cozy teenager bedroom interior, bright morning sunlight streaming through curtains onto wooden desk and unmade bed",
    "player_home_noon.png": "cozy teenager bedroom interior at bright midday, bright sun streaming through curtains onto wooden study desk, bookshelf, unmade bed, clear warm day",
    "player_home_afternoon.png": "cozy teenager bedroom interior, afternoon sunlight through window, study desk with lamp, books on shelves",
    "player_home_sunset.png": "cozy teenager bedroom interior at golden sunset, warm orange light washing across wooden desk and bookshelf, soft sunset glow on bed, serene quiet evening",
    "player_home_evening.png": "cozy bedroom interior at twilight, warm desk lamp glowing, quiet evening room atmosphere, dusk through window",
    "player_home_night.png": "cozy bedroom interior at night, warm yellow bedside lamp light, dark starry night sky outside window, quiet peaceful room",
    "player_home_rain.png": "cozy teenager bedroom on a rainy afternoon, rain droplets sliding down windowpane, soft overcast dim light, warm desk lamp glowing, peaceful calm room",

    # 9. School Corridor / Hallway
    "corridor.png": "japanese high school hallway corridor, wooden floor, lockers, rows of sliding classroom doors with glass windows, warm sunlight streaming through corridor windows",
    "corridor_afternoon.png": "japanese high school corridor hallway in warm late afternoon light, long shadows on polished wooden floor, empty lockers, sliding classroom doors",
    "corridor_sunset.png": "japanese high school hallway at sunset, intense golden-orange sunlight illuminating wooden corridor, silhouettes of window frames, nostalgic peaceful atmosphere",
    "corridor_evening.png": "japanese high school corridor hallway at evening dusk, fluorescent ceiling lights glowing, deep blue sky through windows, quiet empty school after hours",

    # 10. Art Club Room (Ren's Club)
    "art_room.png": "japanese high school art club room interior, wooden easels with canvases, paint jars and brushes on tables, sculptures on shelves, bright afternoon sunlight through tall windows",
    "art_room_sunset.png": "japanese high school art club room at sunset, golden amber light shining on unfinished painting on wooden easel, messy paintbrushes, quiet romantic artistic mood",
    "art_room_evening.png": "japanese high school art club room at twilight, warm desk lamps illuminating sketchbooks and canvases, quiet dusk sky outside windows",

    # 11. School Courtyard & Athletic Track (Mika's Track Practice)
    "courtyard.png": "japanese high school courtyard and athletic running track, green grass, chalk line markings on red dirt track, school building in background, clear blue sky",
    "courtyard_sunset.png": "japanese high school athletic running track at sunset, glowing golden hour sky, empty sports field, long shadows across red clay track, quiet end of club practice",

    # 12. Internet Cafe / Manga Cafe
    "internet_cafe.png": "japanese manga internet cafe private cubicle interior, glowing computer monitor on wooden desk, padded reclining chair, keyboard, headphones, drinks cup, shelves of manga comic books in background, warm dim cozy ambient lighting",
    "internet_cafe_night.png": "japanese internet cafe booth cubicle at late night, glowing computer screen illuminating cozy private booth, neon beverage dispenser in corridor, quiet cozy night atmosphere",

    # 13. Airport
    "airport.png": "modern airport departure terminal, massive floor-to-ceiling glass windows overlooking passenger airplanes on tarmac runway, flight departure information board, rows of terminal seats, bright architectural sunlight",
    "airport_sunset.png": "modern airport terminal departure gate at golden sunset, dramatic amber sunset sky over airport tarmac runway and airplanes outside large glass windows, quiet departure lounge",
    "airport_night.png": "international airport terminal at night, runway lights glowing outside large glass observation windows, reflective polished floor, illuminated flight board, quiet late night travel mood",

    # 14. Cultural Event / School Festival
    "cultural_event.png": "japanese high school cultural festival bunkasai, decorated school hallway and classroom, colorful hand-drawn banners, paper lanterns, carnival game stalls, lively festive celebratory atmosphere",
    "cultural_event_sunset.png": "japanese school cultural festival at sunset, paper lanterns glowing in amber sunset light, decorated festival booths, streamers hanging from ceiling, nostalgic end of festival day",
    "cultural_event_night.png": "school cultural festival at evening night, string fairy lights glowing across school courtyard, decorated food stalls, paper lanterns, lively twilight celebration",

    # 15. Outside School
    "outside_school.png": "outside japanese high school, suburban residential street, concrete sidewalk, utility poles with power lines, pedestrian crosswalk, cherry trees, sunny afternoon",
    "outside_school_sunset.png": "suburban street outside japanese high school at golden sunset, long dramatic shadows stretching across asphalt, warm glowing sunset sky over houses, peaceful walk home",
    "outside_school_rain.png": "street outside japanese high school on a rainy day, glistening wet asphalt reflecting traffic lights, rain puddles on sidewalk, utility poles, overcast mood",

    # 16. Cafe / Coffee Shop
    "cafe.png": "cozy aesthetic japanese coffee shop interior, wooden tables and comfortable chairs, espresso machine on wooden counter, chalkboard menu, pastry display case, warm sunlight through glass window",
    "cafe_afternoon.png": "cozy cafe interior in warm afternoon light, wooden tables, potted plants, steaming cup of coffee on table, soft warm lighting, peaceful quiet ambiance",
    "cafe_evening.png": "charming coffee shop cafe at evening dusk, warm hanging pendant lights glowing, cozy wooden booth seating, twilight outside window, quiet romantic atmosphere",

    # 17. Conbini / Convenience Store
    "conbini.png": "japanese 24 hour convenience store interior, bright fluorescent ceiling lighting, neat shelves stocked with snacks, instant ramen, drinks refrigerators, bento display, clean polished floor",
    "conbini_night.png": "japanese convenience store exterior at night, glowing neon store sign illuminating sidewalk, glass front showing brightly lit interior, quiet suburban street, lonely nostalgic night vibe",
    "conbini_interior_night.png": "inside japanese convenience store at late night, quiet aisles stocked with drinks and snacks, glowing refrigerator cases, warm bakery display counter, empty checkout counter",

    # 18. Night Market / Festival Food Stalls
    "night_market.png": "traditional japanese night street market festival, outdoor food stalls yatai with glowing red paper lanterns, steam rising from takoyaki and yakisoba grills, festive banners, twilight evening sky",
    "night_market_night.png": "lively night market at summer festival, warm red and yellow paper lanterns glowing brightly along bustling street, decorative festival stalls, vibrant colorful festive night atmosphere",

    # 19. Fireworks Events
    "fireworks.png": "summer festival fireworks display in night sky over riverbank, spectacular colorful fireworks bursting in dark sky, glowing reflections on river water surface, festival lanterns and stall silhouettes",
    "fireworks_rooftop.png": "spectacular colorful summer fireworks exploding in night sky viewed from school rooftop, city skyline lights below, colorful firework sparkles reflecting on chain-link fence, breathtaking romantic scene",
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
        prefixes = tuple(p.strip() for p in filter_location.split(",") if p.strip())
        items = [
            (k, v) for k, v in items
            if any(k == p or k.startswith(f"{p}.") or k.startswith(f"{p}_") for p in prefixes)
        ]

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
