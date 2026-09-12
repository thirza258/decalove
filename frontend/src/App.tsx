/**
 * Entry point — the port of `label start` in `game/script.rpy`.
 *
 * Deliberately short, for the same reason the Ren'Py original is: the backend directs
 * the story (PRD §20), the playback rules live in `game/machine.ts`, and this file
 * only decides which screen is on top.
 */

import { useMemo, useState } from "react";
import { ChoiceMenu } from "./components/ChoiceMenu";
import { DialogueBox } from "./components/DialogueBox";
import { FreeTextInput } from "./components/FreeTextInput";
import { LandingPage } from "./components/LandingPage";
import {
  EndingOverlay,
  GenerationErrorModal,
  ExpiredScreen,
  OfflineScreen,
  SetupScreen,
  TitleScreen,
} from "./components/Screens";
import { Stage } from "./components/Stage";
import { StageFrame } from "./components/StageFrame";
import { useDecalove } from "./hooks/useDecalove";
import { useTypewriter } from "./hooks/useTypewriter";
import { humanise } from "./game/art";

/** `label decalove_intro` — three lines before the player is asked anything. */
const INTRO = [
  "Six weeks into the school year, a transfer student walks into Class 2-B.",
  "Everyone else has already decided who they are.",
  "You haven't.",
];

export default function App() {
  const [playing, setPlaying] = useState(false);
  const game = useDecalove();
  const { state } = game;

  // What the box is currently saying. An ambient line displaces the beat's own text
  // while the engine is still writing; it is italic and never a spinner (PRD §11).
  const { ambient, current: step, world } = state;
  const line = useMemo(() => {
    if (ambient) return { speaker: null, color: null, text: ambient, muted: true };
    if (!step) return { speaker: null, color: null, text: "", muted: false };
    const spoken = step.dialogue;
    if (spoken?.text) {
      const character = world?.characters.find((c) => c.id === spoken.speaker);
      return {
        speaker: character?.name ?? humanise(spoken.speaker),
        color: character?.palette?.[0] ?? null,
        text: spoken.text,
        muted: false,
      };
    }
    return { speaker: null, color: null, text: step.narration ?? "", muted: false };
  }, [ambient, step, world]);

  const beat = ambient ? `ambient:${state.ambientSeen}` : (step?.step_id ?? "");
  const typed = useTypewriter(line.text, beat);

  // A click mid-line completes it; only a click on a finished line advances. This is
  // the behaviour every visual novel has, and it is why the typewriter is lifted out
  // of the text box.
  const onStageClick = () => {
    if (state.deciding || state.typing || state.error) return;
    if (!typed.done) {
      typed.complete();
      return;
    }
    game.advance();
  };

  // Show the landing page until the player clicks "Play Now".
  if (!playing) {
    return <LandingPage onPlay={() => setPlaying(true)} />;
  }

  if (state.phase === "boot") {
    return <StageFrame><Booting /></StageFrame>;
  }

  if (state.phase === "offline") {
    return (
      <StageFrame>
        <OfflineScreen message={state.message} onBack={game.backToMenu} />
      </StageFrame>
    );
  }

  if (state.phase === "expired") {
    return (
      <StageFrame>
        <ExpiredScreen onBack={game.backToMenu} />
      </StageFrame>
    );
  }

  if (state.phase === "menu") {
    return (
      <StageFrame>
        <TitleScreen
          title={state.world?.title ?? "Decalove"}
          onStart={game.startNewGame}
          onHome={() => setPlaying(false)}
        />
      </StageFrame>
    );
  }

  if (state.phase === "setup") {
    return (
      <StageFrame>
        <SetupScreen busy={state.busy} onSubmit={game.submitSetup} />
      </StageFrame>
    );
  }

  if (state.phase === "intro") {
    return (
      <StageFrame>
        <Intro onDone={game.finishIntro} />
      </StageFrame>
    );
  }

  return (
    <StageFrame>
      {/* The whole stage is the advance target, as clicking anywhere is in Ren'Py. */}
      <div className="absolute inset-0 cursor-pointer" onClick={onStageClick}>
        <Stage step={state.current} world={state.world} />
        <DialogueBox
          speaker={line.speaker}
          speakerColor={line.color}
          text={typed.shown}
          muted={line.muted}
          showAdvanceHint={typed.done && !state.deciding && !state.typing && !state.busy}
        />
      </div>

      {state.deciding && !state.typing && !state.busy && !state.error && state.current && (
        <ChoiceMenu
          choices={state.current.next_choices}
          onPick={game.chooseOption}
          onSubmitCustom={game.submitFreeText}
          onFreeText={() => game.openFreeText(true)}
        />
      )}

      {state.typing && !state.busy && !state.error && (
        <FreeTextInput
          onSubmit={game.submitFreeText}
          onCancel={() => game.openFreeText(false)}
        />
      )}

      {state.phase === "ended" && <EndingOverlay onBack={game.backToMenu} />}
      {state.error && (
        <GenerationErrorModal message={state.error.message} onRetry={game.retry} onBack={game.backToMenu} />
      )}
    </StageFrame>
  );
}

/** `label decalove_intro`: three lines over the void, click-advanced. */
function Intro({ onDone }: { onDone: () => void }) {
  const [index, setIndex] = useState(0);
  const typed = useTypewriter(INTRO[index] ?? "");

  return (
    <div
      className="absolute inset-0 cursor-pointer bg-vn-void"
      onClick={() => {
        if (!typed.done) {
          typed.complete();
          return;
        }
        if (index + 1 >= INTRO.length) onDone();
        else setIndex(index + 1);
      }}
    >
      <DialogueBox
        speaker={null}
        speakerColor={null}
        text={typed.shown}
        showAdvanceHint={typed.done}
      />
    </div>
  );
}

function Booting() {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-vn-void">
      <span className="text-[22px] text-vn-idle">Reaching the story engine…</span>
    </div>
  );
}
