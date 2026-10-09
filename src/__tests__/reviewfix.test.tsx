import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { videoBehind } from "../Review";
import type { Job } from "../api";

const job = (id: string, over: Partial<Job> = {}): Job => ({ id, shot_id: "S01-09", plan: "production", provider: "kie", model: "bytedance/seedance-2-mini", state: "ready", kind: "video", overrides: {},
  provider_job_id: null, output: `generations/${id}.mp4`, error: null, cost: null, created: 1, updated: 1, attempts: 1, shot_start: 0, shot_end: 4, ...over });
const lip = (id: string, source: string | null, over: Partial<Job> = {}) => job(id, { kind: "lipsync", source_job: source, model: "volcengine/video-to-video-lip-sync", created: 5, ...over });

describe("which take a Review fix re-renders", () => {
  it("is the flagged take itself when it is a video", () => {
    const v = job("v1");
    expect(videoBehind(v, [v])).toBe(v);
  });

  it("is the video under a lip-synced take, never the lip-sync model (the reported 'Fix does nothing')", () => {
    const v = job("v1"), l = lip("l1", "v1");
    const r = videoBehind(l, [v, l]);
    expect(r.id).toBe("v1");
    expect(r.model).toBe("bytedance/seedance-2-mini");
  });

  it("follows a chain of lip-sync passes back to the video", () => {
    const v = job("v1"), l1 = lip("l1", "v1"), l2 = lip("l2", "l1");
    expect(videoBehind(l2, [v, l1, l2]).id).toBe("v1");
  });

  it("falls back to the shot's newest finished video when the link is missing", () => {
    const old = job("v0", { created: 1 }), newer = job("v2", { created: 3, model: "kling-2.6/image-to-video" }), l = lip("l1", "gone");
    expect(videoBehind(l, [old, newer, l]).id).toBe("v2");
    expect(videoBehind(lip("l9", null), [old, newer]).id).toBe("v2");
  });

  it("ignores other shots, other plans, unfinished takes and lip-sync takes when falling back", () => {
    const other = job("x1", { shot_id: "S02-01" }), plan = job("x2", { plan: "directed" }), queued = job("x3", { state: "queued" }), l = lip("l1", null), l0 = lip("l0", null);
    expect(videoBehind(l, [other, plan, queued, l0, l])).toBe(l);                                 // nothing to fall back to: the caller refuses to fix it
  });

  it("does not loop forever on a chain that points at itself", () => {
    const a = lip("a", "b"), b = lip("b", "a");
    expect(["a", "b"]).toContain(videoBehind(a, [a, b]).id);
  });
});
