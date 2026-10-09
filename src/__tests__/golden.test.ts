import { describe, expect, it } from "vitest";
import { goldenSteps, type GoldenInput } from "../GoldenStrip";

const base = (over: Partial<GoldenInput> = {}): GoldenInput => ({
  hasSong: true, shots: Array.from({ length: 10 }, (_, i) => ({ id: `s${i}` })), keyframes: {}, videoReady: new Set(), pending: 0,
  people: { total: 3, withPicture: 3 }, exported: false, ...over,
});
const state = (g: GoldenInput) => Object.fromEntries(goldenSteps(g).steps.map((s) => [s.id, s.state]));

describe("Golden Path strip", () => {
  it("starts at the plan when there is a song but no shots", () => {
    const g = base({ shots: [] });
    expect(state(g)).toMatchObject({ song: "done", plan: "current" });
    expect(goldenSteps(g).next?.id).toBe("plan");
  });
  it("makes keyframes the current step once planned, and counts them", () => {
    const g = base({ keyframes: { s0: "a", s1: "b" } });
    const { steps, next } = goldenSteps(g);
    expect(next?.id).toBe("keyframes");
    expect(steps.find((s) => s.id === "keyframes")).toMatchObject({ done: 2, of: 10, state: "current" });
    expect(state(g)).toMatchObject({ plan: "done", video: "todo" });
  });
  it("moves on to video when every shot has a keyframe, then to export", () => {
    const kf = Object.fromEntries(Array.from({ length: 10 }, (_, i) => [`s${i}`, "x"]));
    expect(goldenSteps(base({ keyframes: kf })).next?.id).toBe("video");
    const ready = new Set(Array.from({ length: 10 }, (_, i) => `s${i}`));
    const g = base({ keyframes: kf, videoReady: ready });
    expect(state(g)).toMatchObject({ keyframes: "done", video: "done", export: "current" });
  });
  it("does not hold the path up for optional pictures of people", () => {
    const g = base({ people: { total: 5, withPicture: 0 } });
    expect(state(g).refs).toBe("todo");
    expect(goldenSteps(g).next?.id).toBe("keyframes");
  });
  it("marks only the steps that cost money", () => {
    const paid = goldenSteps(base()).steps.filter((s) => !s.free).map((s) => s.id);
    expect(paid).toEqual(["keyframes", "video"]);
  });
  it("copes with a project that has no shots at all", () => {
    const g = base({ shots: [], hasSong: false });
    expect(() => goldenSteps(g)).not.toThrow();
    expect(goldenSteps(g).next?.id).toBe("song");
  });
});
