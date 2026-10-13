import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (...a: unknown[]) => invoke(...a), convertFileSrc: (p: string) => `asset://${p}` }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

import type { ShotLevels, ShotSound } from "../api";
import { SoundPanel, toggleShotSound } from "../ShotSound";

const base: ShotSound = {
  shot: "S01-02", native: false, split: false, changed: false, has_audio: true, silent: false, take: { id: "j1", model: "seedance", output: "generations/a.mp4" },
  layers: [{ id: "song", label: "Soundtrack", on: true, gain: null, removed: false, effective_gain: 1, auto: true },
           { id: "all", label: "Sound from the video model", on: false, gain: 1, removed: false }],
};
const view = (snd: Partial<ShotSound> = {}, extra: { busy?: string; err?: string; level?: Record<string, number>; db?: ShotLevels | null } = {}) =>
  renderToStaticMarkup(<SoundPanel shotId="S01-02" snd={{ ...base, ...snd }} busy={extra.busy ?? ""} err={extra.err ?? ""} level={extra.level ?? {}} setLevel={() => {}} db={extra.db}
                                   onSet={() => {}} onRemove={() => {}} onRestore={() => {}} onSplit={() => {}} onReset={() => {}} />);

beforeEach(() => invoke.mockReset());

describe("sound layers panel", () => {
  it("shows the song and the take's own sound, says nothing is rendered again, and offers to split", () => {
    const html = view();
    expect(html).toContain("Soundtrack");
    expect(html).toContain("Sound from the video model");
    expect(html).toContain("nothing is rendered again");
    expect(html).toContain("Split voices from effects");
    expect(html).toContain("100% auto");                                  // the song's level is automatic until chosen
    expect(html).not.toContain("Back to how it was");                    // nothing has been changed yet
  });

  it("after a split lists voices and effects instead, with a delete button for each and a note about the trace", () => {
    const html = view({ split: true, layers: [base.layers[0],
      { id: "voice", label: "Voices", on: true, gain: 1, removed: false }, { id: "other", label: "Sound effects and music", on: true, gain: 1, removed: false }] });
    expect(html).toContain("Voices");
    expect(html).toContain("Sound effects and music");
    expect(html).not.toContain("Sound from the video model");
    expect(html).not.toContain("Split voices from effects");
    expect(html).toContain('aria-label="Delete Voices"');
    expect(html).toContain('aria-label="Delete Sound effects and music"');
    expect(html).toContain("faint trace");
  });

  it("a deleted layer can be restored, and the person can go back to how it was", () => {
    const html = view({ changed: true, layers: [base.layers[0], { ...base.layers[1], on: false, removed: true }] });
    expect(html).toContain(">Restore</button>");
    expect(html).toContain("Back to how it was");
  });

  it("a take with no sound says why, and can be neither split nor ticked on", () => {
    const html = view({ has_audio: false, silent: true });
    expect(html).toContain("no audible sound");
    expect(html).not.toContain("Split voices from effects");
    expect(html).toMatch(/<input[^>]*disabled[^>]*aria-label="Sound from the video model on"|<input[^>]*aria-label="Sound from the video model on"[^>]*disabled/);
  });

  it("a shot with no take, or your own clip, shows only the reason", () => {
    const html = view({ take: null, layers: [], note: "This shot has no video take yet." });
    expect(html).toContain("This shot has no video take yet.");
    expect(html).not.toContain("<ul");
  });

  it("a spoken scene says the soundtrack is not played; every control is disabled while a change is saved", () => {
    expect(view({ native: true })).toContain("the soundtrack is not played");
    expect(view({}, { busy: "all" })).toMatch(/<button[^>]*disabled[^>]*>.*Split voices from effects/);
  });

  it("shows the level being dragged, and an error when one comes back", () => {
    expect(view({}, { level: { all: 40 } })).toContain("40%");
    expect(view({}, { err: "Split this take's sound first." })).toContain("Split this take&#x27;s sound first.");
  });
});

describe("loudness in the panel", () => {
  const lv = (over: Partial<ShotLevels> = {}): ShotLevels => ({ shot: "S01-02", layers: { song: -21.5, all: -21.9 }, mix_db: -18.4, peak_db: -7.9, seconds: 2.5, ...over });
  const on = { layers: [base.layers[0], { ...base.layers[1], on: true }] };

  it("shows the dB of each layer that is on, a meter for it, and the mix under the shot", () => {
    const html = view(on, { db: lv() });
    expect(html).toContain("-21.5 dB");
    expect(html).toContain("-21.9 dB");
    expect((html.match(/class="ss-meter"/g) ?? []).length).toBe(2);
    expect(html).toContain("In the film under this shot: -18.4 dB (peak -7.9 dB)");
    expect(html).not.toContain("Close to the top");
  });

  it("says so when the mix is close to full scale", () => {
    expect(view(on, { db: lv({ peak_db: -0.4 }) })).toContain("Close to the top");
  });

  it("shows no dB for a layer that is off or silent, and nothing before the levels arrive", () => {
    const off = view({}, { db: lv({ layers: { song: -13.5, all: null }, mix_db: -13.5, peak_db: -10.4 }) });
    expect((off.match(/class="ss-meter"/g) ?? []).length).toBe(1);        // only the song
    const none = view(on, { db: null });
    expect(none).not.toContain("ss-meter");
    expect(none).not.toContain("In the film under this shot");
  });

  it("puts a meter's width in step with its level, from silence at -60 dB to full at 0", () => {
    const w = (db: number) => Number(/style="width:([\d.]+)%"/.exec(view(on, { db: lv({ layers: { song: db, all: null } }) }))?.[1]);
    expect(w(-60)).toBe(2);                                                 // never fully empty, so it can be seen
    expect(w(-30)).toBeCloseTo(50, 0);
    expect(w(0)).toBe(100);
  });
});

describe("Shift+M: this shot's own sound on or off", () => {
  const answer = (g: Partial<ShotSound>) => invoke.mockImplementation(async () => ({ ...base, ...g }));

  it("turns the whole sound on when it is off, and tells the person the song goes down", async () => {
    answer({});
    const msg = await toggleShotSound("proj", "S01-02");
    expect(msg).toContain("is on");
    expect(msg).toContain("turned down");
    const sets = invoke.mock.calls.filter(([, a]) => a.action === "set");
    expect(sets).toHaveLength(1);
    expect(sets[0][1].data).toEqual({ shot: "S01-02", layer: "all", on: true });
  });

  it("turns both parts off once they are split and either is on", async () => {
    answer({ split: true, layers: [base.layers[0], { id: "voice", label: "Voices", on: true, gain: 1, removed: false }, { id: "other", label: "Effects", on: false, gain: 1, removed: false }] });
    const msg = await toggleShotSound("proj", "S01-02");
    expect(msg).toContain("is off");
    const sets = invoke.mock.calls.filter(([, a]) => a.action === "set");
    expect(sets.map(([, a]) => [a.data.layer, a.data.on])).toEqual([["voice", false], ["other", false]]);
  });

  it("changes nothing for a take with no sound, a picture, or no take", async () => {
    answer({ has_audio: false });
    expect(await toggleShotSound("proj", "S01-02")).toContain("no audible sound");
    answer({ take: null, layers: [] });
    expect(await toggleShotSound("proj", "S01-02")).toContain("no video take");
    answer({ note: "This take is a picture or one of your own clips, so it has no sound from a video model." });
    expect(await toggleShotSound("proj", "S01-02")).toContain("own clips");
    expect(invoke.mock.calls.filter(([, a]) => a.action === "set")).toHaveLength(0);
  });
});
