import { describe, expect, it } from "vitest";
import { beatGrid, moveAt } from "../overlayMotion";

describe("overlay movement in the player", () => {
  it("starts offset and settles exactly where the layer is placed", () => {
    expect(moveAt("rise", 1, 1, 5, 0.4)).toEqual({ dx: 0, dy: 7, k: 1, reveal: 1 });          // starts 7% of the frame lower
    expect(moveAt("rise", 5, 1, 5, 0.4).dy).toBe(0);
    expect(moveAt("drop", 1, 1, 5, 0.4).dy).toBe(-7);
    expect(moveAt("slide_left", 1, 1, 5, 0.4).dx).toBe(14);
    expect(moveAt("slide_right", 1, 1, 5, 0.4).dx).toBe(-14);
    expect(moveAt("slide_left", 3, 1, 5, 0.4)).toEqual({ dx: 0, dy: 0, k: 1, reveal: 1 });
  });
  it("eases out: most of the move happens early", () => {
    const m = moveAt("rise", 1.3, 1, 5, 0.4);                                      // a quarter of the way through a 1.2 s move
    expect(m.dy).toBeGreaterThan(0);
    expect(m.dy).toBeLessThan(3.2);
  });
  it("zooms from the same sizes the export uses", () => {
    expect(moveAt("zoom_in", 1, 1, 5, 0.4).k).toBeCloseTo(0.82);
    expect(moveAt("zoom_out", 1, 1, 5, 0.4).k).toBeCloseTo(1.18);
    expect(moveAt("zoom_in", 4, 1, 5, 0.4).k).toBeCloseTo(1);
    expect(moveAt("pushin", 5, 1, 5, 0.4).k).toBeCloseTo(1.08);
  });
  it("does nothing for a fade or an unknown name", () => {
    expect(moveAt("fade", 1, 1, 5, 0.4)).toEqual({ dx: 0, dy: 0, k: 1, reveal: 1 });
    expect(moveAt(undefined, 1, 1, 5, 0.4)).toEqual({ dx: 0, dy: 0, k: 1, reveal: 1 });
  });
  it("wipes and types in from the left, a letter at a time for the typewriter", () => {
    expect(moveAt("wipe", 1, 1, 5, 0.4).reveal).toBe(0);
    expect(moveAt("wipe", 1.6, 1, 5, 0.4).reveal).toBeCloseTo(0.5);
    expect(moveAt("wipe", 5, 1, 5, 0.4).reveal).toBe(1);
    expect(moveAt("typewriter", 1.6, 1, 5, 0.4, null, 10).reveal).toBeCloseTo(0.5);       // 5 of 10 letters
    expect(moveAt("typewriter", 1.7, 1, 5, 0.4, null, 10).reveal).toBeCloseTo(0.5);       // still 5 until the sixth arrives
    expect(moveAt("typewriter", 5, 1, 5, 0.4, null, 10).reveal).toBe(1);
  });
  it("bounces from above, pops from nothing and pulses on the beat", () => {
    expect(moveAt("bounce", 1, 1, 5, 0.4).dy).toBeCloseTo(-9);
    expect(moveAt("bounce", 5, 1, 5, 0.4).dy).toBeCloseTo(0);
    expect(moveAt("pop", 1, 1, 5, 0.4).k).toBeCloseTo(0.05);
    expect(moveAt("pop", 5, 1, 5, 0.4).k).toBeCloseTo(1);
    const beat = { period: 1, first: 0 };
    expect(moveAt("pulse", 3, 1, 5, 0.4, beat).k).toBeCloseTo(1.06);                         // on the beat
    expect(moveAt("pulse", 3.9, 1, 5, 0.4, beat).k).toBeLessThan(1.0001);                    // just before the next one
    expect(moveAt("pulse", 3, 1, 5, 0.4, null).k).toBe(1);                                   // no tempo: still
  });
  it("finds the beat grid from the song map", () => {
    expect(beatGrid({ bpm: 120, downbeats: [0.25, 2.25] })).toEqual({ period: 0.5, first: 0.25 });
    expect(beatGrid({ bpm: 0 })).toBeNull();
    expect(beatGrid(null)).toBeNull();
  });
  it("swells on each strong hit and settles, and stays still before the first or with none", () => {
    const hits = [2.0, 3.5];
    expect(moveAt("accent", 2.0, 1, 5, 0.4, null, 0, hits).k).toBeCloseTo(1.08);
    expect(moveAt("accent", 2.35, 1, 5, 0.4, null, 0, hits).k).toBeCloseTo(1);
    expect(moveAt("accent", 3.5, 1, 5, 0.4, null, 0, hits).k).toBeCloseTo(1.08);
    expect(moveAt("accent", 1.5, 1, 5, 0.4, null, 0, hits).k).toBe(1);
    expect(moveAt("accent", 2.0, 1, 5, 0.4, null, 0, []).k).toBe(1);
  });
});
