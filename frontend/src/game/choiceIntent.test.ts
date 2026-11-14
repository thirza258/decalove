import { describe, expect, it } from "vitest";
import { classifyChoice } from "./choiceIntent";

describe("choice intent tags", () => {
  it("names the common intents a menu uses", () => {
    expect(classifyChoice("Offer to help with the page.").key).toBe("support");
    expect(classifyChoice("Ask why she is upset.").key).toBe("ask");
    expect(classifyChoice("Say nothing and let her answer.").key).toBe("observe");
    expect(classifyChoice("Tell her you are sorry.").key).toBe("feeling");
    expect(classifyChoice("Change the subject before she asks.").key).toBe("strategy");
    expect(classifyChoice("Call her out for blaming you.").key).toBe("challenge");
  });

  it("falls back to a neutral tag rather than inventing one", () => {
    const intent = classifyChoice("Count the ceiling tiles.");
    expect(intent.key).toBe("other");
    expect(intent.label).toBe("Choice");
    expect(intent.glyph).toBeTruthy();
  });

  it("returns presentation metadata without touching the option text", () => {
    const intent = classifyChoice("Ask about the notebook.");
    expect(intent.label).toBe("Ask");
    expect(intent.className).toContain("text-");
  });
});
