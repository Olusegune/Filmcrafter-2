import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { barStyle, scaleOf } from "../timingWords";

describe("the dialogue timing strip", () => {
  it("uses one ruler for every shot, from the earliest J cut to the latest voice", () => {
    const s = scaleOf([{ lead: 0.5, seconds: 4, tail: 0, end: 3 }, { lead: 0, seconds: 3, tail: 2, end: 6 }]);
    expect(s).toEqual({ from: -0.5, to: 6 });
  });
  it("places a span in percent, never off an edge and never invisible", () => {
    const s = { from: -1, to: 9 };
    expect(barStyle(s, 0, 5)).toEqual({ left: "10.00%", width: "50.00%" });
    expect(barStyle(s, 8.9, 5).left).toBe("99.00%");
    expect(parseFloat(barStyle(s, 8.9, 5).width)).toBeCloseTo(1, 1);
    expect(parseFloat(barStyle(s, 0, 0.001).width)).toBeGreaterThanOrEqual(0.8);
    expect(barStyle(s, -5, 2).left).toBe("0.00%");
  });
  it("only reads and plays the recordings that are there, and is a view of the Sound plan", () => {
    const t = readFileSync("src/DialogueTiming.tsx", "utf8");
    expect(t).not.toMatch(/queueRender|\.generate\(|castVoice|audioGen|confirmed:\s*true|fetch\(|filmAudioPlan/);
    expect(t).toMatch(/Play the voices/);
    expect(readFileSync("src/SoundPlan.tsx", "utf8")).toMatch(/When each voice falls/);
  });
});

import { videoCostWords } from "../soundPlanWords";
describe("the video price line", () => {
  it("says the price, what is not priced, and that nothing is spent yet", () => {
    const t = videoCostWords({ usd: 9.6, usd_known: 9.6, unknown: 0, shots: 3, lipsync_shots: 1, model: "Seedance 2.0" });
    expect(t).toMatch(/3 shots with Seedance 2\.0 would cost about \$9\.60/);
    expect(t).toMatch(/lip-sync pass on 1/);
    expect(t).toMatch(/Nothing is spent until you confirm in Make/);
  });
  it("is a minimum when some shots have no price, and silent when there is nothing to price", () => {
    expect(videoCostWords({ usd: null, usd_known: 4, unknown: 2, shots: 5, lipsync_shots: 0, model: "M" })).toMatch(/about \$4\.00 \(2 not priced, so this is a minimum\)/);
    expect(videoCostWords({ usd: null, usd_known: null, unknown: 1, shots: 1, lipsync_shots: 0, model: "M" })).toMatch(/no price known yet/);
    expect(videoCostWords(null)).toBe("");
    expect(videoCostWords({ usd: 1, usd_known: 1, unknown: 0, shots: 0, lipsync_shots: 0, model: "M" })).toBe("");
  });
});
