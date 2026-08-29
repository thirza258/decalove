## Static Opening Scene (Steps 00 to 19)
##
## Authored in pure Ren'Py script for instant, zero-latency playback using local static assets.
## Upon reaching choice points, it syncs the player's decision with the story engine API.

define aiko_char = Character("Aiko Serizawa", color="#e05a72")
define ren_char = Character("Ren Hoshikawa", color="#90b8cc")
define mika_char = Character("Mika Todoroki", color="#e68a5c")
define haruto_char = Character("Haruto Amemiya", color="#7c8aa6")

image bg classroom = "images/bg/classroom.png"
image bg cafeteria = "images/bg/cafeteria.png"
image bg library = "images/bg/library.png"
image bg rooftop = "images/bg/rooftop.png"

image aiko = "images/characters/aiko.png"
image aiko composed = "images/characters/aiko/composed.png"
image aiko thoughtful = "images/characters/aiko/thoughtful.png"

image ren = "images/characters/ren.png"
image ren amused = "images/characters/ren/amused.png"

image mika = "images/characters/mika.png"
image mika excited = "images/characters/mika/excited.png"

image haruto = "images/characters/haruto.png"
image haruto composed = "images/characters/haruto/composed.png"


label decalove_static_opening:

    # =========================================================================
    # PART 1: Classroom (Morning) — Steps 00 - 04
    # =========================================================================
    scene bg classroom with dissolve

    # Step 00
    "You have transferred into Class 2-B six weeks into the school year."
    "The seats are arranged, the cliques are set, and everyone has already decided who they are."

    # Step 01
    show aiko composed at decalove_sprite_at with dissolve
    "Class 2-B smells of chalk dust and floor wax. Everyone stops to look as you walk in."

    # Step 02
    aiko_char "You must be the transfer. I'm Aiko — class representative. If you need your syllabus or a locker assignment, let me know after homeroom."

    # Step 03
    hide aiko
    show ren amused at decalove_sprite_at with dissolve
    ren_char "Six weeks in. Bold. I respect it. If you need someone to show you which teachers actually check the homework, I'm by the art room."

    # Step 04
    hide ren
    show aiko composed at decalove_sprite_at with dissolve
    "The morning drags on. Finally, the chime rings for the lunch break."


    # =========================================================================
    # PART 2: Cafeteria (Noon) — Steps 05 - 09
    # =========================================================================
    # Step 05
    scene bg cafeteria with dissolve
    "The hallways are a chaotic rush, pushing you toward the long tables of the cafeteria."

    # Step 06
    show mika excited at decalove_sprite_at with dissolve
    "Before you can even find a seat, a blur of motion slides into the space next to you."

    # Step 07
    mika_char "HEY! You're the new one, right? I'm Mika. You're sitting with us — no arguments, I already saved the bench."

    # Step 08
    hide mika
    show ren amused at decalove_sprite_at with dissolve
    ren_char "Give them room to breathe, Mika. Not everyone runs on rocket fuel."

    # Step 09
    hide ren
    "The noise of the cafeteria washes over the table. It's loud, but strangely comforting."


    # =========================================================================
    # PART 3: Library (Afternoon) — Steps 10 - 14
    # =========================================================================
    # Step 10
    scene bg library with dissolve
    "Escaping the noise, you find the library. The smell of old paper is a welcome relief."

    # Step 11
    show haruto composed at decalove_sprite_at with dissolve
    "Tall shelves cast long shadows. You spot someone shelving books in the quiet corner."

    # Step 12
    haruto_char "...You're in my light."

    # Step 13
    hide haruto with dissolve
    "He goes back to his work, leaving you to the quiet afternoon."

    # Step 14 - Choice Point 1
    "The afternoon opens up. What do you do with it?"

    menu:
        "Go find Aiko — she mentioned something about council work.":
            $ _opening_choice = "Go find Aiko — she mentioned something about council work."

        "See if Ren is still in the art room.":
            $ _opening_choice = "See if Ren is still in the art room."

        "Take Mika up on that offer to show you around.":
            $ _opening_choice = "Take Mika up on that offer to show you around."

        "Stay here with Haruto and the quiet.":
            $ _opening_choice = "Stay here with Haruto and the quiet."

        "Go explore the rooftop everyone keeps mentioning.":
            $ _opening_choice = "Go explore the rooftop everyone keeps mentioning."

    python:
        if store.decalove_game_id:
            # Advance server state to step 14 and trigger background batch generation
            decalove_skip_to_step(14)
            decalove_submit_action(_opening_choice)


    # =========================================================================
    # PART 4: Rooftop (Sunset) — Steps 15 - 19
    # =========================================================================
    # Step 15
    scene bg rooftop with dissolve
    "You wind your way up the stairs, pushing open the heavy metal door to the roof."

    # Step 16
    "The city stretches out past the chain-link fence. The wind is sharper up here."

    # Step 17
    show aiko thoughtful at decalove_sprite_at with dissolve
    aiko_char "It's a good view. People come up here when they need to think."

    # Step 18
    hide aiko with dissolve
    "The sky begins to turn orange. The first day is almost over."

    # Step 19
    show aiko thoughtful at decalove_sprite_at with dissolve
    "The sunset paints everything in warm amber light as your first day draws to a close."
    hide aiko with dissolve

    python:
        if store.decalove_game_id:
            # Fast-forward server cursor through step 19 for seamless handoff to decalove_play
            decalove_skip_to_step(19)

    return
