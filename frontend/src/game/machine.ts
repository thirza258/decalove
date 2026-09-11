/**
 * The playback state machine — the port of `decalove_play` in
 * `game/decalove/50_player.rpy`.
 *
 * The Ren'Py original is a `while True` loop whose blocking calls (`renpy.say`,
 * `renpy.input`, `renpy.call_screen`) *are* the waiting. A browser has no equivalent,
 * so the loop is turned inside out: the player's click is the iteration, and this
 * reducer is one step of it. Every rule the loop encoded survives as a transition
 * here, and the async work (fetching) lives outside in the hook that drives it.
 */

import { AMBIENT_LIMIT, MAX_OFFLINE_STREAK, MAX_PENDING_POLLS } from "../config";
import type { StepsBatchOut, StoryStep, WorldOut } from "../api/types";

export type Phase =
  | "boot"
  | "menu"
  | "setup"
  | "intro"
  | "story"
  | "ended"
  | "offline"
  | "expired";

export interface Profile {
  name: string;
  pronouns: string;
  tone: string;
}

export interface State {
  phase: Phase;
  world: WorldOut | null;
  gameId: string | null;
  profile: Profile;

  /** Where the current beat came from. The authored opening needs no network. */
  source: "opening" | "api";
  /** Steps already delivered, played from memory with zero network latency. */
  buffer: StoryStep[];
  current: StoryStep | null;
  /** True while a blocking step is waiting on the player. */
  deciding: boolean;
  /** True while the free-text box is open. */
  typing: boolean;
  /** A fetch is in flight; the stage stays on the last beat rather than blanking. */
  busy: boolean;

  /** In-world filler shown instead of a spinner (PRD §11). */
  ambient: string | null;
  ambientIndex: number;
  ambientSeen: number;

  pendingStreak: number;
  offlineStreak: number;
  seenEnding: boolean;
  message: string | null;
}

export const initialState: State = {
  phase: "boot",
  world: null,
  gameId: null,
  profile: { name: "You", pronouns: "they/them", tone: "warm" },
  source: "opening",
  buffer: [],
  current: null,
  deciding: false,
  typing: false,
  busy: false,
  ambient: null,
  ambientIndex: -1,
  ambientSeen: 0,
  pendingStreak: 0,
  offlineStreak: 0,
  seenEnding: false,
  message: null,
};

export type Action =
  | { type: "world/loaded"; world: WorldOut }
  | { type: "boot/failed"; message: string }
  | { type: "menu/new" }
  | { type: "setup/submit"; profile: Profile }
  | { type: "game/started"; gameId: string }
  | { type: "intro/done" }
  | { type: "opening/start"; steps: StoryStep[] }
  | { type: "opening/handoff" }
  | { type: "busy"; busy: boolean }
  | { type: "advance" }
  | { type: "batch/received"; body: StepsBatchOut }
  | { type: "batch/append"; body: StepsBatchOut }
  | { type: "batch/failed"; message: string }
  | { type: "decision/typing"; open: boolean }
  | { type: "decision/submitted" }
  | { type: "offline"; message: string }
  | { type: "expired" };

/** Next in-world filler line, never the same one twice in a row. */
function nextAmbient(state: State, ambience: string[]): Pick<State, "ambient" | "ambientIndex" | "ambientSeen"> {
  const seen = state.ambientSeen + 1;
  if (seen > AMBIENT_LIMIT) {
    // The illusion has run out. Saying so beats looking frozen.
    return {
      ambient: "(The story is still catching up. One moment.)",
      ambientIndex: state.ambientIndex,
      ambientSeen: seen,
    };
  }
  if (ambience.length === 0) {
    return { ambient: "The moment holds.", ambientIndex: state.ambientIndex, ambientSeen: seen };
  }
  const index = (state.ambientIndex + 1) % ambience.length;
  return { ambient: ambience[index], ambientIndex: index, ambientSeen: seen };
}

function isBlocking(step: StoryStep | null): boolean {
  return step?.type === "choice" || step?.type === "prompt";
}

/** Show a step: it becomes current, and if it blocks, the player is now deciding. */
function present(state: State, step: StoryStep, rest: StoryStep[]): State {
  return {
    ...state,
    current: step,
    buffer: rest,
    deciding: isBlocking(step),
    typing: false,
    ambient: null,
    ambientSeen: 0,
    busy: false,
  };
}

export function reduce(state: State, action: Action): State {
  switch (action.type) {
    case "world/loaded":
      return { ...state, world: action.world, phase: state.phase === "boot" ? "menu" : state.phase };

    case "boot/failed":
      return { ...state, phase: "offline", message: action.message };

    case "menu/new":
      return { ...initialState, world: state.world, phase: "setup" };

    case "setup/submit":
      return { ...state, profile: action.profile, busy: true };

    case "game/started":
      return { ...state, gameId: action.gameId, phase: "intro", busy: false };

    case "intro/done":
      return { ...state, phase: "story", source: "opening" };

    case "opening/start": {
      const [first, ...rest] = action.steps;
      return present({ ...state, source: "opening" }, first, rest);
    }

    // The opening is done locally; everything after it comes from the engine.
    case "opening/handoff":
      return { ...state, source: "api", buffer: [], deciding: false, typing: false };

    case "busy":
      return { ...state, busy: action.busy };

    case "advance": {
      // A buffered step plays with no network at all. This is the whole reason
      // clicking feels instant, and why the batch endpoint exists.
      if (state.buffer.length > 0) {
        const [next, ...rest] = state.buffer;
        return present(state, next, rest);
      }
      return state; // The hook fetches; the result arrives as batch/received.
    }

    case "batch/received": {
      const body = action.body;
      const settled = { ...state, offlineStreak: 0, busy: false };

      if (body.status === "ready") {
        const steps = body.steps;
        if (steps.length === 0) return { ...settled, pendingStreak: 0 };
        const [first, ...rest] = steps;
        return present({ ...settled, pendingStreak: 0 }, first, rest);
      }

      if (body.status === "awaiting_player") {
        // Reached when a generation failed: the server is offering the same decision
        // point again rather than stranding the player (PRD §26).
        const step = body.steps[0];
        if (!step) return { ...settled, pendingStreak: 0 };
        return present({ ...settled, pendingStreak: 0 }, step, []);
      }

      if (body.status === "pending") {
        const streak = state.pendingStreak + 1;
        if (streak >= MAX_PENDING_POLLS) {
          return {
            ...settled,
            phase: "offline",
            message: "The story engine stopped responding while writing.",
          };
        }
        return { ...settled, pendingStreak: streak, ...nextAmbient(state, body.ambience) };
      }

      // ended
      const step = body.steps[0];
      if (step && !state.seenEnding) {
        return {
          ...present(settled, step, []),
          phase: "ended",
          seenEnding: true,
          deciding: false,
        };
      }
      return { ...settled, phase: "ended", seenEnding: true, deciding: false };
    }

    // Prefetched batch: merge into the existing buffer without interrupting playback.
    // If the buffer was already empty and no current step is shown, present immediately.
    case "batch/append": {
      const body = action.body;
      if (body.status !== "ready" || body.steps.length === 0) return state;

      // De-duplicate: skip steps already in the buffer (by step_id).
      const seen = new Set(state.buffer.map((s) => s.step_id));
      if (state.current) seen.add(state.current.step_id);
      const fresh = body.steps.filter((s) => !seen.has(s.step_id));
      if (fresh.length === 0) return state;

      // If the player is waiting on an empty buffer, present the first fresh step.
      if (!state.current && state.buffer.length === 0 && !state.deciding) {
        const [first, ...rest] = fresh;
        return present(state, first, rest);
      }

      return { ...state, buffer: [...state.buffer, ...fresh] };
    }

    case "batch/failed": {
      const streak = state.offlineStreak + 1;
      if (streak >= MAX_OFFLINE_STREAK) {
        return { ...state, busy: false, phase: "offline", message: action.message };
      }
      return { ...state, busy: false, offlineStreak: streak };
    }

    case "decision/typing":
      return { ...state, typing: action.open };

    // The player answered. If steps remain in the buffer (e.g. continuation beats
    // in a 20-step batch), immediately present the next step so the story continues
    // seamlessly while Celery / background worker generates the next batch.
    case "decision/submitted": {
      const base = { ...state, deciding: false, typing: false, pendingStreak: 0 };
      if (base.buffer.length > 0) {
        const [next, ...rest] = base.buffer;
        return present(base, next, rest);
      }
      return base;
    }

    case "offline":
      return { ...state, busy: false, phase: "offline", message: action.message };

    case "expired":
      return { ...state, busy: false, phase: "expired" };

    default:
      return state;
  }
}
