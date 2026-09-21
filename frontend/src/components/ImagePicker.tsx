import { useEffect, useRef, useState } from "react";
import { writingLibrary } from "../writing/api";
import type { LibraryPicture } from "../writing/api";
import { IMAGE_TYPES } from "../writing/model";
import type { BlockImage } from "../writing/model";
import { useWritingWorkspace } from "../writing/workspaceContext";

/**
 * Choosing a picture: one from this machine, or one an operator has already put in
 * the object store. Either way the bytes stay in storage and the document keeps an id.
 */
export function ImagePicker({ label, onInsert, onClose }: {
  label: string; onInsert: (image: BlockImage) => void; onClose: () => void;
}) {
  const workspace = useWritingWorkspace();
  const [alt, setAlt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pictures, setPictures] = useState<LibraryPicture[] | null>(null);
  const [libraryError, setLibraryError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Opening the chooser puts the caret in the description, so Escape closes it too.
    document.getElementById("image-alt")?.focus();
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 8000);
    void writingLibrary(abort.signal)
      .then((found) => setPictures(found))
      .catch(() => { if (!abort.signal.aborted) { setPictures([]); setLibraryError("The shared library could not be read."); } })
      .finally(() => clearTimeout(timer));
    return () => { abort.abort(); clearTimeout(timer); };
  }, []);

  async function insert(work: Promise<BlockImage>) {
    if (busy) return;
    setBusy(true); setError("");
    try {
      onInsert(await work);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "That picture could not be saved. Try another file.");
    } finally { setBusy(false); }
  }

  return (
    <div className="studio-modal" role="dialog" aria-modal="true" aria-label={label}
      onKeyDown={(event) => { if (event.key === "Escape") onClose(); }}>
      <div className="modal-card">
        <div className="panel-heading"><h2>{label}</h2><button className="small-add" aria-label="Close picture chooser" onClick={onClose}>×</button></div>
        <label htmlFor="image-alt">Describe the picture</label>
        <input id="image-alt" value={alt} maxLength={300} placeholder="A rain-streaked window above a quiet street"
          onChange={(event) => setAlt(event.target.value)} />
        <small>Used as the caption's alternative text, in exports, and when the picture cannot load.</small>
        <div className="modal-upload">
          <button className="writing-button primary" disabled={busy} onClick={() => fileInput.current?.click()}>
            {busy ? "Saving picture…" : "Upload a picture"}
          </button>
          <small>PNG, JPEG, WebP or GIF, up to 5 MB.</small>
          <input hidden type="file" aria-label="Picture file" accept={IMAGE_TYPES.join(",")} ref={fileInput}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void insert(workspace.uploadImage(file, alt));
            }} />
        </div>
        <p className="eyebrow">Shared library</p>
        {pictures === null && <p className="panel-help" role="status">Reading the shared library…</p>}
        {libraryError && <p className="panel-help">{libraryError}</p>}
        {pictures !== null && !pictures.length && !libraryError &&
          <p className="panel-help">No shared pictures yet. An operator can drop files into the object store under <code>writing/library/</code> and they appear here.</p>}
        {!!pictures?.length && <ul className="library-grid">{pictures.map((picture) => (
          <li key={picture.key}>
            <button disabled={busy} onClick={() => void insert(workspace.adoptImage(picture.key, alt))}>
              <span className="library-name">{picture.name}</span>
              <span className="library-size">{Math.max(1, Math.round(picture.size / 1024)).toLocaleString()} KB</span>
            </button>
          </li>
        ))}</ul>}
        {error && <p className="writing-error" role="alert">{error}</p>}
        <div className="modal-actions"><button className="text-button" onClick={onClose}>Cancel</button></div>
      </div>
    </div>
  );
}
