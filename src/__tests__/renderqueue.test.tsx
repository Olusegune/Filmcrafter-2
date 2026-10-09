import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import type { Job } from "../api";
import { batchOutcome, fmtDuration, phaseOf, queueSentence, queueSummary, rowFor, typicalSeconds } from "../queueMath";
import { QueueBanner, QueueChip, RenderQueueSheet } from "../RenderQueue";

const NOW = 10_000;
const job = (id: string, over: Partial<Job> = {}): Job => ({ id, shot_id: "S01-01", plan: "production", provider: "kie", model: "bytedance/seedance-2", state: "queued", kind: "video", overrides: {},
  provider_job_id: null, output: null, error: null, cost: null, created: NOW - 500, updated: NOW - 500, attempts: 0, shot_start: 0, shot_end: 4, ...over });
const done = (id: string, secs: number, over: Partial<Job> = {}) => job(id, { state: "ready", output: id + ".mp4", submitted: NOW - 1000, updated: NOW - 1000 + secs, ...over });
const rendering = (id: string, started: number, over: Partial<Job> = {}) => job(id, { state: "submitted", submitted: NOW - started, updated: NOW - 2, ...over });

describe("how long a model usually takes here", () => {
  it("is the middle of its finished takes, per model and per kind", () => {
    expect(typicalSeconds("bytedance/seedance-2", "video", [done("a", 60), done("b", 100), done("c", 80)])).toBe(80);
    expect(typicalSeconds("bytedance/seedance-2", "video", [done("a", 60), done("b", 100)])).toBe(80);
    expect(typicalSeconds("bytedance/seedance-2", "video", [done("a", 60, { model: "other" })])).toBeNull();
    expect(typicalSeconds("bytedance/seedance-2", "image", [done("a", 60)])).toBeNull();
  });
  it("ignores absurd or unrecorded durations", () => {
    expect(typicalSeconds("bytedance/seedance-2", "video", [done("a", 1), done("b", 99999), job("c", { state: "ready" })])).toBeNull();
  });
});

describe("one row of the queue", () => {
  it("names the phase of every state", () => {
    expect(["queued", "submitting", "submitted", "ready", "uncertain", "failed"].map((s) => phaseOf(job("x", { state: s as Job["state"] })))).toEqual(["waiting", "sending", "rendering", "done", "check", "failed"]);
  });
  it("uses the provider's own progress when it gave one, and estimates time left from it", () => {
    const r = rowFor(rendering("r", 60, { progress: 0.5, detail: "in progress" }), [done("a", 120)], NOW);
    expect(r.fraction).toBe(0.5);
    expect(r.elapsed).toBe(60);
    expect(r.etaS).toBe(60);
    expect(r.label).toBe("Rendering · in progress");
  });
  it("falls back to elapsed over the typical time, and never claims to be finished", () => {
    const r = rowFor(rendering("r", 60), [done("a", 120)], NOW);
    expect(r.fraction).toBeCloseTo(0.5, 2);
    expect(r.etaS).toBe(60);
    expect(rowFor(rendering("r", 500), [done("a", 120)], NOW).fraction).toBe(0.95);
    expect(rowFor(rendering("r", 500), [done("a", 120)], NOW).etaS).toBe(0);
  });
  it("shows no bar or time when nothing is known yet", () => {
    const r = rowFor(rendering("r", 30), [], NOW);
    expect(r.fraction).toBeNull();
    expect(r.etaS).toBeNull();
    expect(r.elapsed).toBe(30);
  });
});

describe("the queue as a whole", () => {
  const jobs = [done("d1", 100), rendering("r1", 20), rendering("r2", 40, { shot_id: "S01-02" }), job("w1", { shot_id: "S01-03", estimate_usd: 1.2 }), job("w2", { shot_id: "S01-04", estimate_usd: 0.8, created: NOW - 400 }),
    job("f1", { state: "failed", updated: NOW - 60, error: "x" }), job("gone", { state: "dismissed" }), done("old", 90, { updated: NOW - 5000 })];
  const q = queueSummary(jobs, NOW);
  it("counts what is rendering, waiting and finished lately, and leaves out dismissed and old takes", () => {
    expect(q.rendering).toBe(2);
    expect(q.waiting).toBe(2);
    expect(q.active).toBe(4);
    expect(q.failed.map((r) => r.job.id)).toEqual(["f1"]);
    expect(q.done.every((r) => NOW - r.job.updated <= 900)).toBe(true);
    expect(q.rows.some((r) => r.job.id === "gone")).toBe(false);
  });
  it("lists what is rendering first, then waiting in the order they were queued", () => {
    expect(q.rows.map((r) => r.job.id).slice(2)).toEqual(["w1", "w2"]);
    expect(q.rows.slice(0, 2).every((r) => r.phase === "rendering")).toBe(true);
  });
  it("adds up what is in flight and gives a time left only when every row can be estimated", () => {
    expect(q.estUsd).toBe(2);
    expect(q.etaS).not.toBeNull();
    expect(queueSummary([rendering("r", 10)], NOW).etaS).toBeNull();
  });
  it("says it in one sentence, or nothing when idle", () => {
    expect(queueSentence(q)).toMatch(/^2 rendering · 2 waiting · about /);
    expect(queueSentence(queueSummary([done("a", 10)], NOW))).toBe("");
  });
});

describe("durations and batch outcomes", () => {
  it("reads naturally", () => {
    expect([5, 59.6, 60, 95, 3600, 4500].map(fmtDuration)).toEqual(["5 s", "1 min", "1 min", "1 min 35 s", "1 h 0 min", "1 h 15 min"]);
  });
  it("counts ready and failed since the batch began, and ignores older or dismissed ones", () => {
    const o = batchOutcome([done("a", 10, { updated: NOW }), done("b", 10, { updated: NOW - 2000 }), job("c", { state: "failed", updated: NOW }), job("d", { state: "dismissed", updated: NOW })], NOW - 100);
    expect(o).toEqual({ ready: 1, failed: 1, text: "Renders finished: 1 ready, 1 failed." });
    expect(batchOutcome([], 0).text).toBe("Renders finished.");
  });
});

describe("what the screen shows", () => {
  const live = queueSummary([rendering("r", 20), job("w", { shot_id: "S01-02" })], NOW);
  it("the chip appears only while something is rendering, with an accessible name", () => {
    expect(renderToStaticMarkup(<QueueChip q={queueSummary([], NOW)} onOpen={() => {}} />)).toBe("");
    const html = renderToStaticMarkup(<QueueChip q={live} onOpen={() => {}} />);
    expect(html).toContain("1 rendering · 1 waiting");
    expect(html).toContain('aria-label="Render queue:');
  });
  it("the Review banner says new takes will appear and offers the queue", () => {
    expect(renderToStaticMarkup(<QueueBanner q={queueSummary([], NOW)} onOpen={() => {}} />)).toBe("");
    const html = renderToStaticMarkup(<QueueBanner q={live} onOpen={() => {}} />);
    expect(html).toContain("2 still rendering");
    expect(html).toContain("See progress");
  });
  it("the queue sheet lists rows with progress bars, cancel only for waiting ones, and retry only for failed ones", () => {
    const jobs = [rendering("r", 20, { progress: 0.4 }), job("w", { shot_id: "S01-02" }), job("f", { shot_id: "S01-03", state: "failed", error: "Prompt was flagged", updated: Math.floor(Date.now() / 1000) })];
    const html = renderToStaticMarkup(<RenderQueueSheet dir="d" jobs={jobs.map((j) => ({ ...j, updated: Math.floor(Date.now() / 1000) }))} shots={[]} onJob={() => {}} onShow={() => {}} onReview={() => {}} onClose={() => {}} />);
    expect(html).toContain('role="progressbar"');
    expect(html).toContain('aria-valuenow="40"');
    expect((html.match(/Cancel \(not sent yet/g) ?? []).length).toBe(1);
    expect((html.match(/Try again/g) ?? []).length).toBe(1);
    expect(html).toContain("Prompt was flagged");
  });
  it("an empty queue says so", () => {
    expect(renderToStaticMarkup(<RenderQueueSheet dir="d" jobs={[]} shots={[]} onJob={() => {}} onShow={() => {}} onReview={() => {}} onClose={() => {}} />)).toContain("Nothing is rendering right now.");
  });
});
