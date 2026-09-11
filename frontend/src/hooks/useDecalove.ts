/**
 * The driver: everything in `decalove_beat` that touches the network.
 *
 * `machine.ts` decides what a result means; this decides when to ask. The split
 * matters because the interesting rules — ambient cycling, the streak counters, the
 * ending guard — are then pure and readable in one place, instead of tangled through
 * effects.
 */

import { useCallback, useEffect, useReducer, useRef } from "react";
import { api } from "../api/client";
import { BATCH_LIMIT, PREFETCH_THRESHOLD, WAIT_MS } from "../config";
import type { StepsBatchOut } from "../api/types";
import {
  OPENING_AFTER_CHOICE,
  OPENING_BEFORE_CHOICE,
  OPENING_CHOICE_STEP,
  OPENING_LAST_STEP,
} from "../game/opening";
import { initialState, reduce, type Profile, type State } from "../game/machine";

export interface Decalove {
  state: State;
  advance: () => void;
  startNewGame: () => void;
  submitSetup: (profile: Profile) => void;
  finishIntro: () => void;
  chooseOption: (choiceId: string) => void;
  submitFreeText: (text: string) => void;
  openFreeText: (open: boolean) => void;
  backToMenu: () => void;
}

export function useDecalove(): Decalove {
  const [state, dispatch] = useReducer(reduce, initialState);

  // Read inside async callbacks, which would otherwise close over a stale snapshot.
  // Written after commit rather than during render; every reader is an event handler
  // or an async continuation, so all of them run after this has flushed.
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  });

  // Guards a fetch already in flight: without it, a player clicking through an empty
  // buffer fires a second long poll behind the first and the batch arrives twice.
  const inFlight = useRef(false);

  // Guards a prefetch already in flight. Separate from inFlight so a prefetch and a
  // primary fetch do not block each other.
  const prefetching = useRef(false);

  // The opening's server-side calls are ordered but not awaited by the UI -- the whole
  // point is that the rooftop scene plays while the engine writes. They still have to
  // reach the server in order, though: skip(19) landing before skip(14) and the action
  // would submit the player's choice against the wrong cursor. Chaining them here keeps
  // the ordering without making the player wait for any of it.
  const openingSync = useRef<Promise<unknown>>(Promise.resolve());

  const afterOpeningSync = useCallback((work: () => Promise<unknown>) => {
    openingSync.current = openingSync.current.then(work, work);
    return openingSync.current;
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const world = await api.world();
      if (cancelled) return;
      if (!world) {
        dispatch({
          type: "boot/failed",
          message: api.lastError ?? "No response from the story engine.",
        });
        return;
      }
      dispatch({ type: "world/loaded", world });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchNext = useCallback(async () => {
    const { gameId } = latest.current;
    if (!gameId || inFlight.current) return;
    inFlight.current = true;
    dispatch({ type: "busy", busy: true });

    try {
      let body: StepsBatchOut | null = await api.stepsBatch(gameId, BATCH_LIMIT, WAIT_MS);

      if (!body) {
        // The single-step endpoint, kept as the fallback the Ren'Py client keeps too.
        const single = await api.nextStep(gameId, WAIT_MS);
        if (single) {
          body = {
            status: single.status,
            steps: single.step ? [single.step] : [],
            queue_depth: single.queue_depth,
            retry_after_ms: single.retry_after_ms,
            ambience: single.ambience,
          };
        }
      }

      if (!body) {
        // Two signals, no status-code parsing: if /worlds still answers, the server is
        // up and it is the save that is gone. Telling someone to restart a healthy
        // server would send them chasing the wrong problem.
        const alive = await api.world();
        if (alive) {
          const stillThere = await api.gameState(gameId);
          if (!stillThere) {
            dispatch({ type: "expired" });
            return;
          }
        }
        dispatch({
          type: "batch/failed",
          message: api.lastError ?? "No response from the server.",
        });
        return;
      }

      dispatch({ type: "batch/received", body });
    } finally {
      inFlight.current = false;
    }
  }, []);

  /**
   * Background prefetch: grab whatever is ready on the server (wait_ms=0) and append
   * it to the buffer silently. If nothing is ready yet, just return — the player still
   * has steps to read and will not notice. This is what makes clicking through 20+
   * steps feel instant instead of pausing for 4 seconds at every batch boundary.
   */
  const prefetchNext = useCallback(async () => {
    const { gameId, source } = latest.current;
    if (!gameId || source === "opening" || prefetching.current || inFlight.current) return;
    prefetching.current = true;

    try {
      // wait_ms=0: grab whatever is queued right now, don't hold the connection.
      const body = await api.stepsBatch(gameId, BATCH_LIMIT, 0);
      if (body && body.steps.length > 0) {
        dispatch({ type: "batch/append", body });
      }
    } finally {
      prefetching.current = false;
    }
  }, []);

  const advance = useCallback(() => {
    const current = latest.current;
    if (current.deciding || current.typing || current.busy) return;

    if (current.buffer.length > 0) {
      dispatch({ type: "advance" });

      // When the buffer is running low, prefetch the next batch in the background
      // so it is already loaded before the player exhausts the current one.
      if (current.buffer.length <= PREFETCH_THRESHOLD) {
        void prefetchNext();
      }
      return;
    }

    // The authored opening has run out. Fast-forward the server cursor through the
    // beats the client played locally, then hand playback to the engine.
    if (current.source === "opening") {
      dispatch({ type: "opening/handoff" });
      void afterOpeningSync(async () => {
        if (current.gameId) await api.skipToStep(current.gameId, OPENING_LAST_STEP);
        return fetchNext();
      });
      return;
    }

    void fetchNext();
  }, [afterOpeningSync, fetchNext, prefetchNext]);

  const startNewGame = useCallback(() => dispatch({ type: "menu/new" }), []);

  const submitSetup = useCallback((profile: Profile) => {
    dispatch({ type: "setup/submit", profile });
    void (async () => {
      const game = await api.newGame({
        player_name: profile.name || "You",
        pronouns: profile.pronouns,
        tone: profile.tone,
      });
      if (!game) {
        dispatch({
          type: "offline",
          message: api.lastError ?? "Could not start a new game.",
        });
        return;
      }
      dispatch({ type: "game/started", gameId: game.game_id });
    })();
  }, []);

  const finishIntro = useCallback(() => {
    dispatch({ type: "intro/done" });
    dispatch({ type: "opening/start", steps: OPENING_BEFORE_CHOICE });
  }, []);

  const answerOpeningChoice = useCallback(
    (text: string) => {
      const { gameId } = latest.current;
      // Both calls, in this order: the skip commits the beats the client played on its
      // own, and the action is what sets the engine writing while the rooftop scene
      // plays. Getting the order wrong would submit against the wrong cursor.
      void afterOpeningSync(async () => {
        if (!gameId) return;
        await api.skipToStep(gameId, OPENING_CHOICE_STEP);
        await api.submitAction(gameId, text);
      });
      dispatch({ type: "decision/submitted" });
      dispatch({ type: "opening/start", steps: OPENING_AFTER_CHOICE });
    },
    [afterOpeningSync],
  );

  const chooseOption = useCallback(
    (choiceId: string) => {
      const { current, buffer, gameId, source } = latest.current;
      if (!current) return;

      if (source === "opening") {
        const picked = current.next_choices.find((c) => c.id === choiceId);
        answerOpeningChoice(picked?.text ?? choiceId);
        return;
      }

      if (!gameId) return;
      const stepId = current.step_id;
      const hadBuffer = buffer.length > 0;
      dispatch({ type: "decision/submitted" });
      void (async () => {
        const accepted = await api.submitChoice(gameId, stepId, choiceId);
        if (!accepted) {
          dispatch({
            type: "batch/failed",
            message: api.lastError ?? "Could not send that choice.",
          });
          return;
        }
        // If the buffer was already empty, we must fetch the next batch now.
        // Otherwise, the player continues reading the remaining buffered steps
        // (steps 15-19) seamlessly while Celery generates in the background.
        if (!hadBuffer) {
          void fetchNext();
        } else {
          void prefetchNext();
        }
      })();
    },
    [answerOpeningChoice, fetchNext, prefetchNext],
  );

  const submitFreeText = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      // An empty answer re-offers the same decision point: the server still has it as
      // the head of the ledger, so nothing has been lost.
      if (!trimmed) {
        dispatch({ type: "decision/typing", open: false });
        return;
      }

      const { current, buffer, gameId, source } = latest.current;
      if (source === "opening") {
        answerOpeningChoice(trimmed);
        return;
      }
      if (!gameId) return;

      const stepId = current?.step_id;
      const hadBuffer = buffer.length > 0;
      dispatch({ type: "decision/submitted" });
      void (async () => {
        const accepted = await api.submitAction(gameId, trimmed, stepId);
        if (!accepted) {
          dispatch({
            type: "batch/failed",
            message: api.lastError ?? "Could not send that.",
          });
          return;
        }
        if (!hadBuffer) {
          void fetchNext();
        } else {
          void prefetchNext();
        }
      })();
    },
    [answerOpeningChoice, fetchNext, prefetchNext],
  );

  const openFreeText = useCallback(
    (open: boolean) => dispatch({ type: "decision/typing", open }),
    [],
  );

  const backToMenu = useCallback(() => dispatch({ type: "menu/new" }), []);

  return {
    state,
    advance,
    startNewGame,
    submitSetup,
    finishIntro,
    chooseOption,
    submitFreeText,
    openFreeText,
    backToMenu,
  };
}
