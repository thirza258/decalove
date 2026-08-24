## Placeholder art.
##
## PRD §26: when image generation fails or is switched off, the game must still
## look like a game. These displayables are built from the palettes the API
## serves with the world, so a location or character looks the same every time
## it appears -- which is what makes them read as art direction rather than as
## an error state.
##
## Generated images, when they exist, arrive as bytes over HTTP and are shown
## with im.Data(). No file is ever written, which matters because the web build's
## filesystem is a sandbox.

init -3 python:

    DECALOVE_FALLBACK_PALETTE = ("#3a4a6b", "#131a2b")
    DECALOVE_GRADIENT_BANDS = 24


    def _decalove_rgb(value):
        text = str(value).lstrip("#")
        if len(text) == 3:
            text = "".join(ch * 2 for ch in text)
        try:
            return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return (60, 70, 100)


    def _decalove_hex(rgb):
        return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


    def decalove_gradient(top, bottom, bands=None):
        """A vertical gradient built from stacked Solids.

        Ren'Py has no gradient displayable and this project ships no image files,
        so the gradient is composed at runtime. Cheap, and it scales to any
        resolution because every band is a fraction of the screen.
        """
        bands = bands or DECALOVE_GRADIENT_BANDS
        start = _decalove_rgb(top)
        end = _decalove_rgb(bottom)
        layers = []
        for index in range(bands):
            t = index / float(max(1, bands - 1))
            colour = [start[c] + (end[c] - start[c]) * t for c in range(3)]
            layers.append(
                Transform(
                    Solid(_decalove_hex(colour)),
                    xysize=(1.0, 1.0 / bands),
                    ypos=index / float(bands),
                    xpos=0.0,
                )
            )
        return Fixed(*layers, xysize=(1.0, 1.0))


    def decalove_background(location_id):
        """Placeholder background for a location, cached per location."""
        cache = store.decalove_bg_cache
        if location_id in cache:
            return cache[location_id]

        location = store.decalove_world_locations.get(location_id, {})
        palette = location.get("palette") or list(DECALOVE_FALLBACK_PALETTE)
        name = location.get("name", location_id.replace("_", " ").title())

        art = Fixed(
            decalove_gradient(palette[0], palette[-1]),
            Transform(Solid("#00000055"), xysize=(1.0, 0.22), ypos=0.78),
            Text(
                name,
                size=34,
                color="#ffffffcc",
                xalign=0.04,
                yalign=0.90,
                outlines=[(2, "#00000099", 0, 0)],
            ),
            xysize=(1.0, 1.0),
        )
        cache[location_id] = art
        return art


    def decalove_sprite(character_id, expression):
        """Placeholder sprite: a coloured column with an initial and a mood."""
        key = (character_id, expression)
        cache = store.decalove_sprite_cache
        if key in cache:
            return cache[key]

        character = store.decalove_world_characters.get(character_id, {})
        palette = character.get("palette") or list(DECALOVE_FALLBACK_PALETTE)
        name = character.get("name", character_id.title())
        initial = name.strip()[:1].upper() or "?"

        art = Fixed(
            Transform(decalove_gradient(palette[0], palette[-1]), xysize=(320, 660), yalign=1.0),
            Text(initial, size=150, color="#ffffff33", xalign=0.5, yalign=0.30),
            Text(
                (expression or "").replace("_", " "),
                size=22,
                color="#ffffffaa",
                xalign=0.5,
                yalign=0.86,
            ),
            xysize=(320, 660),
        )
        cache[key] = art
        return art


    def decalove_remote_image(api, ref, hint):
        """Turn an AssetRef into a displayable, or None if it is not ready.

        Bytes are cached by asset id: the engine reuses the same art across a
        whole run (PRD §19), and re-downloading it every beat would undo that.
        """
        if not ref or ref.get("status") != "ready" or not ref.get("url"):
            return None

        asset_id = ref.get("asset_id") or ref.get("cache_key")
        cache = store.decalove_image_cache
        if asset_id in cache:
            return cache[asset_id]

        data = api.fetch_bytes(ref.get("url"))
        if not data:
            return None

        try:
            art = im.Data(data, "%s-%s.png" % (hint, asset_id))
        except Exception:
            return None

        cache[asset_id] = art
        return art
