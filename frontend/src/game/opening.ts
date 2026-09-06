/**
 * The authored opening — the port of `game/decalove/60_static_opening.rpy`.
 *
 * Data, not code. The Ren'Py version is imperative script (`scene`, `show`, `menu`);
 * here it is a list of step-shaped objects, which means it plays through the exact
 * same renderer and the same decision handling as anything the API sends. The only
 * thing that makes these steps special is that they need no network.
 *
 * That is the point of the scene existing at all: New Game is instant, and the first
 * batch generates behind it (PRD §11). The server has its own authored steps 0-19 in
 * parallel; the two are reconciled by the `skip` calls below, whose indices are
 * *server* cursor positions, not offsets into this list.
 */

import type { StoryStep } from "../api/types";

/** Server cursor position to fast-forward to when the player answers the choice. */
export const OPENING_CHOICE_STEP = 14;
/** ...and at the end, handing playback over to the API loop. */
export const OPENING_LAST_STEP = 19;

let counter = 0;

function step(
  location: string,
  fields: Partial<StoryStep> & Pick<StoryStep, "type">,
): StoryStep {
  const index = counter++;
  return {
    step_id: `opening_${String(index).padStart(5, "0")}`,
    index,
    batch_id: "opening",
    location,
    characters: [],
    next_choices: [],
    ...fields,
  };
}

function narrate(location: string, text: string, character?: string, expression?: string): StoryStep {
  return step(location, {
    type: "narration",
    narration: text,
    characters: character ? [character] : [],
    visual: { background: location, character: character ?? null, expression: expression ?? null },
  });
}

function speak(
  location: string,
  speaker: string,
  expression: string,
  text: string,
): StoryStep {
  return step(location, {
    type: "dialogue",
    dialogue: { speaker, text },
    characters: [speaker],
    visual: { background: location, character: speaker, expression },
  });
}

/** Steps 00-14: classroom, cafeteria, library, ending on the first decision. */
export const OPENING_BEFORE_CHOICE: StoryStep[] = [
  // -- Classroom (morning), steps 00-04 --
  narrate("classroom", "You have transferred into Class 2-B six weeks into the school year."),
  narrate(
    "classroom",
    "The seats are arranged, the cliques are set, and everyone has already decided who they are.",
  ),
  narrate(
    "classroom",
    "Class 2-B smells of chalk dust and floor wax. Everyone stops to look as you walk in.",
    "aiko",
    "composed",
  ),
  speak(
    "classroom",
    "aiko",
    "composed",
    "You must be the transfer. I'm Aiko — class representative. If you need your syllabus or a locker assignment, let me know after homeroom.",
  ),
  speak(
    "classroom",
    "ren",
    "amused",
    "Six weeks in. Bold. I respect it. If you need someone to show you which teachers actually check the homework, I'm by the art room.",
  ),
  narrate(
    "classroom",
    "The morning drags on. Finally, the chime rings for the lunch break.",
    "aiko",
    "composed",
  ),

  // -- Cafeteria (noon), steps 05-09 --
  narrate(
    "cafeteria",
    "The hallways are a chaotic rush, pushing you toward the long tables of the cafeteria.",
  ),
  narrate(
    "cafeteria",
    "Before you can even find a seat, a blur of motion slides into the space next to you.",
    "mika",
    "excited",
  ),
  speak(
    "cafeteria",
    "mika",
    "excited",
    "HEY! You're the new one, right? I'm Mika. You're sitting with us — no arguments, I already saved the bench.",
  ),
  speak("cafeteria", "ren", "amused", "Give them room to breathe, Mika. Not everyone runs on rocket fuel."),
  narrate(
    "cafeteria",
    "The noise of the cafeteria washes over the table. It's loud, but strangely comforting.",
  ),

  // -- Library (afternoon), steps 10-14 --
  narrate(
    "library",
    "Escaping the noise, you find the library. The smell of old paper is a welcome relief.",
  ),
  narrate(
    "library",
    "Tall shelves cast long shadows. You spot someone shelving books in the quiet corner.",
    "haruto",
    "composed",
  ),
  speak("library", "haruto", "composed", "...You're in my light."),
  narrate("library", "He goes back to his work, leaving you to the quiet afternoon."),
  step("library", {
    type: "choice",
    narration: "The afternoon opens up. What do you do with it?",
    visual: { background: "library" },
    next_choices: [
      { id: "aiko", text: "Go find Aiko — she mentioned something about council work." },
      { id: "ren", text: "See if Ren is still in the art room." },
      { id: "mika", text: "Take Mika up on that offer to show you around." },
      { id: "haruto", text: "Stay here with Haruto and the quiet." },
      { id: "rooftop", text: "Go explore the rooftop everyone keeps mentioning." },
    ],
  }),
];

/** Steps 15-19: the rooftop, played after the choice has been sent. */
export const OPENING_AFTER_CHOICE: StoryStep[] = [
  narrate(
    "rooftop",
    "You wind your way up the stairs, pushing open the heavy metal door to the roof.",
  ),
  narrate("rooftop", "The city stretches out past the chain-link fence. The wind is sharper up here."),
  speak("rooftop", "aiko", "thoughtful", "It's a good view. People come up here when they need to think."),
  narrate("rooftop", "The sky begins to turn orange. The first day is almost over."),
  narrate(
    "rooftop",
    "The sunset paints everything in warm amber light as your first day draws to a close.",
    "aiko",
    "thoughtful",
  ),
];
