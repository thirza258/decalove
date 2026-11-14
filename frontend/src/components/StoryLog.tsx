/**
 * The story log: what has actually been delivered, oldest first.
 *
 * Players lose the thread in a long session — a promise made twenty beats ago, the
 * name of someone met in the opening. This is the transcript the engine already keeps,
 * shown without exposing buffered beats or engine state. Choice and prompt steps are
 * omitted; the player's own submitted line is included so the log reads as a scene.
 */

import { useEffect, useRef } from "react";
import type { WorldOut } from "../api/types";
import type { LogEntry } from "../game/machine";
import { humanise } from "../game/art";

interface Props {
  open: boolean;
  onClose: () => void;
  history: LogEntry[];
  world: WorldOut | null;
  playerName: string;
}

export function StoryLog({ open, onClose, history, world, playerName }: Props) {
  const dialog = useRef<HTMLElement>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (open) bottom.current?.scrollIntoView?.({ block: "end" });
  }, [open, history.length]);

  if (!open) return null;

  return (
    <div
      className="absolute inset-0 z-40 flex justify-end bg-black/45"
      onClick={onClose}
      role="presentation"
    >
      <aside
        ref={dialog}
        className="vn-fade flex h-full w-[460px] max-w-[92vw] flex-col border-l border-white/12 bg-vn-void/96 shadow-[-20px_0_60px_rgba(0,0,0,0.45)]"
        role="dialog"
        aria-modal="true"
        aria-label="Story log"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 border-b border-white/10 px-6 py-5">
          <div>
            <h2 className="text-[22px] text-white">Story log</h2>
            <p className="mt-1 text-[12px] text-white/45">
              Only scenes you have read. {history.length === 0 ? "Nothing yet." : `${history.length} lines.`}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="vn-focusable rounded-md border border-white/10 bg-white/5 px-2.5 py-1.5 text-[12px] text-white/65 transition-colors hover:bg-white/12 hover:text-white"
            aria-label="Close the story log"
          >
            Close <span aria-hidden="true">✕</span>
          </button>
        </header>

        <ol className="vn-scroll flex-1 space-y-4 overflow-y-auto px-6 py-5" aria-live="polite">
          {history.length === 0 && (
            <li className="rounded-md border border-dashed border-white/12 px-4 py-6 text-center text-[13px] text-white/40">
              Lines appear here as the story reaches you.
            </li>
          )}
          {history.map((entry) => {
            if (entry.kind === "narration") {
              return (
                <li key={entry.id} className="border-l-2 border-white/12 pl-3 text-[14px] leading-relaxed text-white/55 italic">
                  {entry.text}
                </li>
              );
            }
            const character = world?.characters.find((person) => person.id === entry.speaker);
            const player = entry.kind === "player";
            const name = player ? playerName : character?.name ?? humanise(entry.speaker ?? "");
            const color = player ? "#7fd0e8" : character?.palette?.[0] ?? "#8fa7c4";
            return (
              <li key={entry.id}>
                <div className="flex items-baseline gap-2">
                  <span className="text-[12px] font-medium tracking-wide" style={{ color }}>
                    {name}
                  </span>
                  {player && (
                    <span className="rounded-full border border-vn-accent/30 bg-vn-accent/10 px-1.5 py-px text-[9px] tracking-[0.08em] text-vn-hover/90 uppercase">
                      you
                    </span>
                  )}
                </div>
                <p className="mt-1 text-[15px] leading-relaxed text-white/85">{entry.text}</p>
              </li>
            );
          })}
          <div ref={bottom} />
        </ol>

        <footer className="border-t border-white/10 px-6 py-4 text-[11px] text-white/35">
          Press <kbd className="rounded border border-white/15 px-1">L</kbd> or{" "}
          <kbd className="rounded border border-white/15 px-1">Esc</kbd> to close.
        </footer>
      </aside>
    </div>
  );
}
