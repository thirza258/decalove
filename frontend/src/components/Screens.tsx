/**
 * The framing screens: main menu, character setup, and the two failure screens.
 *
 * `decalove_offline` and `decalove_expired` are deliberately distinct, and the Ren'Py
 * comment says why: telling someone to restart the server when the server is fine
 * would send them chasing the wrong problem. The engine earns that distinction by
 * asking `/worlds` — if it answers, the save is what is gone, not the backend.
 */

import { useEffect, useRef, useState } from "react";
import type { Profile } from "../game/machine";

const PANEL =
  "w-[790px] rounded-sm border border-vn-muted bg-vn-void/90 px-10 py-8 text-white";

export function GenerationErrorModal({ message, onRetry, onBack }: {
  message: string; onRetry: () => void; onBack: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return (
    <dialog ref={dialog} aria-labelledby="story-error-title" aria-describedby="story-error-message"
      onCancel={(event) => event.preventDefault()}
      className="m-auto w-[min(90vw,580px)] rounded-lg border border-vn-muted bg-vn-void p-8 text-white backdrop:bg-black/70">
      <h2 id="story-error-title" className="text-2xl">The story needs a moment</h2>
      <p id="story-error-message" className="mt-4 text-lg text-vn-idle">{message}</p>
      <p className="mt-3 text-vn-idle">Your progress is kept. Retry to continue from here.</p>
      <div className="mt-6 flex flex-wrap gap-4">
        <button type="button" onClick={onRetry} className="cursor-pointer rounded bg-vn-muted px-5 py-3 text-vn-accent hover:bg-vn-hover-muted">Try again</button>
        <button type="button" onClick={onBack} className="cursor-pointer px-5 py-3 text-vn-idle hover:text-white">New story</button>
      </div>
    </dialog>
  );
}

export function TitleScreen({
  title,
  onStart,
  onHome,
}: {
  title: string;
  onStart: () => void;
  onHome?: () => void;
}) {
  return (
    <Centered>
      <h1 className="text-[50px] tracking-wide text-white drop-shadow-lg">{title}</h1>
      <p className="mt-3 max-w-[640px] text-center text-[22px] text-vn-idle">
        A story that is written as you read it.
      </p>
      <div className="mt-10 flex flex-col items-center gap-4">
        <button
          type="button"
          onClick={onStart}
          className="cursor-pointer border-b-2 border-vn-accent px-8 py-2 text-[24px] text-vn-accent transition-colors hover:border-vn-hover hover:text-vn-hover"
        >
          New Game
        </button>
        {onHome && (
          <button
            type="button"
            onClick={onHome}
            className="cursor-pointer text-[18px] text-vn-idle transition-colors hover:text-white"
          >
            About & Cast
          </button>
        )}
      </div>
    </Centered>
  );
}

const PRONOUNS = ["she/her", "he/him", "they/them"];

/** `label decalove_setup` — PRD §7.1 / §30. Same three questions, same options. */
const TONES: { value: string; label: string }[] = [
  { value: "warm", label: "Warm. Funny. The quiet moments earned." },
  { value: "dramatic", label: "Sharper. Let things actually go wrong." },
  { value: "gentle", label: "Slow. Mostly just people, talking." },
];

export function SetupScreen({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (profile: Profile) => void;
}) {
  const [name, setName] = useState("");
  const [pronouns, setPronouns] = useState("they/them");
  const [tone, setTone] = useState("warm");

  return (
    <Centered>
      <form
        className={PANEL}
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ name: name.trim() || "You", pronouns, tone });
        }}
      >
        <label htmlFor="vn-name" className="block text-[24px]">
          What should everyone call you?
        </label>
        <input
          id="vn-name"
          value={name}
          maxLength={24}
          onChange={(event) => setName(event.target.value.replace(/[{}[\]]/g, ""))}
          placeholder="You"
          className="mt-3 w-full border-b-2 border-vn-accent bg-transparent pb-2 text-[22px] outline-none placeholder:text-vn-idle"
        />

        <fieldset className="mt-8">
          <legend className="text-[24px]">Which pronouns should the story use for you?</legend>
          <div className="mt-3 flex gap-3">
            {PRONOUNS.map((option) => (
              <Option
                key={option}
                selected={pronouns === option}
                onSelect={() => setPronouns(option)}
              >
                {option.replace("/", " / ")}
              </Option>
            ))}
          </div>
        </fieldset>

        <fieldset className="mt-8">
          <legend className="text-[24px]">And what kind of second year do you want?</legend>
          <div className="mt-3 flex flex-col gap-2">
            {TONES.map((option) => (
              <Option
                key={option.value}
                selected={tone === option.value}
                onSelect={() => setTone(option.value)}
              >
                {option.label}
              </Option>
            ))}
          </div>
        </fieldset>

        <button
          type="submit"
          disabled={busy}
          className="mt-8 w-full cursor-pointer rounded-sm bg-vn-muted py-3 text-[22px] transition-colors hover:bg-vn-hover-muted disabled:cursor-wait disabled:text-vn-insensitive"
        >
          {busy ? "Starting…" : "Begin"}
        </button>
      </form>
    </Centered>
  );
}

function Option({
  selected,
  onSelect,
  children,
}: {
  selected: boolean;
  onSelect: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`cursor-pointer rounded-sm border px-4 py-2 text-left text-[20px] transition-colors ${
        selected
          ? "border-vn-accent text-vn-selected"
          : "border-transparent bg-vn-muted/40 text-vn-idle hover:text-vn-hover"
      }`}
    >
      {children}
    </button>
  );
}

/** `screen decalove_offline`: the backend cannot be reached at all. */
export function OfflineScreen({
  message,
  onBack,
}: {
  message: string | null;
  onBack: () => void;
}) {
  return (
    <Centered>
      <div className={PANEL}>
        <h2 className="text-[30px]">Cannot reach the Decalove story engine.</h2>
        <p className="mt-4 text-[20px] text-vn-idle">{message}</p>
        <p className="mt-4 text-[18px] text-vn-idle">
          Start it with:{" "}
          <code className="text-vn-accent">uvicorn app.main:app --reload --port 8000</code>
        </p>
        <BackButton onBack={onBack} />
      </div>
    </Centered>
  );
}

/** `screen decalove_expired`: the server is fine; this story is not. */
export function ExpiredScreen({ onBack }: { onBack: () => void }) {
  return (
    <Centered>
      <div className={PANEL}>
        <h2 className="text-[30px]">This story has closed.</h2>
        <p className="mt-4 text-[20px] text-vn-idle">
          Stories that go uncontinued are cleared after a week, and this one was among them.
          The people in it have moved on.
        </p>
        <BackButton onBack={onBack} />
      </div>
    </Centered>
  );
}

export function EndingOverlay({ onBack }: { onBack: () => void }) {
  return (
    <div className="absolute inset-x-0 bottom-[200px] z-20 flex justify-center">
      <button
        type="button"
        onClick={onBack}
        className="cursor-pointer border-b-2 border-vn-accent px-6 py-2 text-[22px] text-vn-accent transition-colors hover:border-vn-hover hover:text-vn-hover"
      >
        The end — back to the title
      </button>
    </div>
  );
}

function BackButton({ onBack }: { onBack: () => void }) {
  return (
    <button
      type="button"
      onClick={onBack}
      className="mt-8 cursor-pointer text-[20px] text-vn-accent transition-colors hover:text-vn-hover"
    >
      Back to the main menu
    </button>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="vn-fade absolute inset-0 z-40 flex flex-col items-center justify-center bg-vn-void">
      {children}
    </div>
  );
}
