import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(() => new Promise(() => {})), convertFileSrc: (p: string) => p }));

import { checkSentence, dollars, KeyframeTools, remodelLine, swapSentence, type CheckSummary, type RemodelPlan, type SwapStatus } from "../KeyframeTools";

const summary = (over: Partial<CheckSummary> = {}): CheckSummary => ({ checked: 4, passed: 4, failed: [], look: [], errors: [], ...over });
const plan = (over: Partial<RemodelPlan> = {}): RemodelPlan => ({ target: { provider: "kie", model: "google/nano-banana-edit", label: "Nano Banana", price_usd: 0.03 }, shots: ["S01-02", "S01-05"], from: [], skipped: [], used: [], usd_est: 0.2, ...over });

describe("prices", () => {
  it("are free, three places for cents and two for dollars", () => {
    expect(dollars(0)).toBe("free");
    expect(dollars(0.06)).toBe("about $0.060");
    expect(dollars(1.5)).toBe("about $1.50");
  });
});

describe("what the hands check says", () => {
  it("says nothing needed checking", () => {
    expect(checkSentence(summary({ checked: 0, passed: 0 }))).toBe("Nothing needed checking.");
  });
  it("says no problems when none were found", () => {
    expect(checkSentence(summary())).toBe("Looked at 4 keyframes. No problems found.");
    expect(checkSentence(summary({ checked: 1, passed: 1 }))).toBe("Looked at 1 keyframe. No problems found.");
  });
  it("names the shots that look wrong and the ones worth a look", () => {
    const t = checkSentence(summary({ passed: 1, failed: [{ shot: "S01-01", kinds: ["anatomy"], detail: "x" }, { shot: "S01-04", kinds: ["anatomy"], detail: "y" }], look: [{ shot: "S01-02", detail: "z" }] }));
    expect(t).toContain("2 have hands or limbs that look wrong (S01-01, S01-04)");
    expect(t).toContain("1 is worth a look (S01-02)");
    expect(t).not.toContain("No problems");
  });
  it("mentions pictures that could not be checked", () => {
    expect(checkSentence(summary({ checked: 2, passed: 2, errors: [{ shot: "S01-03", error: "rate limited" }] }))).toContain("1 picture could not be checked");
  });
});

describe("where the new keyframes are", () => {
  const st = (over: Partial<SwapStatus>): SwapStatus => ({ making: 0, ready: 0, failed: 0, shots_ready: [], reasons: {}, ...over });
  it("is silent when there are none", () => {
    expect(swapSentence(null)).toBe("");
    expect(swapSentence(st({}))).toBe("");
  });
  it("says what is being made, what is ready and what did not come out", () => {
    expect(swapSentence(st({ making: 2, ready: 1, failed: 1 }))).toBe("2 new keyframes are being made. 1 new keyframe is ready to use. 1 did not come out (failed or failed the check).");
    expect(swapSentence(st({ ready: 3 }))).toBe("3 new keyframes are ready to use.");
  });
});

describe("redoing on one model", () => {
  it("says how many and on what, with the price", () => {
    expect(remodelLine(plan())).toBe("2 keyframes were made by a different model. Redo them on Nano Banana: about $0.20.");
    expect(remodelLine(plan({ shots: ["S01-02"], usd_est: 0.1 }))).toBe("1 keyframe was made by a different model. Redo it on Nano Banana: about $0.10.");
  });
  it("says when everything is already on the model", () => {
    expect(remodelLine(plan({ shots: [] }))).toBe("Every keyframe that can be redone is already on Nano Banana.");
  });
});

describe("the sheet", () => {
  it("opens as a dialog with both tools, and nothing is started by opening it", () => {
    const html = renderToStaticMarkup(<KeyframeTools dir="d" onClose={() => {}} />);
    expect(html).toContain('role="dialog"');
    expect(html).toContain("Keyframe tools");
    expect(html).toContain("Check the hands");
    expect(html).toContain("Keep one picture model");
    expect(html).toContain("It only looks; nothing changes.");
  });
});
