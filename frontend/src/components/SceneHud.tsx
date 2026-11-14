/**
 * Where and when the scene is — the information a visual novel usually hides in a
 * corner and a player usually wants: place, day, hour, weather, and who is standing
 * there. It reads from the engine's `world` snapshot (refreshed once per turn) and
 * falls back to the beat's own location/present cast during the authored opening.
 *
 * Deliberately quiet: this is a HUD over the art, not a dashboard. The one interactive
 * control is the story log, which is also reachable with `L`.
 */

import { useEffect, useState } from "react";
import type { StoryStep, WorldCharacter, WorldContext, WorldOut } from "../api/types";
import { humanise } from "../game/art";

interface Props {
  scene: WorldContext | null;
  world: WorldOut | null;
  step: StoryStep | null;
  waiting: boolean;
  deciding: boolean;
  onOpenLog: () => void;
}

const TIME_LABEL: Record<string, string> = {
  morning: "Morning",
  noon: "Noon",
  afternoon: "Afternoon",
  sunset: "Sunset",
  evening: "Evening",
  night: "Night",
};

const TIME_GLYPH: Record<string, string> = {
  morning: "◐",
  noon: "●",
  afternoon: "◑",
  sunset: "◒",
  evening: "◓",
  night: "◕",
};

function label(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function SceneHud({ scene, world, step, waiting, deciding, onOpenLog }: Props) {
  // The beat is fresher than the once-per-turn snapshot: the scene can move inside a
  // buffered batch. Calendar/arc/weather still come from the engine's clock, which a
  // step does not carry.
  const locationId = step?.location || scene?.location || "";
  const location = world?.locations.find((place) => place.id === locationId);
  const present = step?.characters?.length
    ? step.characters
    : scene?.present_characters ?? [];
  const cast = present
    .map((id) => world?.characters.find((character) => character.id === id))
    .filter((character): character is WorldCharacter => Boolean(character));
  const time = step?.visual?.time_of_day ?? scene?.time_of_day ?? "";
  const hour = TIME_LABEL[time] ?? (time ? label(time) : "");
  const arc = scene?.arc ? label(scene.arc) : "";

  return (
    <div className="pointer-events-none absolute left-[26px] top-[22px] z-10 w-[342px]">
      <div className="rounded-[10px] border border-white/10 bg-black/42 px-3.5 py-3 shadow-[0_10px_30px_rgba(0,0,0,0.28)] backdrop-blur-[3px]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate text-[19px] leading-tight text-white/95">
                {location?.name ?? (locationId ? humanise(locationId) : "Decalove")}
              </h2>
              {hour && (
                <span className="shrink-0 rounded-full border border-white/12 bg-white/6 px-2 py-0.5 text-[10px] font-medium tracking-[0.08em] text-white/65 uppercase">
                  <span aria-hidden="true" className="mr-1 text-vn-hover">
                    {TIME_GLYPH[time] ?? "◐"}
                  </span>
                  {hour}
                </span>
              )}
            </div>
            <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] text-white/55">
              {scene && (
                <>
                  <span>Day {scene.day}</span>
                  <span aria-hidden="true">·</span>
                  <span>{scene.weekday}</span>
                  {scene.weather && (
                    <>
                      <span aria-hidden="true">·</span>
                      <span>{label(scene.weather)}</span>
                    </>
                  )}
                  {arc && (
                    <>
                      <span aria-hidden="true">·</span>
                      <span>{arc}</span>
                    </>
                  )}
                </>
              )}
              {!scene && <span className="italic">Opening scene</span>}
            </p>
          </div>

          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenLog();
            }}
            className="vn-focusable pointer-events-auto -mr-1 -mt-1 shrink-0 rounded-md border border-white/10 bg-white/6 px-2 py-1.5 text-[12px] text-white/70 transition-colors hover:bg-white/12 hover:text-white"
            aria-label="Open the story log"
            title="Story log (L)"
          >
            <span aria-hidden="true" className="mr-1">
              ☰
            </span>
            Log
          </button>
        </div>

        {cast.length > 0 && (
          <div className="mt-2.5 flex items-center gap-1.5 border-t border-white/8 pt-2.5">
            <span className="text-[10px] tracking-[0.1em] text-white/35 uppercase">Present</span>
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              {cast.slice(0, 4).map((character) => (
                <span
                  key={character.id}
                  className="flex items-center gap-1 rounded-full bg-white/6 py-0.5 pr-2 pl-0.5 text-[11px] text-white/75"
                >
                  <span
                    aria-hidden="true"
                    className="flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-semibold text-black/70"
                    style={{ background: character.palette?.[0] ?? "#8fa7c4" }}
                  >
                    {character.name.charAt(0)}
                  </span>
                  {character.name.split(" ")[0]}
                </span>
              ))}
              {cast.length > 4 && (
                <span className="text-[11px] text-white/40">+{cast.length - 4}</span>
              )}
            </div>
          </div>
        )}

        <div className="mt-2.5 flex min-h-[18px] items-center justify-between gap-2">
          {waiting ? (
            <span
              className="flex items-center gap-1.5 text-[11px] text-vn-hover/90"
              role="status"
              aria-live="polite"
            >
              <span className="vn-pulse-dot" aria-hidden="true" />
              Writing the next scene…
            </span>
          ) : deciding ? (
            <span className="text-[11px] text-vn-accent/90">Your move</span>
          ) : (
            <span className="text-[11px] text-white/30">Click or press Space to continue</span>
          )}
          <FullscreenButton />
        </div>
      </div>
    </div>
  );
}

/** Maximising the 1280×720 canvas is the one responsive lever a letterboxed VN has. */
function FullscreenButton() {
  const [active, setActive] = useState(false);
  const supported =
    typeof document !== "undefined" && Boolean(document.fullscreenEnabled);

  useEffect(() => {
    if (!supported) return;
    const update = () => setActive(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, [supported]);

  if (!supported) return null;
  return (
    <button
      type="button"
      onClick={async (event) => {
        event.stopPropagation();
        try {
          if (document.fullscreenElement) await document.exitFullscreen();
          else await document.documentElement.requestFullscreen();
        } catch {
          // A browser may refuse outside a user gesture; the button simply does nothing.
        }
      }}
      className="vn-focusable pointer-events-auto rounded px-1 text-[13px] text-white/40 transition-colors hover:text-white/85"
      aria-label={active ? "Leave fullscreen" : "Enter fullscreen"}
      title={active ? "Leave fullscreen" : "Fullscreen"}
    >
      <span aria-hidden="true">{active ? "⤡" : "⛶"}</span>
    </button>
  );
}
