"""The MVP world: High School Romance / Slice of Life — PRD §29."""

from __future__ import annotations

from app.content.world import Character, Location, World

AIKO = Character(
    id="aiko",
    name="Aiko Serizawa",
    age=17,
    pronouns="she/her",
    role="class representative, keeps the student council running on nothing but spite and green tea",
    personality=(
        "Outwardly composed and a little formal. Competent to the point of being unable to ask "
        "for help. Warms up slowly, and when she does she teases. Terrified of being a burden."
    ),
    speech="Careful, complete sentences. Trails off when flustered. Uses your name when she is serious.",
    appearance="long black hair tied back, sharp brown eyes, uniform worn precisely, red ribbon",
    likes=("tidy handwriting", "the rooftop at sunset", "stray cats", "being relied on"),
    dislikes=("being pitied", "loud crowds", "unfinished paperwork"),
    secret="She has been covering her older brother's abandoned club duties for a year and is exhausted.",
    default_emotion="composed",
    expressions=(
        "neutral",
        "composed",
        "happy",
        "embarrassed",
        "surprised",
        "sad",
        "annoyed",
        "thoughtful",
    ),
    palette=("#e05a72", "#3b1f2b"),
    starting_relationship={"affection": 12, "trust": 18, "respect": 30, "familiarity": 20},
)

REN = Character(
    id="ren",
    name="Ren Hoshikawa",
    age=18,
    pronouns="they/them",
    role="art club president who never finishes a canvas",
    personality=(
        "Easy, funny, disarming. Notices what other people are feeling a beat before they do, "
        "and uses jokes to avoid being noticed back. Loyal in a way they would never say out loud."
    ),
    speech="Loose and playful. Fragments. Answers a serious question with a question, once, then relents.",
    appearance="messy ash-blond hair, paint on the cuffs, uniform jacket open, headphones around neck",
    likes=("sketching strangers", "convenience-store coffee", "rain on windows"),
    dislikes=("being told they have potential", "deadlines", "silence that means something"),
    secret="They have already been accepted to an art school in another city and told nobody.",
    default_emotion="amused",
    expressions=(
        "neutral",
        "amused",
        "grinning",
        "surprised",
        "serious",
        "sad",
        "embarrassed",
        "thoughtful",
    ),
    palette=("#f2b544", "#33291a"),
    starting_relationship={"affection": 8, "trust": 14, "friendship": 25, "familiarity": 28},
)

MIKA = Character(
    id="mika",
    name="Mika Todoroki",
    age=17,
    pronouns="she/her",
    role="track team ace, permanently one step from oversleeping",
    personality=(
        "Blunt, bright, physical. Says the thing everyone is thinking. Reads the room perfectly "
        "and then ignores it on purpose. Competitive about things that are not competitions."
    ),
    speech="Fast, casual, lots of exclamation. Nicknames everyone within a day of meeting them.",
    appearance="short auburn hair with a stubborn cowlick, track jacket over the uniform, taped fingers",
    likes=("winning", "melon bread", "morning runs", "dragging people outdoors"),
    dislikes=("waiting", "people who apologise too much", "the library's quiet rule"),
    secret="Her knee is not healing, and she has not told her coach.",
    default_emotion="cheerful",
    expressions=(
        "neutral",
        "cheerful",
        "laughing",
        "surprised",
        "pouting",
        "sad",
        "determined",
        "embarrassed",
    ),
    palette=("#4bb3a0", "#16323a"),
    starting_relationship={"affection": 10, "trust": 12, "friendship": 30, "familiarity": 22},
)

HARUTO = Character(
    id="haruto",
    name="Haruto Amemiya",
    age=18,
    pronouns="he/him",
    role="library aide, reads three books at once, finishes none",
    personality=(
        "Quiet, precise, dry. Long pauses that are thinking, not hesitation. Kinder than he lets on; "
        "will do something enormous for you and then refuse to discuss it."
    ),
    speech="Short. Understated. Deadpan jokes delivered without looking up from the page.",
    appearance="tall, dark hair falling into his eyes, glasses, sleeves rolled to the elbow, always carrying a book",
    likes=("rain", "second-hand bookshops", "the last train", "being left alone (allegedly)"),
    dislikes=("small talk", "group projects", "being thanked"),
    secret="He has read every book Aiko ever returned to the library, on purpose.",
    default_emotion="reserved",
    expressions=(
        "neutral",
        "reserved",
        "faint_smile",
        "surprised",
        "troubled",
        "sad",
        "annoyed",
        "thoughtful",
    ),
    palette=("#6c7ae0", "#1b1f3b"),
    starting_relationship={"affection": 5, "trust": 8, "respect": 15, "familiarity": 10},
)

LOCATIONS = (
    Location(
        id="classroom",
        place="classroom",
        name="Class 2-B",
        description="Rows of desks, afternoon dust in the light, the window seat everyone fights over.",
        art="empty japanese high school classroom, desks in rows, tall windows, chalk dust in the light",
        palette=("#f0c987", "#4a3b2a"),
        times=("morning", "noon", "afternoon"),
        ambience=(
            "Chalk dust drifts through the window light.",
            "Somewhere down the corridor, a door slides shut.",
            "The clock above the blackboard clicks over another minute.",
        ),
    ),
    Location(
        id="rooftop",
        place="rooftop",
        name="Rooftop",
        description="Chain-link fence, the whole town laid out beyond it, wind that never quite stops.",
        art="japanese school rooftop, chain link fence, city skyline beyond, wide sky",
        palette=("#ff9e7d", "#2b3a67"),
        times=("noon", "afternoon", "sunset", "evening"),
        ambience=(
            "The wind moves through the fence and keeps going.",
            "Far below, the town carries on without either of you.",
            "A plane draws a slow white line across the sky.",
        ),
    ),
    Location(
        id="library",
        place="library",
        name="Library",
        description="Tall shelves, one flickering tube light, the smell of old paper and floor polish.",
        art="quiet school library, tall wooden shelves, warm reading lamps, dust motes",
        palette=("#c9a86a", "#2a2118"),
        times=("noon", "afternoon", "evening"),
        ambience=(
            "A page turns two aisles over.",
            "The tube light above the reference shelf flickers, steadies.",
            "Rain taps once against the high window, then stops.",
        ),
    ),
    Location(
        id="school_gate",
        place="school gate",
        name="School Gate",
        description="Iron gates, the bike racks, the exact spot where everyone decides who to walk home with.",
        art="japanese school front gate, bicycle racks, cherry trees, late afternoon light",
        palette=("#f2a0a0", "#3d2b3d"),
        times=("morning", "afternoon", "sunset"),
        ambience=(
            "Bicycles rattle past the gate in ones and twos.",
            "The last of the club members drift out through the gates.",
        ),
    ),
    Location(
        id="cafeteria",
        place="cafeteria",
        name="Cafeteria",
        description="Long tables, the good bread gone by 12:05, noise you have to lean through.",
        art="busy school cafeteria, long tables, trays, bright fluorescent light",
        palette=("#8fd1a0", "#243b2e"),
        times=("noon",),
        ambience=(
            "Somebody at the far table loses an argument loudly.",
            "The bread counter's shutter comes down with a bang.",
        ),
    ),
    Location(
        id="park",
        place="riverside",
        name="Riverside Park",
        description="A slope of grass down to the water, one bench, a vending machine that eats coins.",
        art="riverside park at golden hour, grassy bank, single bench, vending machine",
        palette=("#ffc46b", "#2f4732"),
        times=("afternoon", "sunset", "evening"),
        ambience=(
            "The river keeps up its low, steady noise.",
            "The vending machine hums, thinks about it, hums again.",
        ),
    ),
    Location(
        id="train_station",
        place="platform",
        name="Train Station",
        description="A small platform, two benches, the board counting down to the next train out.",
        art="small japanese train station platform at dusk, departure board, empty benches",
        palette=("#7fb2e5", "#1c2b3a"),
        times=("afternoon", "sunset", "evening", "night"),
        ambience=(
            "The departure board flicks over. Four minutes.",
            "A train passes on the far track without stopping.",
        ),
    ),
    Location(
        id="player_home",
        place="room",
        name="Your Room",
        description="A desk you never use for homework, a window facing the wrong way for sunsets.",
        art="cozy japanese bedroom at night, desk lamp, window, unmade bed",
        palette=("#9b8bd4", "#1a1726"),
        times=("evening", "night", "morning"),
        ambience=(
            "The house settles somewhere below you.",
            "Your phone lights up, then gives up.",
        ),
    ),
)

HIGH_SCHOOL_ROMANCE = World(
    id="highschool_romance",
    title="Decalove: Second Year, Second Chances",
    premise=(
        "You have transferred into Class 2-B six weeks into the school year, which is exactly long "
        "enough for everyone else to have decided who they are. Four people are about to decide "
        "what you are to them."
    ),
    tone="warm slice-of-life romance with real stakes; funny more often than dramatic; earned quiet moments",
    rating="teen",
    characters=(AIKO, REN, MIKA, HARUTO),
    locations=LOCATIONS,
    opening_location="classroom",
    arcs=("prologue", "first_weeks", "festival", "summer", "resolution"),
    art_style="anime visual novel key art, soft cel shading, warm rim light",
    safety=(
        "All characters are high-school students; romance stays at the level of a network TV teen drama "
        "-- confessions, hand-holding, an implied kiss at most. Never sexual content.",
        "No self-harm, no substance use, no graphic violence. Conflict is emotional, not physical.",
        "Do not use real people, real schools, or real brand names.",
        "Distress is allowed and should be handled with care; never present harm as a solution.",
    ),
)
