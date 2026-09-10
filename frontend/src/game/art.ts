/**
 * Placeholder art — the port of `game/decalove/20_art.rpy`.
 *
 * PRD §26: when image generation fails or is switched off, the game must still look
 * like a game. Every fallback is built from the palettes the API serves with the
 * world, so a location or character looks the same every time it appears — which is
 * what makes them read as art direction rather than as an error state.
 *
 * Static art is checked first, exactly as the Ren'Py client checks `renpy.loadable`.
 * There is no synchronous equivalent in a browser, so a file is probed once and the
 * answer cached; until it resolves the gradient stands in, and a hit swaps in on the
 * next render. A miss is not an error and is never logged as one.
 */

import type { WorldCharacter, WorldLocation } from "../api/types";
import { API_BASE, API_PREFIX } from "../config";

export const FALLBACK_PALETTE: [string, string] = ["#3a4a6b", "#131a2b"];

/**
 * The Ren'Py version stacks 24 Solids because Ren'Py has no gradient displayable.
 * CSS does, so the 20 lines become one — the same two-stop vertical ramp.
 */
export function gradient(top: string, bottom: string): string {
  return `linear-gradient(180deg, ${top} 0%, ${bottom} 100%)`;
}

export function paletteOf(
  entity: WorldLocation | WorldCharacter | undefined,
): [string, string] {
  const palette = entity?.palette;
  if (!palette || palette.length === 0) return FALLBACK_PALETTE;
  return [palette[0], palette[palette.length - 1]];
}

/** Title-cased fallback for an id the world payload did not describe. */
export function humanise(id: string): string {
  return id
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

// -- static art probing -----------------------------------------------------------

type ProbeState = "unknown" | "pending" | "hit" | "miss";

const probes = new Map<string, ProbeState>();
const resolved = new Map<string, string | null>();

function probe(candidates: string[], onSettled: () => void): string | null {
  const key = candidates.join("|");
  const cached = resolved.get(key);
  if (cached !== undefined) return cached;

  if (probes.get(key) === "pending") return null;
  probes.set(key, "pending");

  // Sequential rather than parallel: the candidate list is a preference order, and
  // firing all of them would let a less specific file win a race against a better one.
  const tryNext = (position: number) => {
    if (position >= candidates.length) {
      resolved.set(key, null);
      probes.set(key, "miss");
      return; // No re-render: the gradient already on screen is the final answer.
    }
    const image = new Image();
    image.onload = () => {
      resolved.set(key, candidates[position]);
      probes.set(key, "hit");
      onSettled();
    };
    image.onerror = () => tryNext(position + 1);
    image.src = candidates[position];
  };
  tryNext(0);
  return null;
}

/**
 * Static background for a location, if one has been generated into public/images/.
 * Mirrors the Ren'Py candidate order, including the time-of-day variants.
 */
export function staticBackground(
  locationId: string,
  onSettled: () => void,
): string | null {
  return probe(
    [
      `${API_BASE}${API_PREFIX}/static/images/bg/${locationId}.png`,
      `/images/bg/${locationId}.png`,
      `${API_BASE}${API_PREFIX}/static/images/bg/${locationId}_morning.png`,
      `/images/bg/${locationId}_morning.png`,
      `${API_BASE}${API_PREFIX}/static/images/bg/${locationId}_noon.png`,
      `/images/bg/${locationId}_noon.png`,
      `${API_BASE}${API_PREFIX}/static/images/bg/${locationId}_sunset.png`,
      `/images/bg/${locationId}_sunset.png`,
    ],
    onSettled,
  );
}

/** Static sprite for a character, expression-specific first. */
export function staticSprite(
  characterId: string,
  expression: string | null | undefined,
  onSettled: () => void,
): string | null {
  const candidates = expression
    ? [
        `${API_BASE}${API_PREFIX}/static/images/characters/${characterId}/${expression}.png`,
        `/images/characters/${characterId}/${expression}.png`,
        `${API_BASE}${API_PREFIX}/static/images/characters/${characterId}.png`,
        `/images/characters/${characterId}.png`,
      ]
    : [
        `${API_BASE}${API_PREFIX}/static/images/characters/${characterId}.png`,
        `/images/characters/${characterId}.png`,
      ];
  return probe(candidates, onSettled);
}
