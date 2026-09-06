/**
 * Free-text input — the port of `decalove_ask_freetext`.
 *
 * The 300-character cap and the excluded braces come from the Ren'Py call: `{}` and
 * `[]` are Ren'Py text-tag and interpolation syntax. They are stripped here too, so
 * that the same input produces the same story in either client rather than diverging
 * on punctuation.
 *
 * An empty answer is not a submission: the loop re-offers the same decision point,
 * because the server still has it as the head of the ledger.
 */

import { useEffect, useRef, useState } from "react";

interface Props {
  onSubmit: (text: string) => void;
  onCancel: () => void;
}

export function FreeTextInput({ onSubmit, onCancel }: Props) {
  const [value, setValue] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => input.current?.focus(), []);

  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/60">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(value);
        }}
        className="w-[790px] rounded-sm border border-vn-muted bg-vn-void/95 px-10 py-8"
      >
        <label htmlFor="vn-freetext" className="mb-4 block text-[24px] text-white">
          What do you do?
        </label>
        <input
          id="vn-freetext"
          ref={input}
          value={value}
          maxLength={300}
          onChange={(event) => setValue(event.target.value.replace(/[{}[\]]/g, ""))}
          onKeyDown={(event) => {
            if (event.key === "Escape") onCancel();
          }}
          className="w-full border-b-2 border-vn-accent bg-transparent pb-2 text-[22px] text-white outline-none placeholder:text-vn-idle"
          placeholder="Say or do something…"
        />
        <div className="mt-6 flex items-center justify-between text-[18px]">
          <button
            type="button"
            onClick={onCancel}
            className="cursor-pointer text-vn-idle transition-colors hover:text-vn-hover"
          >
            Back to the options
          </button>
          <button
            type="submit"
            className="cursor-pointer text-vn-accent transition-colors hover:text-vn-hover"
          >
            Say it →
          </button>
        </div>
      </form>
    </div>
  );
}
