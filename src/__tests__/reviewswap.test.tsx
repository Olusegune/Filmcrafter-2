import { describe, expect, it } from "vitest";
import type { Job } from "../api";
import { inUseTake, newVersion, swapSummary, takesOf, upgradesFor, verdictOf } from "../reviewSwap";

const job = (id: string, created: number, over: Partial<Job> = {}): Job => ({ id, shot_id: "S01", plan: "production", provider: "kie", model: "m", state: "ready", kind: "video", overrides: {},
  provider_job_id: null, output: `${id}.mp4`, error: null, cost: null, created, updated: created + 5, attempts: 1, shot_start: 0, shot_end: 4, ...over });
const rv = (status: "good" | "minor" | "needs_attention" | "unchecked", over = {}) => ({ reviewed: true, status, ...over });

describe("which take is in the video", () => {
  it("is the approved one, even when a newer one has finished", () => {
    const jobs = [job("a", 1), job("b", 2)];
    expect(inUseTake("S01", jobs, "a")?.id).toBe("a");
  });
  it("is the newest finished take when none is approved, or the approved one is gone", () => {
    const jobs = [job("a", 1), job("b", 2)];
    expect(inUseTake("S01", jobs, null)?.id).toBe("b");
    expect(inUseTake("S01", jobs, "missing")?.id).toBe("b");
  });
  it("ignores keyframes, unfinished takes, reference pictures and other shots, and keeps to the newest take's plan", () => {
    const jobs = [job("k", 9, { kind: "image" }), job("q", 8, { state: "queued" }), job("x", 7, { shot_id: "S02" }), job("p", 6, { kind: "asset" }), job("old", 1, { plan: "directed" }), job("a", 2)];
    expect(takesOf("S01", jobs).map((j) => j.id)).toEqual(["a"]);
  });
  it("is nothing for a shot with no take", () => { expect(inUseTake("S09", [job("a", 1)], null)).toBeUndefined(); });
});

describe("a new version waiting to be swapped in", () => {
  const old = job("a", 1);
  it("is the newest finished take made after the one in use", () => {
    expect(newVersion(old, [old, job("b", 2), job("c", 3)])?.id).toBe("c");
  });
  it("includes a lip-synced take made from the new video", () => {
    expect(newVersion(old, [old, job("b", 2), job("l", 3, { kind: "lipsync", source_job: "b" })])?.id).toBe("l");
  });
  it("waits while the shot is still rendering (a lip-sync pass may be coming), and offers nothing when nothing is newer", () => {
    expect(newVersion(old, [old, job("b", 2), job("l", 3, { kind: "lipsync", state: "submitted", output: null })])).toBeNull();
    expect(newVersion(old, [old])).toBeNull();
    expect(newVersion(job("b", 2), [old, job("b", 2)])).toBeNull();
  });
  it("does not count a re-rendered keyframe as a new version", () => {
    expect(newVersion(old, [old, job("k", 5, { kind: "image" })])).toBeNull();
  });
});

describe("what the automatic check said about the new version", () => {
  it("maps the statuses to the words on screen", () => {
    expect(verdictOf(job("a", 1, { review: rv("good") }))).toBe("good");
    expect(verdictOf(job("a", 1, { review: rv("minor") }))).toBe("minor");
    expect(verdictOf(job("a", 1, { review: rv("needs_attention") }))).toBe("major");
    expect(verdictOf(job("a", 1, { review: rv("unchecked") }))).toBe("unchecked");
    expect(verdictOf(job("a", 1, { review: { reviewed: false } }))).toBe("checking");
    expect(verdictOf(job("a", 1))).toBe("checking");
  });
  it("treats an accepted take as good", () => {
    expect(verdictOf(job("a", 1, { review: rv("needs_attention", { accepted: true }) }))).toBe("good");
    expect(verdictOf(job("a", 1, { review: rv("unchecked", { accepted: true }) }))).toBe("good");
  });
});

describe("upgrades across shots and the sentence above the buttons", () => {
  const shots = [{ id: "S01" }, { id: "S02" }, { id: "S03" }];
  const jobs = [job("a", 1, { review: rv("needs_attention") }), job("b", 5, { review: rv("good") }),
    job("c", 1, { shot_id: "S02" }), job("d", 6, { shot_id: "S02", review: rv("minor") }), job("e", 1, { shot_id: "S03" })];
  const pinned = { S01: "a", S02: "c" };   // Fix keeps the flagged take in the video until the new one is swapped in
  it("without an approved take the newest is already in use, so there is nothing to swap", () => {
    expect(upgradesFor(shots, jobs, {}, new Set())).toEqual([]);
  });
  it("lists one upgrade per shot that has a newer take, in shot order", () => {
    const u = upgradesFor(shots, jobs, pinned, new Set());
    expect(u.map((x) => [x.shot.id, x.cur.id, x.next.id, x.verdict])).toEqual([["S01", "a", "b", "good"]].concat([["S02", "c", "d", "minor"]]).map((r) => r as never));
  });
  it("leaves out a version the user chose not to take, and treats an approved newer take as already in use", () => {
    expect(upgradesFor(shots, jobs, pinned, new Set(["b"])).map((x) => x.shot.id)).toEqual(["S02"]);
    expect(upgradesFor(shots, jobs, { ...pinned, S01: "b" }, new Set()).map((x) => x.shot.id)).toEqual(["S02"]);
  });
  it("says what the check found, in one sentence", () => {
    expect(swapSummary([{ verdict: "good" }])).toBe("1 new version is ready to swap in. All of them look good.");
    expect(swapSummary([{ verdict: "good" }, { verdict: "minor" }, { verdict: "major" }])).toBe("3 new versions are ready to swap in. 2 still have issues the check found; the rest look good.");
    expect(swapSummary([{ verdict: "good" }, { verdict: "checking" }])).toContain("1 is still being checked");
    expect(swapSummary([{ verdict: "unchecked" }])).toContain("look before you swap");
  });
});
