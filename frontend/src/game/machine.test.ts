/**
 * The rules `decalove_play` encoded as a blocking loop, asserted as transitions.
 *
 * These are the behaviours that are easy to lose in a rewrite and invisible when
 * lost: the player just sees a spinner, or a replayed ending, or a dead end.
 */

import { describe, expect, it } from "vitest";
import { AMBIENT_LIMIT, MAX_OFFLINE_STREAK, MAX_PENDING_POLLS } from "../config";
import type { StepsBatchOut, StoryStep } from "../api/types";
import { initialState, reduce, type State } from "./machine";

function step(overrides: Partial<StoryStep> = {}): StoryStep {
  return {
    step_id: "step_00000",
    index: 0,
    batch_id: "b",
    type: "narration",
    location: "classroom",
    characters: [],
    narration: "A line.",
    next_choices: [],
    ...overrides,
  };
}

function batch(overrides: Partial<StepsBatchOut> = {}): StepsBatchOut {
  return { status: "ready", steps: [], queue_depth: 0, retry_after_ms: 700, ambience: [], ...overrides };
}

const playing: State = { ...initialState, phase: "story", gameId: "g1", source: "api" };

describe("delivery", () => {
  it("plays the first step and buffers the rest", () => {
    const steps = [step({ step_id: "a" }), step({ step_id: "b" }), step({ step_id: "c" })];
    const state = reduce(playing, { type: "batch/received", body: batch({ steps }) });

    expect(state.current?.step_id).toBe("a");
    // The whole reason clicking feels instant: b and c need no further network.
    expect(state.buffer.map((s) => s.step_id)).toEqual(["b", "c"]);
  });

  it("advances through the buffer without touching the network", () => {
    let state = reduce(playing, {
      type: "batch/received",
      body: batch({ steps: [step({ step_id: "a" }), step({ step_id: "b" })] }),
    });
    state = reduce(state, { type: "advance" });

    expect(state.current?.step_id).toBe("b");
    expect(state.buffer).toHaveLength(0);
  });

  it("hands control to the player on a blocking step", () => {
    const state = reduce(playing, {
      type: "batch/received",
      body: batch({
        steps: [step({ type: "choice", next_choices: [{ id: "c1", text: "Go" }] })],
      }),
    });
    expect(state.deciding).toBe(true);
  });

  it("re-offers the decision on awaiting_player rather than stranding the player", () => {
    const decision = step({ type: "choice", next_choices: [{ id: "c1", text: "Go" }] });
    const state = reduce(playing, {
      type: "batch/received",
      body: batch({ status: "awaiting_player", steps: [decision] }),
    });

    expect(state.deciding).toBe(true);
    expect(state.current?.step_id).toBe(decision.step_id);
  });
});

describe("decisions and pipelined continuation", () => {
  it("immediately advances to continuation steps when buffer is non-empty upon decision submission", () => {
    const decision = step({ step_id: "s14", type: "choice", next_choices: [{ id: "c1", text: "Go" }] });
    const continuation1 = step({ step_id: "s15", narration: "You move forward." });
    const continuation2 = step({ step_id: "s16", narration: "The hall is quiet." });

    // Player reached decision step s14, with s15 and s16 buffered
    const state = reduce(playing, {
      type: "batch/received",
      body: batch({ steps: [decision, continuation1, continuation2] }),
    });

    expect(state.deciding).toBe(true);
    expect(state.current?.step_id).toBe("s14");
    expect(state.buffer.map((s) => s.step_id)).toEqual(["s15", "s16"]);

    // Player submits decision
    const submittedState = reduce(state, { type: "decision/submitted" });

    // Next step (s15) should immediately become current and deciding becomes false
    expect(submittedState.deciding).toBe(false);
    expect(submittedState.current?.step_id).toBe("s15");
    expect(submittedState.buffer.map((s) => s.step_id)).toEqual(["s16"]);
  });

  it("leaves current unchanged and marks deciding false when buffer is empty on submission", () => {
    const decision = step({ step_id: "s14", type: "choice", next_choices: [{ id: "c1", text: "Go" }] });
    const state = reduce(playing, {
      type: "batch/received",
      body: batch({ steps: [decision] }),
    });

    expect(state.deciding).toBe(true);
    expect(state.buffer).toHaveLength(0);

    const submittedState = reduce(state, { type: "decision/submitted" });
    expect(submittedState.deciding).toBe(false);
    expect(submittedState.current?.step_id).toBe("s14");
    expect(submittedState.buffer).toHaveLength(0);
  });

  it("appends prefetched batch into buffer and deduplicates", () => {
    const cur = step({ step_id: "s1" });
    const buf = step({ step_id: "s2" });
    const fresh1 = step({ step_id: "s2" }); // duplicate
    const fresh2 = step({ step_id: "s3" }); // new

    const state: State = { ...playing, current: cur, buffer: [buf] };
    const nextState = reduce(state, {
      type: "batch/append",
      body: batch({ steps: [fresh1, fresh2] }),
    });

    expect(nextState.current?.step_id).toBe("s1");
    expect(nextState.buffer.map((s) => s.step_id)).toEqual(["s2", "s3"]);
  });
});

describe("pending is never a spinner", () => {
  it("cycles the location's ambient lines without repeating", () => {
    const ambience = ["Wind on the fence.", "A door, somewhere below."];
    let state = playing;
    const seen: string[] = [];

    for (let i = 0; i < 4; i += 1) {
      state = reduce(state, { type: "batch/received", body: batch({ status: "pending", ambience }) });
      seen.push(state.ambient!);
    }

    expect(seen).toEqual([ambience[0], ambience[1], ambience[0], ambience[1]]);
    // Never the same line twice running, which is the only thing that would give it away.
    expect(seen.slice(1).every((line, i) => line !== seen[i])).toBe(true);
  });

  it("stops pretending after the ambient limit", () => {
    let state = playing;
    for (let i = 0; i <= AMBIENT_LIMIT; i += 1) {
      state = reduce(state, {
        type: "batch/received",
        body: batch({ status: "pending", ambience: ["Wind."] }),
      });
    }
    expect(state.ambient).toContain("still catching up");
  });

  it("gives up after too many consecutive pending polls", () => {
    let state = playing;
    for (let i = 0; i < MAX_PENDING_POLLS; i += 1) {
      state = reduce(state, { type: "batch/received", body: batch({ status: "pending" }) });
    }
    expect(state.phase).toBe("offline");
    expect(state.message).toContain("stopped responding while writing");
  });

  it("clears the ambient run as soon as a real beat lands", () => {
    let state = reduce(playing, { type: "batch/received", body: batch({ status: "pending" }) });
    expect(state.ambient).not.toBeNull();

    state = reduce(state, { type: "batch/received", body: batch({ steps: [step()] }) });
    expect(state.ambient).toBeNull();
    expect(state.pendingStreak).toBe(0);
  });
});

describe("failure", () => {
  it("tolerates a couple of transport failures before saying so", () => {
    let state = playing;
    for (let i = 0; i < MAX_OFFLINE_STREAK - 1; i += 1) {
      state = reduce(state, { type: "batch/failed", message: "boom" });
    }
    expect(state.phase).toBe("story");

    state = reduce(state, { type: "batch/failed", message: "boom" });
    expect(state.phase).toBe("offline");
  });

  it("forgives a failure once a beat arrives", () => {
    let state = reduce(playing, { type: "batch/failed", message: "boom" });
    state = reduce(state, { type: "batch/received", body: batch({ steps: [step()] }) });
    expect(state.offlineStreak).toBe(0);
  });
});

describe("the ending", () => {
  it("shows the closing beat once and only once", () => {
    const closing = step({ type: "ending", narration: "The end." });
    let state = reduce(playing, {
      type: "batch/received",
      body: batch({ status: "ended", steps: [closing] }),
    });

    expect(state.phase).toBe("ended");
    expect(state.current?.narration).toBe("The end.");
    expect(state.deciding).toBe(false);

    // A second "ended" must not replay it -- the loop can see the status twice.
    const replayed = reduce(state, {
      type: "batch/received",
      body: batch({ status: "ended", steps: [step({ narration: "Something else." })] }),
    });
    expect(replayed.current?.narration).toBe("The end.");
  });
});

describe("the authored opening", () => {
  it("plays from memory and then hands over to the engine", () => {
    let state = reduce(
      { ...initialState, phase: "story", gameId: "g1" },
      { type: "opening/start", steps: [step({ step_id: "o1" }), step({ step_id: "o2" })] },
    );
    expect(state.source).toBe("opening");
    expect(state.current?.step_id).toBe("o1");

    state = reduce(state, { type: "opening/handoff" });
    expect(state.source).toBe("api");
    expect(state.buffer).toHaveLength(0);
  });
});
