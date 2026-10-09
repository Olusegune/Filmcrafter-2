import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/api/webview", () => ({ getCurrentWebview: () => ({ onDragDropEvent: () => Promise.resolve(() => {}) }) }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

import type { LightShot, LightingPlan } from "../api";
import { END_IDEAS, FramesStage, framesStep } from "../Frames";
import { LightStrip, LightingSheet } from "../Lighting";
import { applySentence, kelvinColour, levelOpacity, lightColour, MOOD_TINT, targets } from "../lightingView";
import { SHORTCUTS } from "../shortcuts";

describe("what a shot needs before it can render start to end", () => {
  it("asks for the start frame first, then where the shot lands, then it is ready", () => {
    expect(framesStep({ start: null, end: null, end_mode: "none" }).step).toBe("start");
    expect(framesStep({ start: "a.png", end: null, end_mode: "none" }).step).toBe("end");
    expect(framesStep({ start: "a.png", end: null, end_mode: "own" })).toMatchObject({ step: "end", text: "Make or bring an end frame." });
    expect(framesStep({ start: "a.png", end: null, end_mode: "next" }).text).toContain("next shot has no start frame");
    expect(framesStep({ start: "a.png", end: "b.png", end_mode: "own" }).step).toBe("ready");
  });
  it("offers ideas for how a shot ends, transformations first", () => {
    expect(END_IDEAS[0]).toContain("decades older");
    expect(new Set(END_IDEAS).size).toBe(END_IDEAS.length);
  });
  it("is one keypress away: E opens the frames", () => {
    expect(SHORTCUTS.find((s) => s.id === "frames")).toMatchObject({ spec: "e", keys: "E" });
  });
  it("shows a loading line until the engine answers (never an empty stage)", () => {
    expect(renderToStaticMarkup(<FramesStage dir="d" shot="S01-01" hasKey />)).toContain("Loading frames");
  });
});

const shot = (id: string, over: Partial<LightShot> = {}, k = 4500, level = 2, mood = "hope"): LightShot => ({ shot: id, scene: 1, start: 0, end: 2, section: "", mood, label: "Hope", valence: 0, arousal: 0.4, intensity: 5,
  confidence: 1, also: [], held: false, user_set: false, director: "", why: "because", design: { term: "golden", label: "Golden hour", kelvin: k, contrast: "", level, key: "", accent: "", motion: "", practical: false, haze: false, wording: "words" }, ...over });
const plan = (shots: LightShot[]): LightingPlan => ({ shots, scenes: [{ scene: 1, heading: "INT. ROOM - NIGHT", from: "Hope", to: "Hope", arc: "Hope", terms: ["golden"] }], count: shots.length, user_set: shots.filter((s) => s.user_set).length });

describe("colours on the lighting strip", () => {
  it("makes warm light orange, neutral light white and cold light blue", () => {
    const hex = (c: string) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
    const warm = hex(kelvinColour(2700)), neutral = hex(kelvinColour(6500)), cold = hex(kelvinColour(10000));
    expect(warm[0]).toBeGreaterThan(warm[2] + 80);
    expect(Math.min(...neutral)).toBeGreaterThan(240);
    expect(cold[2]).toBeGreaterThan(cold[0]);
  });
  it("never leaves the 0-255 range, at any temperature", () => {
    for (const k of [-5, 0, 1000, 1900, 2700, 6600, 12000, 99999]) expect(kelvinColour(k)).toMatch(/^#[0-9a-f]{6}$/);
  });
  it("tints toward the mood and darkens as the light gets harder", () => {
    const a = lightColour({ mood: "anger", design: shot("a", {}, 5600, 0).design }), b = lightColour({ mood: "anger", design: shot("a", {}, 5600, 4).design });
    expect(a).not.toBe(b);
    expect(lightColour({ mood: "grief", design: shot("a").design })).not.toBe(lightColour({ mood: "joy", design: shot("a").design }));
    expect(lightColour({ mood: "unknown", design: shot("a").design })).toMatch(/^#[0-9a-f]{6}$/);
    expect(Object.keys(MOOD_TINT)).toHaveLength(17);
  });
  it("gets softer-to-harder opacity in order", () => {
    const o = [0, 1, 2, 3, 4].map(levelOpacity);
    expect([...o].sort((x, y) => y - x)).toEqual(o);
    expect(levelOpacity(99)).toBe(o[4]);
  });
});

describe("what Apply will write", () => {
  const p = plan([shot("S1"), shot("S2", { user_set: true }), shot("S3")]);
  it("skips the lights you chose yourself unless you ask", () => {
    expect(targets(p, new Set(), false).targets.map((s) => s.shot)).toEqual(["S1", "S3"]);
    expect(targets(p, new Set(), true).targets.map((s) => s.shot)).toEqual(["S1", "S2", "S3"]);
    expect(targets(p, new Set(["S2"]), false).targets).toEqual([]);
  });
  it("uses only the ticked rows when some are ticked", () => {
    expect(targets(p, new Set(["S3"]), false).targets.map((s) => s.shot)).toEqual(["S3"]);
  });
  it("says in words what will happen", () => {
    expect(applySentence(targets(p, new Set(), false), 0, false)).toContain("all 2 shots. 1 light you chose yourself stays as it is");
    expect(applySentence(targets(p, new Set(), true), 0, true)).toContain("replaces 1 light you chose yourself (Undo brings them back)");
    expect(applySentence(targets(p, new Set(["S2"]), false), 1, false)).toContain("so nothing would change");
    expect(applySentence(targets(plan([]), new Set(), false), 0, false)).toBe("Nothing to apply.");
    expect(applySentence(targets(p, new Set(["S3"]), false), 1, false)).toContain("1 selected shot");
  });
});

describe("the lighting screen", () => {
  it("draws one block per shot, as wide as the shot is long, with a name for screen readers", () => {
    const html = renderToStaticMarkup(<LightStrip shots={[shot("S1"), shot("S2", { end: 6 })]} />);
    expect((html.match(/lt-seg/g) ?? []).length).toBe(2);
    expect(html).toContain("The planned light across 2 shots");
    expect(html).toContain('aria-label="S1: Hope, Golden hour"');
  });
  it("shows a reading line first, never a blank sheet", () => {
    const html = renderToStaticMarkup(<LightingSheet dir="d" onClose={() => {}} />);
    expect(html).toContain("Light the story");
    expect(html).toContain("Reading the mood of each shot");
  });
});
