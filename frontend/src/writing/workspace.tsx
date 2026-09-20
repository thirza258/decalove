import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { API_BASE, API_PREFIX } from "../config";
import { isDocument, newDocument } from "./model";
import type { Library, WritingDocument } from "./model";
import { WorkspaceContext } from "./workspaceContext";

export interface CourseProgress { completed: string[]; exercises: Record<string, string> }
export interface WorkspaceData { library: Library; progress: CourseProgress }
interface WorkspaceResponse { id: string; revision: number; data: WorkspaceData; storage: string; files: string }
interface Recovery { id: string; revision: number; data: WorkspaceData; dirty: boolean }
export interface WorkspaceContextValue {
  id: string;
  data: WorkspaceData;
  status: "loading" | "saved" | "unsaved" | "saving" | "error";
  error: string;
  temporary: boolean;
  update: (transform: (data: WorkspaceData) => WorkspaceData) => void;
  retry: () => void;
  reload: () => void;
  exportDocument: (doc: WritingDocument, format: "txt" | "json") => Promise<string>;
}

export const WORKSPACE_CACHE = "decalove.workspace.v1";

function validData(value: unknown): value is WorkspaceData {
  if (!value || typeof value !== "object") return false;
  const data = value as WorkspaceData;
  return data.library?.version === 1 && Array.isArray(data.library.documents) &&
    data.library.documents.length > 0 && data.library.documents.every(isDocument) &&
    data.library.documents.some((d) => d.id === data.library.activeId) &&
    Array.isArray(data.progress?.completed) && data.progress.completed.every((x) => typeof x === "string") &&
    !!data.progress.exercises && typeof data.progress.exercises === "object" &&
    Object.values(data.progress.exercises).every((x) => typeof x === "string");
}

function loadRecovery(): Recovery {
  const requested = new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("workspace");
  const id = requested && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(requested) ? requested : null;
  try {
    const saved = JSON.parse(localStorage.getItem(WORKSPACE_CACHE) ?? "null") as Recovery | null;
    if (saved && (!id || id === saved.id) && /^[0-9a-f-]{36}$/i.test(saved.id) &&
        Number.isInteger(saved.revision) && validData(saved.data)) return saved;
  } catch { /* A failed browser cache does not prevent server-backed writing. */ }
  const doc = newDocument();
  return { id: id ?? crypto.randomUUID(), revision: 0, dirty: false,
    data: { library: { version: 1, activeId: doc.id, documents: [doc] }, progress: { completed: [], exercises: {} } } };
}

class StorageError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.status = status; }
}

async function storageRequest(path: string, method = "POST", payload?: unknown, signal?: AbortSignal): Promise<Response> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 20000);
  try {
    const response = await fetch(`${API_BASE}${API_PREFIX}/writing/workspaces/${path}`, {
      method, signal: controller.signal,
      headers: payload === undefined ? undefined : { "Content-Type": "application/json" },
      body: payload === undefined ? undefined : JSON.stringify(payload),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { detail?: unknown } | null;
      throw new StorageError(typeof body?.detail === "string" ? body.detail : response.status === 422
        ? "This workspace exceeds the save limits. Keep chapters under 120,000 characters and at most 50 documents. Export a copy before making changes."
        : "Server storage is unavailable. Keep this page open and retry saving.", response.status);
    }
    // Consume the body before releasing the timeout: a stalled body is also bounded.
    const body = await response.text();
    return new Response(body, { status: response.status, headers: response.headers });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

export function WritingWorkspaceProvider({ children }: { children: ReactNode }) {
  const [initial] = useState(loadRecovery);
  const [data, setData] = useState(initial.data);
  const [status, setStatus] = useState<WorkspaceContextValue["status"]>("loading");
  const [error, setError] = useState("");
  const [temporary, setTemporary] = useState(false);
  const [ready, setReady] = useState(false);
  const live = useRef({ ...initial, connected: false, saving: false });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(false);

  function cache() {
    try {
      const { id, revision, data: current, dirty } = live.current;
      localStorage.setItem(WORKSPACE_CACHE, JSON.stringify({ id, revision, data: current, dirty }));
    } catch {
      if (mounted.current) setError("Browser recovery is unavailable. Keep this page open until your changes are saved to the server.");
    }
  }

  async function flush() {
    const state = live.current;
    if (state.saving || !state.connected || !state.dirty) return;
    state.saving = true;
    try {
      while (state.dirty && state.connected) {
        const snapshot = state.data;
        if (mounted.current) setStatus("saving");
        const response = await storageRequest(state.id, "PUT", { revision: state.revision, data: snapshot });
        const saved = await response.json() as WorkspaceResponse;
        state.revision = saved.revision;
        state.dirty = state.data !== snapshot;
        cache();
      }
      if (mounted.current) { setStatus("saved"); setError(""); }
    } catch (failure) {
      state.connected = false;
      if (mounted.current) {
        setStatus("error");
        setError(failure instanceof StorageError ? failure.message : "Could not save to the server. Your edits are still here; retry when connected.");
      }
    } finally { state.saving = false; }
  }

  async function connect(signal?: AbortSignal, replaceLocal = false) {
    try {
      const state = live.current;
      const response = await storageRequest(state.id, "POST", undefined, signal);
      const saved = await response.json() as WorkspaceResponse;
      if (signal?.aborted || !mounted.current) return;
      if (!validData(saved.data) || !Number.isInteger(saved.revision)) throw new Error("Invalid saved workspace");
      if (!state.dirty || replaceLocal) {
        state.data = saved.data; state.revision = saved.revision;
        state.dirty = false;
        setData(saved.data);
      }
      state.connected = true;
      setTemporary(saved.storage !== "mongo" || saved.files !== "minio");
      setStatus(state.dirty ? "unsaved" : "saved"); setError(""); setReady(true);
      cache();
      if (state.dirty) void flush();
    } catch (failure) {
      if (signal?.aborted || !mounted.current) return;
      setReady(true); setStatus("error");
      setError(failure instanceof StorageError ? failure.message : "Cannot reach saved workspaces. You can keep writing here and retry the connection.");
    }
  }

  useEffect(() => {
    mounted.current = true;
    const abort = new AbortController();
    const pendingTimer = timer;
    const current = live.current;
    // Save the workspace identifier immediately, so interrupted initial requests retry it.
    cache();
    void connect(abort.signal);
    const warn = (event: BeforeUnloadEvent) => {
      if (current.dirty) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      mounted.current = false;
      abort.abort();
      if (pendingTimer.current) clearTimeout(pendingTimer.current);
      window.removeEventListener("beforeunload", warn);
      void flush();
    };
    // This effect owns one workspace connection. Async saves read the live state ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function update(transform: (current: WorkspaceData) => WorkspaceData) {
    const state = live.current;
    state.data = transform(state.data); state.dirty = true;
    setData(state.data); setStatus(state.connected ? "unsaved" : "error");
    cache();
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => void flush(), 650);
  }

  async function exportDocument(doc: WritingDocument, format: "txt" | "json") {
    const metadata = await (await storageRequest(`${live.current.id}/files`, "POST", { document: doc, format })).json() as { id: string };
    return (await storageRequest(`${live.current.id}/files/${metadata.id}`, "GET")).text();
  }

  const value: WorkspaceContextValue = { id: initial.id, data, status, error, temporary, update, retry: () => { void connect(); },
    reload: () => { if (window.confirm("Load the server version and discard unsaved changes in this tab? Download a recovery copy first if you need to keep them.")) void connect(undefined, true); }, exportDocument };
  return <WorkspaceContext.Provider value={value}>{ready ? children : <div className="writing-app writing-loading" role="status">Opening your saved writing room…</div>}</WorkspaceContext.Provider>;
}
