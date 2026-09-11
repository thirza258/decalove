/**
 * The decision point — allows selecting traditional visual-novel choices
 * or typing custom natural-language action/dialogue directly.
 *
 * PRD §8: Method A (preset options) and Method B (free-text action).
 * Both are presented together so the player can choose a preset option
 * or write their own response to guide the story generation.
 */

import { useState, useRef, useEffect } from "react";
import type { Choice } from "../api/types";

interface Props {
  choices: Choice[];
  onPick: (choiceId: string) => void;
  onSubmitCustom: (text: string) => void;
  onFreeText?: () => void;
}

export function ChoiceMenu({ choices, onPick, onSubmitCustom, onFreeText }: Props) {
  const [customText, setCustomText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus the custom input when the decision point appears
  useEffect(() => {
    // Small delay so render completes
    const timer = setTimeout(() => {
      inputRef.current?.focus();
    }, 100);
    return () => clearTimeout(timer);
  }, []);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = customText.trim();
    if (!trimmed) return;
    onSubmitCustom(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Submit on Enter
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div
      className="absolute inset-0 z-20 flex items-center justify-center bg-black/50 pb-[100px]"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex w-[790px] flex-col items-center gap-[10px] rounded-lg border border-vn-muted/60 bg-vn-void/95 p-6 shadow-2xl backdrop-blur-sm">
        <div className="w-full text-center">
          <span className="text-[18px] font-medium tracking-wide text-vn-accent uppercase">
            What will you do?
          </span>
        </div>

        {/* Preset choices */}
        <div className="flex w-full flex-col gap-[8px]">
          {choices.map((choice, index) => (
            <button
              key={choice.id}
              type="button"
              onClick={() => onPick(choice.id)}
              className="group flex w-full cursor-pointer items-center justify-between rounded-sm bg-vn-muted/50 px-6 py-3 text-left text-[20px] text-vn-idle transition-all duration-200 hover:bg-vn-hover-muted/80 hover:text-white"
            >
              <div className="flex items-center gap-3">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-[13px] text-vn-idle group-hover:bg-vn-accent group-hover:text-white">
                  {index + 1}
                </span>
                <span>{choice.text}</span>
              </div>
              <span className="text-[14px] text-vn-accent opacity-0 transition-opacity group-hover:opacity-100">
                Choose ↵
              </span>
            </button>
          ))}
        </div>

        {/* Divider */}
        <div className="my-1 flex w-full items-center gap-3">
          <div className="h-px flex-1 bg-white/10" />
          <span className="text-[13px] tracking-wider text-white/40 uppercase">
            or write your own response
          </span>
          <div className="h-px flex-1 bg-white/10" />
        </div>

        {/* Direct custom user input */}
        <form
          onSubmit={handleSubmit}
          className="flex w-full items-center gap-2 rounded-sm border border-vn-muted/80 bg-black/60 p-1.5 transition-colors focus-within:border-vn-accent"
        >
          <input
            ref={inputRef}
            type="text"
            value={customText}
            maxLength={300}
            onChange={(e) => setCustomText(e.target.value.replace(/[{}[\]]/g, ""))}
            onKeyDown={handleKeyDown}
            placeholder="Type what you say or do (e.g. ask Aiko about after school, tease Ren...)"
            className="flex-1 bg-transparent px-3 py-1.5 text-[19px] text-white outline-none placeholder:text-white/30"
          />
          <button
            type="submit"
            disabled={!customText.trim()}
            className="cursor-pointer rounded-sm bg-vn-accent px-5 py-2 text-[17px] font-medium text-white transition-all hover:bg-vn-hover disabled:cursor-not-allowed disabled:opacity-30"
          >
            Act ↵
          </button>
        </form>

        <div className="flex w-full items-center justify-between text-[13px] text-white/40">
          <span>✨ The story and characters will dynamically react to your input.</span>
          {onFreeText && (
            <button
              type="button"
              onClick={onFreeText}
              className="cursor-pointer text-vn-idle transition-colors hover:text-vn-hover"
            >
              Expanded view ↗
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
