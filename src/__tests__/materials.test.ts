import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { canTick, summaryWords, typeWords } from "../materialsWords";
import { buildSteps } from "../guideSteps";
import type { MaterialItem } from "../api";

const base: MaterialItem = { id: "a", type: "storyboard", title: "t", on: true, blocked: "", notes: [] };

describe("bringing in your own materials", () => {
  it("says where each piece goes, in words", () => {
    expect(typeWords({ ...base, shot: "S01-02", shot_label: "S01-02 · Tea", how: "the file name" })).toBe("Panel for S01-02 · Tea, matched by the file name");
    expect(typeWords({ ...base, type: "storyboard" })).toBe("Which shot is this panel for?");
    expect(typeWords({ ...base, type: "asset", kind: "environment", name: "Kitchen", create: true, media_kind: "reference" })).toBe("New place: Kitchen");
    expect(typeWords({ ...base, type: "asset", kind: "character", entry_name: "Sarah", media_kind: "front" })).toBe("character: Sarah · front view");
    expect(typeWords({ ...base, type: "note", target: "tone" })).toBe("Add to the Bible's tone");
  });
  it("only lets a ready item be ticked", () => {
    expect(canTick(base)).toBe(true);
    expect(canTick({ ...base, blocked: "locked" })).toBe(false);
    expect(canTick({ ...base, type: "unsorted" })).toBe(false);
  });
  it("counts what will be brought in", () => {
    expect(summaryWords({ storyboard: 2, asset: 1, note: 1 })).toBe("2 storyboard panels, 1 picture for the cast, places and props, 1 note");
    expect(summaryWords({})).toBe("");
  });
  it("is an optional step in the guide and never blocks the next one", () => {
    const f = { progress: { story: { locked: false, as_is: false }, cast: { characters: 0, places: 0, style: false }, shots: { count: 0 }, make: { shots: 0, keyframe: 0, video: 0 } } as never, voices: null, sound: null, pro: false, exported: false };
    const s = buildSteps(f);
    expect(s.find((x) => x.id === "materials")?.optional).toBe(true);
    expect(s.find((x) => x.status === "next")?.id).toBe("story");
  });
  it("the screen only reads and copies: nothing paid, nothing sent", () => {
    for (const f of ["src/BringMaterials.tsx", "src/materialsWords.ts"]) {
      const t = readFileSync(f, "utf8");
      expect(t).not.toMatch(/queueRender|\.generate\(|castVoice|audioGen|confirmed:\s*true|fetch\(/);
    }
    expect(readFileSync("src/BringMaterials.tsx", "utf8")).toMatch(/filmMaterials/);
  });
});
