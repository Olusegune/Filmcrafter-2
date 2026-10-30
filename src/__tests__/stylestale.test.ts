import { describe, expect, it } from "vitest";
import { effectiveLook, styleChangedSince } from "../styleStale";

describe("a shot made in an earlier style is marked, never re-rendered", () => {
  const take = (look: string | null | undefined, over = {}) => ({ state: "ready", kind: "video", look, ...over });
  it("marks a finished video take made in another look", () => {
    expect(styleChangedSince([take("claymation")], "noir")).toBe(true);
  });
  it("leaves alone takes in the same look, unrecorded looks, pictures and unfinished takes", () => {
    expect(styleChangedSince([take("noir")], "noir")).toBe(false);
    expect(styleChangedSince([take(null), take(undefined)], "noir")).toBe(false);
    expect(styleChangedSince([take("claymation", { kind: "image" })], "noir")).toBe(false);
    expect(styleChangedSince([take("claymation", { state: "failed" })], "noir")).toBe(false);
    expect(styleChangedSince([], "noir")).toBe(false);
  });
});

describe("the look a shot is played in", () => {
  const own = { shots: { "S06-02": "anime" }, scenes: [{ scene: 6, style: "live-action" }, { scene: 1, style: null }] };
  it("is the shot's own look, then its scene's, then the film's", () => {
    expect(effectiveLook(own, "S06-02", 6, "noir")).toBe("anime");
    expect(effectiveLook(own, "S06-03", 6, "noir")).toBe("live-action");
    expect(effectiveLook(own, "S01-01", 1, "noir")).toBe("noir");
    expect(effectiveLook(null, "S01-01", 1, "noir")).toBe("noir");
    expect(effectiveLook({ shots: {}, scenes: [] }, "S01-01", undefined, "noir")).toBe("noir");
  });
  it("compares a take with the shot's own look, not the film's", () => {
    const made = [{ state: "ready", kind: "video", look: "noir" }];
    expect(styleChangedSince(made, effectiveLook(own, "S06-02", 6, "noir"))).toBe(true);           // the shot got its own look after the take was made
    expect(styleChangedSince(made, effectiveLook(own, "S01-01", 1, "noir"))).toBe(false);          // a shot with no look of its own still follows the film
    const inOwn = [{ state: "ready", kind: "video", look: "anime" }];
    expect(styleChangedSince(inOwn, effectiveLook(own, "S06-02", 6, "claymation"))).toBe(false);   // the film's look changed, but this shot keeps its own: nothing to flag
    expect(styleChangedSince(inOwn, effectiveLook({ shots: {}, scenes: [] }, "S06-02", 6, "claymation"))).toBe(true);   // its own look was cleared: it follows the film again
  });
});
