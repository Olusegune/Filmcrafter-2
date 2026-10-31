import { describe, expect, it } from "vitest";
import { clipAt, clipName, clockTime, cutNotes, frameSeconds, nearest, snapPoints } from "../cutMath";
import type { Cut } from "../api";

const FT = 254_016_000_000 / 24;
const clip = (id: string, shot: string, a: number, b: number) => ({ id, shot, start: a * FT, source_in: 0, duration: (b - a) * FT, take: null, start_s: a / 24, duration_s: (b - a) / 24, source_in_s: 0, start_frame: a, frames: b - a });
const cut = (over: Partial<Cut> = {}): Cut => ({ stored: true, unplaced: [], orphans: [], can_undo: false, can_redo: false, history: [],
  sequence: { fps: [24, 1], frame_ticks: FT, ticks_per_second: 254_016_000_000, length: 240 * FT, length_s: 10, tracks: [{ id: "V1", kind: "video", locked: false, hidden: false, muted: false, clips: [clip("c1", "S1", 0, 96), clip("c2", "S2", 96, 240)] }],
    markers: [{ id: "m1", at: 120 * FT, at_s: 5, name: "turn" }], ranges: [] }, ...over });

describe("the cut lane's helpers", () => {
  it("knows how long a frame is", () => { expect(frameSeconds(cut())).toBeCloseTo(1 / 24, 9); });

  it("snaps to the film's ends, other clips' edges, markers and the playhead, but not to the clip being dragged", () => {
    expect(snapPoints(cut(), null, null)).toEqual([0, 4, 5, 10]);
    expect(snapPoints(cut(), "c2", 2.5)).toEqual([0, 2.5, 4, 5, 10]);                      // c2's own edges are not offered back to it; the film's end and the other clip's edge still are
  });

  it("picks the nearest point within reach and leaves a time alone when none is", () => {
    const p = [0, 4, 5, 10];
    expect(nearest(p, 4.05, 0.1)).toBe(4);
    expect(nearest(p, 4.6, 0.1)).toBe(4.6);
    expect(nearest(p, 4.5, 0.6)).toBe(4);                                                    // a tie goes to the earlier point
  });

  it("tells the person plainly what is not in the film", () => {
    expect(cutNotes(cut())).toEqual([]);
    expect(cutNotes(cut({ unplaced: ["S3"] }))[0]).toBe("Shot S3 is not in the cut, so it is left out of the film.");
    expect(cutNotes(cut({ unplaced: ["S3", "S4", "S5", "S6"] }))[0]).toMatch(/^4 shots \(S3, S4, S5…\) are not in the cut, so they are left out/);
    expect(cutNotes(cut({ orphans: ["c9"] }))[0]).toMatch(/no longer in the plan/);
    expect(cutNotes(cut(), [{ start: 3 }, { start: 11 }])).toEqual(["1 layer starts after the end of the cut, so it will not be seen."]);
    expect(cutNotes(cut(), [{ start: 11 }, { start: 12 }])[0]).toMatch(/^2 layers start after the end/);
  });

  it("says times the way the timeline does and finds the clip under a time", () => {
    expect(clockTime(0)).toBe("0:00.00");
    expect(clockTime(75.5)).toBe("1:15.50");
    expect(clockTime(-3)).toBe("0:00.00");
    expect(clipName(clip("c1", "S1", 24, 72))).toBe("S1 from 0:01.00 for 0:02.00");
    expect(clipAt(cut(), 1)?.id).toBe("c1");
    expect(clipAt(cut(), 4)?.id).toBe("c2");                                                 // an edge belongs to the clip that starts there
    expect(clipAt(cut(), 11)).toBeNull();
  });
});
