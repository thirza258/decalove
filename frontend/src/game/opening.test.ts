import { describe, expect, it } from "vitest";
import {
  OPENING_BEFORE_CHOICE, OPENING_AFTER_CHOICE, OPENING_CHOICE_STEP, OPENING_LAST_STEP,
} from "./opening";

describe("opening handoff", () => {
  it("uses the same decision and final indices as the server skip calls", () => {
    const opening = [...OPENING_BEFORE_CHOICE, ...OPENING_AFTER_CHOICE];
    expect(opening.map((step) => step.index)).toEqual(Array.from({ length: 20 }, (_, i) => i));
    expect(OPENING_BEFORE_CHOICE.at(-1)?.index).toBe(OPENING_CHOICE_STEP);
    expect(OPENING_BEFORE_CHOICE.at(-1)?.type).toBe("choice");
    expect(OPENING_AFTER_CHOICE.at(-1)?.index).toBe(OPENING_LAST_STEP);
  });

  it("keeps every branch in the library until the generated response arrives", () => {
    for (const step of OPENING_AFTER_CHOICE) {
      expect(step.location).toBe("library");
      expect(step.visual?.background).toBe("library");
      expect(step.type).toBe("narration");
      expect(step.characters).toEqual([]);
      expect(step.next_choices).toEqual([]);
    }
  });
});
