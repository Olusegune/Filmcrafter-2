import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { buildSteps, doneCount, nextStep, requiredCount } from "../guideSteps";

const prog = (o: Record<string, unknown> = {}) => ({
  story: { locked: false, as_is: false }, cast: { characters: 0, places: 0, style: false }, shots: { count: 0 },
  make: { shots: 0, keyframe: 0, video: 0 }, ...o,
}) as never;
const facts = (o = {}) => ({ progress: prog(), voices: null, sound: null, pro: false, exported: false, ...o });

describe("first-film guide steps", () => {
  it("starts at the story and nothing else blocks it", () => {
    const s = buildSteps(facts());
    expect(nextStep(s)?.id).toBe("story");
    expect(s.filter((x) => x.status === "next")).toHaveLength(1);
  });
  it("moves on as things get done", () => {
    const s = buildSteps(facts({ progress: prog({ story: { locked: true, as_is: false }, cast: { characters: 2, places: 1, style: true } }), voices: { people: 2, recorded: 1 } }));
    expect(nextStep(s)?.id).toBe("voices");
    expect(doneCount(s)).toBe(2);
  });
  it("optional sound never blocks, and shots only show in Pro", () => {
    expect(buildSteps(facts()).some((x) => x.id === "shots")).toBe(false);
    expect(buildSteps(facts({ pro: true })).some((x) => x.id === "shots")).toBe(true);
    const s = buildSteps(facts());
    expect(requiredCount(s)).toBe(s.filter((x) => !x.optional).length);
    expect(s.find((x) => x.id === "sound")?.optional).toBe(true);
  });
  it("the guide only reads and points: it never starts paid work", () => {
    for (const f of ["src/FirstFilm.tsx", "src/guideSteps.ts"]) {
      const t = readFileSync(f, "utf8");
      expect(t).not.toMatch(/queueRender|\.generate\(|confirmed:\s*true|renderStart|"speak"|"design"/);
    }
  });
});

describe("whole-film sound preview", () => {
  it("asks the free local mix for the whole film and never an AI call", () => {
    const t = readFileSync("src/SceneSound.tsx", "utf8");
    expect(t).toMatch(/Hear the whole film/);
    expect(t).toMatch(/scene: "all"/);
  });
});
