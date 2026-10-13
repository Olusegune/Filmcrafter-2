import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => `asset://${p}` }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { GivenToModel } from "../GivenToModel";
import type { ModelInput } from "../api";

(globalThis as unknown as { window?: object }).window ??= {};                 // api.mediaUrl looks at window; the server renderer has none
const view = (inputs: ModelInput[]) => renderToStaticMarkup(<GivenToModel dir="C:/p" inputs={inputs} />);
const kf: ModelInput = { role: "first_frame", label: "Starts from this frame (your approved keyframe)", path: "assets/kf.png", sent: true };
const ref: ModelInput = { role: "reference", label: "reference for Beatrice", path: "assets/b.png", sent: false };

describe("what the video model is given, as pictures", () => {
  it("shows nothing when there is nothing to show", () => {
    expect(view([])).toBe("");
  });
  it("shows each picture in order with what it is for, and how many are used", () => {
    const html = view([kf, ref, { role: "audio", label: "The song's vocal under this shot, for Beatrice to follow", path: null, sent: true }]);
    expect(html).toContain("2 of 3 used");
    expect(html.indexOf("First frame")).toBeLessThan(html.indexOf("Reference"));
    expect(html.indexOf("Reference")).toBeLessThan(html.indexOf("Your recording"));
    expect(html).toContain("assets/kf.png");
    expect(html).toContain("The song&#x27;s vocal under this shot, for Beatrice to follow");
    expect(html).toContain("♪");
  });
  it("dims a picture the model will not take, and says so in words and to a screen reader", () => {
    const html = view([kf, ref]);
    expect(html).toMatch(/mi-item off role-reference/);
    expect(html).toContain("not used: this model won&#x27;t take it here");
    expect(html).toContain("reference for Beatrice (not used by this model): show larger");
    expect(html).not.toMatch(/mi-item off role-first_frame/);
  });
  it("makes every picture a button that can be enlarged", () => {
    const html = view([kf]);
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain("show larger");
  });
});
