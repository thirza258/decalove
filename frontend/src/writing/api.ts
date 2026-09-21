import { API_BASE, API_PREFIX } from "../config";
import { SHOTS } from "./model";
import type { StoryboardRequest, StoryboardSuggestion, WritingRequest, WritingSuggestion } from "./model";

export async function writingStatus(signal: AbortSignal): Promise<boolean> {
  const response = await fetch(`${API_BASE}${API_PREFIX}/writing/status`, { signal });
  if (!response.ok) throw new Error("The writing service could not be reached.");
  const data = await response.json() as { available: boolean };
  return data.available;
}

export interface LibraryPicture { key: string; name: string; size: number }

/** Pictures an operator placed in the object store by hand — see docs/IMAGES.md. */
export async function writingLibrary(signal: AbortSignal): Promise<LibraryPicture[]> {
  const response = await fetch(`${API_BASE}${API_PREFIX}/writing/library`, { signal });
  if (!response.ok) throw new Error("The shared picture library could not be read.");
  const data = await response.json() as { pictures?: LibraryPicture[] };
  return (data.pictures ?? []).filter((picture) => picture && typeof picture.key === "string" && typeof picture.name === "string");
}

async function proposal(path: string, request: unknown, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(`${API_BASE}${API_PREFIX}/writing/${path}`, {
    method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof data?.detail === "string" ? data.detail : response.status === 422
      ? "This request is too large or incomplete. Check the selected passage and shorten the draft or notes."
      : "AI assistance is unavailable. Your draft is safe; you can retry this request.");
  }
  return response.json();
}

export async function requestStoryboard(request: StoryboardRequest, signal: AbortSignal): Promise<StoryboardSuggestion> {
  const data = await proposal("storyboard", request, signal) as StoryboardSuggestion;
  if (!Array.isArray(data.panels) || !data.panels.length || data.panels.length > 24 ||
      typeof data.summary !== "string" || data.panels.some((p) => !p || typeof p.description !== "string" ||
        typeof p.title !== "string" || typeof p.dialogue !== "string" || typeof p.notes !== "string" ||
        !SHOTS.some((shot) => shot.id === p.shot))) {
    throw new Error("The AI returned an unreadable storyboard. Please retry.");
  }
  return data;
}

export async function requestWriting(request: WritingRequest, signal: AbortSignal): Promise<WritingSuggestion> {
  const data = await proposal("assist", request, signal) as WritingSuggestion;
  if (!Array.isArray(data.blocks) || !data.blocks.length || data.blocks.length > 220 ||
      typeof data.summary !== "string" || data.blocks.some((b) => !b ||
        !["heading", "dialogue", "narration"].includes(b.kind) || typeof b.text !== "string" || typeof b.speaker !== "string")) {
    throw new Error("The AI returned an unreadable suggestion. Please retry.");
  }
  return data;
}
