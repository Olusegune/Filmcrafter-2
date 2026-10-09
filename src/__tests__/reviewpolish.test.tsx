import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(() => new Promise(() => {})), convertFileSrc: (p: string) => p }));

import { reviewHeadline, splitIssues, swapHeadline } from "../reviewSwap";
import { ReviewSheet } from "../Review";
import type { Job, Shot } from "../api";

describe("the line under the Review title", () => {
  const base = { rendered: 6, shots: 12, good: 0, minor: 0, major: 0, unchecked: 0, rendering: 0 };
  it("says how many takes there are, and nothing else when all is plain", () => {
    expect(reviewHeadline(base)).toBe("6 of 12 shots have a take.");
  });
  it("says how they look, in the order a person worries", () => {
    expect(reviewHeadline({ ...base, good: 3, minor: 2, major: 1 })).toBe("6 of 12 shots have a take: 3 look good, 2 have small notes, 1 needs attention.");
    expect(reviewHeadline({ ...base, good: 1, minor: 1, unchecked: 4, rendering: 2 })).toBe("6 of 12 shots have a take: 1 looks good, 1 has small notes, 4 were not checked by eye, 2 are being made.");
    expect(reviewHeadline({ ...base, unchecked: 1, rendering: 1 })).toContain("1 was not checked by eye, 1 is being made");
  });
});

describe("what the check found, most serious first", () => {
  const issues = [{ severity: "minor", detail: "a" }, { severity: "major", detail: "b" }, { severity: "minor", detail: "c" }, { severity: "major", detail: "d" }];
  it("shows the most serious issue first and keeps the rest behind it, in their own order", () => {
    const s = splitIssues(issues);
    expect(s.first?.detail).toBe("b");
    expect(s.rest.map((i) => i.detail)).toEqual(["d", "a", "c"]);
  });
  it("copes with one issue, none, and nothing at all", () => {
    expect(splitIssues([issues[0]])).toEqual({ first: issues[0], rest: [] });
    expect(splitIssues([])).toEqual({ first: null, rest: [] });
    expect(splitIssues(undefined)).toEqual({ first: null, rest: [] });
  });
  it("does not change the list it is given", () => {
    const copy = JSON.stringify(issues);
    splitIssues(issues);
    expect(JSON.stringify(issues)).toBe(copy);
  });
});

describe("the two lines over 'use all'", () => {
  it("says what is ready and the one thing worth knowing", () => {
    expect(swapHeadline([{ verdict: "good" }])).toEqual({ title: "1 new version ready to swap in", detail: "All of them look good." });
    expect(swapHeadline([{ verdict: "major" }])).toEqual({ title: "1 new version ready to swap in", detail: "It still has issues the check found." });
    expect(swapHeadline([{ verdict: "major" }, { verdict: "minor" }]).detail).toBe("All of them still have issues the check found.");
    expect(swapHeadline([{ verdict: "good" }, { verdict: "good" }, { verdict: "minor" }])).toEqual({ title: "3 new versions ready to swap in", detail: "1 of them still has issues the check found." });
    expect(swapHeadline([{ verdict: "good" }, { verdict: "checking" }, { verdict: "checking" }]).detail).toBe("2 are still being checked.");
    expect(swapHeadline([{ verdict: "unchecked" }]).detail).toContain("look before you swap");
  });
});

describe("the Review sheet", () => {
  const shots: Shot[] = ["S01-01", "S01-02"].map((id, i) => ({ id, scene: 1, number: i + 1, start: i * 6, end: i * 6 + 5, beats: [], source_shots: [], performers: [], framing: "", state: "", renderer: "" }));
  const take = (id: string, shot: string, created: number, review: unknown): Job => ({ id, shot_id: shot, plan: "production", provider: "kie", model: "m/model", state: "ready", kind: "video", output: `g/${id}.mp4`, created, updated: created, overrides: {}, review } as unknown as Job);
  const bad = { reviewed: true, status: "needs_attention", summary: "Too wide.", issues: [{ kind: "framing", severity: "major", detail: "Medium shot, not a close-up.", fix: "" }, { kind: "wardrobe", severity: "minor", detail: "Wrong collar.", fix: "" }, { kind: "anatomy", severity: "major", detail: "Fused fingers.", fix: "" }] };
  const jobs = [take("a1", "S01-01", 1, { reviewed: true, status: "good", summary: "ok", issues: [] }), take("a2", "S01-01", 2, bad), take("b1", "S01-02", 1, bad)];
  const html = renderToStaticMarkup(<ReviewSheet dir="" shots={shots} jobs={jobs} inUse={{ "S01-01": "a1" }} keys={{ openai: true, fal: true, kie: true, google: false, elevenlabs: false } as never} onSelect={() => {}} onJobs={() => {}} onClose={() => {}} />);
  it("says each thing once: no bar, no legend and no banner repeating what the tabs and the cards already say", () => {
    for (const gone of ["rv-bar", "rv-legend", "swap-banner"]) expect(html).not.toContain(gone);
  });
  it("puts the counts in the tabs and the total in one quiet sentence", () => {
    expect(html.match(/class="rv-count"/g)).toHaveLength(4);
    expect(html).toContain("2 of 2 shots have a take: 1 looks good, 1 needs attention.");
  });
  it("shows one issue per card and the others behind a 'more details' line, most serious first", () => {
    expect(html).toContain("Medium shot, not a close-up.");
    expect(html).toContain("2 more details");
    expect(html.indexOf("Fused fingers.")).toBeGreaterThan(html.indexOf("rv-more"));
    expect(html.indexOf("Wrong collar.")).toBeGreaterThan(html.indexOf("Fused fingers."));
  });
  it("gives each card one warm action, the others quiet", () => {
    expect(html.match(/btn small primary/g)).toHaveLength(1);
    expect(html.match(/btn small ghost/g)!.length).toBeGreaterThanOrEqual(2);
  });
});
