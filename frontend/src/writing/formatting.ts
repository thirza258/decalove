import type { MarkKind, TextMark, WritingBlock } from "./model";

export const FONTS = { serif: 'Georgia, "Times New Roman", serif', sans: 'system-ui, sans-serif', mono: 'ui-monospace, monospace' };
function mergeMarks(marks: TextMark[]): TextMark[] {
  const output: TextMark[] = [];
  for (const kind of ["bold", "italic", "underline"] as const) {
    for (const mark of marks.filter((m) => m.kind === kind).sort((a, b) => a.start - b.start)) {
      const last = output.at(-1);
      if (last?.kind === kind && last.end >= mark.start) last.end = Math.max(last.end, mark.end);
      else output.push({ ...mark });
    }
  }
  return output;
}
const escapeText = (text: string) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** Only escaped text and our own fixed tags ever enter the editable DOM. */
export function richHTML(text: string, marks: TextMark[] = []): string {
  const points = [...new Set([0, text.length, ...marks.flatMap((m) => [m.start, m.end])])].sort((a, b) => a - b);
  return points.slice(0, -1).map((start, i) => {
    let value = escapeText(text.slice(start, points[i + 1]));
    const active = marks.filter((m) => m.start <= start && m.end >= points[i + 1]);
    if (active.some((m) => m.kind === "bold")) value = `<strong>${value}</strong>`;
    if (active.some((m) => m.kind === "italic")) value = `<em>${value}</em>`;
    if (active.some((m) => m.kind === "underline")) value = `<u>${value}</u>`;
    return value;
  }).join("");
}

export function readRichText(root: HTMLElement): { text: string; marks: TextMark[] } {
  let text = "";
  const marks: TextMark[] = [];
  function walk(node: Node, active: MarkKind[]) {
    if (node.nodeType === Node.TEXT_NODE) {
      const start = text.length;
      text += node.textContent ?? "";
      for (const kind of active) if (text.length > start) marks.push({ start, end: text.length, kind });
      return;
    }
    if (!(node instanceof HTMLElement)) return;
    if (node.tagName === "BR") { text += "\n"; return; }
    const next = [...active];
    if (["STRONG", "B"].includes(node.tagName) || node.style.fontWeight === "bold") next.push("bold");
    if (["EM", "I"].includes(node.tagName) || node.style.fontStyle === "italic") next.push("italic");
    if (node.tagName === "U" || node.style.textDecoration.includes("underline")) next.push("underline");
    if (["DIV", "P"].includes(node.tagName) && node !== root && text && !text.endsWith("\n")) text += "\n";
    node.childNodes.forEach((child) => walk(child, [...new Set(next)]));
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

export function toggleMark(marks: TextMark[], start: number, end: number, kind: MarkKind): TextMark[] {
  if (start === end) return marks;
  marks = mergeMarks(marks);
  const has = marks.some((m) => m.kind === kind && m.start <= start && m.end >= end);
  const kept = marks.flatMap((m) => {
    if (m.kind !== kind || m.end <= start || m.start >= end) return [m];
    return [...(m.start < start ? [{ ...m, end: start }] : []), ...(m.end > end ? [{ ...m, start: end }] : [])];
  });
  return mergeMarks(has ? kept : [...kept, { start, end, kind }]);
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
