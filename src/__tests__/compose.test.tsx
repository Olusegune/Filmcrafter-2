import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/api/webview", () => ({ getCurrentWebview: () => ({ onDragDropEvent: () => Promise.resolve(() => {}) }) }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

import { ComposeTab, MODES, motionStep, secs } from "../Compose";

describe("the three ways to make a shot", () => {
  it("are start to end, references and motion, each said in plain words", () => {
    expect(MODES.map((m) => m.id)).toEqual(["frames", "refs", "motion"]);
    expect(MODES.every((m) => m.label && m.blurb.length > 40)).toBe(true);
    expect(MODES[0].label).toBe("Start → End");
    expect(MODES[2].blurb).toContain("video of a movement");
  });
});

describe("what a motion take needs", () => {
  it("asks for the video, then the character, then it is ready", () => {
    expect(motionStep({ video: null, image: null })).toMatchObject({ step: "video" });
    expect(motionStep({ video: null, image: "a.png" }).text).toContain("3 to 30 seconds");
    expect(motionStep({ video: "v.mp4", image: null })).toMatchObject({ step: "image" });
    expect(motionStep({ video: "v.mp4", image: "a.png" }).step).toBe("ready");
  });
  it("writes lengths the way the screen does", () => {
    expect(secs(6)).toBe("6 s");
    expect(secs(6.04)).toBe("6 s");
    expect(secs(2.55)).toBe("2.6 s");
    expect(secs(null)).toBe("");
  });
});

describe("the tab", () => {
  it("opens on Start → End with the three ways to switch, and says what each is for", () => {
    const html = renderToStaticMarkup(<ComposeTab dir="d" shot="S01-01" keys={{ openai: false, fal: false, kie: true, google: false } as never} />);
    expect(html).toContain('role="tablist"');
    for (const m of MODES) expect(html).toContain(m.label);
    expect(html).toContain('aria-selected="true"');
    expect(html).toContain("Two pictures");
  });
});

import { clipLine } from "../Compose";

describe("how a saved motion is described", () => {
  it("is its length and its size, whichever are known", () => {
    expect(clipLine({ seconds: 12.4, width: 1080, height: 1920 })).toBe("12.4 s · 1080×1920");
    expect(clipLine({ seconds: 8, width: null, height: null })).toBe("8 s");
    expect(clipLine({ seconds: null, width: 1280, height: 720 })).toBe("1280×720");
    expect(clipLine({ seconds: null, width: null, height: null })).toBe("");
  });
});

import { filterClips, parseTags, tagCounts } from "../Compose";
import { proofAdvice } from "../Frames";
import type { MotionClip } from "../api";

const clipOf = (name: string, tags: string[] = []): MotionClip => ({ id: name, name, seconds: 5, width: 160, height: 90, added: 1, thumb: null, tags });

describe("finding a saved motion", () => {
  const all = [clipOf("Slow walk", ["walk", "slow"]), clipOf("Salsa", ["dance"]), clipOf("Runway", ["walk"]), { ...clipOf("Old one"), tags: undefined }];
  it("matches the name or a tag, whatever the case", () => {
    expect(filterClips(all, "SALSA", null).map((c) => c.name)).toEqual(["Salsa"]);
    expect(filterClips(all, "wal", null).map((c) => c.name)).toEqual(["Slow walk", "Runway"]);
    expect(filterClips(all, "  ", null)).toHaveLength(4);
  });
  it("narrows by tag and by both", () => {
    expect(filterClips(all, "", "walk").map((c) => c.name)).toEqual(["Slow walk", "Runway"]);
    expect(filterClips(all, "run", "walk").map((c) => c.name)).toEqual(["Runway"]);
    expect(filterClips(all, "salsa", "walk")).toEqual([]);
  });
  it("counts the tags in use, most used first, and copes with motions saved before tags existed", () => {
    expect(tagCounts(all)).toEqual([["walk", 2], ["dance", 1], ["slow", 1]]);
  });
  it("reads typed tags the way the engine does", () => {
    expect(parseTags("Walk,  slow , , WALK, a very long tag that goes on past the limit")).toEqual(["walk", "slow", "a very long tag that goe"]);
    expect(parseTags("1,2,3,4,5,6,7,8,9,10")).toHaveLength(8);
    expect(parseTags("")).toEqual([]);
  });
});

describe("what to say after checking where a take landed", () => {
  it("offers to mark an unproven model only when the take landed", () => {
    expect(proofAdvice({ ok: true, verdict: "landed", proven: false }).canMark).toBe(true);
    expect(proofAdvice({ ok: true, verdict: "landed", proven: true })).toMatchObject({ canMark: false, text: expect.stringContaining("already") });
    expect(proofAdvice({ ok: true, verdict: "missed", proven: false }).canMark).toBe(false);
    expect(proofAdvice({ ok: true, verdict: "unclear", proven: false }).canMark).toBe(false);
    expect(proofAdvice({ ok: false }).canMark).toBe(false);
  });
});

import { isTracked } from "../api";

describe("which engine calls can be undone", () => {
  it("are the ones that change a shot's settings", () => {
    expect(isTracked("library", "approve")).toBe(true);
    expect(isTracked("library", "lock")).toBe(true);
    expect(isTracked("frames", "set")).toBe(true);
    expect(isTracked("compose", "set_motion")).toBe(true);
  });
  it("are not reads, renders or the motion library", () => {
    expect(isTracked("frames", "get")).toBe(false);
    expect(isTracked("compose", "queue_motion")).toBe(false);
    expect(isTracked("compose", "library_remove")).toBe(false);
    expect(isTracked("nothing", "set")).toBe(false);
  });
});
