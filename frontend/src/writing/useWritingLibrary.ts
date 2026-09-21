import { useRef, useState } from "react";
import { newDocument, normalizeDocument } from "./model";
import type { Library, WritingDocument, WritingFormat } from "./model";
import { useWritingWorkspace } from "./workspaceContext";

export function useWritingLibrary() {
  const workspace = useWritingWorkspace();
  const library = workspace.data.library;
  const [history, setHistory] = useState<{ past: WritingDocument[]; future: WritingDocument[] }>({ past: [], future: [] });
  const lastGroup = useRef("");
  // Normalised here so every editor, panel and board can read the newer fields.
  const doc = normalizeDocument(library.documents.find((d) => d.id === library.activeId)!);

  function save(next: Library) {
    workspace.update((data) => ({ ...data, library: next }));
  }

  function replace(next: WritingDocument) {
    save({ ...library, documents: library.documents.map((d) => d.id === next.id ? next : d) });
  }

  function edit(patch: Partial<WritingDocument>, group = "") {
    if (!group || lastGroup.current !== group) {
      setHistory((h) => ({ past: [...h.past.slice(-49), doc], future: [] }));
    } else {
      setHistory((h) => ({ ...h, future: [] }));
    }
    lastGroup.current = group;
    replace({ ...doc, ...patch, updatedAt: new Date().toISOString() });
  }

  function open(id: string) {
    save({ ...library, activeId: id });
    setHistory({ past: [], future: [] });
    lastGroup.current = "";
  }

  function add(format: WritingFormat = "script", exercise = "", imported?: WritingDocument) {
    if (library.documents.length >= 50) return null;
    const fresh = imported ?? newDocument(format, exercise);
    save({ ...library, activeId: fresh.id, documents: [...library.documents, fresh] });
    setHistory({ past: [], future: [] });
    lastGroup.current = "";
    return fresh;
  }

  function remove() {
    const remaining = library.documents.filter((d) => d.id !== doc.id);
    if (!remaining.length) remaining.push(newDocument(doc.format));
    save({ ...library, activeId: remaining[0].id, documents: remaining });
    setHistory({ past: [], future: [] });
    lastGroup.current = "";
  }

  function undo() {
    const previous = history.past.at(-1);
    if (!previous) return;
    replace(previous);
    setHistory({ past: history.past.slice(0, -1), future: [doc, ...history.future] });
    lastGroup.current = "";
  }
  function redo() {
    const next = history.future[0];
    if (!next) return;
    replace(next);
    setHistory({ past: [...history.past, doc], future: history.future.slice(1) });
    lastGroup.current = "";
  }
  return { doc, documents: library.documents, edit, open, add, remove, undo, redo,
    canUndo: history.past.length > 0, canRedo: history.future.length > 0 };
}
