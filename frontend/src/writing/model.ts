export type BlockKind = "heading" | "dialogue" | "narration" | "image";
export type WritingFormat = "script" | "novel";
export type WritingAction = "starter" | "continue" | "dialogue" | "narrate" | "rewrite";
export type MarkKind = "bold" | "italic" | "underline" | "color" | "highlight";
export type MarkColor = "green" | "teal" | "blue" | "violet" | "plum" | "crimson" | "amber" | "slate";
export type ShotSize = "establishing" | "wide" | "medium" | "close" | "insert" | "over-shoulder";

/** Named colours, never raw values: a document can only ever reach a CSS class. */
export const MARK_COLORS: { id: MarkColor; label: string }[] = [
  { id: "green", label: "Green" }, { id: "teal", label: "Teal" }, { id: "blue", label: "Blue" },
  { id: "violet", label: "Violet" }, { id: "plum", label: "Plum" }, { id: "crimson", label: "Crimson" },
  { id: "amber", label: "Amber" }, { id: "slate", label: "Slate" },
];
export const COLOR_IDS: readonly string[] = MARK_COLORS.map((c) => c.id);
export const SHOTS: { id: ShotSize; label: string }[] = [
  { id: "establishing", label: "Establishing" }, { id: "wide", label: "Wide" }, { id: "medium", label: "Medium" },
  { id: "close", label: "Close-up" }, { id: "insert", label: "Insert" }, { id: "over-shoulder", label: "Over shoulder" },
];
export const MAX_IMAGE_BYTES = 5_000_000;
export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
export const MAX_NOTES = 30;
export const MAX_COMMENTS = 100;
export const MAX_PANELS = 40;

export interface TextMark { start: number; end: number; kind: MarkKind; value?: MarkColor }
/** A picture in the asset store. Only its identifier travels inside the workspace. */
export interface BlockImage { id: string; alt: string; width: number }
export interface WritingBlock {
  id: string; kind: BlockKind; text: string; speaker: string;
  marks?: TextMark[];
  alignment?: "left" | "center" | "right" | "justify";
  font?: "serif" | "sans" | "mono";
  size?: number;
  listStyle?: "none" | "bullet" | "number";
  image?: BlockImage;
}
export interface DocumentNote { id: string; title: string; body: string; color?: MarkColor; updatedAt: string }
export interface DocumentComment {
  id: string; blockId?: string; quote: string; author: string; body: string; resolved: boolean; createdAt: string;
}
/** Where a chosen picture belongs. Held as a description, never as a closure over a
 *  document: the chooser stays open while the writer works, and the placement has to
 *  read the manuscript as it is when the picture arrives. */
export type PictureTarget = { kind: "passage" } | { kind: "replace"; id: string } | { kind: "panel"; id: string };
export interface StoryboardPanel {
  id: string; shot: ShotSize; title: string; description: string; dialogue: string; notes: string; image?: BlockImage;
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
  notes: DocumentNote[];
  comments: DocumentComment[];
  storyboard: StoryboardPanel[];
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
export type StoryboardRequest = Omit<WritingRequest, "action" | "dialogue_count" | "selected_index">
  & { panel_count: number };
export interface StoryboardProposal { shot: ShotSize; title: string; description: string; dialogue: string; notes: string }
export interface StoryboardSuggestion { summary: string; provider: string; panels: StoryboardProposal[] }

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
    dialogueCount: 50, blocks: [newBlock("narration")], notes: [], comments: [], storyboard: [],
    updatedAt: new Date().toISOString(),
  };
}

/** A workspace saved before notes, comments or a storyboard existed is still valid. */
export function normalizeDocument(doc: WritingDocument): WritingDocument {
  if (doc.notes && doc.comments && doc.storyboard) return doc;
  return { ...doc, notes: doc.notes ?? [], comments: doc.comments ?? [], storyboard: doc.storyboard ?? [] };
}

const isColor = (value: unknown): value is MarkColor => typeof value === "string" && COLOR_IDS.includes(value);
const isText = (value: unknown, limit: number) => typeof value === "string" && value.length <= limit;
const isImage = (value: unknown): value is BlockImage => {
  const image = value as BlockImage;
  return !!image && typeof image === "object" && /^[0-9a-f]{64}$/.test(image.id) &&
    isText(image.alt, 300) && Number.isInteger(image.width) && image.width >= 20 && image.width <= 100;
};

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
      typeof b.speaker === "string" && ["heading", "dialogue", "narration", "image"].includes(b.kind) &&
      (b.kind === "image" ? isImage(b.image) : b.image === undefined) &&
      (!b.marks || (Array.isArray(b.marks) && b.marks.every((m) => ["bold", "italic", "underline", "color", "highlight"].includes(m.kind) &&
        (["color", "highlight"].includes(m.kind) ? isColor(m.value) : m.value === undefined) &&
        Number.isInteger(m.start) && Number.isInteger(m.end) && m.start >= 0 && m.end > m.start && m.end <= b.text.length))) &&
      (!b.alignment || ["left", "center", "right", "justify"].includes(b.alignment)) &&
      (!b.font || ["serif", "sans", "mono"].includes(b.font)) &&
      (b.size === undefined || (Number.isInteger(b.size) && b.size >= 12 && b.size <= 32)) &&
      (!b.listStyle || ["none", "bullet", "number"].includes(b.listStyle))) &&
    new Set(d.blocks.map((b) => b.id)).size === d.blocks.length &&
    // Notes, comments and the storyboard arrived later: absent is as valid as empty.
    (!d.notes || (Array.isArray(d.notes) && d.notes.length <= MAX_NOTES && d.notes.every((n) => n &&
      typeof n.id === "string" && isText(n.title, 120) && isText(n.body, 2000) && isText(n.updatedAt, 40) &&
      (n.color === undefined || isColor(n.color))))) &&
    (!d.comments || (Array.isArray(d.comments) && d.comments.length <= MAX_COMMENTS && d.comments.every((c) => c &&
      typeof c.id === "string" && (c.blockId === undefined || typeof c.blockId === "string") &&
      isText(c.quote, 160) && isText(c.author, 60) && isText(c.body, 1000) &&
      typeof c.resolved === "boolean" && isText(c.createdAt, 40)))) &&
    (!d.storyboard || (Array.isArray(d.storyboard) && d.storyboard.length <= MAX_PANELS && d.storyboard.every((p) => p &&
      typeof p.id === "string" && SHOTS.some((s) => s.id === p.shot) && isText(p.title, 120) &&
      isText(p.description, 800) && isText(p.dialogue, 300) && isText(p.notes, 400) &&
      (p.image === undefined || isImage(p.image)))) &&
      new Set(d.storyboard.map((p) => p.id)).size === d.storyboard.length);
}

export function toRequest(doc: WritingDocument, action: WritingAction, selectedId: string | null): WritingRequest {
  const selected = doc.blocks.findIndex((b) => b.id === selectedId);
  return {
    action, format: doc.format, title: doc.title, genre: doc.genre, theme: doc.theme,
    premise: doc.premise, characters: doc.characters, reference: doc.reference, prompt: doc.prompt,
    dialogue_count: doc.dialogueCount,
    // An illustration keeps its place in the draft, so passage numbers still line up.
    blocks: doc.blocks.map(({ kind, text, speaker, image }) => ({
      kind, speaker, text: kind === "image" ? text || image?.alt || "" : text,
    })),
    selected_index: selected < 0 ? null : selected,
  };
}

export function toStoryboardRequest(doc: WritingDocument, panelCount: number): StoryboardRequest {
  const { action: _action, dialogue_count: _count, selected_index: _selected, ...context } = toRequest(doc, "starter", null);
  return { ...context, panel_count: panelCount };
}

export const imageLabel = (alt: string) => alt.trim() || "untitled illustration";

export function newPanel(panel: Partial<StoryboardPanel> = {}): StoryboardPanel {
  return { id: crypto.randomUUID(), shot: "medium", title: "", description: "", dialogue: "", notes: "", ...panel };
}

/**
 * A first pass at a shot list, drawn from the manuscript itself: a heading opens a
 * panel, narration describes it, and the first spoken line is what we hear over it.
 * Everything stays editable — this is a starting point, not a conversion.
 */
export function panelsFromManuscript(doc: WritingDocument): StoryboardPanel[] {
  const panels: StoryboardPanel[] = [];
  let current: StoryboardPanel | null = null;
  const open = (title: string) => {
    current = newPanel({ shot: panels.length ? "medium" : "establishing", title });
    panels.push(current);
    return current;
  };
  for (const block of doc.blocks) {
    if (panels.length >= MAX_PANELS) break;
    const text = block.text.trim();
    if (block.kind === "heading") { if (text) open(text.slice(0, 120)); continue; }
    if (block.kind === "image") {
      const panel = open(imageLabel(block.image?.alt ?? "").slice(0, 120));
      panel.description = text.slice(0, 800);
      panel.image = block.image;
      current = null;
      continue;
    }
    if (!text) continue;
    if (!current) current = open("");
    if (block.kind === "narration") {
      current.description = current.description ? `${current.description} ${text}`.slice(0, 800) : text.slice(0, 800);
    } else if (!current.dialogue) {
      current.dialogue = `${block.speaker ? `${block.speaker}: ` : ""}${text}`.slice(0, 300);
      // A spoken line tightens the framing, unless a heading already opened the scene.
      if (current.shot === "medium") current.shot = "close";
      if (!current.title) current.title = block.speaker.slice(0, 120);
      current = null;
    }
  }
  return panels.filter((panel) => panel.description.trim() || panel.dialogue.trim() || panel.title.trim());
}

export function exportText(doc: WritingDocument): string {
  let listNumber = 0;
  const passages = doc.blocks.map((b) => {
    const prefix = b.listStyle === "bullet" ? "• " : b.listStyle === "number" ? `${++listNumber}. ` : "";
    if (b.kind === "image") return `${prefix}[Image: ${imageLabel(b.image?.alt ?? "")}]${b.text.trim() ? `\n${b.text}` : ""}`;
    if (b.kind !== "dialogue") return prefix + b.text;
    return prefix + (doc.format === "script" ? `${b.speaker || "CHARACTER"}: ${b.text}`
      : `“${b.text}”${b.speaker ? ` — ${b.speaker}` : ""}`);
  });
  const body = `${doc.title}\n\n${passages.join("\n\n")}\n`;
  const panels = doc.storyboard ?? [];
  if (!panels.length) return body;
  // The same shot list the server writes into an exported .txt.
  const lines = ["STORYBOARD"];
  panels.forEach((panel, index) => {
    lines.push(`${index + 1}. ${panel.shot.toUpperCase()}${panel.title.trim() ? ` — ${panel.title}` : ""}`);
    if (panel.description.trim()) lines.push(`   ${panel.description}`);
    if (panel.dialogue.trim()) lines.push(`   “${panel.dialogue}”`);
    if (panel.notes.trim()) lines.push(`   Note: ${panel.notes}`);
    if (panel.image) lines.push(`   [Image: ${imageLabel(panel.image.alt)}]`);
  });
  return `${body}\n${lines.join("\n")}\n`;
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
