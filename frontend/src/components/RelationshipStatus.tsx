/**
 * Where you stand with everyone — the implication of the last move, on screen.
 *
 * The engine has always tracked this and has always sent it; nothing here decides
 * anything. Affection is the bar because it is the axis the story is about; every
 * other axis appears only when a beat moves it, which is the moment it means
 * something. The flash replays on `seq` so two identical deltas in a row both show.
 */

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

function summarise(delta: RelationshipDelta): string {
  return Object.entries(delta)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 2)
    .map(([axis, amount]) => `${amount > 0 ? "+" : "−"}${Math.abs(amount)} ${AXIS_LABEL[axis] ?? axis}`)
    .join("  ");
}

export function RelationshipStatus({ standing, delta, world, seq }: Props) {
  const rows = Object.values(standing).filter((character) => character.met || delta[character.id]);
  if (rows.length === 0) return null;

  return (
    <div
      className="pointer-events-none absolute right-[26px] top-[22px] flex w-[228px] flex-col gap-[9px]"
      aria-label="How the others feel about you"
    >
      {rows.map((character) => {
        const affection = character.relationship.affection ?? 0;
        const moved = delta[character.id];
        const accent = world?.characters.find((c) => c.id === character.id)?.palette?.[0] ?? "#8fa7c4";
        return (
          <div key={character.id} className="rounded-[7px] bg-black/38 px-[11px] py-[7px] backdrop-blur-[2px]">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[15px] text-vn-selected/90" style={{ color: accent }}>
                {character.name}
              </span>
              <span className="text-[12px] tabular-nums text-vn-idle">{affection}</span>
            </div>
            <div className="mt-[5px] h-[3px] w-full overflow-hidden rounded-full bg-white/15">
              <div
                className="h-full rounded-full transition-[width] duration-500 ease-out"
                style={{ width: `${Math.max(0, Math.min(100, affection))}%`, background: accent }}
              />
            </div>
            {moved && (
              <div
                key={`${character.id}-${seq}`}
                className="vn-standing-delta mt-[4px] text-[12px] tabular-nums"
                style={{ color: (moved.affection ?? Object.values(moved)[0]) >= 0 ? "#8fd6a4" : "#e2948c" }}
              >
                {summarise(moved)}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
