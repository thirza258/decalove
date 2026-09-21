import { useEffect, useRef, useState } from "react";
import { requestWriting } from "../writing/api";
import { toRequest } from "../writing/model";
import type { WritingAction, WritingBlock, WritingDocument, WritingRequest, WritingSuggestion } from "../writing/model";

interface Attempt { request: WritingRequest; original: WritingBlock | null }
interface Props {
  doc: WritingDocument;
  /** Availability is checked once for the whole studio; the storyboard needs it too. */
  status: "checking" | "ready" | "unavailable";
  onStatus: (status: "checking" | "ready" | "unavailable") => void;
  selectedId: string | null;
  onEdit: (patch: Partial<WritingDocument>, group?: string) => void;
  onInsert: (blocks: WritingSuggestion["blocks"], original: WritingBlock | null) => string | null;
}

export function WritingAssistant({ doc, status, onStatus, selectedId, onEdit, onInsert }: Props) {
  const [action, setAction] = useState<WritingAction>("starter");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [suggestion, setSuggestion] = useState<WritingSuggestion | null>(null);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const pending = useRef({ controller: null as AbortController | null, sequence: 0 });
  const selected = doc.blocks.find((b) => b.id === selectedId);
  const counted = ["starter", "continue", "dialogue"].includes(action);
  const source = attempt?.original;
  const current = doc.blocks.find((b) => b.id === source?.id);
  const rewriteChanged = !!source && (!current || current.text !== source.text || current.kind !== source.kind || current.speaker !== source.speaker);

  useEffect(() => {
    const requests = pending.current;
    return () => { requests.controller?.abort(); requests.sequence++; };
  }, []);

  async function generate(retry?: Attempt) {
    if (pending.current.controller) return;
    const snapshot = retry ?? {
      request: toRequest(doc, action, selectedId),
      original: action === "rewrite" && selected ? { ...selected } : null,
    };
    if (snapshot.request.action === "rewrite" && !snapshot.original?.text.trim()) {
      setError("Select a passage in your document to rewrite first."); return;
    }
    const abort = new AbortController();
    pending.current.controller = abort;
    const requestId = ++pending.current.sequence;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; abort.abort(); }, 120000);
    setBusy(true); setError(""); setNotice(""); setSuggestion(null); setAttempt(snapshot);
    try {
      const response = await requestWriting(snapshot.request, abort.signal);
      if (pending.current.sequence !== requestId) return;
      setSuggestion(response); onStatus("ready");
    } catch (failure) {
      if (pending.current.sequence !== requestId) return;
      setError(timedOut ? "The writing request timed out. Your draft is safe. Retry when ready."
        : failure instanceof Error && failure.name !== "TypeError" ? failure.message
        : "The writing service could not be reached. Keep writing, or retry this request.");
    } finally {
      clearTimeout(timer);
      if (pending.current.sequence === requestId) { pending.current.controller = null; setBusy(false); }
    }
  }

  function cancel() {
    pending.current.sequence++;
    pending.current.controller?.abort(); pending.current.controller = null;
    setBusy(false); setNotice("Request cancelled. Your draft is unchanged.");
  }
  function accept() {
    if (!suggestion || rewriteChanged) return;
    const problem = onInsert(suggestion.blocks, source ?? null);
    if (problem) { setError(problem); return; }
    setSuggestion(null); setError(""); setNotice(source ? "Passage updated. You can keep editing or undo the change." : "Added to your draft. Every line is yours to edit.");
  }

  return (
    <aside className="assistant-panel" aria-label="AI writing partner">
      <div className="panel-heading"><span className="assistant-spark" aria-hidden="true">✳</span><div><h2>Your writing partner</h2><p>A little help. Your voice.</p></div></div>
      <div className={`assistant-availability ${status}`}><span aria-hidden="true" />{status === "ready" ? "AI assistance ready" : status === "checking" ? "Checking AI availability…" : "AI is currently unavailable"}</div>
      {status === "unavailable" && <p className="panel-help">You can write, save, and take courses now. Try a request when AI assistance is available.</p>}
      <label htmlFor="writing-action">What are we working on?</label>
      <select id="writing-action" value={action} onChange={(e) => setAction(e.target.value as WritingAction)}>
        <option value="starter">Draft a scene</option><option value="continue">Continue the story</option>
        <option value="dialogue">Write a conversation</option><option value="narrate">Add narration</option><option value="rewrite">Rewrite selected passage</option>
      </select>
      {counted && <div className="dialogue-target"><div><label htmlFor="dialogue-target">Dialogue lines</label><small>With narration between exchanges</small></div><select id="dialogue-target" value={doc.dialogueCount} onChange={(e) => onEdit({ dialogueCount: Number(e.target.value) })}>{[10, 25, 50, 75, 100].map((n) => <option value={n} key={n}>{n}</option>)}{![10, 25, 50, 75, 100].includes(doc.dialogueCount) && <option value={doc.dialogueCount}>{doc.dialogueCount}</option>}</select></div>}
      {action === "rewrite" && <p className="selection-note">{selected?.kind === "image" ? "An illustration cannot be rewritten. Select a written passage."
        : selected?.text.trim() ? `Selected: ${selected.text.slice(0, 110)}${selected.text.length > 110 ? "…" : ""}` : "Click a passage in the document to select it."}</p>}
      <label htmlFor="writing-prompt">Your instructions</label>
      <textarea id="writing-prompt" value={doc.prompt} maxLength={4000} rows={5} placeholder="Two old friends meet again. Keep the tension quiet. Let what they don't say matter…" onChange={(e) => onEdit({ prompt: e.target.value }, "prompt")} />
      <div className="context-note"><span aria-hidden="true">◎</span><p>Uses your current draft, story brief, characters, and reference notes. Add any details you want it to preserve.</p></div>
      <div className="assistant-actions">
        <button className="writing-button primary" onClick={() => void generate()} disabled={busy || (action === "rewrite" && (!selected?.text.trim() || selected.kind === "image"))}>{busy ? "Writing your suggestion…" : "✳ Generate suggestion"}</button>
        {busy && <button className="text-button" onClick={cancel}>Cancel request</button>}
      </div>
      {busy && <p className="panel-help" role="status">You can keep editing while your suggestion is prepared. A full scene can take a minute or two.</p>}
      {error && <div className="writing-error" role="alert"><p>{error}</p>{attempt && !busy && <button className="text-button" onClick={() => void generate(attempt)}>Retry same request ↻</button>}</div>}
      {notice && <p className="writing-notice" role="status">{notice}</p>}
      {suggestion && <section className="suggestion-review" aria-label="Review AI suggestion">
        <p className="eyebrow">Your suggestion</p><h3>Make it your own.</h3><p>{suggestion.summary}</p>
        <small>{suggestion.blocks.filter((b) => b.kind === "dialogue").length} dialogue lines · {suggestion.blocks.filter((b) => b.kind === "narration").length} narration passages</small>
        <div className="suggestion-blocks">{suggestion.blocks.map((block, index) => <div key={index} className={`suggestion-block ${block.kind}`}>
          <label htmlFor={`suggestion-${index}`}>{block.kind === "dialogue" ? block.speaker : block.kind === "heading" ? "Heading" : "Narration"}<span className="sr-only"> suggestion {index + 1}</span></label>
          <textarea id={`suggestion-${index}`} value={block.text} maxLength={12000} rows={Math.min(6, Math.max(2, Math.ceil(block.text.length / 35)))} onChange={(e) => setSuggestion({ ...suggestion, blocks: suggestion.blocks.map((b, i) => i === index ? { ...b, text: e.target.value } : b) })} />
        </div>)}</div>
        {rewriteChanged && <p className="writing-error">The original passage changed while this suggestion was being written. Generate a new rewrite to preserve your latest edits.</p>}
        <div className="suggestion-buttons"><button className="writing-button primary" onClick={accept} disabled={rewriteChanged || suggestion.blocks.some((b) => !b.text.trim())}>{source ? "Replace selected passage" : "Insert at end"}</button><button className="text-button" onClick={() => { setSuggestion(null); setNotice("Suggestion discarded. Your draft is unchanged."); }}>Discard</button></div>
      </section>}
      <div className="assistant-tip"><p className="eyebrow">A note from the writing room</p><p>Give each character a different want. Let the conversation change what they are willing to say.</p><a href="#/courses">Explore the dialogue course ↗</a></div>
    </aside>
  );
}
