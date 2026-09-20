import { useLayoutEffect, useRef } from "react";
import { FONTS, readRichText, richHTML, selectedOffsets, selectOffsets } from "../writing/formatting";
import type { WritingBlock } from "../writing/model";

export function RichPassage({ block, label, placeholder, onChange }: {
  block: WritingBlock; label: string; placeholder: string;
  onChange: (patch: Partial<WritingBlock>) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const composing = useRef(false);
  const html = richHTML(block.text, block.marks);
  useLayoutEffect(() => {
    const root = ref.current;
    if (!root || composing.current || root.innerHTML === html) return;
    const range = selectedOffsets(root);
    root.innerHTML = html;
    if (range && document.activeElement === root) selectOffsets(root, range.start, range.end);
  }, [html]);

  function commit() {
    if (ref.current && !composing.current) onChange(readRichText(ref.current));
  }
  function insertText(text: string) {
    const root = ref.current;
    const selection = window.getSelection();
    if (!root || !selection?.rangeCount) return;
    const range = selection.getRangeAt(0);
    if (!root.contains(range.commonAncestorContainer)) return;
    const available = 12000 - (root.textContent?.length ?? 0) + range.toString().length;
    range.deleteContents();
    const node = document.createTextNode(text.slice(0, Math.max(0, available)));
    range.insertNode(node); range.setStartAfter(node); range.collapse(true);
    selection.removeAllRanges(); selection.addRange(range);
    commit();
  }
  return <div id={`block-${block.id}`} ref={ref} role="textbox" aria-multiline="true" aria-label={label}
    contentEditable suppressContentEditableWarning spellCheck className="rich-passage" data-placeholder={placeholder}
    style={{ textAlign: block.alignment, fontFamily: block.font ? FONTS[block.font] : undefined, fontSize: block.size ? `${block.size}px` : undefined }}
    onInput={commit}
    onCompositionStart={() => { composing.current = true; }}
    onCompositionEnd={() => { composing.current = false; commit(); }}
    onKeyDown={(event) => { if (event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); insertText("\n"); } }}
    onPaste={(event) => { event.preventDefault(); insertText(event.clipboardData.getData("text/plain")); }}
    onDrop={(event) => { event.preventDefault(); }}
  />;
}
