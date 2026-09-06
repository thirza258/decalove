/**
 * The scene: background, then at most one sprite — the port of `decalove_render`.
 *
 * Resolution order matches the Ren'Py client exactly: a generated image from the API
 * first, then a static file under public/images/, then the palette gradient. The last
 * one is not an error state — it is built from the palettes the API serves with the
 * world, so a place looks the same every time you are in it (PRD §26).
 */

import { useState } from "react";
import { api } from "../api/client";
import type { StoryStep, WorldOut } from "../api/types";
import { gradient, humanise, paletteOf, staticBackground, staticSprite } from "../game/art";

interface Props {
  step: StoryStep | null;
  world: WorldOut | null;
}

export function Stage({ step, world }: Props) {
  // A static-art probe resolves after paint; this is how the swap-in gets a render.
  const [, settle] = useState(0);
  const onSettled = () => settle((n) => n + 1);

  const visual = step?.visual ?? null;
  const locationId = step?.location ?? visual?.background ?? "";
  const location = world?.locations.find((l) => l.id === locationId);

  const generatedBg = api.assetUrl(
    step?.background_asset?.status === "ready" ? step.background_asset.url : null,
  );
  const staticBg = generatedBg ? null : staticBackground(locationId, onSettled);
  const [bgTop, bgBottom] = paletteOf(location);
  const backgroundImage = generatedBg ?? staticBg;

  const characterId = visual?.character ?? null;
  const character = world?.characters.find((c) => c.id === characterId);
  const generatedSprite = api.assetUrl(
    step?.character_asset?.status === "ready" ? step.character_asset.url : null,
  );
  const staticSpriteUrl =
    !generatedSprite && characterId
      ? staticSprite(characterId, visual?.expression, onSettled)
      : null;
  const spriteImage = generatedSprite ?? staticSpriteUrl;

  return (
    <div className="absolute inset-0 overflow-hidden">
      {backgroundImage ? (
        <img
          key={backgroundImage}
          src={backgroundImage}
          alt=""
          className="vn-dissolve absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <div
          key={locationId}
          className="vn-dissolve absolute inset-0"
          style={{ backgroundImage: gradient(bgTop, bgBottom) }}
        >
          {/* The location's name, the way the Ren'Py fallback labels a place rather
              than leaving the player to guess where they are. */}
          <div className="absolute inset-x-0 bottom-0 h-[22%] bg-black/33" />
          <span
            className="absolute left-[4%] bottom-[7%] text-[34px] text-white/80"
            style={{ textShadow: "2px 2px 0 rgba(0,0,0,0.6)" }}
          >
            {location?.name ?? humanise(locationId)}
          </span>
        </div>
      )}

      {characterId && (
        <div
          key={`${characterId}-${visual?.expression ?? ""}`}
          className="vn-dissolve absolute bottom-0 left-1/2 -translate-x-1/2"
        >
          {spriteImage ? (
            // `fit="contain", xysize=(420, 700)` in decalove_render.
            <img
              src={spriteImage}
              alt={character?.name ?? humanise(characterId)}
              className="h-[700px] w-[420px] object-contain object-bottom"
            />
          ) : (
            <SpritePlaceholder
              name={character?.name ?? humanise(characterId)}
              expression={visual?.expression ?? ""}
              palette={paletteOf(character)}
            />
          )}
        </div>
      )}
    </div>
  );
}

/** `decalove_sprite`: a palette column, a large initial, and the expression named. */
function SpritePlaceholder({
  name,
  expression,
  palette,
}: {
  name: string;
  expression: string;
  palette: [string, string];
}) {
  const initial = name.trim().charAt(0).toUpperCase() || "?";
  return (
    <div
      className="relative h-[660px] w-[320px]"
      style={{ backgroundImage: gradient(palette[0], palette[1]) }}
    >
      <span className="absolute inset-x-0 top-[22%] text-center text-[150px] leading-none text-white/20">
        {initial}
      </span>
      <span className="absolute inset-x-0 bottom-[10%] text-center text-[22px] text-white/65">
        {expression.replace(/_/g, " ")}
      </span>
    </div>
  );
}
