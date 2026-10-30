import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => `asset://${p}` }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { Dialog, defaults } from "../ask";
import { updateText } from "../Updates";

describe("in-app confirmation", () => {
  it("uses the first line as the title and the rest as paragraphs, with the OK word you give", () => {
    const html = renderToStaticMarkup(<Dialog message={"Make 3 pictures?\n\nCost: about $0.42.\nOn GPT Image."} ok="Make 3" danger={false} done={() => {}} />);
    expect(html).toContain("<h3>Make 3 pictures?</h3>");
    expect(html).toContain("Cost: about $0.42.");
    expect(html).toContain(">Make 3</button>");
    expect(html).toContain('role="alertdialog"');
    expect(html).not.toContain("danger");
  });
  it("is red and named for what it does when something is removed or replaced", () => {
    expect(defaults("Remove “Bell” from the library?")).toEqual({ ok: "Remove", danger: true });
    expect(defaults("Clear the Recent list?")).toEqual({ ok: "Clear", danger: true });
    expect(defaults("Replace the lyrics in the editor with this file?")).toEqual({ ok: "Replace", danger: true });
    expect(defaults("Go back to Tuesday?")).toEqual({ ok: "Go back", danger: false });
    expect(defaults("Make 4 pictures?")).toEqual({ ok: "Continue", danger: false });
  });
});

describe("update messages", () => {
  const base = { current: "1.10.0", latest: null, url: "u", notes: "", published: null, prerelease: false };
  it("says what happened in plain words", () => {
    expect(updateText({ ...base, status: "update", latest: "1.11.0" })).toMatchObject({ tone: "new", text: expect.stringContaining("1.11.0 is available") });
    expect(updateText({ ...base, status: "up_to_date" })).toMatchObject({ tone: "ok", text: expect.stringContaining("latest version (1.10.0)") });
    expect(updateText({ ...base, status: "disabled" }).text).toMatch(/checks are off/);
    expect(updateText({ ...base, status: "offline" }).text).toMatch(/internet connection/);
    expect(updateText({ ...base, status: "unavailable" }).text).toMatch(/releases page/);
  });
});

import { ShotRefs } from "../ShotRefs";
describe("pictures used in a shot", () => {
  (globalThis as any).window = (globalThis as any).window ?? {};                 // api.mediaUrl looks at window; the server renderer has none
  const library = { items: [
    { id: "c1", kind: "character", name: "Beatrice", files: ["a.png"] }, { id: "p1", kind: "prop", name: "Bell", files: ["b.png"] },
    { id: "s1", kind: "set", name: "Home", files: [] }, { id: "ch", kind: "character", name: "Cast sheet", files: ["c.png"], sheet: true }],
    assign: { project: ["c1"], scenes: {}, shots: { S1: { add: ["p1"] } } } } as any;
  const shot = { id: "S1", references: [{ id: "c1", kind: "character", name: "Beatrice", from: "project" }, { id: "p1", kind: "prop", name: "Bell", from: "shot" }] } as any;
  const html = renderToStaticMarkup(<ShotRefs dir="d" shot={shot} library={library} thumbs={{ "a.png": "t/a.png" }} want={() => {}} onChanged={() => {}} />);
  it("lists people and props that have pictures, marks which are on and where from", () => {
    expect(html).toContain("Pictures used in this shot");
    expect(html).toContain("Beatrice"); expect(html).toContain("Bell");
    expect(html).toContain("whole project"); expect(html).toContain("this shot only");
    expect(html.match(/aria-pressed="true"/g)?.length).toBe(2);
  });
  it("leaves out places with no picture and the combined cast sheets, and offers a way back to automatic", () => {
    expect(html).not.toContain("Home"); expect(html).not.toContain("Cast sheet");
    expect(html).toContain("Back to automatic");                                         // this shot has its own add
  });
  it("shows nothing for a library with no pictures", () => {
    expect(renderToStaticMarkup(<ShotRefs dir="d" shot={shot} library={{ items: [], assign: { project: [], scenes: {}, shots: {} } } as any} thumbs={{}} want={() => {}} onChanged={() => {}} />)).toBe("");
  });
});

import { Takes } from "../Takes";
describe("video takes", () => {
  (globalThis as any).window = (globalThis as any).window ?? {};
  const job = (id: string, created: number, extra = {}) => ({ id, created, model: "bytedance/seedance-1.5-pro", output: `generations/${id}.mp4`, state: "ready", kind: "video", cost: 14, cost_unit: "credits", ...extra }) as any;
  const takes = [job("a", 1), job("b", 2), job("c", 3)];
  it("shows the take that is in the video, marks it, and lists every take to choose from", () => {
    const html = renderToStaticMarkup(<Takes dir="d" shotId="S01-01" takes={takes} approved="b" onUse={() => {}} />);
    expect(html).toContain("3 finished"); expect(html).toContain("In the video"); expect(html).toContain("generations/b.mp4");
    expect(html).toContain("This take is in the video and on the timeline."); expect(html).not.toContain("Use this take in the video");
    expect((html.match(/role="option"/g) ?? []).length).toBe(3);
  });
  it("offers to use the newest take when none has been chosen yet", () => {
    const html = renderToStaticMarkup(<Takes dir="d" shotId="S01-01" takes={takes} approved={null} onUse={() => {}} />);
    expect(html).toContain("generations/c.mp4"); expect(html).toContain("Use this take in the video");
  });
  it("shows nothing when there is no finished take, and no strip for a single take", () => {
    expect(renderToStaticMarkup(<Takes dir="d" shotId="S" takes={[]} approved={null} onUse={() => {}} />)).toBe("");
    expect(renderToStaticMarkup(<Takes dir="d" shotId="S" takes={[takes[0]]} approved={null} onUse={() => {}} />)).not.toContain('role="listbox"');
  });
});
