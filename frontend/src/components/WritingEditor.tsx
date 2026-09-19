import { useState } from "react";
import { newBlock } from "../writing/model";
import type { BlockKind, MarkKind, WritingBlock, WritingDocument } from "../writing/model";
import { FONTS, richHTML, selectedOffsets, toggleMark } from "../writing/formatting";
import { RichPassage } from "./RichPassage";
import { FindReplace } from "./FindReplace";

interface Props {
  doc: WritingDocument;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onEdit: (patch: Partial<WritingDocument>, group?: string) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

export function WritingEditor({ doc, selectedId, onSelect, onEdit, undo, redo, canUndo, canRedo }: Props) {
  const [finding, setFinding] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [zoom, setZoom] = useState(100);
  const selected = doc.blocks.find((b) => b.id === selectedId);
  const dialogueCount = doc.blocks.filter((b) => b.kind === "dialogue" && b.text.trim()).length;
  const narrationCount = doc.blocks.filter((b) => b.kind === "narration" && b.text.trim()).length;
  const words = doc.blocks.map((b) => b.text).join(" ").trim().split(/\s+/).filter(Boolean).length;

  function updateBlock(id: string, patch: Partial<WritingBlock>, group = "") {
    onEdit({ blocks: doc.blocks.map((b) => b.id === id ? { ...b, ...patch } : b) }, group);
  }
  function add(kind: BlockKind) {
    if (doc.blocks.length >= 1000) return;
    const block = newBlock(kind);
    const index = doc.blocks.findIndex((b) => b.id === selectedId);
    const blocks = [...doc.blocks];
    blocks.splice(index < 0 ? blocks.length : index + 1, 0, block);
    onEdit({ blocks });
    onSelect(block.id);
    requestAnimationFrame(() => document.getElementById(`block-${block.id}`)?.focus());
  }
  function move(index: number, direction: number) {
    const blocks = [...doc.blocks];
    [blocks[index], blocks[index + direction]] = [blocks[index + direction], blocks[index]];
    onEdit({ blocks });
  }

  function format(kind: MarkKind) {
    if (!selected) return;
    const field = document.getElementById(`block-${selected.id}`);
    const range = field ? selectedOffsets(field) : null;
    const start = range && range.end > range.start ? range.start : 0;
    const end = range && range.end > range.start ? range.end : selected.text.length;
    updateBlock(selected.id, { marks: toggleMark(selected.marks ?? [], start, end, kind) });
  }
  function find() {
    setFinding(true);
    requestAnimationFrame(() => document.getElementById("find-text")?.focus());
  }

  return (
    <section className={`writing-desk ${focusMode ? "focus-mode" : ""}`} aria-label="Document editor" onKeyDown={(event) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === "f") { event.preventDefault(); find(); }
      if (key === "z") { event.preventDefault(); if (event.shiftKey) redo(); else undo(); }
      if (key === "y") { event.preventDefault(); redo(); }
      const mark = ({ b: "bold", i: "italic", u: "underline" } as const)[key as "b" | "i" | "u"];
      if (mark) { event.preventDefault(); format(mark); }
    }}>
      <div className="editor-toolbar" role="toolbar" aria-label="Document tools">
        <div className="format-switch" role="group" aria-label="Document format">
          <button aria-pressed={doc.format === "script"} onClick={() => onEdit({ format: "script" })}>Script</button>
          <button aria-pressed={doc.format === "novel"} onClick={() => onEdit({ format: "novel" })}>Novel</button>
        </div>
        <span className="toolbar-divider" />
        <button disabled={doc.blocks.length >= 1000} onClick={() => add("dialogue")} title="Add a spoken line after the selected passage">+ Dialogue</button>
        <button disabled={doc.blocks.length >= 1000} onClick={() => add("narration")}>+ Narration</button>
        <button disabled={doc.blocks.length >= 1000} onClick={() => add("heading")}>+ Heading</button>
        <span className="toolbar-spacer" />
        <button aria-label="Undo edit" title="Undo edit" onClick={undo} disabled={!canUndo}>↶</button>
        <button aria-label="Redo edit" title="Redo edit" onClick={redo} disabled={!canRedo}>↷</button>
      </div>
      <div className="formatting-toolbar" role="toolbar" aria-label="Text formatting">
        <select aria-label="Font family" disabled={!selected} value={selected?.font ?? "serif"} onChange={(e) => selected && updateBlock(selected.id, { font: e.target.value as WritingBlock["font"] })}><option value="serif">Serif</option><option value="sans">Sans serif</option><option value="mono">Monospace</option></select>
        <select aria-label="Font size" disabled={!selected} value={selected?.size ?? 16} onChange={(e) => selected && updateBlock(selected.id, { size: Number(e.target.value) })}>{[12, 14, 16, 18, 20, 24, 28, 32].map((size) => <option key={size}>{size}</option>)}</select>
        {([['bold', 'B'], ['italic', 'I'], ['underline', 'U']] as const).map(([kind, label]) => <button className={`format-${kind}`} key={kind} title={`${kind} (Ctrl/⌘+${label}) — select words or a whole passage`} aria-label={kind[0].toUpperCase() + kind.slice(1)} disabled={!selected?.text} onMouseDown={(e) => e.preventDefault()} onClick={() => format(kind)}>{label}</button>)}
        <select aria-label="Paragraph alignment" disabled={!selected} value={selected?.alignment ?? "left"} onChange={(e) => selected && updateBlock(selected.id, { alignment: e.target.value as WritingBlock["alignment"] })}><option value="left">Align left</option><option value="center">Center</option><option value="right">Align right</option><option value="justify">Justify</option></select>
        <select aria-label="List style" disabled={!selected} value={selected?.listStyle ?? "none"} onChange={(e) => selected && updateBlock(selected.id, { listStyle: e.target.value as WritingBlock["listStyle"] })}><option value="none">No list</option><option value="bullet">• Bullets</option><option value="number">1. Numbered</option></select>
        <button title="Clear formatting from selected passage" disabled={!selected} onClick={() => selected && updateBlock(selected.id, { marks: [], alignment: "left", font: "serif", size: 16, listStyle: "none" })}>Clear</button>
        <button onClick={find} title="Find and replace (Ctrl/⌘+F)">Find</button>
        <button onClick={() => window.print()}>Print</button>
        <button aria-pressed={focusMode} onClick={() => setFocusMode(!focusMode)}>{focusMode ? "Exit focus" : "Focus"}</button>
      </div>
      {finding && <FindReplace blocks={doc.blocks} onChange={(blocks) => onEdit({ blocks })} onSelect={onSelect} onClose={() => setFinding(false)} />}
      <div className="paper-area">
        <div className={`manuscript ${doc.format}`} style={{ zoom: zoom / 100 }}>
          <div className="paper-kicker"><span>{doc.format === "script" ? "An original script" : "A novel in progress"}</span><span>Decalove / Writing Studio</span></div>
          <input className="manuscript-title" aria-label="Document title" value={doc.title} maxLength={200} placeholder="Untitled story" onChange={(e) => onEdit({ title: e.target.value }, "title")} />
          <p className="paper-subtitle">{doc.theme || "A place for your next story."}</p>
          <div className="paper-rule" />
          {doc.blocks.every((b) => !b.text.trim()) && <p className="editor-hint">Start with a place, a voice, or something left unsaid.<br />Write below, or build a scene with your AI writing partner.</p>}
          <div className="manuscript-blocks">
            {doc.blocks.map((block, index) => (
              <div key={block.id} className={`manuscript-block ${block.kind} list-${block.listStyle ?? "none"} ${selectedId === block.id ? "selected" : ""}`} onFocus={() => onSelect(block.id)}>
                <span className="block-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                {block.kind === "dialogue" && <input className="block-speaker" aria-label={`Speaker for passage ${index + 1}`} value={block.speaker} placeholder="CHARACTER" maxLength={100} onChange={(e) => updateBlock(block.id, { speaker: e.target.value }, `speaker-${block.id}`)} />}
                <RichPassage block={block} label={`${block.kind === "dialogue" ? "Dialogue" : block.kind === "heading" ? "Heading" : "Narration"} passage ${index + 1}`}
                  placeholder={block.kind === "dialogue" ? "What do they say?" : block.kind === "heading" ? "A chapter or scene title…" : "Set the scene. Let us notice something…"}
                  onChange={(patch) => updateBlock(block.id, patch, `text-${block.id}`)} />
                <div className="block-controls">
                  <select aria-label={`Type of passage ${index + 1}`} value={block.kind} onChange={(e) => updateBlock(block.id, { kind: e.target.value as BlockKind, speaker: e.target.value === "dialogue" ? block.speaker : "" })}>
                    <option value="dialogue">Dialogue</option><option value="narration">Narration</option><option value="heading">Heading</option>
                  </select>
                  <button disabled={index === 0} onClick={() => move(index, -1)} aria-label={`Move passage ${index + 1} up`}>↑</button>
                  <button disabled={index === doc.blocks.length - 1} onClick={() => move(index, 1)} aria-label={`Move passage ${index + 1} down`}>↓</button>
                  <button onClick={() => onEdit({ blocks: doc.blocks.filter((b) => b.id !== block.id) })} aria-label={`Remove passage ${index + 1}`}>×</button>
                </div>
              </div>
            ))}
          </div>
          <button className="add-passage" disabled={doc.blocks.length >= 1000} onClick={() => add(doc.format === "script" ? "dialogue" : "narration")}>+ Keep writing</button>
        </div>
      </div>
      <footer className="editor-status"><span>{words.toLocaleString()} words · {Math.max(1, Math.ceil(words / 200))} min read</span><span>{dialogueCount} / {doc.dialogueCount} dialogue lines</span><span>{narrationCount} narration passages</span><select aria-label="Page zoom" value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>{[80, 90, 100, 110, 125].map((value) => <option key={value} value={value}>{value}%</option>)}</select></footer>
      <article className="print-manuscript"><h1>{doc.title}</h1>{doc.blocks.filter((b) => b.text.trim()).map((b) => <section className={`list-${b.listStyle ?? "none"}`} key={b.id} style={{ textAlign: b.alignment, fontFamily: b.font ? FONTS[b.font] : undefined, fontSize: `${b.size ?? 16}px` }}>
        {b.kind === "dialogue" && <strong>{b.speaker}</strong>}
        <div className={b.kind} dangerouslySetInnerHTML={{ __html: richHTML(b.text, b.marks) }} />
      </section>)}</article>
    </section>
  );
}
