## Decalove -- entry point.
##
## This file is deliberately short. Ren'Py owns presentation; the story itself is
## directed by the backend (PRD §20), and the playback loop lives in
## game/decalove/50_player.rpy.

image decalove_void = Solid("#0b0d14")

default decalove_player_name = "You"
default decalove_player_pronouns = "they/them"
default decalove_player_tone = "warm"


label start:

    scene decalove_void

    python:
        decalove_boot_ok = decalove_load_world()

    if not decalove_boot_ok:
        call screen decalove_offline(message=decalove_api.last_error or "No response from the story engine.")
        return

    call decalove_intro

    call decalove_setup

    if not decalove_game_id:
        call screen decalove_offline(message=decalove_api.last_error or "Could not start a new game.")
        return

    call decalove_play

    return


label decalove_intro:

    "Six weeks into the school year, a transfer student walks into Class 2-B."

    "Everyone else has already decided who they are."

    "You haven't."

    return


## Character setup -- PRD §7.1 / §30.
label decalove_setup:

    python:
        decalove_player_name = (
            renpy.input(
                "What should everyone call you?",
                default="",
                length=24,
                exclude="{}[]",
            ).strip()
            or "You"
        )

    menu:

        "Which pronouns should the story use for you?"

        "she / her":
            $ decalove_player_pronouns = "she/her"

        "he / him":
            $ decalove_player_pronouns = "he/him"

        "they / them":
            $ decalove_player_pronouns = "they/them"

    menu:

        "And what kind of second year do you want?"

        "Warm. Funny. The quiet moments earned.":
            $ decalove_player_tone = "warm"

        "Sharper. Let things actually go wrong.":
            $ decalove_player_tone = "dramatic"

        "Slow. Mostly just people, talking.":
            $ decalove_player_tone = "gentle"

    python:
        decalove_new_game(
            decalove_player_name,
            decalove_player_pronouns,
            decalove_player_tone,
        )

    return
