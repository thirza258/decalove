/**
 * HTTP client for the Decalove API — the port of `game/decalove/10_api.rpy`.
 *
 * Like the Ren'Py original it never throws: a failed call returns `null` and records
 * `lastError`, because the playback loop distinguishes "the server said nothing" from
 * "the server said pending" and both have to be ordinary control flow.
 */

import { API_BASE, API_PREFIX, HTTP_MARGIN_MS } from "../config";
import type {
  AcceptedOut,
  GameStateOut,
  NewGameRequest,
  NextStepOut,
  StepsBatchOut,
  WorldOut,
} from "./types";

export class DecaloveAPI {
  lastError: string | null = null;

  private readonly base: string;
  private readonly prefix: string;

  constructor(base: string = API_BASE, prefix: string = API_PREFIX) {
    this.base = base;
    this.prefix = prefix;
  }

  url(path: string): string {
    return this.base + this.prefix + path;
  }

  /**
   * Resolve an AssetRef URL against the API.
   *
   * The API returns an absolute URL when the object store can hand one out directly,
   * and a path relative to the API root when it has to proxy the bytes itself. Both
   * shapes arrive on the same field, so both have to be handled here — the Ren'Py
   * client makes the same branch in `fetch_bytes`.
   *
   * Unlike Ren'Py there is no byte-fetching and no image cache: this is an <img src>,
   * and the browser's HTTP cache is the cache.
   */
  assetUrl(url: string | null | undefined): string | null {
    if (!url) return null;
    return url.startsWith("http") ? url : this.base + url;
  }

  private async call<T>(
    path: string,
    {
      method,
      payload,
      params,
      waitMs = 0,
    }: {
      method?: string;
      payload?: unknown;
      params?: Record<string, string | number>;
      waitMs?: number;
    } = {},
  ): Promise<T | null> {
    // More than the server was asked to hold for, always. A tighter budget turns a
    // slow-but-successful long poll into an abort the loop reads as an outage.
    const timeout = waitMs + HTTP_MARGIN_MS;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    let target = this.url(path);
    if (params) {
      target += "?" + new URLSearchParams(
        Object.entries(params).map(([k, v]) => [k, String(v)]),
      );
    }

    try {
      const response = await fetch(target, {
        method: method ?? "GET",
        signal: controller.signal,
        headers: payload !== undefined ? { "content-type": "application/json" } : undefined,
        body: payload !== undefined ? JSON.stringify(payload) : undefined,
      });
      if (!response.ok) {
        this.lastError = `${response.status} ${response.statusText}`;
        return null;
      }
      this.lastError = null;
      return response.status === 204 ? (null as T) : ((await response.json()) as T);
    } catch (error) {
      this.lastError =
        error instanceof DOMException && error.name === "AbortError"
          ? `no response within ${(timeout / 1000).toFixed(0)}s`
          : String(error instanceof Error ? error.message : error);
      return null;
    } finally {
      clearTimeout(timer);
    }
  }

  world() {
    return this.call<WorldOut>("/worlds");
  }

  newGame(request: NewGameRequest) {
    return this.call<GameStateOut>("/games", { method: "POST", payload: request });
  }

  gameState(gameId: string) {
    return this.call<GameStateOut>(`/games/${gameId}`);
  }

  /**
   * A whole batch at once, so the beats after the first play with no network at all.
   * This is what makes clicking feel instant.
   */
  stepsBatch(gameId: string, limit: number, waitMs: number) {
    return this.call<StepsBatchOut>(`/games/${gameId}/steps/batch`, {
      params: { limit, wait_ms: waitMs },
      waitMs,
    });
  }

  /** The single-step endpoint, kept as the fallback the Ren'Py client also keeps. */
  nextStep(gameId: string, waitMs: number) {
    return this.call<NextStepOut>(`/games/${gameId}/steps/next`, {
      params: { wait_ms: waitMs },
      waitMs,
    });
  }

  submitChoice(gameId: string, stepId: string, choiceId: string) {
    return this.call<AcceptedOut>(`/games/${gameId}/choices`, {
      method: "POST",
      payload: { step_id: stepId, choice_id: choiceId },
    });
  }

  submitAction(gameId: string, input: string) {
    return this.call<AcceptedOut>(`/games/${gameId}/actions`, {
      method: "POST",
      payload: { input },
    });
  }

  /** Fast-forward the server cursor after the client has played the opening locally. */
  skipToStep(gameId: string, untilStep: number) {
    return this.call<GameStateOut>(`/games/${gameId}/skip`, {
      method: "POST",
      payload: { until_step: untilStep },
    });
  }
}

export const api = new DecaloveAPI();
