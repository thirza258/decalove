import { COLOR_IDS } from "./model";
import type { MarkColor, MarkKind, TextMark, WritingBlock } from "./model";

export const FONTS = { serif: 'Georgia, "Times New Roman", serif', sans: 'system-ui, sans-serif', mono: 'ui-monospace, monospace' };
const KINDS: MarkKind[] = ["bold", "italic", "underline", "color", "highlight"];
const VALUED: MarkKind[] = ["color", "highlight"];
/** Marks of the same kind merge only when they are the same colour. */
const groupOf = (mark: TextMark) => `${mark.kind}:${mark.value ?? ""}`;
const rank = (group: string) => `${KINDS.indexOf(group.split(":")[0] as MarkKind)}${group}`;
export const markClass = (kind: MarkKind, value: MarkColor) => `mark-${kind === "highlight" ? "highlight" : "color"}-${value}`;

function mergeMarks(marks: TextMark[]): TextMark[] {
  const output: TextMark[] = [];
  for (const group of [...new Set(marks.map(groupOf))].sort((a, b) => rank(a).localeCompare(rank(b)))) {
    for (const mark of marks.filter((m) => groupOf(m) === group).sort((a, b) => a.start - b.start)) {
      const last = output.at(-1);
      if (last && groupOf(last) === group && last.end >= mark.start) last.end = Math.max(last.end, mark.end);
      else output.push({ ...mark });
    }
  }
  return output;
}
const escapeText = (text: string) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const paletteOf = (marks: TextMark[], kind: MarkKind): MarkColor | undefined => {
  const value = marks.find((m) => m.kind === kind)?.value;
  // Defence in depth: an imported backup can only ever name a colour we ship.
  return value && COLOR_IDS.includes(value) ? value : undefined;
};

/** Only escaped text and our own fixed tags and classes ever enter the editable DOM. */
export function richHTML(text: string, marks: TextMark[] = []): string {
  const points = [...new Set([0, text.length, ...marks.flatMap((m) => [m.start, m.end])])].sort((a, b) => a - b);
  return points.slice(0, -1).map((start, i) => {
    let value = escapeText(text.slice(start, points[i + 1]));
    const active = marks.filter((m) => m.start <= start && m.end >= points[i + 1]);
    if (active.some((m) => m.kind === "bold")) value = `<strong>${value}</strong>`;
    if (active.some((m) => m.kind === "italic")) value = `<em>${value}</em>`;
    if (active.some((m) => m.kind === "underline")) value = `<u>${value}</u>`;
    const color = paletteOf(active, "color");
    if (color) value = `<span class="${markClass("color", color)}">${value}</span>`;
    const highlight = paletteOf(active, "highlight");
    if (highlight) value = `<span class="${markClass("highlight", highlight)}">${value}</span>`;
    return value;
  }).join("");
}

export function readRichText(root: HTMLElement): { text: string; marks: TextMark[] } {
  let text = "";
  const marks: TextMark[] = [];
  function walk(node: Node, active: Pick<TextMark, "kind" | "value">[]) {
    if (node.nodeType === Node.TEXT_NODE) {
      const start = text.length;
      text += node.textContent ?? "";
      for (const mark of active) if (text.length > start) marks.push({ ...mark, start, end: text.length });
      return;
    }
    if (!(node instanceof HTMLElement)) return;
    if (node.tagName === "BR") { text += "\n"; return; }
    let next = [...active];
    // One entry per kind: nesting the same kind twice, or a colour inside a colour,
    // means the innermost wins rather than both applying to the same words.
    const add = (kind: MarkKind, value?: MarkColor) => {
      next = next.filter((m) => m.kind !== kind);
      next.push({ kind, ...(value ? { value } : {}) });
    };
    if (["STRONG", "B"].includes(node.tagName) || node.style.fontWeight === "bold") add("bold");
    if (["EM", "I"].includes(node.tagName) || node.style.fontStyle === "italic") add("italic");
    if (node.tagName === "U" || node.style.textDecoration.includes("underline")) add("underline");
    for (const name of node.classList) {
      const found = /^mark-(color|highlight)-([a-z]+)$/.exec(name);
      if (found && COLOR_IDS.includes(found[2])) add(found[1] === "highlight" ? "highlight" : "color", found[2] as MarkColor);
    }
    if (["DIV", "P"].includes(node.tagName) && node !== root && text && !text.endsWith("\n")) text += "\n";
    node.childNodes.forEach((child) => walk(child, next));
  }
  walk(root, []);
  text = text.slice(0, 12000);
  return { text, marks: mergeMarks(marks.filter((m) => m.start < text.length).map((m) => ({ ...m, end: Math.min(m.end, text.length) }))) };
}

export function selectedOffsets(root: HTMLElement): { start: number; end: number } | null {
  const selection = window.getSelection();
  if (!selection?.rangeCount) return null;
  const range = selection.getRangeAt(0);
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null;
  const prefix = range.cloneRange();
  prefix.selectNodeContents(root); prefix.setEnd(range.startContainer, range.startOffset);
  const start = prefix.toString().length;
  return { start, end: start + range.toString().length };
}

export function selectOffsets(root: HTMLElement, start: number, end: number) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  if (!nodes.length) return;
  function point(offset: number): [Text, number] {
    for (const node of nodes) {
      if (offset <= node.length) return [node, offset];
      offset -= node.length;
    }
    return [nodes[nodes.length - 1], nodes[nodes.length - 1].length];
  }
  const range = document.createRange();
  range.setStart(...point(start)); range.setEnd(...point(end));
  const selection = window.getSelection();
  selection?.removeAllRanges(); selection?.addRange(range);
}

/**
 * Bold, italic and underline toggle. A colour replaces the colour already there, and
 * asking for no colour clears it — which is what a writer means by "remove colour".
 */
export function toggleMark(marks: TextMark[], start: number, end: number, kind: MarkKind, value?: MarkColor): TextMark[] {
  if (start === end) return marks;
  marks = mergeMarks(marks);
  const valued = VALUED.includes(kind);
  const has = marks.some((m) => m.kind === kind && (!valued || m.value === value) && m.start <= start && m.end >= end);
  const kept = marks.flatMap((m) => {
    if (m.kind !== kind || m.end <= start || m.start >= end) return [m];
    return [...(m.start < start ? [{ ...m, end: start }] : []), ...(m.end > end ? [{ ...m, start: end }] : [])];
  });
  if (has || (valued && !value)) return mergeMarks(kept);
  return mergeMarks([...kept, { start, end, kind, ...(valued ? { value } : {}) }]);
}

export function replaceRange(block: WritingBlock, start: number, end: number, replacement: string): WritingBlock {
  const delta = replacement.length - (end - start);
  return { ...block, text: block.text.slice(0, start) + replacement + block.text.slice(end), marks: (block.marks ?? []).flatMap((m) => {
    if (m.end <= start) return [m];
    if (m.start >= end) return [{ ...m, start: m.start + delta, end: m.end + delta }];
    if (m.start >= start && m.end <= end) return [];
    return [{ ...m, start: Math.min(m.start, start), end: Math.max(start + replacement.length, m.end + delta) }];
  }) };
}
