// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { StepsBatchOut, StoryStep } from "../api/types";
import { useDecalove } from "./useDecalove";

vi.mock("../api/client", () => ({ api: {
  world: vi.fn(), newGame: vi.fn(), skipToStep: vi.fn(), stepsBatch: vi.fn(), gameState: vi.fn(),
  submitChoice: vi.fn(), submitAction: vi.fn(), retryGeneration: vi.fn(), lastStatus: null,
} }));
vi.mock("../game/opening", () => ({
  OPENING_CHOICE_STEP: 14, OPENING_LAST_STEP: 19,
  OPENING_BEFORE_CHOICE: [{ step_id: "opening-choice", index: 14, type: "choice", next_choices: [{ id: "a", text: "Hi Aiko" }] }],
  OPENING_AFTER_CHOICE: [{ step_id: "opening-tail", index: 19, type: "narration", narration: "The bell rings.", next_choices: [] }],
}));
const beat = (index: number, type: StoryStep["type"] = "narration"): StoryStep => ({
  index, step_id: `step_${index}`, type, batch_id: "batch", location: "classroom",
  characters: [], narration: "The story continues.", next_choices: [{ id: "a", text: "Talk" }],
});
const batch = (status: StepsBatchOut["status"], steps: StoryStep[] = []): StepsBatchOut => ({
  status, steps, queue_depth: 0, retry_after_ms: 700, ambience: ["The moment holds."],
});

beforeEach(() => {
  vi.useFakeTimers();
  vi.resetAllMocks();
  vi.mocked(api.world).mockResolvedValue({ web_mode: true } as never);
  vi.mocked(api.newGame).mockResolvedValue({ game_id: "g1" } as never);
  vi.mocked(api.skipToStep).mockResolvedValue({ game_id: "g1" } as never);
  vi.mocked(api.submitAction).mockResolvedValue({ game_id: "g1", batch_id: "b1", status: "queued" });
  vi.mocked(api.submitChoice).mockResolvedValue({ game_id: "g1", batch_id: "b2", status: "queued" });
  vi.mocked(api.stepsBatch).mockResolvedValue(batch("pending"));
  vi.mocked(api.retryGeneration).mockResolvedValue({ game_id: "g1", batch_id: "retry", status: "queued" });
  vi.mocked(api.gameState).mockResolvedValue(null);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

async function opening() {
  const hook = renderHook(() => useDecalove());
  await act(async () => {});
  act(() => hook.result.current.startNewGame());
  await act(async () => hook.result.current.submitSetup({ name: "Kai", pronouns: "they/them", tone: "warm" }));
  act(() => hook.result.current.finishIntro());
  return hook;
}
async function handoff() {
  const hook = await opening();
  await act(async () => hook.result.current.chooseOption("a"));
  await act(async () => hook.result.current.advance());
  expect(hook.result.current.state.source).toBe("api");
  return hook;
}
async function poll() { await act(async () => { await vi.advanceTimersByTimeAsync(750); }); }

describe("background web story playback", () => {
  it("polls pending generation and presents the result without extra clicks", async () => {
    vi.mocked(api.stepsBatch).mockResolvedValueOnce(batch("pending")).mockResolvedValueOnce(batch("ready", [beat(20), beat(21, "choice")]));
    const hook = await handoff();
    await poll();
    expect(hook.result.current.state.waiting).toBe(true);
    await poll();
    expect(hook.result.current.state.current?.index).toBe(20);
    expect(hook.result.current.state.waiting).toBe(false);
    expect(api.stepsBatch).toHaveBeenCalledTimes(2);
    expect(api.stepsBatch).toHaveBeenLastCalledWith("g1", 20, 4000, 19);
  });

  it("re-reads the engine's relationship values while the player is deciding", async () => {
    vi.mocked(api.stepsBatch).mockResolvedValueOnce(batch("ready", [beat(20, "choice")]));
    vi.mocked(api.gameState).mockResolvedValue({ game_id: "g1", characters: {
      aiko: { id: "aiko", name: "Aiko", relationship: { affection: 47 }, current_emotion: "composed", met: true },
    } } as never);
    const hook = await handoff();
    await poll();

    expect(hook.result.current.state.deciding).toBe(true);
    await act(async () => {});
    // The beat's own deltas move the numbers; this is the correction behind them.
    expect(hook.result.current.state.standing.aiko.relationship.affection).toBe(47);
    expect(api.gameState).toHaveBeenCalledWith("g1");
  });

  it("keeps the story in place on AI exhaustion and retries the same game", async () => {
    vi.mocked(api.stepsBatch).mockResolvedValueOnce({ ...batch("failed"), error: "All AI attempts failed" });
    const hook = await handoff();
    await poll();
    expect(hook.result.current.state.phase).toBe("story");
    expect(hook.result.current.state.error?.kind).toBe("generation");
    expect(hook.result.current.state.current?.step_id).toBe("opening-tail");
    vi.mocked(api.stepsBatch).mockResolvedValue(batch("ready", [beat(20)]));
    await act(async () => hook.result.current.retry());
    await poll();
    expect(api.retryGeneration).toHaveBeenCalledWith("g1");
    expect(api.newGame).toHaveBeenCalledTimes(1);
    expect(hook.result.current.state.current?.index).toBe(20);
    expect(hook.result.current.state.error).toBeNull();
  });

  it("does not lose the opening choice on failed submission and keeps its request ID", async () => {
    vi.mocked(api.submitAction).mockResolvedValueOnce(null);
    const hook = await opening();
    await act(async () => hook.result.current.chooseOption("a"));
    expect(hook.result.current.state.deciding).toBe(true);
    expect(hook.result.current.state.current?.step_id).toBe("opening-choice");
    expect(hook.result.current.state.error?.kind).toBe("submission");
    const firstRequest = vi.mocked(api.submitAction).mock.calls[0];
    await act(async () => hook.result.current.retry());
    expect(vi.mocked(api.submitAction).mock.calls[1]).toEqual(firstRequest);
    expect(hook.result.current.state.current?.step_id).toBe("opening-tail");
  });

  it("ignores rapid double choice submissions", async () => {
    const hook = await opening();
    await act(async () => {
      hook.result.current.chooseOption("a");
      hook.result.current.chooseOption("a");
    });
    expect(api.submitAction).toHaveBeenCalledTimes(1);
  });

  it("ignores responses from an abandoned game", async () => {
    let resolve!: (body: StepsBatchOut) => void;
    vi.mocked(api.stepsBatch).mockReturnValue(new Promise((done) => { resolve = done; }));
    const hook = await handoff();
    await poll();
    act(() => hook.result.current.startNewGame());
    await act(async () => resolve(batch("ready", [beat(20)])));
    expect(hook.result.current.state.phase).toBe("setup");
    expect(hook.result.current.state.current).toBeNull();
  });

  it("uses the in-flight prefetch when the player reaches an empty buffer", async () => {
    vi.mocked(api.stepsBatch).mockResolvedValueOnce(batch("ready", [beat(20, "choice"), beat(21), beat(22)]));
    const hook = await handoff();
    await poll();
    await act(async () => hook.result.current.chooseOption("a"));
    let resolve!: (body: StepsBatchOut) => void;
    vi.mocked(api.stepsBatch).mockReturnValue(new Promise((done) => { resolve = done; }));
    await poll(); // prefetch starts while step 21 is read
    act(() => hook.result.current.advance()); // step 22
    act(() => hook.result.current.advance()); // wait for the same prefetch
    expect(api.stepsBatch).toHaveBeenCalledTimes(2);
    await act(async () => resolve(batch("ready", [beat(23), beat(24, "choice")])));
    expect(hook.result.current.state.current?.index).toBe(23);
    expect(api.stepsBatch).toHaveBeenCalledTimes(2);
  });

  it("opens a connection error after bounded transport retries, preserving the save", async () => {
    vi.mocked(api.stepsBatch).mockResolvedValue(null);
    const hook = await handoff();
    await poll(); await poll(); await poll();
    expect(hook.result.current.state.error?.kind).toBe("connection");
    expect(hook.result.current.state.gameId).toBe("g1");
    expect(hook.result.current.state.phase).toBe("story");
  });
});


describe("custom player input", () => {
  it("submits the player's own opening action without selecting a preset", async () => {
    const hook = await opening();
    const text = "I ask Aiko why the library closes early on Fridays.";
    await act(async () => hook.result.current.submitFreeText(`  ${text}  `));
    expect(api.submitAction).toHaveBeenCalledWith("g1", text, undefined, expect.any(String));
    expect(api.submitChoice).not.toHaveBeenCalled();
    expect(hook.result.current.state.current?.step_id).toBe("opening-tail");
  });

  it("sends expanded input against the current generated decision and continues polling", async () => {
    vi.mocked(api.stepsBatch).mockResolvedValueOnce(batch("ready", [beat(20, "choice")]));
    const hook = await handoff();
    await poll();
    vi.mocked(api.submitAction).mockClear();
    act(() => hook.result.current.openFreeText(true));
    const text = "I apologise to Aiko, then ask if she still wants help with the festival.";
    await act(async () => hook.result.current.submitFreeText(text));
    expect(api.submitAction).toHaveBeenCalledWith("g1", text, "step_20", expect.any(String));
    expect(api.submitChoice).not.toHaveBeenCalled();
    expect(hook.result.current.state.typing).toBe(false);
    expect(hook.result.current.state.waiting).toBe(true);
    vi.mocked(api.stepsBatch).mockResolvedValueOnce(batch("ready", [beat(21)]));
    await poll();
    expect(hook.result.current.state.current?.index).toBe(21);
  });

  it("retries exactly the same custom response after a failed POST", async () => {
    vi.mocked(api.stepsBatch).mockResolvedValueOnce(batch("ready", [beat(20, "choice")]));
    const hook = await handoff();
    await poll();
    vi.mocked(api.submitAction).mockClear().mockResolvedValueOnce(null);
    const text = "I ask her about the letter she mentioned.";
    await act(async () => hook.result.current.submitFreeText(text));
    expect(hook.result.current.state.error?.kind).toBe("submission");
    expect(hook.result.current.state.deciding).toBe(true);
    const request = vi.mocked(api.submitAction).mock.calls[0];
    await act(async () => hook.result.current.retry());
    expect(vi.mocked(api.submitAction).mock.calls[1]).toEqual(request);
  });

  it("leaves the decision unanswered when custom input is empty", async () => {
    const hook = await opening();
    act(() => hook.result.current.openFreeText(true));
    act(() => hook.result.current.submitFreeText("   "));
    expect(api.submitAction).not.toHaveBeenCalled();
    expect(hook.result.current.state.deciding).toBe(true);
  });
});
