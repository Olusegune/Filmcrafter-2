import { describe, expect, it } from "vitest";
import { evalKeys, upsertKey, type Key } from "../overlayKeys";

// the same cases as VECTORS in analysis/tests/test_keyframes.py
const VECTORS: [Key[], number, Record<string, number>][] = [
  [[{ t: 0, x: 0.2, ease: "linear" }, { t: 2, x: 0.8 }], 1.0, { x: 0.5 }],
  [[{ t: 0, x: 0.0, ease: "ease_in" }, { t: 2, x: 1.0 }], 1.0, { x: 0.25 }],
  [[{ t: 0, x: 0.0, ease: "ease_out" }, { t: 2, x: 1.0 }], 1.0, { x: 0.75 }],
  [[{ t: 0, x: 0.0, ease: "ease_in_out" }, { t: 2, x: 1.0 }], 0.5, { x: 0.15625 }],
  [[{ t: 0, x: 0.0, ease: "hold" }, { t: 2, x: 1.0 }], 1.9, { x: 0.0 }],
  [[{ t: 1, x: 0.3 }, { t: 3, x: 0.7 }], 0.0, { x: 0.3 }],
  [[{ t: 1, x: 0.3 }, { t: 3, x: 0.7 }], 9.0, { x: 0.7 }],
  [[{ t: 0, x: 0.1, ease: "linear" }, { t: 1, scale: 2 }, { t: 2, x: 0.5 }], 1.0, { x: 0.3, scale: 2.0 }],
];

describe("keyframe curves", () => {
  it.each(VECTORS)("agrees with the engine (%j at %f)", (keys, t, want) => {
    const got = evalKeys(keys, t);
    expect(Object.keys(got).sort()).toEqual(Object.keys(want).sort());
    for (const k of Object.keys(want)) expect((got as Record<string, number>)[k]).toBeCloseTo(want[k], 3);
  });
  it("sets nothing when there are no keys", () => {
    expect(evalKeys(undefined, 1)).toEqual({});
    expect(evalKeys([], 1)).toEqual({});
  });
  it("changes a key within a tenth of a second instead of adding a second one, and keeps the keys in time order", () => {
    const one = upsertKey([], 1, { x: 0.2 });
    expect(one).toHaveLength(1);
    expect(upsertKey(one, 1.05, { y: 0.9 })).toEqual([{ t: 1, ease: "ease_in_out", x: 0.2, y: 0.9 }]);
    const two = upsertKey(one, 0.2, { x: 0.5 });
    expect(two.map((k) => k.t)).toEqual([0.2, 1]);
  });
  it("stops at twelve keys", () => {
    let keys: Key[] = [];
    for (let i = 0; i < 15; i++) keys = upsertKey(keys, i * 0.5, { x: 0.5 });
    expect(keys).toHaveLength(12);
  });
});
