import { useEffect, useRef, useState } from "react";
import { writingStatus } from "../writing/api";
import { downloadFile, exportText, importText, isDocument, newBlock, newDocument, normalizeDocument, THEME_STARTERS } from "../writing/model";
import type { BlockImage, PictureTarget, WritingBlock, WritingSuggestion } from "../writing/model";
import { useWritingLibrary } from "../writing/useWritingLibrary";
import { useWritingWorkspace } from "../writing/workspaceContext";
import { WritingNav } from "./WritingNav";
import { WritingAssistant } from "./WritingAssistant";
import { WritingEditor } from "./WritingEditor";
import { NotesPanel } from "./NotesPanel";
import { StoryboardBoard } from "./StoryboardBoard";
import { ImagePicker } from "./ImagePicker";

export default function WritingStudio({ exercise, onExerciseUsed }: { exercise: string; onExerciseUsed: () => void }) {
  const library = useWritingLibrary();
  const workspace = useWritingWorkspace();
  const { doc, edit } = library;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [view, setView] = useState<"manuscript" | "storyboard">("manuscript");
  const [sidePanel, setSidePanel] = useState<"assistant" | "notes">("assistant");
  const [commentOn, setCommentOn] = useState<string | null>(null);
  const [picker, setPicker] = useState<{ label: string; target: PictureTarget } | null>(null);
  const [aiStatus, setAiStatus] = useState<"checking" | "ready" | "unavailable">("checking");
  const [mobilePanel, setMobilePanel] = useState<"brief" | "editor" | "assistant">("editor");
  const fileInput = useRef<HTMLInputElement>(null);
  const usedExercise = useRef(false);
  const exerciseError = exercise && library.documents.length >= 50
    ? "This workspace has 50 documents. Export and remove a completed document to start the exercise." : "";

  useEffect(() => {
    if (exercise && !usedExercise.current) {
      if (!library.add("script", exercise)) {
        return;
      }
      usedExercise.current = true;
      onExerciseUsed();
    }
  }, [exercise, library, onExerciseUsed]);

  // One availability check for the studio: the assistant and the storyboard share it.
  useEffect(() => {
    const check = new AbortController();
    const timeout = setTimeout(() => check.abort(), 5000);
    let active = true;
    void writingStatus(check.signal).then((available) => {
      if (active) setAiStatus(available ? "ready" : "unavailable");
    }).catch(() => { if (active) setAiStatus("unavailable"); }).finally(() => clearTimeout(timeout));
    return () => { active = false; check.abort(); clearTimeout(timeout); };
  }, []);

  function insert(blocks: WritingSuggestion["blocks"], original: WritingBlock | null): string | null {
    const fresh = blocks.map((b) => newBlock(b.kind, b.text, b.speaker));
    let next: WritingBlock[];
    if (original) {
      const current = doc.blocks.find((b) => b.id === original.id);
      if (!current || current.text !== original.text || current.kind !== original.kind || current.speaker !== original.speaker) return "The selected passage has changed. Generate a new rewrite first.";
      // Keep paragraph styling, including formatting edits made during generation.
      // Word ranges no longer apply to rewritten text.
      fresh[0] = { ...current, text: fresh[0].text, marks: [] };
      next = doc.blocks.flatMap((b) => b.id === original.id ? fresh : [b]);
    } else {
      next = [...doc.blocks.filter((b) => b.text.trim() || b.speaker.trim() || b.kind === "image"), ...fresh];
    }
    if (next.length > 1000) return "This document has reached 1,000 passages. Start a new chapter in a new document.";
    edit({ blocks: next });
    setSelectedId(fresh[0]?.id ?? null);
    setMobilePanel("editor");
    return null;
  }

  /** Reads the document as it is now, not as it was when the chooser was opened. */
  function placeImage(target: PictureTarget, image: BlockImage) {
    if (target.kind === "panel") {
      edit({ storyboard: doc.storyboard.map((p) => p.id === target.id ? { ...p, image } : p) });
      return;
    }
    if (target.kind === "replace") {
      // A replaced picture keeps the width the writer chose for that passage.
      edit({ blocks: doc.blocks.map((b) => b.id === target.id
        ? { ...b, image: { ...image, width: b.image?.width ?? image.width } } : b) });
      return;
    }
    if (doc.blocks.length >= 1000) { setError("This document has reached 1,000 passages. Start a new chapter in a new document."); return; }
    const block = { ...newBlock("image"), image };
    const blocks = [...doc.blocks];
    const index = blocks.findIndex((b) => b.id === selectedId);
    blocks.splice(index < 0 ? blocks.length : index + 1, 0, block);
    edit({ blocks });
    setSelectedId(block.id);
  }

  function comment(blockId: string) {
    setSelectedId(blockId);
    setCommentOn(blockId);
    setSidePanel("notes");
    setMobilePanel("assistant");
    requestAnimationFrame(() => document.getElementById("comment-body")?.focus());
  }

  async function importFile(file: File) {
    setError("");
    try {
      if (library.documents.length >= 50) throw new Error("This workspace has 50 documents. Export and remove a completed document before importing another.");
      if (file.size > 2_000_000) throw new Error("Choose a text or Decalove backup file under 2 MB.");
      const text = await file.text();
      let imported;
      if (file.name.toLowerCase().endsWith(".json")) {
        const backup = JSON.parse(text) as { version: number; document: unknown };
        if (backup.version !== 1 || !isDocument(backup.document)) throw new Error("This is not a supported Decalove document backup.");
        imported = normalizeDocument({ ...backup.document, id: crypto.randomUUID(), updatedAt: new Date().toISOString() });
      } else {
        if (text.length > 120000) throw new Error("Import one chapter at a time (up to 120,000 characters).");
        const blocks = importText(text);
        if (!blocks.length || blocks.length > 1000 || blocks.some((b) => b.text.length > 12000)) throw new Error("Use 1–1,000 paragraphs, with at most 12,000 characters in each paragraph.");
        imported = { ...newDocument(doc.format), title: file.name.replace(/\.[^.]+$/, "").slice(0, 200), blocks };
      }
      library.add(imported.format, "", imported);
      setSelectedId(null); setMobilePanel("editor");
    } catch (failure) { setError(failure instanceof Error ? failure.message : "The file could not be read."); }
  }

  async function download(backup: boolean, local = false) {
    const name = (doc.title || "Untitled story").replace(/[^\p{L}\p{N} ._-]/gu, "_").slice(0, 120);
    setExporting(true); setError("");
    try {
      const content = local ? (backup ? JSON.stringify({ version: 1, document: doc }, null, 2) : exportText(doc))
        : await workspace.exportDocument(doc, backup ? "json" : "txt");
      downloadFile(`${name}.${backup ? "json" : "txt"}`, content, backup ? "application/json" : "text/plain;charset=utf-8");
    } catch { setError("The document file could not be saved to server storage. Retry, or download a local recovery copy."); }
    finally { setExporting(false); }
  }

  return (
    <div className="writing-app studio-app" onKeyDown={(event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); workspace.retry(); }
    }}>
      <WritingNav active="studio" />
      <header className="studio-heading">
        <h1>Writing Studio<span>.</span></h1>
        <div className="studio-view-switch" role="group" aria-label="Studio view">
          {([["manuscript", "Manuscript"], ["storyboard", "Storyboard"]] as const).map(([name, label]) => (
            <button key={name} aria-pressed={view === name} onClick={() => { setView(name); setMobilePanel("editor"); }}>
              {label}{name === "storyboard" && doc.storyboard.length ? ` · ${doc.storyboard.length}` : ""}
            </button>
          ))}
        </div>
        <div className="studio-file-actions"><span className="save-status" role="status">{workspace.status === "saved" ? workspace.temporary ? "Temporary server save" : "✓ Saved to workspace" : workspace.status === "saving" ? "Saving…" : workspace.status === "error" ? "Server save unavailable" : "Unsaved changes"}</span><button className="writing-button" onClick={() => fileInput.current?.click()}>Import</button><button className="writing-button" disabled={exporting} onClick={() => void download(false)}>Export .txt</button><button className="writing-button" disabled={exporting} onClick={() => void download(true)}>{exporting ? "Saving file…" : "Back up"}</button></div>
        <input hidden type="file" aria-label="Import manuscript" accept=".txt,.md,.json,text/plain,application/json" ref={fileInput} onChange={(e) => { const file = e.target.files?.[0]; if (file) void importFile(file); e.target.value = ""; }} />
      </header>
      {(workspace.error || error || exerciseError) && <div className="studio-alert writing-error" role="alert">{workspace.error || error || exerciseError}<div><button className="text-button" onClick={workspace.retry}>Retry server save</button><span> · </span><button className="text-button" onClick={() => void download(true, true)}>Download recovery copy</button><span> · </span><button className="text-button" onClick={workspace.reload}>Load server version</button></div></div>}
      {workspace.temporary && <p className="studio-storage-note">Server storage is running in temporary mode. Export a backup to keep your work across server restarts.</p>}
      <div className="mobile-studio-tabs" role="group" aria-label="Writing workspace panels">{([['brief', 'Story brief'], ['editor', view === "storyboard" ? 'Storyboard' : 'Manuscript'], ['assistant', sidePanel === "notes" ? 'Notes' : 'AI partner']] as const).map(([panel, title]) => <button key={panel} aria-pressed={mobilePanel === panel} onClick={() => setMobilePanel(panel)}>{title}</button>)}</div>
      <main className={`studio-layout show-${mobilePanel}`}>
        <aside className="story-panel" aria-label="Story brief">
          <div className="panel-heading"><h2>Your stories</h2><button className="small-add" aria-label="New document" disabled={library.documents.length >= 50} onClick={() => { library.add(); setSelectedId(null); }}>+</button></div>
          <label htmlFor="document-picker" className="sr-only">Open document</label>
          <select id="document-picker" value={doc.id} onChange={(e) => { library.open(e.target.value); setSelectedId(null); }}>{library.documents.map((d) => <option value={d.id} key={d.id}>{d.title || "Untitled story"}</option>)}</select>
          <div className="document-actions"><button className="text-button" onClick={workspace.retry} title="Save workspace (Ctrl/⌘+S)">Save now</button><button className="text-button" onClick={() => { if (window.confirm(`Remove “${doc.title || "Untitled story"}” from this workspace? Export a backup first if you want to keep it.`)) { library.remove(); setSelectedId(null); } }}>Remove document</button></div>
          <div className="panel-divider" />
          <p className="eyebrow">The story brief</p>
          <label htmlFor="story-genre">Genre</label>
          <input id="story-genre" value={doc.genre} maxLength={100} list="genre-ideas" onChange={(e) => edit({ genre: e.target.value }, "genre")} />
          <datalist id="genre-ideas">{["Contemporary", "Romance", "Fantasy", "Mystery", "Science fiction", "Literary fiction", "Adventure"].map((genre) => <option key={genre}>{genre}</option>)}</datalist>
          <label htmlFor="story-theme">The question underneath</label>
          <textarea id="story-theme" rows={3} maxLength={2000} placeholder="What is your story really exploring?" value={doc.theme} onChange={(e) => edit({ theme: e.target.value }, "theme")} />
          <details className="theme-starters"><summary>Need a theme starter?</summary><p>Choose a question and premise. You can change both.</p><div>{THEME_STARTERS.map((starter) => <button key={starter.name} onClick={() => edit({ theme: starter.theme, premise: starter.premise })}>{starter.name} <span aria-hidden="true">↗</span></button>)}</div></details>
          <label htmlFor="story-premise">Premise & setting</label>
          <textarea id="story-premise" rows={4} maxLength={5000} placeholder="Who wants what? Where are we, and what's in the way?" value={doc.premise} onChange={(e) => edit({ premise: e.target.value }, "premise")} />
          <label htmlFor="story-characters">Characters & their voices</label>
          <textarea id="story-characters" rows={4} maxLength={5000} placeholder="Mara — careful with words, wants to make amends.&#10;Jules — jokes when uncomfortable, wants an honest answer." value={doc.characters} onChange={(e) => edit({ characters: e.target.value }, "characters")} />
          <details className="reference-notes"><summary>Reference story & continuity notes {doc.reference && <span aria-label="Reference notes added">●</span>}</summary><label htmlFor="story-reference">Existing story or background</label><textarea id="story-reference" rows={8} maxLength={30000} placeholder="Paste your existing story, a chapter summary, or details the AI should know. Separate planned events from things already written." value={doc.reference} onChange={(e) => edit({ reference: e.target.value }, "reference")} /><small>Included with your current draft whenever you request AI help.</small></details>
          <div className="story-panel-note"><span aria-hidden="true">⌁</span><p>Drafts, pictures and lessons save to your workspace. Keep your <a href={`#/studio?workspace=${workspace.id}`}>private workspace link</a> to open it on another device. Backups include your story notes.</p></div>
        </aside>
        <div className="studio-center">
          {view === "manuscript"
            ? <WritingEditor key={`editor-${doc.id}`} doc={doc} selectedId={selectedId} onSelect={setSelectedId} onEdit={edit}
                onPickImage={(label, target) => setPicker({ label, target })} onComment={comment}
                undo={library.undo} redo={library.redo} canUndo={library.canUndo} canRedo={library.canRedo} />
            : <StoryboardBoard key={`board-${doc.id}`} doc={doc} onEdit={edit} aiReady={aiStatus === "ready"}
                onPickImage={(label, target) => setPicker({ label, target })} />}
        </div>
        <div className="studio-side">
          <div className="side-tabs" role="tablist" aria-label="Studio side panel">
            {([["assistant", "AI partner"], ["notes", `Notes${doc.comments.filter((c) => !c.resolved).length ? ` · ${doc.comments.filter((c) => !c.resolved).length}` : ""}`]] as const).map(([name, label]) => (
              <button key={name} role="tab" id={`side-tab-${name}`} aria-controls={`side-panel-${name}`}
                aria-selected={sidePanel === name} onClick={() => setSidePanel(name)}>{label}</button>
            ))}
          </div>
          {/* Both stay mounted: switching tabs must never abandon a request in flight. */}
          <div className="side-panel" role="tabpanel" id="side-panel-assistant" aria-labelledby="side-tab-assistant" hidden={sidePanel !== "assistant"}>
            <WritingAssistant key={`assistant-${doc.id}`} doc={doc} status={aiStatus} onStatus={setAiStatus}
              selectedId={selectedId} onEdit={edit} onInsert={insert} />
          </div>
          <div className="side-panel" role="tabpanel" id="side-panel-notes" aria-labelledby="side-tab-notes" hidden={sidePanel !== "notes"}>
            <NotesPanel doc={doc} onEdit={edit} target={commentOn} onTarget={setCommentOn}
              onSelect={(id) => { setSelectedId(id); setView("manuscript"); setMobilePanel("editor"); }} />
          </div>
        </div>
      </main>
      {picker && <ImagePicker label={picker.label} onClose={() => setPicker(null)}
        onInsert={(image) => { placeImage(picker.target, image); setPicker(null); }} />}
    </div>
  );
}
