## Client-side session state and boot.
##
## The server is the source of truth (PRD §33). Everything here is either a cache
## of something the server said, or presentation state that does not belong in
## the save at all.

init -3 python:

    def decalove_reset_caches():
        store.decalove_bg_cache = {}
        store.decalove_sprite_cache = {}
        store.decalove_image_cache = {}


    def decalove_load_world():
        """Fetch the authored world once at boot.

        Returns True on success. On failure the game still runs -- with a single
        fallback palette and no character colours -- because a cold backend
        should produce a readable message, not a traceback.
        """
        world = decalove_api.get("/worlds")
        if not world:
            store.decalove_world_characters = {}
            store.decalove_world_locations = {}
            store.decalove_world_title = "Decalove"
            return False

        store.decalove_world_title = world.get("title", "Decalove")
        store.decalove_world_characters = {c["id"]: c for c in world.get("characters", [])}
        store.decalove_world_locations = {l["id"]: l for l in world.get("locations", [])}

        ## One Ren'Py Character per cast member, tinted with their palette so the
        ## name box matches the placeholder sprite.
        speakers = {}
        for character_id, data in store.decalove_world_characters.items():
            palette = data.get("palette") or ["#dddddd"]
            speakers[character_id] = Character(data.get("name", character_id.title()), color=palette[0])
        store.decalove_speakers = speakers
        return True


    def decalove_speaker_for(character_id):
        speaker = store.decalove_speakers.get(character_id)
        if speaker is None:
            ## A character the world payload did not describe: still show a name
            ## rather than dropping the line.
            speaker = Character(str(character_id).replace("_", " ").title())
            store.decalove_speakers[character_id] = speaker
        return speaker


    def decalove_new_game(name, pronouns, tone, romance_focus=None):
        payload = {
            "player_name": name or "You",
            "pronouns": pronouns or "they/them",
            "tone": tone or "warm",
            "romance_focus": romance_focus,
        }
        state = decalove_api.post("/games", payload)
        if not state:
            return None
        store.decalove_game_id = state["game_id"]
        store.decalove_seen_ending = False
        store.decalove_ambient_index = -1
        store.decalove_ambient_seen = 0
        decalove_reset_caches()
        return state


    def decalove_resume():
        """Re-attach to the server-side game after a load.

        Saves store the game id, never the story itself: the ledger lives on the
        server, and copying it into a save would let the two diverge. See
        docs/ARCHITECTURE.md -- a save is a bookmark, not a rewind point.

        Returns the state dict, the string "expired", or None. The distinction
        matters: the server deletes games nobody has continued for a week, so a
        failed fetch here is more often a collected save than a dead server, and
        telling the player to go and start uvicorn would be simply wrong.
        """
        if not store.decalove_game_id:
            return None

        decalove_reset_caches()
        state = decalove_api.get("/games/%s" % store.decalove_game_id)
        if state is not None:
            return state

        ## Two signals, no status-code parsing: renpy.fetch reports failures as
        ## FetchError text, so instead ask a question we know the answer to. If the
        ## server still answers /worlds then it is up, and the save is what is gone.
        if decalove_api.get("/worlds") is not None:
            return "expired"
        return None


    def decalove_ambient_line(ambience):
        """Next in-world filler line, never the same one twice in a row."""
        store.decalove_ambient_seen += 1
        if not ambience:
            return "The moment holds."
        store.decalove_ambient_index = (store.decalove_ambient_index + 1) % len(ambience)
        return ambience[store.decalove_ambient_index]


## Persisted with the save.
default decalove_game_id = None

## Set when a loaded save points at a game the server has garbage collected.
default decalove_save_expired = False

## Guards against replaying the closing beat if the loop sees "ended" twice.
default decalove_seen_ending = False

## Presentation only -- rebuilt on boot and after every load.
default decalove_world_title = "Decalove"
default decalove_world_characters = {}
default decalove_world_locations = {}
default decalove_speakers = {}
default decalove_bg_cache = {}
default decalove_sprite_cache = {}
default decalove_image_cache = {}
default decalove_ambient_index = -1
default decalove_ambient_seen = 0
default decalove_shown_character = None


label after_load:
    ## Displayables and fetched bytes are not worth carrying in a save file, and
    ## a stale asset URL would fail to load. Rebuild from the live API instead.
    ##
    ## A load resumes inside the playback loop, so an expired save is flagged here
    ## and handled there rather than jumping out of after_load.
    python:
        decalove_load_world()
        decalove_save_expired = decalove_resume() == "expired"
    return
