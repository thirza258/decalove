/**
 * The text box — `gui.textbox_height` (185), `gui.name_xpos` (240) and
 * `gui.dialogue_xpos/width` (268/744) used verbatim, because the stage *is* the
 * 1280x720 canvas those numbers were written for.
 *
 * Translucent rather than opaque, and the text occupies well under the full width:
 * both are standard visual-novel practice, and gui.rpy already encodes both. The box
 * is meant to stay out of the way of the art behind it.
 */

interface Props {
  /** Character name, or null for unattributed narration. */
  speaker: string | null;
  speakerColor: string | null;
  /** Only the revealed prefix; the typewriter lives in the caller. */
  text: string;
  /** Italic, for the ambient lines shown while the engine is still writing. */
  muted?: boolean;
  /** Hidden while a decision is on screen — the choices are the prompt then. */
  showAdvanceHint: boolean;
}

export function DialogueBox({ speaker, speakerColor, text, muted, showAdvanceHint }: Props) {
  return (
    <div className="absolute inset-x-0 bottom-0 h-[185px] bg-gradient-to-t from-black/90 via-black/75 to-black/40">
      {speaker && (
        <div
          className="absolute top-[18px] left-[240px] text-[30px] leading-none"
          style={{
            color: speakerColor ?? undefined,
            textShadow: "2px 2px 0 rgba(0,0,0,0.75)",
          }}
        >
          {speaker}
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

      {showAdvanceHint && (
        <span className="absolute right-[40px] bottom-[16px] animate-pulse text-[16px] text-vn-idle">
          click to continue ▾
        </span>
      )}
    </div>
  );
}
