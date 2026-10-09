import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));

import { atEnd, clampTime, compareFacts, DRIFT_TOLERANCE, fmtClock, FRAME_FPS, needsResync, stepTime } from "../compareMath";
import { TakeCompare } from "../Compare";
import type { Version } from "../api";

const take = (n: number, over: Partial<Version> = {}): Version => ({ id: `t${n}`, n, state: "ready", provider: "kie", model: "bytedance/seedance-2", output: `generations/t${n}.mp4`, kind: "video", created: n, cost: 50, cost_unit: "credits", approved: false, ...over });

describe("one clock for two takes", () => {
  it("keeps a time inside the clip and ignores nonsense", () => {
    expect(clampTime(-3, 5)).toBe(0);
    expect(clampTime(9, 5)).toBe(5);
    expect(clampTime(2.5, 5)).toBe(2.5);
    expect(clampTime(Number.NaN, 5)).toBe(0);
    expect(clampTime(3, 0)).toBe(0);
  });
  it("steps one frame at a time and stops at both ends", () => {
    expect(stepTime(1, 1, 5)).toBeCloseTo(1 + 1 / FRAME_FPS);
    expect(stepTime(1, -1, 5)).toBeCloseTo(1 - 1 / FRAME_FPS);
    expect(stepTime(0, -1, 5)).toBe(0);
    expect(stepTime(5, 1, 5)).toBe(5);
    expect(stepTime(1, 1, 5, 0)).toBeCloseTo(1 + 1 / FRAME_FPS);          // a missing frame rate falls back to 24
  });
  it("pulls the follower back only when it has drifted", () => {
    expect(needsResync(2, 2 + DRIFT_TOLERANCE / 2, 5)).toBe(false);
    expect(needsResync(2, 2.5, 5)).toBe(true);
    expect(needsResync(2, 1.5, 5)).toBe(true);
  });
  it("leaves a shorter clip that has ended on its last frame", () => {
    expect(needsResync(7, 3, 3)).toBe(false);          // the clip is 3 s long and sits on its end while the clock reads 7 s
    expect(needsResync(7, 2, 3)).toBe(true);           // but one that has not got there is brought on
  });
  it("knows when the longer clip has finished", () => {
    expect(atEnd(4.99, 5)).toBe(true);
    expect(atEnd(4, 5)).toBe(false);
    expect(atEnd(0, 0)).toBe(false);
  });
  it("writes the time as minutes, seconds and hundredths", () => {
    expect(fmtClock(0)).toBe("0:00.00");
    expect(fmtClock(65.5)).toBe("1:05.50");
    expect(fmtClock(-2)).toBe("0:00.00");
  });
});

describe("what differs between two takes", () => {
  it("marks only the rows that differ", () => {
    const f = compareFacts(take(1), take(2), 5, 5);
    expect(f.map((r) => [r.label, r.differs])).toEqual([["Model", false], ["Length", false], ["Price", false]]);
  });
  it("names a different model, length and price, and which cost less", () => {
    const f = compareFacts(take(1, { cost: 80 }), take(2, { provider: "fal", model: "fal-ai/wan/v2", cost: 0.4, cost_unit: "usd" }), 5, 6.5);
    expect(f[0]).toMatchObject({ differs: true, a: "kie: bytedance/seedance-2", b: "fal: wan/v2" });
    expect(f[1]).toMatchObject({ differs: true, a: "5 s", b: "6.5 s" });
    expect(f[2]).toMatchObject({ differs: true, a: "80 credits", b: "0.4 USD" });
    expect(f[2].note).toBeUndefined();                  // different units cannot be compared
  });
  it("says which was cheaper when both are in the same unit", () => {
    expect(compareFacts(take(1, { cost: 30 }), take(2, { cost: 50 }), 5, 5)[2].note).toBe("Left cost less");
    expect(compareFacts(take(1, { cost: 90 }), take(2, { cost: 50 }), 5, 5)[2].note).toBe("Right cost less");
  });
  it("copes with an unknown price and a length not loaded yet", () => {
    const f = compareFacts(take(1, { cost: null }), take(2), null, 5);
    expect(f[2]).toMatchObject({ a: "not known", differs: true });
    expect(f[1]).toMatchObject({ a: "…", differs: false });
  });
  it("treats lengths a frame apart as the same", () => {
    expect(compareFacts(take(1), take(2), 5, 5.03)[1].differs).toBe(false);
  });
});

describe("the compare view", () => {
  const src = (v: Version) => (v.output ? `/p/${v.output}` : null);
  const props = { src, busy: false, locked: false, onUse: () => {}, onSwap: () => {} };
  it("shows both takes, one set of controls and the facts", () => {
    const html = renderToStaticMarkup(<TakeCompare left={take(1)} right={take(2, { approved: true })} {...props} />);
    expect(html.match(/<video/g)).toHaveLength(2);
    for (const word of ["Play both", "Back one frame", "Forward one frame", "Position in both takes", "Speed", "Loop", "Swap", "Model", "Length", "Price", "In the video", "Use this one"]) expect(html, word).toContain(word);
    expect(html).toContain("/p/generations/t1.mp4");
  });
  it("asks for the second take until one is chosen, and has no controls yet", () => {
    const html = renderToStaticMarkup(<TakeCompare left={take(1)} right={null} {...props} />);
    expect(html.match(/<video/g)).toHaveLength(1);
    expect(html).toContain("Click a version on the right");
    expect(html).not.toContain("Play both");
  });
  it("won't offer to use a take when the shot is locked", () => {
    const html = renderToStaticMarkup(<TakeCompare left={take(1)} right={take(2)} {...props} locked />);
    expect(html.match(/disabled=""/g)?.length).toBeGreaterThanOrEqual(2);
  });
  it("says so when a take has no video", () => {
    expect(renderToStaticMarkup(<TakeCompare left={take(1, { output: null })} right={take(2)} {...props} />)).toContain("No video to show");
  });
});
