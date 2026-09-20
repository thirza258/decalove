import { useState } from "react";
import { replaceRange, selectOffsets } from "../writing/formatting";
import type { WritingBlock } from "../writing/model";

export function FindReplace({ blocks, onChange, onSelect, onClose }: {
  blocks: WritingBlock[]; onChange: (blocks: WritingBlock[]) => void;
  onSelect: (id: string) => void; onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [replacement, setReplacement] = useState("");
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [cursor, setCursor] = useState(-1);
  const [notice, setNotice] = useState("");
  const matches: { id: string; start: number; end: number }[] = [];
  if (query) for (const block of blocks) {
    const escaped = Array.from(query, (char) => "\\^$.*+?()[]{}|".includes(char) ? "\\" + char : char).join("");
    for (const found of block.text.matchAll(new RegExp(escaped, caseSensitive ? "gu" : "giu"))) {
      if (matches.length >= 10000) break;
      matches.push({ id: block.id, start: found.index, end: found.index + found[0].length });
    }
  }
  function reveal(index: number) {
    const target = matches[index % matches.length];
    if (!target) return;
    setCursor(index % matches.length); onSelect(target.id);
    requestAnimationFrame(() => {
      const field = document.getElementById(`block-${target.id}`);
      if (field) { field.focus(); field.scrollIntoView({ block: "center" }); selectOffsets(field, target.start, target.end); }
    });
  }
  function replace(all: boolean) {
    const selected = all ? matches : [matches[Math.max(0, cursor) % matches.length]].filter(Boolean);
    const updated = blocks.map((block) => selected.filter((m) => m.id === block.id).reverse().reduce(
      (value, match) => replaceRange(value, match.start, match.end, replacement), block,
    ));
    if (updated.some((b) => b.text.length > 12000)) { setNotice("That replacement would make a passage too long."); return; }
    onChange(updated); setCursor(-1); setNotice(`Replaced ${selected.length} ${selected.length === 1 ? "match" : "matches"}.`);
  }
  return <section className="find-replace" aria-label="Find and replace">
    <div><input id="find-text" aria-label="Find text" placeholder="Find in manuscript" value={query} onChange={(e) => { setQuery(e.target.value); setCursor(-1); setNotice(""); }} /><button onClick={() => reveal(cursor + 1)} disabled={!matches.length}>Next match</button><button aria-label="Close find and replace" onClick={onClose}>×</button></div>
    <div><input aria-label="Replacement text" placeholder="Replace with" value={replacement} onChange={(e) => setReplacement(e.target.value)} /><button onClick={() => replace(false)} disabled={!matches.length}>Replace</button><button onClick={() => replace(true)} disabled={!matches.length}>Replace all</button></div>
    <div><label><input type="checkbox" checked={caseSensitive} onChange={(e) => setCaseSensitive(e.target.checked)} /> Match case</label><span role="status">{notice || `${matches.length} matches`}</span></div>
  </section>;
}
