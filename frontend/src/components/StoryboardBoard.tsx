import { useEffect, useRef, useState } from "react";
import { requestStoryboard } from "../writing/api";
import { MAX_PANELS, SHOTS, newPanel, panelsFromManuscript, toStoryboardRequest } from "../writing/model";
import type { PictureTarget, StoryboardPanel, StoryboardRequest, StoryboardSuggestion, WritingDocument } from "../writing/model";
import { useWritingWorkspace } from "../writing/workspaceContext";

interface Props {
  doc: WritingDocument;
  onEdit: (patch: Partial<WritingDocument>, group?: string) => void;
  onPickImage: (label: string, target: PictureTarget) => void;
  aiReady: boolean;
}

const shotLabel = (shot: StoryboardPanel["shot"]) => SHOTS.find((s) => s.id === shot)?.label ?? shot;

/**
 * The scene as frames. Panels are the writer's: the manuscript can propose a first
 * pass and the AI can draft a shot list, but nothing here edits the manuscript back.
 */
export function StoryboardBoard({ doc, onEdit, onPickImage, aiReady }: Props) {
  const workspace = useWritingWorkspace();
  const panels = doc.storyboard;
  const [panelCount, setPanelCount] = useState(8);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [suggestion, setSuggestion] = useState<StoryboardSuggestion | null>(null);
  const [attempt, setAttempt] = useState<StoryboardRequest | null>(null);
  const pending = useRef({ controller: null as AbortController | null, sequence: 0 });
  const room = MAX_PANELS - panels.length;

  useEffect(() => {
    const requests = pending.current;
    return () => { requests.controller?.abort(); requests.sequence++; };
  }, []);

  function save(next: StoryboardPanel[], message = "") {
    onEdit({ storyboard: next.slice(0, MAX_PANELS) });
    setNotice(message);
  }
  function editPanel(id: string, patch: Partial<StoryboardPanel>, group = "") {
    onEdit({ storyboard: panels.map((p) => p.id === id ? { ...p, ...patch } : p) }, group);
  }
  function move(index: number, direction: number) {
    const next = [...panels];
    [next[index], next[index + direction]] = [next[index + direction], next[index]];
    save(next);
  }
  function buildFromManuscript() {
    const drafted = panelsFromManuscript(doc);
    if (!drafted.length) { setError("Write some of the scene first — a heading, narration or a line of dialogue."); return; }
    setError("");
    save([...panels, ...drafted].slice(0, MAX_PANELS),
      `Added ${Math.min(drafted.length, room)} panel${Math.min(drafted.length, room) === 1 ? "" : "s"} from the manuscript. Every one is yours to change.`);
  }

  async function draft(retry?: StoryboardRequest) {
    if (pending.current.controller) return;
    const request = retry ?? toStoryboardRequest(doc, panelCount);
    const abort = new AbortController();
    pending.current.controller = abort;
    const requestId = ++pending.current.sequence;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; abort.abort(); }, 120000);
    setBusy(true); setError(""); setNotice(""); setSuggestion(null); setAttempt(request);
    try {
      const response = await requestStoryboard(request, abort.signal);
      if (pending.current.sequence !== requestId) return;
      setSuggestion(response);
    } catch (failure) {
      if (pending.current.sequence !== requestId) return;
      setError(timedOut ? "The storyboard request timed out. Your panels are safe. Retry when ready."
        : failure instanceof Error && failure.name !== "TypeError" ? failure.message
        : "The writing service could not be reached. Keep working, or retry this request.");
    } finally {
      clearTimeout(timer);
      if (pending.current.sequence === requestId) { pending.current.controller = null; setBusy(false); }
    }
  }
  function cancel() {
    pending.current.sequence++;
    pending.current.controller?.abort(); pending.current.controller = null;
    setBusy(false); setNotice("Request cancelled. Your storyboard is unchanged.");
  }
  function acceptSuggestion() {
    if (!suggestion) return;
    const added = suggestion.panels.slice(0, room).map((panel) => newPanel(panel));
    save([...panels, ...added], `Added ${added.length} panel${added.length === 1 ? "" : "s"}. Edit any frame, or reorder them.`);
    setSuggestion(null);
  }

  return (
    <section className="storyboard" aria-label="Storyboard">
      <div className="editor-toolbar" role="toolbar" aria-label="Storyboard tools">
        <button disabled={room <= 0} onClick={() => save([...panels, newPanel()])}>+ Panel</button>
        <button disabled={room <= 0} onClick={buildFromManuscript} title="Draw a first pass from headings, narration and dialogue">Build from manuscript</button>
        <span className="toolbar-divider" />
        <label className="inline-field" htmlFor="panel-count">Panels</label>
        <select id="panel-count" value={panelCount} onChange={(event) => setPanelCount(Number(event.target.value))}>
          {[4, 6, 8, 12, 16, 24].map((count) => <option key={count} value={count}>{count}</option>)}
        </select>
        <button disabled={busy || !aiReady || room <= 0} onClick={() => void draft()}>{busy ? "Drafting panels…" : "✳ Draft panels with AI"}</button>
        {busy && <button onClick={cancel}>Cancel</button>}
        <span className="toolbar-spacer" />
        <span className="panel-count-note">{panels.length} / {MAX_PANELS} panels</span>
        <button onClick={() => window.print()}>Print</button>
      </div>
      <div className="paper-area">
        <div className="storyboard-sheet">
          <div className="paper-kicker"><span>Shot list — {doc.title || "Untitled story"}</span><span>Decalove / Writing Studio</span></div>
          {!aiReady && <p className="panel-help">AI drafting is unavailable right now. You can still build panels from the manuscript and edit them.</p>}
          {error && <div className="writing-error" role="alert"><p>{error}</p>{attempt && !busy && <button className="text-button" onClick={() => void draft(attempt)}>Retry same request ↻</button>}</div>}
          {notice && <p className="writing-notice" role="status">{notice}</p>}
          {busy && <p className="panel-help" role="status">Your shot list is being drafted. You can keep editing panels while it works.</p>}
          {suggestion && <section className="suggestion-review" aria-label="Review storyboard suggestion">
            <p className="eyebrow">Proposed panels</p><p>{suggestion.summary}</p>
            <ol className="suggestion-panels">{suggestion.panels.map((panel, index) => (
              <li key={index}><strong>{shotLabel(panel.shot)}{panel.title ? ` — ${panel.title}` : ""}</strong>
                <p>{panel.description}</p>{panel.dialogue && <p className="panel-line">“{panel.dialogue}”</p>}</li>
            ))}</ol>
            <div className="suggestion-buttons">
              <button className="writing-button primary" disabled={room <= 0} onClick={acceptSuggestion}>Add {Math.min(suggestion.panels.length, room)} panel{Math.min(suggestion.panels.length, room) === 1 ? "" : "s"}</button>
              <button className="text-button" onClick={() => { setSuggestion(null); setNotice("Suggestion discarded. Your storyboard is unchanged."); }}>Discard</button>
            </div>
          </section>}
          {!panels.length && !suggestion && <p className="editor-hint">A storyboard is the scene in frames.<br />Build a first pass from your manuscript, add a panel by hand, or ask for a shot list.</p>}
          <ol className="storyboard-grid">
            {panels.map((panel, index) => (
              <li key={panel.id} className="storyboard-panel">
                <div className="panel-frame">
                  {panel.image
                    ? <img src={workspace.imageUrl(panel.image.id)} alt={panel.image.alt} loading="lazy" />
                    : <span className="panel-placeholder" aria-hidden="true">▣</span>}
                  <span className="panel-index">{index + 1}</span>
                </div>
                <div className="panel-fields">
                  <select aria-label={`Shot for panel ${index + 1}`} value={panel.shot}
                    onChange={(event) => editPanel(panel.id, { shot: event.target.value as StoryboardPanel["shot"] })}>
                    {SHOTS.map((shot) => <option key={shot.id} value={shot.id}>{shot.label}</option>)}
                  </select>
                  <input aria-label={`Title of panel ${index + 1}`} value={panel.title} maxLength={120} placeholder="Panel title"
                    onChange={(event) => editPanel(panel.id, { title: event.target.value }, `panel-title-${panel.id}`)} />
                  <textarea aria-label={`What we see in panel ${index + 1}`} rows={3} maxLength={800} value={panel.description}
                    placeholder="What does the camera see?" onChange={(event) => editPanel(panel.id, { description: event.target.value }, `panel-desc-${panel.id}`)} />
                  <input aria-label={`Line heard over panel ${index + 1}`} value={panel.dialogue} maxLength={300} placeholder="A line heard over it"
                    onChange={(event) => editPanel(panel.id, { dialogue: event.target.value }, `panel-line-${panel.id}`)} />
                  <input aria-label={`Staging note for panel ${index + 1}`} value={panel.notes} maxLength={400} placeholder="Staging, light, sound…"
                    onChange={(event) => editPanel(panel.id, { notes: event.target.value }, `panel-note-${panel.id}`)} />
                </div>
                <div className="panel-controls">
                  <button onClick={() => onPickImage(panel.image ? `Replace the frame for panel ${index + 1}` : `Add a frame to panel ${index + 1}`,
                    { kind: "panel", id: panel.id })}>{panel.image ? "Replace frame" : "Add frame"}</button>
                  <button disabled={index === 0} aria-label={`Move panel ${index + 1} earlier`} onClick={() => move(index, -1)}>←</button>
                  <button disabled={index === panels.length - 1} aria-label={`Move panel ${index + 1} later`} onClick={() => move(index, 1)}>→</button>
                  <button aria-label={`Remove panel ${index + 1}`} onClick={() => save(panels.filter((p) => p.id !== panel.id))}>×</button>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <article className="print-storyboard"><h1>{doc.title} — storyboard</h1>
        {panels.map((panel, index) => <section key={panel.id}>
          <strong>{index + 1}. {shotLabel(panel.shot)}{panel.title ? ` — ${panel.title}` : ""}</strong>
          {panel.image && <img src={workspace.imageUrl(panel.image.id)} alt={panel.image.alt} />}
          {panel.description && <p>{panel.description}</p>}
          {panel.dialogue && <p className="panel-line">“{panel.dialogue}”</p>}
          {panel.notes && <p className="panel-note">Note: {panel.notes}</p>}
        </section>)}
      </article>
    </section>
  );
}
