// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WritingStudio from "../components/WritingStudio";
import CoursesPage from "../components/CoursesPage";
import { WritingWorkspaceProvider, WORKSPACE_CACHE } from "./workspace";
import type { WorkspaceData } from "./workspace";
import { newDocument } from "./model";
import type { WritingSuggestion } from "./model";
import { requestWriting, writingStatus } from "./api";
import { selectOffsets } from "./formatting";

vi.mock("./api", () => ({ requestWriting: vi.fn(), writingStatus: vi.fn() }));
let serverData: WorkspaceData;
let revision: number;
let failSave: boolean;
let saveRequests: { revision: number; data: WorkspaceData }[];
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const suggestion: WritingSuggestion = { summary: "A quiet answer.", provider: "test", blocks: [
  { kind: "dialogue", speaker: "Mara", text: "You remembered." },
  { kind: "narration", speaker: "", text: "The kettle clicked off." },
] };

beforeEach(() => {
  const items = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => { items.set(key, value); },
    removeItem: (key: string) => { items.delete(key); },
    clear: () => items.clear(),
  });
  localStorage.clear();
  window.location.hash = "/studio";
  const doc = newDocument();
  serverData = { library: { version: 1, activeId: doc.id, documents: [doc] }, progress: { completed: [], exercises: {} } };
  revision = 0; failSave = false; saveRequests = [];
  vi.resetAllMocks();
  vi.mocked(writingStatus).mockResolvedValue(true);
  vi.mocked(requestWriting).mockResolvedValue(clone(suggestion));
  vi.stubGlobal("fetch", vi.fn(async (_input: string, init: RequestInit) => {
    if (init.method === "PUT") {
      const request = JSON.parse(init.body as string) as { revision: number; data: WorkspaceData };
      saveRequests.push(request);
      if (failSave) return new Response(JSON.stringify({ detail: "Storage is unavailable. Keep your draft open and retry saving." }), { status: 503 });
      if (request.revision !== revision && JSON.stringify(request.data) !== JSON.stringify(serverData)) return new Response(JSON.stringify({ detail: "This workspace changed in another tab. Export your unsaved draft before reloading." }), { status: 409 });
      if (request.revision === revision) { serverData = clone(request.data); revision++; }
    }
    return new Response(JSON.stringify({ id: "workspace", revision, data: clone(serverData), storage: "mongo", files: "minio" }));
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function studio(exercise = "") {
  const result = render(<WritingWorkspaceProvider><WritingStudio exercise={exercise} onExerciseUsed={() => {}} /></WritingWorkspaceProvider>);
  await screen.findByLabelText("Document title");
  await screen.findByText("AI assistance ready");
  return result;
}
function writePassage(text: string, label = "Narration passage 1") {
  const editor = screen.getByRole("textbox", { name: label });
  act(() => editor.focus());
  editor.textContent = text;
  fireEvent.input(editor);
  return editor;
}

describe("writing studio", () => {
  it("sends the full author context with a default of 50 dialogue lines and accepts a suggestion without losing concurrent edits", async () => {
    let resolve!: (value: WritingSuggestion) => void;
    vi.mocked(requestWriting).mockReturnValue(new Promise((done) => { resolve = done; }));
    await studio();
    fireEvent.change(screen.getByLabelText("Document title"), { target: { value: "Unopened" } });
    writePassage("  The envelope is still sealed.  ");
    fireEvent.change(screen.getByLabelText("Existing story or background"), { target: { value: "Only Mara knows the sender." } });
    fireEvent.change(screen.getByLabelText("Characters & their voices"), { target: { value: "Jules is concise." } });
    fireEvent.change(screen.getByLabelText("Your instructions"), { target: { value: "  No confession yet.\nKeep the silence.  " } });
    fireEvent.click(screen.getByRole("button", { name: "✳ Generate suggestion" }));
    const request = vi.mocked(requestWriting).mock.calls[0][0];
    expect(request.dialogue_count).toBe(50);
    expect(request.prompt).toBe("  No confession yet.\nKeep the silence.  ");
    expect(request.reference).toBe("Only Mara knows the sender.");
    expect(request.blocks[0].text).toBe("  The envelope is still sealed.  ");
    writePassage("My newer opening.");
    await act(async () => resolve(clone(suggestion)));
    expect(screen.getByRole("textbox", { name: "Narration passage 1" }).textContent).toBe("My newer opening.");
    expect(screen.queryByRole("textbox", { name: "Dialogue passage 2" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Insert at end" }));
    expect(screen.getByRole("textbox", { name: "Dialogue passage 2" }).textContent).toBe("You remembered.");
    await waitFor(() => expect(serverData.library.documents[0].blocks).toHaveLength(3));
    expect(serverData.library.documents[0].blocks[0].text).toBe("My newer opening.");
  });

  it("retries the exact failed request even if the prompt and draft have changed", async () => {
    vi.mocked(requestWriting).mockRejectedValueOnce(new Error("Provider unavailable"));
    await studio();
    writePassage("Original draft");
    fireEvent.change(screen.getByLabelText("Your instructions"), { target: { value: "Original prompt" } });
    fireEvent.click(screen.getByRole("button", { name: "✳ Generate suggestion" }));
    await screen.findByText("Provider unavailable");
    writePassage("New local draft");
    fireEvent.change(screen.getByLabelText("Your instructions"), { target: { value: "Changed prompt" } });
    fireEvent.click(screen.getByRole("button", { name: "Retry same request ↻" }));
    await screen.findByRole("region", { name: "Review AI suggestion" });
    expect(vi.mocked(requestWriting).mock.calls[1][0]).toEqual(vi.mocked(requestWriting).mock.calls[0][0]);
    expect(screen.getByRole("textbox", { name: "Narration passage 1" }).textContent).toBe("New local draft");
  });

  it("does not replace a passage edited while its rewrite was in flight", async () => {
    let resolve!: (value: WritingSuggestion) => void;
    vi.mocked(requestWriting).mockReturnValue(new Promise((done) => { resolve = done; }));
    await studio();
    writePassage("The old wording.");
    fireEvent.change(screen.getByLabelText("What are we working on?"), { target: { value: "rewrite" } });
    fireEvent.click(screen.getByRole("button", { name: "✳ Generate suggestion" }));
    writePassage("My important correction.");
    await act(async () => resolve({ ...suggestion, blocks: [{ kind: "narration", speaker: "", text: "A proposed rewrite." }] }));
    expect((screen.getByRole("button", { name: "Replace selected passage" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/original passage changed/)).toBeTruthy();
  });

  it("cancels abandoned requests and ignores their late results", async () => {
    let resolve!: (value: WritingSuggestion) => void;
    vi.mocked(requestWriting).mockReturnValue(new Promise((done) => { resolve = done; }));
    await studio();
    fireEvent.click(screen.getByRole("button", { name: "✳ Generate suggestion" }));
    const signal = vi.mocked(requestWriting).mock.calls[0][1];
    fireEvent.click(screen.getByRole("button", { name: "New document" }));
    expect(signal.aborted).toBe(true);
    await act(async () => resolve(clone(suggestion)));
    expect(screen.queryByRole("region", { name: "Review AI suggestion" })).toBeNull();
    expect(screen.getByRole("textbox", { name: "Narration passage 1" }).textContent).toBe("");
  });

  it("formats selected words, finds and replaces text, and can undo the replacement", async () => {
    await studio();
    const editor = writePassage("A red letter and a red door.");
    act(() => selectOffsets(editor, 2, 5));
    fireEvent.mouseDown(screen.getByRole("button", { name: "Bold" }));
    fireEvent.click(screen.getByRole("button", { name: "Bold" }));
    expect(editor.querySelector("strong")?.textContent).toBe("red");
    fireEvent.click(screen.getByRole("button", { name: "Find" }));
    fireEvent.change(screen.getByLabelText("Find text"), { target: { value: "red" } });
    fireEvent.change(screen.getByLabelText("Replacement text"), { target: { value: "blue" } });
    expect(screen.getByText("2 matches")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Replace all" }));
    expect(editor.textContent).toBe("A blue letter and a blue door.");
    fireEvent.click(screen.getByRole("button", { name: "Undo edit" }));
    expect(editor.textContent).toBe("A red letter and a red door.");
    expect(editor.querySelector("strong")?.textContent).toBe("red");
    await waitFor(() => expect(serverData.library.documents[0].blocks[0].marks).toEqual([{ start: 2, end: 5, kind: "bold" }]));
  });

  it("keeps unsaved edits after a storage outage and retries them to the server", async () => {
    await studio();
    failSave = true;
    writePassage("Do not lose this paragraph.");
    await screen.findByText(/Storage is unavailable/);
    expect(screen.getByText("Server save unavailable")).toBeTruthy();
    expect(JSON.parse(localStorage.getItem(WORKSPACE_CACHE)!).dirty).toBe(true);
    failSave = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry server save" }));
    await screen.findByText("✓ Saved to workspace");
    expect(serverData.library.documents[0].blocks[0].text).toBe("Do not lose this paragraph.");
    expect(saveRequests[1].data).toEqual(saveRequests[0].data);
  });

  it("refuses to overwrite another tab and restores the server draft on a fresh visit", async () => {
    const view = await studio();
    serverData.library.documents[0].title = "Other tab's saved title";
    revision++;
    writePassage("This tab's unsaved work");
    await screen.findByText(/changed in another tab/);
    expect(serverData.library.documents[0].blocks[0].text).toBe("");
    expect(screen.getByRole("textbox", { name: "Narration passage 1" }).textContent).toBe("This tab's unsaved work");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Load server version" }));
    await waitFor(() => expect((screen.getByLabelText("Document title") as HTMLInputElement).value).toBe("Other tab's saved title"));
    view.unmount();
    await studio();
    expect((screen.getByLabelText("Document title") as HTMLInputElement).value).toBe("Other tab's saved title");
  });
});

it("course lessons offer detailed narrative practice and save progress with the same workspace", async () => {
  const practice = vi.fn();
  render(<WritingWorkspaceProvider><CoursesPage onPractice={practice} /></WritingWorkspaceProvider>);
  fireEvent.click(await screen.findByRole("button", { name: /Make narration carry feeling/ }));
  expect(screen.getByRole("heading", { name: "Take a closer look" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Read the example closely" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Build it in passes" })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Your practice notes"), { target: { value: "Stay in Mara's perspective." } });
  fireEvent.click(screen.getByRole("button", { name: "Mark lesson complete" }));
  fireEvent.click(screen.getByRole("button", { name: /Practice in the studio/ }));
  expect(practice.mock.calls[0][0]).toContain("Stay in Mara's perspective.");
  expect(practice.mock.calls[0][0]).toContain("Craft guidance:");
  await waitFor(() => expect(serverData.progress.completed).toEqual(["narration-pov"]));
  expect(serverData.progress.exercises["narration-pov"]).toBe("Stay in Mara's perspective.");
});
