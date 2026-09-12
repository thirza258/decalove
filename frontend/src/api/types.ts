/**
 * Wire types for the Decalove API, mirroring `api/app/models/game.py` and
 * `api/app/domain/story.py`.
 *
 * Only the fields this client actually renders are modelled. The API sends more
 * (relationship deltas, memory proposals, flags) — those are the engine's business,
 * and typing them here would invite the client to start owning state it must not
 * own (PRD §33: the server is the source of truth).
 */

export type StepType =
  | "narration"
  | "dialogue"
  | "transition"
  | "event"
  | "choice"
  | "prompt"
  | "ending";

export type AssetStatus = "ready" | "pending" | "unavailable";

/** Blocking steps hand control back to the player. */
export const BLOCKING_STEPS: readonly StepType[] = ["choice", "prompt"];

export interface AssetRef {
  cache_key: string;
  status: AssetStatus;
  asset_id?: string | null;
  /** Absolute when the object store hands out a direct URL, relative to the API otherwise. */
  url?: string | null;
}

export interface VisualSpec {
  background: string;
  character?: string | null;
  expression?: string | null;
  pose?: string | null;
  time_of_day?: string | null;
  weather?: string | null;
  mood?: string | null;
  composition?: string | null;
}

export interface DialogueLine {
  /** A character id, or "player" for a line the player chose. */
  speaker: string;
  text: string;
  emotion?: string | null;
}

export interface Choice {
  id: string;
  text: string;
}

export interface StoryStep {
  step_id: string;
  index: number;
  batch_id: string;
  type: StepType;
  location: string;
  characters: string[];
  narration?: string | null;
  dialogue?: DialogueLine | null;
  next_choices: Choice[];
  visual?: VisualSpec | null;
  background_asset?: AssetRef | null;
  character_asset?: AssetRef | null;
  fallback?: boolean;
}

export type DeliveryStatus = "ready" | "pending" | "awaiting_player" | "ended" | "failed";

export interface StepsBatchOut {
  error?: string | null;
  batch_id?: string | null;
  status: DeliveryStatus;
  steps: StoryStep[];
  queue_depth: number;
  retry_after_ms: number;
  ambience: string[];
}

export interface NextStepOut {
  error?: string | null;
  batch_id?: string | null;
  status: DeliveryStatus;
  step?: StoryStep | null;
  queue_depth: number;
  retry_after_ms: number;
  ambience: string[];
}

export interface WorldCharacter {
  id: string;
  name: string;
  pronouns: string;
  role: string;
  expressions: string[];
  /** Two hex colours, used to draw consistent placeholder art (PRD §26). */
  palette: string[];
}

export interface WorldLocation {
  id: string;
  name: string;
  description: string;
  palette: string[];
  /** In-world filler lines shown while a batch is generating (PRD §11). */
  ambience: string[];
}

export interface WorldOut {
  id: string;
  title: string;
  premise: string;
  tone: string;
  rating: string;
  opening_location: string;
  characters: WorldCharacter[];
  locations: WorldLocation[];
  /** When true, the API only serves pre-existing images from storage; no runtime generation. */
  web_mode?: boolean;
}

export interface GameStateOut {
  pending?: { batch_id: string; status: string; error?: string | null } | null;
  game_id: string;
  world_id: string;
  current_step_index: number;
  queue_depth: number;
  awaiting_player: boolean;
  ended: boolean;
}

export interface AcceptedOut {
  game_id: string;
  batch_id?: string | null;
  status?: string | null;
}

export interface NewGameRequest {
  player_name: string;
  pronouns: string;
  tone: string;
  romance_focus?: string | null;
}

export interface ActionRequest {
  input: string;
  step_id?: string | null;
}
