import { useState } from "react";
import { MARK_COLORS, MAX_COMMENTS, MAX_NOTES } from "../writing/model";
import type { DocumentComment, DocumentNote, MarkColor, WritingDocument } from "../writing/model";

const AUTHOR_CACHE = "decalove.writing.author";
const readAuthor = () => {
  try { return localStorage.getItem(AUTHOR_CACHE) ?? ""; } catch { return ""; }
};
const rememberAuthor = (name: string) => {
  try { localStorage.setItem(AUTHOR_CACHE, name); } catch { /* A private window still comments. */ }
};
const when = (iso: string) => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

interface Props {
  doc: WritingDocument;
  onEdit: (patch: Partial<WritingDocument>, group?: string) => void;
  /** The passage the writer asked to comment on, owned by the studio around us. */
  target: string | null;
  onTarget: (blockId: string | null) => void;
  onSelect: (id: string) => void;
}

/**
 * Notes and comments: the margin of the manuscript. Comments hold on to a passage,
 * but never depend on it — a passage can be rewritten or deleted and the remark stays,
 * shown as unanchored, because losing the note with the paragraph is the worse failure.
 */
export function NotesPanel({ doc, onEdit, target, onTarget, onSelect }: Props) {
  const [author, setAuthor] = useState(readAuthor);
  const [draft, setDraft] = useState("");
  const [showResolved, setShowResolved] = useState(false);

  const anchor = doc.blocks.find((b) => b.id === target);
  const open = doc.comments.filter((c) => !c.resolved);
  const shown = showResolved ? doc.comments : open;
  const excerpt = (comment: DocumentComment) => {
    const block = doc.blocks.find((b) => b.id === comment.blockId);
    return block ? (block.text.trim() || block.image?.alt || "an empty passage").slice(0, 120) : "";
  };

  function addComment() {
    if (!draft.trim() || doc.comments.length >= MAX_COMMENTS) return;
    rememberAuthor(author.trim());
    const comment: DocumentComment = {
      id: crypto.randomUUID(), quote: (anchor?.text.trim() || anchor?.image?.alt || "").slice(0, 160),
      author: author.trim().slice(0, 60), body: draft.trim().slice(0, 1000), resolved: false,
      createdAt: new Date().toISOString(), ...(target ? { blockId: target } : {}),
    };
    onEdit({ comments: [comment, ...doc.comments] });
    setDraft(""); onTarget(null);
  }
  function editComment(id: string, patch: Partial<DocumentComment>) {
    onEdit({ comments: doc.comments.map((c) => c.id === id ? { ...c, ...patch } : c) });
  }
  function addNote() {
    if (doc.notes.length >= MAX_NOTES) return;
    const note: DocumentNote = { id: crypto.randomUUID(), title: "", body: "", updatedAt: new Date().toISOString() };
    onEdit({ notes: [note, ...doc.notes] });
    requestAnimationFrame(() => document.getElementById(`note-title-${note.id}`)?.focus());
  }
  function editNote(id: string, patch: Partial<DocumentNote>, group: string) {
    onEdit({ notes: doc.notes.map((n) => n.id === id ? { ...n, ...patch, updatedAt: new Date().toISOString() } : n) }, group);
  }

  return (
    <aside className="assistant-panel notes-panel" aria-label="Notes and comments">
      <div className="panel-heading"><span className="assistant-spark" aria-hidden="true">✎</span>
        <div><h2>Notes &amp; comments</h2><p>The margin of your manuscript.</p></div></div>

      <section aria-label="Comments">
        <div className="notes-section-title"><p className="eyebrow">Comments</p>
          <span>{open.length} open{doc.comments.length > open.length ? ` · ${doc.comments.length - open.length} resolved` : ""}</span></div>
        <p className="selection-note">{anchor
          ? `On passage ${doc.blocks.indexOf(anchor) + 1}: ${(anchor.text.trim() || anchor.image?.alt || "an empty passage").slice(0, 90)}`
          : "A general comment on this document. Select a passage and choose Comment to attach one."}</p>
        <label htmlFor="comment-author">Your name (optional)</label>
        <input id="comment-author" value={author} maxLength={60} placeholder="Who is writing this note?"
          onChange={(event) => setAuthor(event.target.value)} />
        <label htmlFor="comment-body">Comment</label>
        <textarea id="comment-body" rows={3} maxLength={1000} value={draft} placeholder="What should change here, and why?"
          onChange={(event) => setDraft(event.target.value)} />
        <div className="comment-compose-actions">
          <button className="writing-button primary" disabled={!draft.trim() || doc.comments.length >= MAX_COMMENTS} onClick={addComment}>Add comment</button>
          {target && <button className="text-button" onClick={() => onTarget(null)}>Detach from passage</button>}
        </div>
        {doc.comments.length >= MAX_COMMENTS && <p className="panel-help">This document holds {MAX_COMMENTS} comments. Resolve and delete a few to add more.</p>}
        {doc.comments.length > open.length && <label className="notes-toggle"><input type="checkbox" checked={showResolved}
          onChange={(event) => setShowResolved(event.target.checked)} /> Show resolved comments</label>}
        <ul className="comment-list">
          {shown.map((comment) => (
            <li key={comment.id} className={`comment-card ${comment.resolved ? "resolved" : ""}`}>
              <div className="comment-meta"><strong>{comment.author || "Anonymous"}</strong><span>{when(comment.createdAt)}</span></div>
              {comment.blockId
                ? (excerpt(comment)
                  ? <button className="comment-anchor" onClick={() => onSelect(comment.blockId!)}>“{excerpt(comment)}”</button>
                  : <p className="comment-orphan">The passage this refers to was removed{comment.quote ? `: “${comment.quote}”` : "."}</p>)
                : <p className="comment-orphan">On the whole document.</p>}
              <p className="comment-body">{comment.body}</p>
              <div className="comment-actions">
                <button className="text-button" onClick={() => editComment(comment.id, { resolved: !comment.resolved })}>{comment.resolved ? "Reopen" : "Resolve"}</button>
                <button className="text-button" onClick={() => onEdit({ comments: doc.comments.filter((c) => c.id !== comment.id) })}>Delete</button>
              </div>
            </li>
          ))}
        </ul>
        {!shown.length && <p className="panel-help">No open comments. Select a passage and choose Comment to leave one.</p>}
      </section>

      <section aria-label="Notes" className="notes-block">
        <div className="notes-section-title"><p className="eyebrow">Notes</p>
          <button className="small-add" aria-label="New note" disabled={doc.notes.length >= MAX_NOTES} onClick={addNote}>+</button></div>
        {!doc.notes.length && <p className="panel-help">Keep research, reminders and cut lines here. Notes save with the document and travel in its backup.</p>}
        <ul className="note-list">
          {doc.notes.map((note) => (
            <li key={note.id} className={`note-card ${note.color ? `note-${note.color}` : ""}`}>
              <input id={`note-title-${note.id}`} aria-label="Note title" value={note.title} maxLength={120} placeholder="Title"
                onChange={(event) => editNote(note.id, { title: event.target.value }, `note-title-${note.id}`)} />
              <textarea aria-label={`Note: ${note.title || "untitled"}`} rows={3} maxLength={2000} value={note.body} placeholder="Something to remember…"
                onChange={(event) => editNote(note.id, { body: event.target.value }, `note-body-${note.id}`)} />
              <div className="note-actions">
                <select aria-label={`Colour of note: ${note.title || "untitled"}`} value={note.color ?? ""}
                  onChange={(event) => editNote(note.id, { color: (event.target.value || undefined) as MarkColor | undefined }, "")}>
                  <option value="">No colour</option>
                  {MARK_COLORS.map((color) => <option key={color.id} value={color.id}>{color.label}</option>)}
                </select>
                <button className="text-button" onClick={() => onEdit({ notes: doc.notes.filter((n) => n.id !== note.id) })}>Delete note</button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
