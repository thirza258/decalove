import { describe, expect, it } from "vitest";
import { exportText, isDocument, newDocument, normalizeDocument, panelsFromManuscript } from "./model";
import type { MarkColor, WritingBlock, WritingDocument } from "./model";

function document(patch: Partial<WritingDocument> = {}): WritingDocument {
  return { ...newDocument(), id: "11111111-1111-4111-8111-111111111111", title: "Rooftops", ...patch };
}
const block = (patch: Partial<WritingBlock>): WritingBlock =>
  ({ id: crypto.randomUUID(), kind: "narration", text: "", speaker: "", ...patch });
const picture = (alt: string) => ({ id: "a".repeat(64), alt, width: 100 });

describe("the document a writer takes away", () => {
  it("writes illustrations and the storyboard into the exported manuscript", () => {
    const doc = document({
      blocks: [block({ text: "The city went quiet." }),
               block({ kind: "image", text: "Before the rain.", image: picture("Wet rooftops at dusk") })],
      storyboard: [{ id: "panel", shot: "establishing", title: "The roof", description: "Wet tiles, one open door.",
                     dialogue: "You came.", notes: "Hold before she turns.", image: picture("Rooftop") }],
    });
    // Byte for byte what the server writes into an exported .txt — see manuscript_text.
    expect(exportText(doc)).toBe(`Rooftops

The city went quiet.

[Image: Wet rooftops at dusk]
Before the rain.

STORYBOARD
1. ESTABLISHING — The roof
   Wet tiles, one open door.
   “You came.”
   Note: Hold before she turns.
   [Image: Rooftop]
`);
    expect(exportText(document({ blocks: [block({ text: "Only prose." })] }))).toBe("Rooftops\n\nOnly prose.\n");
    expect(exportText(document({ blocks: [block({ kind: "image", image: picture("  ") })] })))
      .toContain("[Image: untitled illustration]");
  });

  it("draws a first storyboard pass from headings, narration and dialogue", () => {
    const panels = panelsFromManuscript(document({ blocks: [
      block({ kind: "heading", text: "The roof" }),
      block({ text: "Wet tiles, one open door." }),
      block({ kind: "dialogue", speaker: "Mara", text: "You came." }),
      block({ text: "She does not turn around." }),
    ] }));
    expect(panels).toHaveLength(2);
    expect(panels[0]).toMatchObject({ shot: "establishing", title: "The roof", description: "Wet tiles, one open door.", dialogue: "Mara: You came." });
    expect(panels[1]).toMatchObject({ description: "She does not turn around.", dialogue: "" });
    // An empty manuscript proposes nothing rather than a page of blank frames.
    expect(panelsFromManuscript(document())).toEqual([]);
  });

  it("accepts a workspace saved before notes, comments and pictures existed", () => {
    const legacy = { ...document(), notes: undefined, comments: undefined, storyboard: undefined } as unknown as WritingDocument;
    expect(isDocument(legacy)).toBe(true);
    expect(normalizeDocument(legacy)).toMatchObject({ notes: [], comments: [], storyboard: [] });
    expect(isDocument(document({ blocks: [block({ kind: "image" })] }))).toBe(false);
    expect(isDocument(document({ blocks: [block({ text: "x", image: picture("y") })] }))).toBe(false);
    expect(isDocument(document({ blocks: [block({ text: "red", marks: [{ start: 0, end: 3, kind: "color" }] })] }))).toBe(false);
    expect(isDocument(document({ blocks: [block({ text: "red", marks: [{ start: 0, end: 3, kind: "color", value: "puce" as MarkColor }] })] }))).toBe(false);
    expect(isDocument(document({ blocks: [block({ text: "red", marks: [{ start: 0, end: 3, kind: "highlight", value: "amber" }] })] }))).toBe(true);
  });
});
