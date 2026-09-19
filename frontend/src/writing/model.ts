export type BlockKind = "heading" | "dialogue" | "narration";
export type WritingFormat = "script" | "novel";
export type WritingAction = "starter" | "continue" | "dialogue" | "narrate" | "rewrite";
export type MarkKind = "bold" | "italic" | "underline";
export interface TextMark { start: number; end: number; kind: MarkKind }
export interface WritingBlock {
  id: string; kind: BlockKind; text: string; speaker: string;
  marks?: TextMark[];
  alignment?: "left" | "center" | "right" | "justify";
  font?: "serif" | "sans" | "mono";
  size?: number;
  listStyle?: "none" | "bullet" | "number";
}
export interface WritingDocument {
  id: string;
  title: string;
  format: WritingFormat;
  genre: string;
  theme: string;
  premise: string;
  characters: string;
  reference: string;
  prompt: string;
  dialogueCount: number;
  blocks: WritingBlock[];
  updatedAt: string;
}
export interface Library { version: 1; activeId: string; documents: WritingDocument[] }
export interface WritingRequest {
  action: WritingAction;
  format: WritingFormat;
  title: string;
  genre: string;
  theme: string;
  premise: string;
  characters: string;
  reference: string;
  prompt: string;
  dialogue_count: number;
  blocks: Pick<WritingBlock, "kind" | "text" | "speaker">[];
  selected_index: number | null;
}
export interface WritingSuggestion {
  summary: string;
  provider: string;
  blocks: Pick<WritingBlock, "kind" | "text" | "speaker">[];
}

export const THEME_STARTERS = [
  { name: "Finding belonging", theme: "Can you belong somewhere without making yourself useful?", premise: "Two neighbours who have never spoken must pack up a community library before it closes." },
  { name: "The cost of truth", theme: "When does protecting someone become taking away their choice?", premise: "An apprentice discovers that the letter they must deliver will expose their mentor's oldest lie." },
  { name: "Second chances", theme: "Is an apology enough when the damage cannot be undone?", premise: "Former friends meet at a train station to return something neither has been able to throw away." },
  { name: "Ambition & home", theme: "What do we owe the people who helped us leave?", premise: "On the night before a life-changing departure, a musician's sibling asks them to stay for one last rehearsal." },
];

export function newBlock(kind: BlockKind, text = "", speaker = ""): WritingBlock {
  return { id: crypto.randomUUID(), kind, text, speaker };
}

export function newDocument(format: WritingFormat = "script", exercise = ""): WritingDocument {
  return {
    id: crypto.randomUUID(), title: "Untitled story", format, genre: "Contemporary",
    theme: "", premise: "", characters: "", reference: "", prompt: exercise,
    dialogueCount: 50, blocks: [newBlock("narration")], updatedAt: new Date().toISOString(),
  };
}

export function isDocument(value: unknown): value is WritingDocument {
  if (!value || typeof value !== "object") return false;
  const d = value as WritingDocument;
  return typeof d.id === "string" && !!d.id &&
    ["title", "genre", "theme", "premise", "characters", "reference", "prompt", "updatedAt"].every(
      (key) => typeof d[key as keyof WritingDocument] === "string",
    ) && (d.format === "script" || d.format === "novel") &&
    Number.isInteger(d.dialogueCount) && d.dialogueCount >= 1 && d.dialogueCount <= 100 &&
    Array.isArray(d.blocks) && d.blocks.length <= 1000 &&
    d.blocks.every((b) => b && typeof b.id === "string" && typeof b.text === "string" &&
      typeof b.speaker === "string" && ["heading", "dialogue", "narration"].includes(b.kind) &&
      (!b.marks || (Array.isArray(b.marks) && b.marks.every((m) => ["bold", "italic", "underline"].includes(m.kind) &&
        Number.isInteger(m.start) && Number.isInteger(m.end) && m.start >= 0 && m.end > m.start && m.end <= b.text.length))) &&
      (!b.alignment || ["left", "center", "right", "justify"].includes(b.alignment)) &&
      (!b.font || ["serif", "sans", "mono"].includes(b.font)) &&
      (b.size === undefined || (Number.isInteger(b.size) && b.size >= 12 && b.size <= 32)) &&
      (!b.listStyle || ["none", "bullet", "number"].includes(b.listStyle))) &&
    new Set(d.blocks.map((b) => b.id)).size === d.blocks.length;
}

export function toRequest(doc: WritingDocument, action: WritingAction, selectedId: string | null): WritingRequest {
  const selected = doc.blocks.findIndex((b) => b.id === selectedId);
  return {
    action, format: doc.format, title: doc.title, genre: doc.genre, theme: doc.theme,
    premise: doc.premise, characters: doc.characters, reference: doc.reference, prompt: doc.prompt,
    dialogue_count: doc.dialogueCount,
    blocks: doc.blocks.map(({ kind, text, speaker }) => ({ kind, text, speaker })),
    selected_index: selected < 0 ? null : selected,
  };
}

export function exportText(doc: WritingDocument): string {
  let listNumber = 0;
  return `${doc.title}\n\n${doc.blocks.map((b) => {
    const prefix = b.listStyle === "bullet" ? "• " : b.listStyle === "number" ? `${++listNumber}. ` : "";
    if (b.kind !== "dialogue") return prefix + b.text;
    return prefix + (doc.format === "script" ? `${b.speaker || "CHARACTER"}: ${b.text}`
      : `“${b.text}”${b.speaker ? ` — ${b.speaker}` : ""}`);
  }).join("\n\n")}\n`;
}

/** Plain text is imported as editable paragraphs, never interpreted as HTML. */
export function importText(text: string): WritingBlock[] {
  return text.split(/\r?\n\s*\r?\n/).filter((p) => p.trim()).map((paragraph) => {
    const dialogue = /^([^:\n]{1,100}):[ \t]+([^]*?)$/.exec(paragraph);
    return dialogue ? newBlock("dialogue", dialogue[2], dialogue[1]) : newBlock("narration", paragraph);
  });
}

export function downloadFile(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
