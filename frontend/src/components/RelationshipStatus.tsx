/**
 * Where you stand with everyone — the implication of the last move, on screen.
 *
 * The engine has always tracked this and has always sent it; nothing here decides
 * anything. Affection stays the headline because it is the axis the story is about;
 * trust, romance and anger appear beneath it because they are what make an affection
 * number mean something. Every value is engine-owned and overwritten on sync.
 *
 * The panel can collapse to names and the affection bar — useful when the stage is
 * letterboxed small and the art deserves the room. The delta flash replays on `seq`, so
 * two identical moves in a row both show.
 */

import { useState } from "react";
import type { CharacterStanding, RelationshipDelta, WorldOut } from "../api/types";

interface Props {
  standing: Record<string, CharacterStanding>;
  delta: Record<string, RelationshipDelta>;
  world: WorldOut | null;
  seq: number;
}

const AXIS_LABEL: Record<string, string> = {
  affection: "affection", trust: "trust", respect: "respect", fear: "fear",
  jealousy: "jealousy", friendship: "friendship", romance: "romance",
  familiarity: "familiarity", anger: "anger",
};

const SECONDARY: { axis: string; color: string }[] = [
  { axis: "trust", color: "#8fd6a4" },
  { axis: "romance", color: "#e3a8c8" },
  { axis: "anger", color: "#e2948c" },
];

function summarise(delta: RelationshipDelta): string {
  return Object.entries(delta)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 2)
    .map(([axis, amount]) => `${amount > 0 ? "+" : "−"}${Math.abs(amount)} ${AXIS_LABEL[axis] ?? axis}`)
    .join("  ");
}

function Meter({
  value,
  color,
  label,
  compact = false,
}: {
  value: number;
  color: string;
  label: string;
  compact?: boolean;
}) {
  const bounded = Math.max(0, Math.min(100, value));
  return (
    <div
      className={`${compact ? "h-[3px]" : "h-[4px]"} w-full overflow-hidden rounded-full bg-white/12`}
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={bounded}
    >
      <div
        className="h-full rounded-full transition-[width] duration-500 ease-out"
        style={{ width: `${bounded}%`, background: color }}
      />
    </div>
  );
}

export function RelationshipStatus({ standing, delta, world, seq }: Props) {
  const [expanded, setExpanded] = useState(true);
  const rows = Object.values(standing).filter((character) => character.met || delta[character.id]);
  if (rows.length === 0) return null;

  return (
    <div
      className="pointer-events-none absolute right-[26px] top-[22px] z-10 w-[272px]"
      aria-label="How the others feel about you"
    >
      <div className="rounded-[10px] border border-white/10 bg-black/42 px-3 py-2.5 shadow-[0_10px_30px_rgba(0,0,0,0.28)] backdrop-blur-[3px]">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-[10px] font-medium tracking-[0.12em] text-white/40 uppercase">
            People · {rows.length}
          </h2>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              setExpanded((value) => !value);
            }}
            className="vn-focusable pointer-events-auto -mr-1 rounded px-1 text-[11px] text-white/45 transition-colors hover:text-white"
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse relationship details" : "Expand relationship details"}
            title={expanded ? "Show less" : "Show trust, romance and anger"}
          >
            {expanded ? "Less −" : "More +"}
          </button>
        </div>

        <div className="mt-1.5 flex flex-col gap-2.5">
          {rows.map((character) => {
            const affection = character.relationship.affection ?? 0;
            const moved = delta[character.id];
            const accent = world?.characters.find((c) => c.id === character.id)?.palette?.[0] ?? "#8fa7c4";
            const emotion = character.current_emotion && character.current_emotion !== "neutral"
              ? character.current_emotion.replace(/_/g, " ")
              : "";
            return (
              <div key={character.id}>
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-black/70"
                    style={{ background: accent }}
                  >
                    {character.name.charAt(0)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-[14px] text-white/90" style={{ color: accent }}>
                        {character.name}
                      </span>
                      <span className="shrink-0 text-[11px] tabular-nums text-white/55">
                        <span className="text-white/35">aff </span>
                        {affection}
                      </span>
                    </div>
                    <div className="mt-[4px]">
                      <Meter
                        value={affection}
                        color={accent}
                        label={`${character.name}: affection ${affection} of 100`}
                      />
                    </div>
                  </div>
                </div>

                {expanded && (
                  <div className="mt-1.5 grid grid-cols-3 gap-x-2.5 gap-y-1 pl-8">
                    {SECONDARY.map(({ axis, color }) => {
                      const value = character.relationship[axis] ?? 0;
                      return (
                        <div key={axis}>
                          <div className="flex items-baseline justify-between gap-1">
                            <span className="text-[9px] tracking-[0.04em] text-white/35 capitalize">
                              {axis}
                            </span>
                            <span className="text-[10px] tabular-nums text-white/55">{value}</span>
                          </div>
                          <div className="mt-[2px]">
                            <Meter
                              value={value}
                              color={color}
                              label={`${character.name}: ${axis} ${value} of 100`}
                              compact
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="mt-1 min-h-[13px] pl-8">
                  {emotion && (
                    <span className="mr-2 text-[10px] text-white/45 italic">{emotion}</span>
                  )}
                  {moved && (
                    <span
                      key={`${character.id}-${seq}`}
                      className="vn-standing-delta text-[11px] tabular-nums"
                      style={{
                        color:
                          (moved.affection ?? Object.values(moved)[0]) >= 0 ? "#8fd6a4" : "#e2948c",
                      }}
                    >
                      {summarise(moved)}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
