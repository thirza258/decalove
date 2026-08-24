## Decalove-specific screens.

## The decision point. Traditional VN options (PRD §8 Method A) plus a permanent
## door into free text (Method B) -- the player should never have to guess
## whether typing is allowed.
##
## The free-text option returns a sentinel rather than opening the input here:
## renpy.input() starts an interaction, and starting one from inside a screen
## that is itself an interaction is not allowed. The caller opens it instead.
screen decalove_choice(items, allow_freetext=True):
    modal True
    zorder 100
    style_prefix "choice"

    ## Up to MAX_CHOICES story options plus the free-text button -- six rows at the
    ## outside. Centred with tighter spacing so the tallest case still fits at 1280x720,
    ## which is what Ren'Py's own default menu does for arbitrary-length lists.
    vbox:
        xalign 0.5
        yalign 0.5
        spacing 6

        for item in items:
            textbutton item["text"] action Return(item["id"])

        if allow_freetext:
            textbutton _("Say something else...") action Return("__freetext__")


## Shown when the backend cannot be reached at all.
screen decalove_offline(message):
    modal True
    zorder 200

    frame:
        xalign 0.5
        yalign 0.5
        xpadding 40
        ypadding 30

        vbox:
            spacing 14
            xmaximum 720

            text _("Cannot reach the Decalove story engine.") size 30
            text message size 20
            text _("Start it with:  uvicorn app.main:app --reload --port 8000") size 18
            textbutton _("Back to the main menu") action Return(True) xalign 0.5


## Shown when a loaded save points at a story the server has already collected.
## Deliberately distinct from decalove_offline: telling someone to restart the
## server when the server is fine would send them chasing the wrong problem.
screen decalove_expired():
    modal True
    zorder 200

    frame:
        xalign 0.5
        yalign 0.5
        xpadding 40
        ypadding 30

        vbox:
            spacing 14
            xmaximum 720

            text _("This story has closed.") size 30
            text _("Stories that go uncontinued are cleared after a week, and this save points at one of them. The people in it have moved on.") size 20
            text _("Your other saves are unaffected.") size 18
            textbutton _("Back to the main menu") action Return(True) xalign 0.5
