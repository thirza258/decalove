/** Network driver for buffered playback and recoverable background generation. */
import { useCallback, useEffect, useReducer, useRef } from "react";
import { api } from "../api/client";
import { BATCH_LIMIT, PREFETCH_THRESHOLD, WAIT_MS } from "../config";
import {
  OPENING_AFTER_CHOICE, OPENING_BEFORE_CHOICE, OPENING_CHOICE_STEP, OPENING_LAST_STEP,
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
  retry: () => void;
}

export function useDecalove(): Decalove {
  const [state, dispatch] = useReducer(reduce, initialState);
  const latest = useRef(state);
  useEffect(() => { latest.current = state; });

  // One delivery request at a time: both endpoints advance the server cursor.
  const fetching = useRef(false);
  const submitting = useRef(false);
  const epoch = useRef(0);
  const retryOperation = useRef<(() => Promise<void>) | null>(null);
  const wantsNext = useRef(false);
  const receivedIndex = useRef(OPENING_LAST_STEP);

  useEffect(() => {
    let cancelled = false;
    void api.world().then((world) => {
      if (cancelled) return;
      dispatch(world ? { type: "world/loaded", world } : {
        type: "boot/failed", message: "Cannot connect to the story service. Please try again shortly.",
      });
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => () => { epoch.current += 1; }, []);

  const showError = useCallback((kind: "generation" | "connection" | "submission", message: string) => {
    dispatch(latest.current.world?.web_mode
      ? { type: "error", kind, message }
      : { type: "offline", message });
  }, []);

  const fetchNext = useCallback(async (background = false) => {
    const { gameId, source } = latest.current;
    if (!gameId || source === "opening" || submitting.current) return;
    if (!background) {
      wantsNext.current = true;
      dispatch({ type: "playback/wait" });
    }
    if (fetching.current) return;
    fetching.current = true;
    const token = epoch.current;
    if (!background) dispatch({ type: "busy", busy: true });
    try {
      const body = await api.stepsBatch(gameId, BATCH_LIMIT, background ? 0 : WAIT_MS, receivedIndex.current);
      if (token !== epoch.current) return;
      if (!body) {
        if (api.lastStatus === 404) {
          dispatch({ type: "expired" });
        } else if (wantsNext.current) {
          dispatch({ type: "batch/failed", message: "The connection was interrupted. Your story is still here. Please try again." });
        }
        return;
      }
      if (body.status === "ready") {
        for (const step of body.steps) receivedIndex.current = Math.max(receivedIndex.current, step.index);
      }
      const foreground = wantsNext.current;
      if (foreground && body.status !== "pending") wantsNext.current = false;
      dispatch({ type: foreground ? "batch/received" : "batch/append", body });
    } finally {
      if (token === epoch.current) fetching.current = false;
    }
  }, []);

  // Continue polling without clicks. Prefetch only after the current run's decision
  // has been answered; fetching before then could skip the player's turn.
  useEffect(() => {
    if (state.phase !== "story" || state.source !== "api" || state.error || state.busy || state.deciding || state.typing) return;
    const waiting = state.waiting;
    const canPrefetch = state.buffer.length > 0 && state.buffer.length <= PREFETCH_THRESHOLD
      && !state.buffer.some((step) => step.type === "choice" || step.type === "prompt" || step.type === "ending");
    if (!waiting && !canPrefetch) return;
    const timer = setInterval(() => { void fetchNext(!waiting); }, state.retryAfterMs);
    return () => clearInterval(timer);
  }, [state, fetchNext]);

  // Re-read the engine's relationship values once per turn, while the player is
  // reading the question rather than waiting on anything. Beats carry their own
  // deltas, so this is a correction, not the source: it costs one idle request and
  // means a missed beat cannot leave the numbers on screen quietly wrong.
  const { gameId, deciding, phase, source } = state;
  useEffect(() => {
    if (!gameId || !deciding || phase !== "story" || source !== "api") return;
    const token = epoch.current;
    let live = true;
    void api.gameState(gameId).then((synced) => {
      if (live && token === epoch.current && synced?.characters) {
        dispatch({ type: "state/synced", characters: synced.characters });
      }
    });
    return () => { live = false; };
  }, [gameId, deciding, phase, source]);

  const runSubmission = useCallback(async (operation: () => Promise<void>) => {
    if (submitting.current) return;
    submitting.current = true;
    const token = epoch.current;
    retryOperation.current = operation;
    dispatch({ type: "busy", busy: true });
    try { await operation(); }
    finally {
      if (token === epoch.current) {
        submitting.current = false;
        dispatch({ type: "busy", busy: false });
      }
    }
  }, []);

  const handoff = useCallback(() => {
    const { gameId } = latest.current;
    if (!gameId) return;
    const token = epoch.current;
    void runSubmission(async () => {
      const synced = await api.skipToStep(gameId, OPENING_LAST_STEP);
      if (token !== epoch.current) return;
      if (!synced) {
        showError("submission", "Could not reconnect to your story. Please try again.");
        return;
      }
      retryOperation.current = null;
      // The authored opening ran locally; the engine's own numbers arrive with the sync.
      if (synced.characters) dispatch({ type: "state/synced", characters: synced.characters });
      dispatch({ type: "opening/handoff" });
    });
  }, [runSubmission, showError]);

  const advance = useCallback(() => {
    const current = latest.current;
    if (current.phase !== "story" || current.deciding || current.typing || current.busy || current.error || submitting.current) return;
    if (current.buffer.length > 0) dispatch({ type: "advance" });
    else if (current.source === "opening") handoff();
    else void fetchNext();
  }, [fetchNext, handoff]);

  const startNewGame = useCallback(() => {
    epoch.current += 1;
    fetching.current = false;
    submitting.current = false;
    wantsNext.current = false;
    receivedIndex.current = OPENING_LAST_STEP;
    retryOperation.current = null;
    dispatch({ type: "menu/new" });
  }, []);

  const submitSetup = useCallback((profile: Profile) => {
    if (submitting.current) return;
    dispatch({ type: "setup/submit", profile });
    const token = epoch.current;
    void runSubmission(async () => {
      const game = await api.newGame({ player_name: profile.name || "You", pronouns: profile.pronouns, tone: profile.tone });
      if (token !== epoch.current) return;
      if (!game) {
        dispatch({ type: "offline", message: "Could not start a new story. Please try again." });
        return;
      }
      retryOperation.current = null;
      dispatch({ type: "game/started", gameId: game.game_id });
      if (game.characters) dispatch({ type: "state/synced", characters: game.characters });
    });
  }, [runSubmission]);

  const finishIntro = useCallback(() => {
    dispatch({ type: "intro/done" });
    dispatch({ type: "opening/start", steps: OPENING_BEFORE_CHOICE });
  }, []);

  const answer = useCallback((kind: "choice" | "text", value: string) => {
    const { current, gameId, source, deciding, error } = latest.current;
    if (!current || !gameId || !deciding || error || submitting.current) return;
    const token = epoch.current;
    const requestId = crypto.randomUUID();
    void runSubmission(async () => {
      if (source === "opening") {
        const synced = await api.skipToStep(gameId, OPENING_CHOICE_STEP);
        if (token !== epoch.current) return;
        if (!synced) {
          showError("submission", "Could not send your choice. Please try again.");
          return;
        }
        if (synced.characters) dispatch({ type: "state/synced", characters: synced.characters });
      }
      const text = kind === "choice" ? current.next_choices.find((choice) => choice.id === value)?.text ?? value : value;
      const accepted = kind === "choice" && source !== "opening"
        ? await api.submitChoice(gameId, current.step_id, value, requestId)
        : await api.submitAction(gameId, text, source === "opening" ? undefined : current.step_id, requestId);
      if (token !== epoch.current) return;
      if (!accepted?.batch_id) {
        showError("submission", "Could not send your choice. Please try again.");
        return;
      }
      retryOperation.current = null;
      dispatch({ type: "decision/submitted" });
      if (source === "opening") dispatch({ type: "opening/start", steps: OPENING_AFTER_CHOICE });
    });
  }, [runSubmission, showError]);

  const retry = useCallback(() => {
    const { error, gameId } = latest.current;
    if (!error || submitting.current || fetching.current) return;
    dispatch({ type: "error/retry" });
    if (error.kind === "submission" && retryOperation.current) {
      void runSubmission(retryOperation.current);
      return;
    }
    if (error.kind === "generation" && gameId) {
      const token = epoch.current;
      void runSubmission(async () => {
        const accepted = await api.retryGeneration(gameId);
        if (token !== epoch.current) return;
        if (!accepted?.batch_id) {
          showError("generation", "The story service is still unavailable. Please try again shortly.");
          return;
        }
        dispatch({ type: "playback/wait" });
      });
      return;
    }
    void fetchNext();
  }, [fetchNext, runSubmission, showError]);

  return {
    state, advance, startNewGame, submitSetup, finishIntro, retry,
    chooseOption: (choiceId) => answer("choice", choiceId),
    submitFreeText: (text) => {
      if (text.trim()) answer("text", text.trim());
      else dispatch({ type: "decision/typing", open: false });
    },
    openFreeText: (open) => dispatch({ type: "decision/typing", open }),
    backToMenu: startNewGame,
  };
}
