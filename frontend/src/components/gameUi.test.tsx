// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CharacterStanding, StoryStep, WorldOut } from "../api/types";
import type { LogEntry } from "../game/machine";
import { ChoiceMenu } from "./ChoiceMenu";
import { RelationshipStatus } from "./RelationshipStatus";
import { SceneHud } from "./SceneHud";
import { StoryLog } from "./StoryLog";

afterEach(cleanup);

const world: WorldOut = {
  id: "highschool_romance",
  title: "Second Year, Second Chances",
  premise: "A transfer student.",
  tone: "warm",
  rating: "teen",
  opening_location: "classroom",
  characters: [
    {
      id: "aiko", name: "Aiko Serizawa", pronouns: "she/her", role: "class rep",
      expressions: ["neutral"], palette: ["#8fb7d9", "#31506b"],
    },
    {
      id: "ren", name: "Ren Hoshikawa", pronouns: "he/him", role: "artist",
      expressions: ["neutral"], palette: ["#d99b9b", "#6b3131"],
    },
  ],
  locations: [
    {
      id: "library", name: "School Library", description: "Quiet stacks.",
      palette: ["#aabbcc", "#223344"], ambience: ["Pages turn."],
    },
  ],
};

function beat(overrides: Partial<StoryStep> = {}): StoryStep {
  return {
    step_id: "step_00003", index: 3, batch_id: "b", type: "dialogue",
    location: "library", characters: ["aiko"], next_choices: [],
    dialogue: { speaker: "aiko", text: "You came back.", emotion: "surprised" },
    visual: { background: "library", time_of_day: "afternoon" },
    ...overrides,
  };
}

describe("SceneHud", () => {
  it("names the place, the clock, the arc and who is present", () => {
    render(
      <SceneHud
        scene={{
          location: "library", time_of_day: "afternoon", weekday: "Tuesday",
          day: 3, weather: "clear", arc: "first_weeks", present_characters: ["aiko", "ren"],
        }}
        world={world}
        step={beat()}
        waiting={false}
        deciding={false}
        onOpenLog={() => {}}
      />,
    );
    expect(screen.getByRole("heading", { name: "School Library" })).toBeTruthy();
    expect(screen.getByText("Day 3")).toBeTruthy();
    expect(screen.getByText("Tuesday")).toBeTruthy();
    expect(screen.getByText("Clear")).toBeTruthy();
    expect(screen.getByText("First Weeks")).toBeTruthy();
    // The beat's own cast is fresher than the once-per-turn snapshot; Ren is not in it.
    expect(screen.getByText("Aiko")).toBeTruthy();
    expect(screen.queryByText("Ren")).toBeNull();
  });

  it("prefers the current beat's location over a once-per-turn snapshot", () => {
    render(
      <SceneHud
        scene={{
          location: "classroom", time_of_day: "morning", weekday: "Monday",
          day: 1, weather: "clear", arc: "prologue", present_characters: ["ren"],
        }}
        world={world}
        step={beat()}
        waiting={false}
        deciding={false}
        onOpenLog={() => {}}
      />,
    );
    expect(screen.getByRole("heading", { name: "School Library" })).toBeTruthy();
  });

  it("shows the live status and opens the log", () => {
    const open = vi.fn();
    render(
      <SceneHud scene={null} world={world} step={beat()} waiting deciding={false} onOpenLog={open} />,
    );
    expect(screen.getByText("Writing the next scene…")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open the story log" }));
    expect(open).toHaveBeenCalledOnce();
  });
});

describe("StoryLog", () => {
  const history: LogEntry[] = [
    { id: "s1", kind: "narration", speaker: null, text: "Rain on the high windows.", index: 1 },
    { id: "s2", kind: "dialogue", speaker: "aiko", text: "You came back.", index: 2 },
    { id: "p1", kind: "player", speaker: "Kai", text: "I said I would.", index: 3 },
  ];

  it("reads back narration, dialogue and the player's own line", () => {
    render(<StoryLog open onClose={() => {}} history={history} world={world} playerName="Kai" />);
    expect(screen.getByText("Rain on the high windows.")).toBeTruthy();
    expect(screen.getByText("Aiko Serizawa")).toBeTruthy();
    expect(screen.getByText("You came back.")).toBeTruthy();
    expect(screen.getByText("Kai")).toBeTruthy();
    expect(screen.getByText("I said I would.")).toBeTruthy();
  });

  it("closes with its button and with Escape", () => {
    const close = vi.fn();
    render(<StoryLog open onClose={close} history={history} world={world} playerName="Kai" />);
    fireEvent.click(screen.getByRole("button", { name: "Close the story log" }));
    expect(close).toHaveBeenCalledOnce();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(close).toHaveBeenCalledTimes(2);
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <StoryLog open={false} onClose={() => {}} history={history} world={world} playerName="Kai" />,
    );
    expect(container.innerHTML).toBe("");
  });
});

describe("ChoiceMenu", () => {
  const choices = [
    { id: "c1", text: "Offer to help with the page." },
    { id: "c2", text: "Ask why she is upset." },
    { id: "c3", text: "Say nothing." },
  ];

  it("shows an intent tag without changing the option text", () => {
    render(<ChoiceMenu choices={choices} onPick={() => {}} onSubmitCustom={() => {}} />);
    expect(screen.getAllByText("Support").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Ask").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Observe").length).toBeGreaterThan(0);
    expect(screen.getByText("Offer to help with the page.")).toBeTruthy();
  });

  it("picks with number keys", () => {
    const pick = vi.fn();
    render(<ChoiceMenu choices={choices} onPick={pick} onSubmitCustom={() => {}} />);
    fireEvent.keyDown(window, { key: "2" });
    expect(pick).toHaveBeenCalledWith("c2");
  });

  it("submits a typed line", () => {
    const custom = vi.fn();
    render(<ChoiceMenu choices={choices} onPick={() => {}} onSubmitCustom={custom} />);
    const input = screen.getByLabelText("Write your own action or line");
    fireEvent.change(input, { target: { value: "I apologise to Aiko." } });
    fireEvent.submit(input.closest("form")!);
    expect(custom).toHaveBeenCalledWith("I apologise to Aiko.");
  });
});

describe("RelationshipStatus", () => {
  const standing: Record<string, CharacterStanding> = {
    aiko: {
      id: "aiko", name: "Aiko Serizawa", met: true,
      current_emotion: "surprised",
      relationship: { affection: 42, trust: 31, romance: 8, anger: 3 },
    },
  };

  it("shows affection plus the axes that give it meaning", () => {
    render(
      <RelationshipStatus
        standing={standing}
        delta={{ aiko: { affection: 3, trust: 1 } }}
        world={world}
        seq={1}
      />,
    );
    expect(screen.getByText("Aiko Serizawa")).toBeTruthy();
    expect(screen.getByText("surprised")).toBeTruthy();
    expect(screen.getByText("trust")).toBeTruthy();
    expect(screen.getByText("romance")).toBeTruthy();
    expect(screen.getByText("anger")).toBeTruthy();
    expect(screen.getByText(/\+3 affection\s+\+1 trust/)).toBeTruthy();
    expect(
      screen.getByRole("meter", { name: "Aiko Serizawa: affection 42 of 100" }),
    ).toBeTruthy();
  });

  it("collapses to the headline without losing the engine's values", () => {
    render(
      <RelationshipStatus standing={standing} delta={{}} world={world} seq={0} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Collapse relationship details" }));
    expect(screen.queryByText("trust")).toBeNull();
    expect(screen.getByText("Aiko Serizawa")).toBeTruthy();
  });
});
