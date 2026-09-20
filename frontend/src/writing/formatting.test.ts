// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { readRichText, replaceRange, richHTML, selectedOffsets, selectOffsets, toggleMark } from "./formatting";
import { exportText, importText, isDocument, newBlock, newDocument } from "./model";
import { COURSES } from "./courses";
import { WORKSHOPS } from "./workshops";

describe("manuscript text and formatting", () => {
  it("renders overlapping marks without interpreting manuscript HTML", () => {
    const root = document.createElement("div");
    const text = '<img src=x onerror="alert(1)"> & the letter';
    root.innerHTML = richHTML(text, [{ start: 0, end: 5, kind: "bold" }, { start: 2, end: 8, kind: "italic" }]);
    expect(root.querySelector("img")).toBeNull();
    expect(root.textContent).toBe(text);
    const read = readRichText(root);
    expect(read.text).toBe(text);
    expect(read.marks).toEqual([{ start: 0, end: 5, kind: "bold" }, { start: 2, end: 8, kind: "italic" }]);
  });

  it("preserves exact whitespace, Unicode, and selection across formatting", () => {
    const root = document.createElement("div");
    document.body.append(root);
    const text = "  🙂 Keep\nthis pause.  ";
    root.innerHTML = richHTML(text, [{ start: 3, end: 9, kind: "underline" }]);
    selectOffsets(root, 5, 14);
    expect(selectedOffsets(root)).toEqual({ start: 5, end: 14 });
    expect(readRichText(root).text).toBe(text);
    root.remove();
  });

  it("toggles only the chosen words and preserves surrounding marks", () => {
    const marks = [{ start: 0, end: 4, kind: "bold" as const }, { start: 4, end: 10, kind: "bold" as const }];
    expect(toggleMark(marks, 2, 8, "bold")).toEqual([{ start: 0, end: 2, kind: "bold" }, { start: 8, end: 10, kind: "bold" }]);
    expect(toggleMark([], 2, 8, "italic")).toEqual([{ start: 2, end: 8, kind: "italic" }]);
  });

  it("find/replace adjusts formatting after an edit instead of moving it to other words", () => {
    const block = { ...newBlock("narration", "A red letter"), marks: [{ start: 6, end: 12, kind: "bold" as const }] };
    const result = replaceRange(block, 2, 5, "blue");
    expect(result.text).toBe("A blue letter");
    expect(result.marks).toEqual([{ start: 7, end: 13, kind: "bold" }]);
  });

  it("imports editable prose and dialogue and preserves formatting in document backups", () => {
    const doc = newDocument();
    doc.title = "After the rain";
    doc.blocks = importText("MARA: I kept the letter.\n\nRain darkened the windowsill.");
    doc.blocks[0].marks = [{ start: 0, end: 6, kind: "italic" }];
    expect(doc.blocks[0].kind).toBe("dialogue");
    expect(exportText(doc)).toContain("MARA: I kept the letter.");
    expect(isDocument(JSON.parse(JSON.stringify(doc)))).toBe(true);
    expect(isDocument({ ...doc, blocks: [{ ...doc.blocks[0], marks: [{ kind: "bold", start: 0, end: 10000 }] }] })).toBe(false);
  });
});

it("every course lesson has a complete narrative workshop and a concrete deliverable", () => {
  const lessons = COURSES.flatMap((c) => c.lessons);
  expect(lessons).toHaveLength(18);
  for (const lesson of lessons) {
    const workshop = WORKSHOPS[lesson.id];
    expect(workshop.reading.length).toBeGreaterThanOrEqual(3);
    expect(workshop.practice.length).toBeGreaterThanOrEqual(5);
    expect(workshop.annotations.length).toBeGreaterThanOrEqual(3);
    expect(workshop.deliverable.length).toBeGreaterThan(40);
  }
});
