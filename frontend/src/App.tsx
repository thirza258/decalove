/**
 * Entry point — the port of `label start` in `game/script.rpy`.
 *
 * Deliberately short, for the same reason the Ren'Py original is: the backend directs
 * the story (PRD §20), the playback rules live in `game/machine.ts`, and this file
 * only decides which screen is on top.
 */

import { lazy, Suspense, useEffect, useMemo, useState } from "react";
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
import { RelationshipStatus } from "./components/RelationshipStatus";
import { Stage } from "./components/Stage";
import { StageFrame } from "./components/StageFrame";
import { useDecalove } from "./hooks/useDecalove";
import { useTypewriter } from "./hooks/useTypewriter";
import { humanise } from "./game/art";
import "./writing.css";
import { WritingWorkspaceProvider } from "./writing/workspace";

const CoursesPage = lazy(() => import("./components/CoursesPage"));
const WritingStudio = lazy(() => import("./components/WritingStudio"));

function currentPage() {
  const page = window.location.hash.slice(2).split("?")[0];
  return ["play", "courses", "studio"].includes(page) ? page : "home";
}

function currentWorkspace() {
  return new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("workspace") ?? "current";
}

/** `label decalove_intro` — three lines before the player is asked anything. */
const INTRO = [
  "Six weeks into the school year, a transfer student walks into Class 2-B.",
  "Everyone else has already decided who they are.",
  "You haven't.",
];

export default function App() {
  const [page, setPage] = useState(currentPage);
  const [workspaceKey, setWorkspaceKey] = useState(currentWorkspace);
  const [exercise, setExercise] = useState("");
  useEffect(() => {
    const navigate = () => {
      setPage(currentPage());
      setWorkspaceKey(currentWorkspace());
      const root = document.getElementById("root");
      if (root) root.scrollTop = 0;
    };
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  if (page === "play") return <GamePlayer onHome={() => { window.location.hash = "/"; }} />;
  if (page === "home") return <LandingPage onPlay={() => { window.location.hash = "/play"; }} />;
  return (
    <Suspense fallback={<div className="writing-app writing-loading" role="status">Opening the writing room…</div>}>
      <WritingWorkspaceProvider key={workspaceKey}>
        {page === "courses" ? <CoursesPage onPractice={(prompt) => { setExercise(prompt); window.location.hash = "/studio"; }} />
          : <WritingStudio exercise={exercise} onExerciseUsed={() => setExercise("")} />}
      </WritingWorkspaceProvider>
    </Suspense>
  );
}

function GamePlayer({ onHome }: { onHome: () => void }) {
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
          onHome={onHome}
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
        <RelationshipStatus
          standing={state.standing}
          delta={state.standingDelta}
          world={state.world}
          seq={state.standingSeq}
        />
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
