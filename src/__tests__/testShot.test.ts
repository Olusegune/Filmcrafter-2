import { describe, expect, it } from "vitest";
import { pickTestShot, type TestCandidate } from "../testShot";

const shot = (id: string, start: number, end: number, over: Partial<TestCandidate> = {}): TestCandidate => ({ id, start, end, performers: ["Ada"], framing: "wide shot", ...over });
const lyrics = [{ start: 4, end: 8 }];
const kf = (...ids: string[]) => Object.fromEntries(ids.map((i) => [i, `project:assets/${i}.png`]));

describe("which shot to test before rendering them all", () => {
  it("prefers a shot with a mouth to sync and a face close enough to judge, and says why", () => {
    const r = pickTestShot([shot("A", 0, 3), shot("B", 4, 7, { framing: "medium close-up", emotion: "dread" }), shot("C", 8, 11)], kf("A", "B", "C"), new Set(), lyrics)!;
    expect(r.id).toBe("B");
    expect(r.why).toEqual(["a mouth to sync to the song", "a face close enough to judge", "the feeling “dread”"]);
  });
  it("only considers shots with an approved keyframe and no take yet", () => {
    const shots = [shot("A", 4, 7, { framing: "close-up" }), shot("B", 8, 10)];
    expect(pickTestShot(shots, kf("B"), new Set(), lyrics)!.id).toBe("B");           // A has no keyframe
    expect(pickTestShot(shots, kf("A", "B"), new Set(["A"]), lyrics)!.id).toBe("B");  // A already has a take
    expect(pickTestShot(shots, {}, new Set(), lyrics)).toBeNull();
    expect(pickTestShot(shots, kf("A", "B"), new Set(["A", "B"]), lyrics)).toBeNull();
  });
  it("picks a dance shot when nothing is sung, and ignores a wide shot's pretence of being close", () => {
    const r = pickTestShot([shot("A", 0, 4), shot("B", 10, 14, { text: "Ada dances across the room" }), shot("C", 20, 24, { framing: "wide close shot of the room" })], kf("A", "B", "C"), new Set(), [])!;
    expect(r.id).toBe("B");
    expect(r.why).toContain("a dance move");
    expect(pickTestShot([shot("C", 20, 24, { framing: "wide close shot of the room" })], kf("C"), new Set(), [])!.why).not.toContain("a face close enough to judge");
  });
  it("needs a performer for any of it, and never picks a shot with no length", () => {
    expect(pickTestShot([shot("A", 4, 7, { performers: [] })], kf("A"), new Set(), lyrics)!.why).toEqual([]);
    expect(pickTestShot([shot("A", 4, 4)], kf("A"), new Set(), lyrics)).toBeNull();
  });
  it("copes with lyrics that have no times", () => {
    expect(pickTestShot([shot("A", 4, 7)], kf("A"), new Set(), [{ start: null }, {}])).not.toBeNull();
  });
});
