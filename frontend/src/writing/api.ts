import { API_BASE, API_PREFIX } from "../config";
import type { WritingRequest, WritingSuggestion } from "./model";

export async function writingStatus(signal: AbortSignal): Promise<boolean> {
  const response = await fetch(`${API_BASE}${API_PREFIX}/writing/status`, { signal });
  if (!response.ok) throw new Error("The writing service could not be reached.");
  const data = await response.json() as { available: boolean };
  return data.available;
}

export async function requestWriting(request: WritingRequest, signal: AbortSignal): Promise<WritingSuggestion> {
  const response = await fetch(`${API_BASE}${API_PREFIX}/writing/assist`, {
    method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof data?.detail === "string" ? data.detail : response.status === 422
      ? "This request is too large or incomplete. Check the selected passage and shorten the draft or notes."
      : "AI assistance is unavailable. Your draft is safe; you can retry this request.");
  }
  const data = await response.json() as WritingSuggestion;
  if (!Array.isArray(data.blocks) || !data.blocks.length || data.blocks.length > 220 ||
      typeof data.summary !== "string" || data.blocks.some((b) => !b ||
        !["heading", "dialogue", "narration"].includes(b.kind) || typeof b.text !== "string" || typeof b.speaker !== "string")) {
    throw new Error("The AI returned an unreadable suggestion. Please retry.");
  }
  return data;
}
