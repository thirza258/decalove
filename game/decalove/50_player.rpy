## The playback loop.
##
## This is the whole client-side game: ask the server for the next beat, show it,
## and when the beat is a decision point, hand control to the player. Generation
## happens behind it and is never named on screen (PRD §11).

transform decalove_sprite_at:
    xalign 0.5
    yalign 1.0

init -2 python:

    def _decalove_fit(art, width, height):
        return Transform(art, fit="cover", xysize=(width, height))


    def decalove_render(step):
        """Put the scene on screen: background, then at most one sprite."""
        visual = step.get("visual") or {}
        location = step.get("location") or visual.get("background")

        generated = decalove_remote_image(decalove_api, step.get("background_asset"), "bg")
        if generated is not None:
            background = _decalove_fit(generated, config.screen_width, config.screen_height)
        else:
            background = decalove_background(location)

        renpy.scene()
        renpy.show("bg", what=background)

        character_id = visual.get("character")
        if character_id:
            sprite = decalove_remote_image(decalove_api, step.get("character_asset"), "ch")
            if sprite is not None:
                sprite = Transform(sprite, fit="contain", xysize=(420, 700))
            else:
                sprite = decalove_sprite(character_id, visual.get("expression"))
            renpy.show("who", what=sprite, at_list=[decalove_sprite_at])
            store.decalove_shown_character = character_id
        else:
            store.decalove_shown_character = None

        renpy.with_statement(dissolve)


    def decalove_speak(step):
        """Say the beat. Narration is unattributed; dialogue gets its speaker."""
        dialogue = step.get("dialogue")
        if dialogue and dialogue.get("text"):
            if step.get("narration"):
                renpy.say(None, step["narration"])
            decalove_speaker_for(dialogue["speaker"])(dialogue["text"])
        elif step.get("narration"):
            renpy.say(None, step["narration"])


    def decalove_submit_choice(step, choice_id):
        return decalove_api.post(
            "/games/%s/choices" % store.decalove_game_id,
            {"step_id": step["step_id"], "choice_id": choice_id},
        )


    def decalove_submit_action(text):
        return decalove_api.post(
            "/games/%s/actions" % store.decalove_game_id, {"input": text}
        )


    def decalove_ask_freetext():
        """PRD §8 Method B. Called from outside any screen, never from within one."""
        typed = renpy.input(
            _("What do you do?"),
            default="",
            length=300,
            exclude="{}[]",
        )
        return (typed or "").strip()


    def decalove_decide(step):
        """Hand control back to the player and submit whatever they do with it.

        Returns True if something was submitted. False means the player gave an
        empty answer, in which case the loop re-offers the same decision point --
        the server still has it as the head of the ledger.
        """
        choices = step.get("next_choices") or []

        if step.get("type") == "prompt" or not choices:
            typed = decalove_ask_freetext()
            if not typed:
                return False
            return decalove_submit_action(typed) is not None

        picked = renpy.call_screen("decalove_choice", items=choices, allow_freetext=True)

        if picked == "__freetext__":
            typed = decalove_ask_freetext()
            if not typed:
                return False
            return decalove_submit_action(typed) is not None

        return decalove_submit_choice(step, picked) is not None


    def decalove_beat():
        """One turn of the loop. Returns 'ok', 'pending', 'ended', 'offline' or 'expired'."""
        if store.decalove_save_expired:
            return "expired"

        body = decalove_api.get(
            "/games/%s/steps/next" % store.decalove_game_id,
            params={"wait_ms": DECALOVE_WAIT_MS},
            wait_ms=DECALOVE_WAIT_MS,
        )
        if body is None:
            return "offline"

        status = body.get("status")

        if status == "ready":
            step = body["step"]
            store.decalove_ambient_seen = 0
            decalove_render(step)
            decalove_speak(step)
            if step.get("type") in ("choice", "prompt"):
                decalove_decide(step)
            return "ok"

        if status == "awaiting_player":
            ## Reached when a generation failed: the server is offering the same
            ## decision point again rather than stranding the player.
            store.decalove_ambient_seen = 0
            decalove_decide(body["step"])
            return "ok"

        if status == "pending":
            if store.decalove_ambient_seen >= DECALOVE_AMBIENT_LIMIT:
                ## The illusion has run out. Saying so beats looking frozen.
                renpy.say(None, "{i}(The story is still catching up. One moment.){/i}")
                store.decalove_ambient_seen += 1
            else:
                renpy.say(None, decalove_ambient_line(body.get("ambience")))
            return "pending"

        if status == "ended":
            ## The server carries the ending step here so a client that reconnected --
            ## or that lost the response the beat was delivered in -- still sees the
            ## story close rather than being dropped back to the menu mid-sentence.
            step = body.get("step")
            if step and not store.decalove_seen_ending:
                store.decalove_seen_ending = True
                decalove_render(step)
                decalove_speak(step)
            return "ended"

        return "ok"


label decalove_play:
    python:
        _pending_streak = 0
        _offline_streak = 0

        while True:
            _outcome = decalove_beat()

            if _outcome == "ended":
                break

            if _outcome == "expired":
                decalove_save_expired = False
                renpy.call_screen("decalove_expired")
                break

            if _outcome == "pending":
                _pending_streak += 1
                _offline_streak = 0
                if _pending_streak >= DECALOVE_MAX_PENDING_POLLS:
                    renpy.call_screen(
                        "decalove_offline",
                        message=_("The story engine stopped responding while writing."),
                    )
                    break
                continue

            if _outcome == "offline":
                _offline_streak += 1
                if _offline_streak >= 3:
                    renpy.call_screen(
                        "decalove_offline",
                        message=decalove_api.last_error or _("No response from the server."),
                    )
                    break
                continue

            _pending_streak = 0
            _offline_streak = 0
    return
