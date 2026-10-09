import { describe, expect, it, vi } from "vitest";
import engineSource from "../../analysis/filmcrafter_engine/transitions.py?raw";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { barBox, drag, MIN_LEN, packLanes, seekInto, snapPoints, snapTo } from "../laneMath";
import { LayerBar, laneCount } from "../LayerLanes";
import { TransitionPicker } from "../TransitionHandles";
import { TRANSITION_LIST, transitionGlyph, transitionSeconds } from "../transitions";
import type { BoardShot, Overlay } from "../api";

const layer = (over: Partial<Overlay> = {}): Overlay => ({ id: "o1", kind: "text", text: "Come downstairs!", source: "manual", start: 5, end: 9, x: 0.5, y: 0.5, size: 0.06, width: 0.6, color: "#fff", fade: 0.4,
  enabled: true, placed: true, reason: "", explicit: true, explicit_end: true, ...over });
const shot = (over: Partial<BoardShot> = {}): BoardShot => ({ id: "S01-02", scene: 1, start: 4, end: 8, beat: "", performers: [], status: "ready", locked: false, approved: null, thumb_src: null,
  thumb_source: "placeholder", preview: null, keyframe: null, versions: [], references: [], ...over });

describe("which lane a layer sits in", () => {
  it("puts layers that do not overlap in the same lane and overlapping ones in new lanes", () => {
    const lanes = packLanes([{ id: "a", start: 0, end: 4 }, { id: "b", start: 2, end: 6 }, { id: "c", start: 4, end: 8 }, { id: "d", start: 3, end: 5 }]);
    expect(lanes).toEqual({ a: 0, b: 1, c: 0, d: 2 });
  });
  it("is the same whatever order the layers arrive in, and empty for none", () => {
    const s = [{ id: "a", start: 0, end: 4 }, { id: "b", start: 1, end: 3 }, { id: "c", start: 5, end: 6 }];
    expect(packLanes([...s].reverse())).toEqual(packLanes(s));
    expect(packLanes([])).toEqual({});
  });
  it("counts the lanes the timeline must make room for, ignoring layers with no time", () => {
    expect(laneCount([])).toBe(0);
    expect(laneCount([layer(), layer({ id: "o2", start: 6, end: 10 }), layer({ id: "o3", placed: false, start: null, end: null })])).toBe(2);
  });
});

describe("dragging a layer", () => {
  const from = { start: 5, end: 9 };
  it("moves it with its length kept, and never off either end of the song", () => {
    expect(drag("move", from, 2, 60)).toEqual({ start: 7, end: 11 });
    expect(drag("move", from, -50, 60)).toEqual({ start: 0, end: 4 });
    expect(drag("move", from, 90, 60)).toEqual({ start: 56, end: 60 });
  });
  it("trims either edge but never below the shortest layer, nor past the song", () => {
    expect(drag("trim-start", from, 1, 60)).toEqual({ start: 6, end: 9 });
    const short = drag("trim-start", from, 99, 60);
    expect(short.end - short.start).toBeCloseTo(MIN_LEN, 5);
    expect(drag("trim-start", from, -99, 60).start).toBe(0);
    expect(drag("trim-end", from, 2, 60)).toEqual({ start: 5, end: 11 });
    expect(drag("trim-end", from, -99, 60).end).toBeCloseTo(5 + MIN_LEN, 5);
    expect(drag("trim-end", from, 99, 12).end).toBe(12);
  });
  it("snaps an edge to a beat, lyric or shot edge that is close, from either end of the layer", () => {
    expect(snapTo(5.07, [5, 8], 0.1)).toBe(5);
    expect(snapTo(5.4, [5, 8], 0.1)).toBe(5.4);
    expect(drag("move", from, 0.96, 60, [6], 0.1)).toEqual({ start: 6, end: 10 });
    expect(drag("move", from, 1.97, 60, [11], 0.1)).toEqual({ start: 7, end: 11 });
    expect(drag("trim-end", from, 0.04, 60, [9], 0.1)).toEqual({ start: 5, end: 9 });
  });
  it("collects snap points from beats, lyrics, shot edges and the playhead, once each", () => {
    expect(snapPoints({ downbeats: [0, 2], lyrics: [{ start: 2 }, { start: null }], shots: [{ start: 0, end: 2 }, { start: 2, end: 4 }], playhead: 3.004 })).toEqual([0, 2, 3, 4]);
  });
  it("puts the bar and its keyframe diamonds in pixels for the zoom", () => {
    expect(barBox({ start: 5, end: 9, keys: [{ t: 0 }, { t: 2 }] }, 24)).toEqual({ left: 120, width: 96, keys: [0, 48] });
    expect(barBox({ start: 5, end: 5.001 }, 24).width).toBe(6);
  });
});

describe("choosing a layer on the timeline", () => {
  it("leaves the playhead alone when it is already inside the layer", () => {
    expect(seekInto(6, 5, 9)).toBeNull();
    expect(seekInto(5, 5, 9)).toBeNull();
    expect(seekInto(9, 5, 9)).toBeNull();
  });
  it("moves the playhead just inside the layer when it is before or after it, so the layer shows on the player and can be dragged", () => {
    expect(seekInto(0, 8, 12)).toBe(8.5);
    expect(seekInto(60, 8, 12)).toBe(8.5);
    expect(seekInto(0, 8, 8.4)).toBe(8.2);                                       // a very short layer: the middle of it
  });
  it("never lands outside the layer, and ignores a layer with no length", () => {
    const t = seekInto(0, 8, 8.06)!;
    expect(t).toBeGreaterThanOrEqual(8);
    expect(t).toBeLessThanOrEqual(8.06);
    expect(seekInto(0, 8, 8)).toBeNull();
  });
});

describe("a layer's bar", () => {
  const bar = (o: Overlay, extra: Partial<Parameters<typeof LayerBar>[0]> = {}) =>
    renderToStaticMarkup(<LayerBar o={o} lane={1} pps={24} selected={false} onSelect={() => {}} onToggle={() => {}} onPointer={() => {}} onNudge={() => {}} {...extra} />);
  it("is named, timed and placed in its lane", () => {
    const html = bar(layer());
    expect(html).toContain('aria-label="Layer Come downstairs!, 0:05.0 to 0:09.0"');
    expect(html).toContain("left:120px;width:96px;top:22px");
    expect(html).toContain('aria-label="Hide Come downstairs!"');
  });
  it("says when it is hidden and offers to show it", () => {
    const html = bar(layer({ enabled: false }));
    expect(html).toContain(", hidden");
    expect(html).toContain('aria-label="Show Come downstairs!"');
    expect(html).toContain("lane-bar k-text off");
  });
  it("shows the selected layer, a drag in progress, and keyframes", () => {
    const html = bar(layer({ keys: [{ t: 1 } as never] }), { selected: true, live: { start: 6, end: 10 } });
    expect(html).toContain("sel");
    expect(html).toContain("dragging");
    expect(html).toContain("left:144px");
    expect(html).toContain("lane-key");
  });
  it("can be reached and moved from the keyboard", () => {
    const html = bar(layer());
    expect(html).toContain('tabindex="0"');
    expect(html).toContain("arrow keys nudge");
  });
});

describe("transitions", () => {
  it("keeps the same list, labels and default lengths as the engine", () => {
    const py = engineSource;
    const rows = [...py.matchAll(/^\s+"(\w+)": \("([^"]+)", "(\w+)", ([\d.]+)\),$/gm)].map((m) => ({ id: m[1], label: m[2], group: m[3], secs: Number(m[4]) }));
    expect(TRANSITION_LIST).toEqual(rows);
  });
  it("gives every transition its own picture on the timeline, except where two are mirror twins of one idea", () => {
    const g = TRANSITION_LIST.map((t) => transitionGlyph(t.id));
    expect(new Set(g).size).toBe(g.length);
    expect(transitionGlyph(undefined)).toBe("|");
  });
  it("works out the length in force the way the engine does: chosen, else default, never more than half the shot", () => {
    expect(transitionSeconds("dissolve", null, 4)).toBe(0.5);
    expect(transitionSeconds("dissolve", 1.2, 4)).toBe(1.2);
    expect(transitionSeconds("dissolve", 9, 10)).toBe(2);
    expect(transitionSeconds("dissolve", 1.5, 1)).toBe(0.5);
    expect(transitionSeconds("cut", 1, 4)).toBe(0);
  });
  const picker = (s = shot(), over: Partial<Parameters<typeof TransitionPicker>[0]> = {}) =>
    renderToStaticMarkup(<TransitionPicker shot={s} prev={shot({ id: "S01-01", start: 0, end: 4 })} busy={false} err="" scene={1} onPick={() => {}} onLength={() => {}} onApply={() => {}} onClose={() => {}} {...over} />);
  it("lists every transition in groups and marks the one in use", () => {
    const html = picker(shot({ transition: "wipe_left" }));
    expect(html).toContain("S01-01 → S01-02");
    for (const t of TRANSITION_LIST) expect(html).toContain(`title="${t.label}"`);
    expect(html).toMatch(/aria-pressed="true"[^>]*title="Wipe to the left"/);
    expect(html).toContain("Transition length in seconds");
    expect(html).toContain("0.50 s");
  });
  it("shows no length for a cut, shows the chosen one otherwise, and says nothing is shifted in time", () => {
    expect(picker()).not.toContain("Transition length");
    const html = picker(shot({ transition: "dissolve", transition_s: 1.25 }));
    expect(html).toContain("1.25 s");
    expect(html).toContain("no shot is moved in time");
  });
  it("offers to apply to the scene or every cut, and disables everything while saving", () => {
    expect(picker()).toContain("Apply to this scene");
    expect(picker()).toContain("Apply to every cut");
    const busy = picker(shot({ transition: "dissolve" }), { busy: true, err: "Unknown transition." });
    expect((busy.match(/<button[^>]*disabled/g) ?? []).length).toBeGreaterThanOrEqual(17);
    expect(busy).toContain('role="alert"');
  });
});
