/**
 * The decision point — the port of `screen decalove_choice`.
 *
 * Traditional visual-novel options (PRD §8 Method A) plus a permanent door into free
 * text (Method B). The free-text button is always there on purpose: the player should
 * never have to guess whether typing is allowed.
 *
 * `gui.choice_button_width` is 790px on the 1280 canvas, so that is the width here.
 */

import type { Choice } from "../api/types";

interface Props {
  choices: Choice[];
  onPick: (choiceId: string) => void;
  onFreeText: () => void;
}

export function ChoiceMenu({ choices, onPick, onFreeText }: Props) {
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/35">
      <div className="flex flex-col items-center gap-[6px]">
        {choices.map((choice) => (
          <button
            key={choice.id}
            type="button"
            onClick={() => onPick(choice.id)}
            className="w-[790px] cursor-pointer rounded-sm bg-vn-muted/70 px-6 py-3 text-center text-[22px] text-vn-idle transition-colors hover:bg-vn-hover-muted/80 hover:text-vn-hover"
          >
            {choice.text}
          </button>
        ))}

        <button
          type="button"
          onClick={onFreeText}
          className="mt-2 w-[790px] cursor-pointer rounded-sm border border-vn-muted px-6 py-3 text-center text-[22px] text-vn-idle italic transition-colors hover:border-vn-accent hover:text-vn-hover"
        >
          Say something else…
        </button>
      </div>
    </div>
  );
}
