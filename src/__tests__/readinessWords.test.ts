import { describe, expect, it } from "vitest";
import { goLabel, levelWords, moreWords, nextSentence } from "../readinessWords";

describe("the next-step words", () => {
  it("names where each step goes", () => {
    expect(goLabel("voice")).toBe("Open the voices");
    expect(goLabel("make")).toBe("Open Make");
    expect(goLabel("soundplan")).toBe("Open the Sound plan");
  });
  it("says the film is ready, or the one next thing, or that there is nothing yet", () => {
    expect(nextSentence(null, true)).toMatch(/ready to export/);
    expect(nextSentence({ step: "x", level: "look", what: "8 shots have no keyframe.", why: "", go: "make", shot: null, fix: null }, false)).toBe("8 shots have no keyframe.");
    expect(nextSentence(null, false)).toBe("Nothing to do yet.");
  });
  it("shows the list button only when there is more than the next step", () => {
    expect(moreWords(1)).toBe("");
    expect(moreWords(4)).toBe("All 4 things");
    expect(levelWords("fix")).toBe("Fix");
  });
});
