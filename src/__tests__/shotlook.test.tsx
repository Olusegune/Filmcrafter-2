import { afterEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: (cmd: string, args: unknown) => invoke(cmd, args), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { LookPicker } from "../Looks";
import type { StyleBibleRead } from "../api";
import { sameAsLabel, saveShotLook, ShotLook } from "../ShotLook";

const read: StyleBibleRead = { style: { id: "claymation", name: "Claymation", prompt: "" }, scenes: [], shots: {}, precedence: [],
  styles: [{ id: "claymation", name: "Claymation", group: "", description: "" }, { id: "anime", name: "Anime", group: "", description: "" }, { id: "noir", name: "Noir", group: "", description: "" }] };
afterEach(() => invoke.mockReset());

const view = (over: Partial<Parameters<typeof ShotLook>[0]> = {}) =>
  renderToStaticMarkup(<ShotLook dir="p" shotId="S01-01" own={read} filmLook="claymation" sceneLook="claymation" onChanged={() => {}} {...over} />);

describe("the look of one shot", () => {
  it("offers the other looks, and 'same as the film' first", () => {
    const html = view();
    expect(html).toContain("Look for this shot");
    expect(html).toContain("Same as its film (Claymation)</option>");
    expect(html).toContain(">Anime</option>");
    expect(html).toContain(">Noir</option>");
    expect(html).not.toContain(">Claymation</option>");                      // the look it already has is the first option
    expect(html).toContain("never re-rendered");
  });
  it("names the scene when the scene has a look of its own, and offers the film's look", () => {
    const html = view({ sceneLook: "noir" });
    expect(html).toContain("Same as its scene (Noir)");
    expect(html).toContain(">Claymation</option>");
    expect(html).not.toContain(">Noir</option>");
  });
  it("shows a shot's own look as picked and the panel open", () => {
    const html = view({ own: { ...read, shots: { "S01-01": "anime" } } });
    expect(html).toMatch(/<option value="anime" selected=""/);
    expect(html).toMatch(/<details[^>]*open/);
    expect(html).toContain(">Own<");
    expect(html).toContain("made in its own look");
  });
  it("shows nothing until the looks are read", () => {
    expect(view({ own: null })).toBe("");
  });
  it("words the first option for the scene or the film", () => {
    expect(sameAsLabel(read, "claymation", "claymation")).toBe("Same as its film (Claymation)");
    expect(sameAsLabel(read, "claymation", "anime")).toBe("Same as its scene (Anime)");
  });
  it("saves a pick for that shot only, and the empty option clears it", async () => {
    invoke.mockResolvedValue(read);
    await saveShotLook("p", "S01-01", "anime");
    expect(invoke).toHaveBeenLastCalledWith("stylebible", { dir: "p", action: "set_shot", data: { shot: "S01-01", style: "anime" } });
    await saveShotLook("p", "S01-02", "");
    expect(invoke).toHaveBeenLastCalledWith("stylebible", { dir: "p", action: "set_shot", data: { shot: "S01-02", style: null } });
    expect(invoke).toHaveBeenCalledTimes(2);                                 // nothing else was asked of the app: no render, no price
  });
});

describe("the picker opened from the shot's Look chip", () => {
  const picker = (shot: Parameters<typeof LookPicker>[0]["shot"]) =>
    renderToStaticMarkup(<LookPicker value={{ style: "claymation" }} director={true} onCancel={() => {}} onSave={() => {}} shot={shot} />);
  it("is about this shot only: no film notes or wording, and a button back to what it inherits when it has its own", () => {
    const html = picker({ id: "S01-01", own: true, sameAs: "Same as its film (Claymation)", onClear: () => {} });
    expect(html).toContain("Look for shot S01-01");
    expect(html).toContain("a new take shows its price first");
    expect(html).not.toContain("Your notes");
    expect(html).not.toContain("Prompt wording");
    expect(html).toContain("Same as its film (Claymation)");
  });
  it("has no way back when the shot has no look of its own, and is the film's picker without a shot", () => {
    expect(picker({ id: "S01-01", own: false, sameAs: "Same as its film (Claymation)", onClear: () => {} })).not.toContain("Same as its film (Claymation)");
    expect(picker(undefined)).toContain("One style for the whole video");
  });
});
