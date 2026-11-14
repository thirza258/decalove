/**
 * The text box — `gui.textbox_height` (185), `gui.name_xpos` (240) and
 * `gui.dialogue_xpos/width` (268/744) used verbatim, because the stage *is* the
 * 1280x720 canvas those numbers were written for.
 *
 * Translucent rather than opaque, and the text occupies well under the full width:
 * both are standard visual-novel practice, and gui.rpy already encodes both. The box
 * is meant to stay out of the way of the art behind it.
 *
 * The visible text is the typewriter prefix. A separate screen-reader-only region
 * announces the full line only once it has finished, so assistive technology is not
 * made to read along at 45 characters per second.
 */

interface Props {
  /** Character name, or null for unattributed narration. */
  speaker: string | null;
  speakerColor: string | null;
  /** Only the revealed prefix; the typewriter lives in the caller. */
  text: string;
  /** The full line, for the screen-reader announcement. */
  fullText?: string;
  /** Whether the typewriter has finished. */
  revealed?: boolean;
  /** How the speaker is feeling, shown as a quiet chip beside the name. */
  emotion?: string | null;
  /** Italic, for the ambient lines shown while the engine is still writing. */
  muted?: boolean;
  /** Hidden while a decision is on screen — the choices are the prompt then. */
  showAdvanceHint: boolean;
}

export function DialogueBox({
  speaker,
  speakerColor,
  text,
  fullText,
  revealed = true,
  emotion,
  muted,
  showAdvanceHint,
}: Props) {
  const feeling = emotion && emotion !== "neutral" ? emotion.replace(/_/g, " ") : "";

  return (
    <section
      className="absolute inset-x-0 bottom-0 h-[185px] bg-gradient-to-t from-black/92 via-black/78 to-black/35"
      aria-label="Dialogue"
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />

      {speaker && (
        <div className="absolute top-[18px] left-[240px] flex items-baseline gap-2.5">
          <span
            aria-hidden="true"
            className="mb-[3px] inline-block h-[16px] w-[3px] rounded-full"
            style={{ background: speakerColor ?? "#0099cc" }}
          />
          <span
            className="text-[30px] leading-none"
            style={{
              color: speakerColor ?? undefined,
              textShadow: "2px 2px 0 rgba(0,0,0,0.75)",
            }}
          >
            {speaker}
          </span>
          {feeling && (
            <span className="rounded-full border border-white/12 bg-white/6 px-2 py-[2px] text-[11px] tracking-[0.06em] text-white/55 capitalize">
              {feeling}
            </span>
          )}
        </div>
      )}

      <p
        className={`absolute left-[268px] w-[744px] text-[22px] leading-[1.45] ${
          muted ? "italic text-white/70" : "text-white"
        }`}
        style={{
          top: speaker ? "62px" : "40px",
          textShadow: "1px 1px 2px rgba(0,0,0,0.8)",
        }}
      >
        {text}
      </p>

      {/* Announce the completed line once; the typewriter prefix would otherwise make
          a screen reader re-read the sentence on every character. */}
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {revealed ? fullText ?? text : ""}
      </span>

      {showAdvanceHint && (
        <span className="absolute right-[40px] bottom-[16px] flex items-center gap-1.5 text-[15px] text-vn-idle">
          <span className="animate-pulse" aria-hidden="true">
            ▾
          </span>
          click or press <kbd className="rounded border border-white/20 px-1.5 py-px text-[11px] text-white/60">Space</kbd>
        </span>
      )}
    </section>
  );
}
