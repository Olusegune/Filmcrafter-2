import { describe, expect, it } from "vitest";
import { attentionStarts, COMPACT_HEIGHT, HEIGHT_MAX, HEIGHT_MIN, PPS_MAX, PPS_MIN, readLayout, stepAttention, writeLayout } from "../timelineView";

const memory = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v); }, m }; };

describe("the timeline layout is remembered for each project", () => {
  it("is empty until something is saved", () => {
    expect(readLayout("C:/a", memory())).toEqual({});
  });
  it("keeps one layout per project", () => {
    const s = memory();
    writeLayout("C:/a", { pps: 80, height: 300 }, s);
    writeLayout("C:/b", { pps: 12, compact: true }, s);
    expect(readLayout("C:/a", s)).toEqual({ pps: 80, height: 300 });
    expect(readLayout("C:/b", s)).toEqual({ pps: 12, compact: true });
  });
  it("changing one part keeps the rest", () => {
    const s = memory();
    writeLayout("C:/a", { pps: 80, height: 300 }, s);
    writeLayout("C:/a", { compact: true }, s);
    expect(readLayout("C:/a", s)).toEqual({ pps: 80, height: 300, compact: true });
    writeLayout("C:/a", { compact: false }, s);
    expect(readLayout("C:/a", s).compact).toBeUndefined();
  });
  it("starts a project that has none from the old shared zoom and height", () => {
    const s = memory();
    s.setItem("pf-zoom", "40"); s.setItem("pf-tl-h", "320");
    expect(readLayout("C:/new", s)).toEqual({ pps: 40, height: 320 });
    writeLayout("C:/new", { pps: 90 }, s);
    expect(readLayout("C:/new", s)).toEqual({ pps: 90, height: 320 });
  });
  it("clamps numbers and ignores damaged values", () => {
    const s = memory();
    s.setItem("pf-tl:C:/a", JSON.stringify({ pps: 99999, height: 1, compact: "yes" }));
    expect(readLayout("C:/a", s)).toEqual({ pps: PPS_MAX, height: HEIGHT_MIN });
    s.setItem("pf-tl:C:/a", JSON.stringify({ pps: 0.4, height: 99999 }));
    expect(readLayout("C:/a", s)).toEqual({ pps: PPS_MIN, height: HEIGHT_MAX });
    for (const bad of ["{not json", "null", "[1,2]", "7", JSON.stringify({ pps: "fast", height: null })]) {
      s.setItem("pf-tl:C:/a", bad);
      expect(readLayout("C:/a", s)).toEqual({});
    }
  });
  it("never throws when storage is missing or blocked", () => {
    const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    expect(readLayout("C:/a", blocked)).toEqual({});
    expect(() => writeLayout("C:/a", { pps: 10 }, blocked)).not.toThrow();
    expect(readLayout("C:/a", null)).toEqual({});
    expect(() => writeLayout("C:/a", { pps: 10 }, null)).not.toThrow();
  });
  it("compact is shorter than the smallest height the person can drag to", () => {
    expect(COMPACT_HEIGHT).toBeGreaterThanOrEqual(HEIGHT_MIN);
    expect(COMPACT_HEIGHT).toBeLessThan(262);
  });
});

describe("stepping between the shots that need attention", () => {
  const shots = [{ id: "a", start: 0 }, { id: "b", start: 4 }, { id: "c", start: 8 }, { id: "d", start: 12 }];
  const starts = attentionStarts(shots, new Set(["d", "b", "zzz"]));
  it("lists their start times in order, leaving out ids that are not shots", () => {
    expect(starts).toEqual([4, 12]);
    expect(attentionStarts(shots, new Set())).toEqual([]);
  });
  it("goes to the next one after the playhead", () => {
    expect(stepAttention(starts, 0, 1)).toBe(4);
    expect(stepAttention(starts, 4, 1)).toBe(12);
    expect(stepAttention(starts, 12, 1)).toBeNull();
  });
  it("goes to the previous one, not the shot you are in", () => {
    expect(stepAttention(starts, 13, -1)).toBe(12);
    expect(stepAttention(starts, 12.1, -1)).toBe(4);       // just inside the shot: go back to the one before
    expect(stepAttention(starts, 12.3, -1)).toBe(12);      // well inside it: its own start first
    expect(stepAttention(starts, 4, -1)).toBeNull();
  });
  it("finds nothing when no shot needs attention", () => {
    expect(stepAttention([], 5, 1)).toBeNull();
    expect(stepAttention([], 5, -1)).toBeNull();
  });
});
