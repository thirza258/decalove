/**
 * The decision point — allows selecting traditional visual-novel choices
 * or typing custom natural-language action/dialogue directly.
 *
 * PRD §8: Method A (preset options) and Method B (free-text action).
 * Both are presented together so the player can choose a preset option
 * or write their own response to guide the story generation.
 *
 * Each option carries a small intent tag (Support, Ask, Challenge, …). It is a local
 * reading for scannability, never a rewrite: the engine's option text is shown exactly.
 * Number keys pick an option; `E` jumps to the free-text field.
 */

import { useEffect, useRef, useState } from "react";
import type { Choice } from "../api/types";
import { classifyChoice, type ChoiceIntentStyle } from "../game/choiceIntent";

interface Props {
  choices: Choice[];
  onPick: (choiceId: string) => void;
  onSubmitCustom: (text: string) => void;
  onFreeText?: () => void;
}

function IntentTag({ intent }: { intent: ChoiceIntentStyle }) {
  return (
    <span
      className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-[0.06em] uppercase ${intent.className}`}
      title={`This option reads as: ${intent.label}`}
    >
      <span aria-hidden="true" className="mr-1">
        {intent.glyph}
      </span>
      {intent.label}
    </span>
  );
}

export function ChoiceMenu({ choices, onPick, onSubmitCustom, onFreeText }: Props) {
  const [customText, setCustomText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus the custom input when the decision point appears.
  useEffect(() => {
    const timer = setTimeout(() => inputRef.current?.focus(), 100);
    return () => clearTimeout(timer);
  }, []);

  // Number keys pick; E focuses the writer. Guarded so typing "1" or "e" in the
  // free-text field stays typing.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable)
      ) {
        return;
      }
      if (/^[1-9]$/.test(event.key)) {
        const choice = choices[Number(event.key) - 1];
        if (choice) {
          event.preventDefault();
          onPick(choice.id);
        }
      } else if (event.key.toLowerCase() === "e") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [choices, onPick]);

  const handleSubmit = (event?: React.FormEvent) => {
    if (event) event.preventDefault();
    const trimmed = customText.trim();
    if (!trimmed) return;
    onSubmitCustom(trimmed);
  };

  return (
    <div
      className="absolute inset-0 z-20 flex items-center justify-center bg-black/55 px-6 pb-[80px]"
      onClick={(event) => event.stopPropagation()}
    >
      <div
        className="flex max-h-[78%] w-[820px] max-w-full flex-col items-center gap-[10px] overflow-hidden rounded-xl border border-vn-muted/60 bg-vn-void/96 p-6 shadow-2xl backdrop-blur-sm"
        role="dialog"
        aria-modal="true"
        aria-labelledby="vn-decision-title"
      >
        <div className="w-full text-center">
          <span
            id="vn-decision-title"
            className="text-[18px] font-medium tracking-[0.1em] text-vn-accent uppercase"
          >
            What will you do?
          </span>
          <p className="mt-1 text-[12px] text-white/40">
            Press <kbd className="rounded border border-white/15 px-1">1</kbd>–
            <kbd className="rounded border border-white/15 px-1">{choices.length}</kbd> to choose, or{" "}
            <kbd className="rounded border border-white/15 px-1">E</kbd> to write your own.
          </p>
        </div>

        {/* Preset choices */}
        <div className="vn-scroll flex w-full flex-col gap-[8px] overflow-y-auto pr-1">
          {choices.map((choice, index) => {
            const intent = classifyChoice(choice.text);
            return (
              <button
                key={choice.id}
                type="button"
                onClick={() => onPick(choice.id)}
                aria-label={`Option ${index + 1}, ${intent.label}: ${choice.text}`}
                className="vn-focusable group flex w-full cursor-pointer items-center gap-3 rounded-lg border border-transparent bg-vn-muted/40 px-4 py-3 text-left text-[19px] text-vn-idle transition-all duration-200 hover:border-white/15 hover:bg-vn-hover-muted/70 hover:text-white focus-visible:border-vn-hover"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/8 text-[13px] tabular-nums text-vn-idle transition-colors group-hover:bg-vn-accent group-hover:text-white">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1">{choice.text}</span>
                <IntentTag intent={intent} />
                <span
                  aria-hidden="true"
                  className="text-[14px] text-vn-accent opacity-0 transition-opacity group-hover:opacity-100"
                >
                  ↵
                </span>
              </button>
            );
          })}
        </div>

        {/* Divider */}
        <div className="my-0.5 flex w-full items-center gap-3">
          <div className="h-px flex-1 bg-white/10" />
          <span className="text-[11px] tracking-[0.12em] text-white/35 uppercase">
            or write your own response
          </span>
          <div className="h-px flex-1 bg-white/10" />
        </div>

        {/* Direct custom user input */}
        <form
          onSubmit={handleSubmit}
          className="flex w-full items-center gap-2 rounded-lg border border-vn-muted/80 bg-black/60 p-1.5 transition-colors focus-within:border-vn-accent"
        >
          <input
            ref={inputRef}
            type="text"
            value={customText}
            maxLength={300}
            onChange={(event) => setCustomText(event.target.value.replace(/[{}[\]]/g, ""))}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                handleSubmit();
              }
            }}
            placeholder="Type what you say or do (e.g. ask Aiko about after school, tease Ren...)"
            className="flex-1 bg-transparent px-3 py-1.5 text-[18px] text-white outline-none placeholder:text-white/30"
            aria-label="Write your own action or line"
          />
          <span className="text-[10px] tabular-nums text-white/25">
            {customText.length > 240 ? `${customText.length}/300` : ""}
          </span>
          <button
            type="submit"
            disabled={!customText.trim()}
            className="vn-focusable cursor-pointer rounded-md bg-vn-accent px-5 py-2 text-[17px] font-medium text-white transition-all hover:bg-vn-hover disabled:cursor-not-allowed disabled:opacity-30"
          >
            Act ↵
          </button>
        </form>

        <div className="flex w-full items-center justify-between gap-4 text-[12px] text-white/40">
          <span>✨ The story and characters react to what you actually write.</span>
          {onFreeText && (
            <button
              type="button"
              onClick={onFreeText}
              className="vn-focusable shrink-0 cursor-pointer text-vn-idle transition-colors hover:text-vn-hover"
            >
              Expanded view ↗
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
