// S-01: paid work is queued only with a one-use token from the shell (confirm_spend), and only the audited screens may queue it.
import { beforeEach, describe, expect, it, vi } from "vitest";

const calls: { cmd: string; args: Record<string, unknown> }[] = [];
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async (cmd: string, args: Record<string, unknown>) => { calls.push({ cmd, args }); return cmd === "confirm_spend" ? "tok-123" : []; }),
  convertFileSrc: (p: string) => p,
}));

import { api } from "../api";

beforeEach(() => { calls.length = 0; });

describe("the spend token", () => {
  it("queueRender gets a token for exactly the batch it queues, then queues with it", async () => {
    await api.queueRender("/p", ["S01-02", "S01-01"], "fal", "m", {}, [], "image");
    expect(calls.map((c) => c.cmd)).toEqual(["confirm_spend", "queue_render"]);
    expect(calls[0].args).toEqual({ dir: "/p", shots: ["S01-02", "S01-01"], provider: "fal", kind: "image" });
    expect(calls[1].args).toMatchObject({ dir: "/p", shots: ["S01-02", "S01-01"], provider: "fal", kind: "image", spendToken: "tok-123" });
  });

  it("every call asks again: a token is never reused, so a retry or a second lip-sync is confirmed on its own", async () => {
    await api.queueRender("/p", ["a"], "kie", "m", {});
    await api.queueRender("/p", ["a"], "kie", "m", {}, [], "lipsync", "job1");
    expect(calls.filter((c) => c.cmd === "confirm_spend")).toHaveLength(2);
    expect(calls[2].args).toMatchObject({ kind: "lipsync" });
    expect(calls[3].args).toMatchObject({ kind: "lipsync", sourceJob: "job1" });
  });

  it("does not queue when the shell refuses to confirm", async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    (invoke as ReturnType<typeof vi.fn>).mockRejectedValueOnce("That isn't a FilmCrafter project.");
    await expect(api.queueRender("/nope", ["a"], "fal", null, {})).rejects.toBeTruthy();
    expect(calls.some((c) => c.cmd === "queue_render")).toBe(false);
  });
});

describe("who may queue paid work", () => {
  // Each of these shows the price (an ask(), a confirmation sheet, or the price beside the button) before it calls api.queueRender. A new file here needs the same, then an entry below.
  const AUDITED = ["Command.tsx", "Compose.tsx", "Extend.tsx", "Frames.tsx", "Keyframe.tsx", "MakeFilm.tsx", "Render.tsx", "Review.tsx", "SelectReview.tsx", "Studio.tsx", "Upgrade.tsx"];
  const all = import.meta.glob("../*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
  const text = (f: string) => all[`../${f}`];
  const files = Object.keys(all).map((k) => k.slice(3)).sort();

  it("only the audited screens call api.queueRender", () => {
    const callers = files.filter((f) => /api\.queueRender\(/.test(text(f)));
    expect(callers).toEqual(AUDITED);
  });

  it("nothing but the api layer invokes queue_render or confirm_spend directly", () => {
    const offenders = files.filter((f) => f !== "api.ts" && /invoke\(\s*["'](queue_render|confirm_spend)["']/.test(text(f)));
    expect(offenders).toEqual([]);
  });
});
