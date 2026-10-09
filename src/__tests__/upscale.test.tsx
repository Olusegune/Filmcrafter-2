import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { UpscaleChoices } from "../UpscaleSheet";
import type { UpscaleTool } from "../api";

const tools: UpscaleTool[] = [
  { id: "kie-topaz-image", provider: "kie", model: "topaz/image-upscale", media: "image", label: "Topaz · picture", blurb: "Topaz Gigapixel quality.", ready: true, factors: [2, 4] },
  { id: "fal-clarity-image", provider: "fal", model: "fal-ai/clarity-upscaler", media: "image", label: "Clarity · picture (fal)", blurb: "Adds fine detail.", ready: false, factors: [2, 4] },
];
const view = (over: Partial<Parameters<typeof UpscaleChoices>[0]> = {}) => renderToStaticMarkup(<UpscaleChoices tools={tools} tool="kie-topaz-image" factor={2} busy={false} onTool={() => {}} onFactor={() => {}} {...over} />);

describe("choosing an upscaler", () => {
  it("lists each tool with what it is for, and marks the one picked", () => {
    const html = view();
    expect(html).toContain("Topaz · picture");
    expect(html).toContain("Topaz Gigapixel quality.");
    expect(html).toMatch(/aria-checked="true"[^>]*class="up-tool on"/);
  });
  it("disables a tool whose provider key is missing and says which key", () => {
    const html = view();
    expect(html).toMatch(/<button[^>]*disabled[^>]*>.*Clarity/s);
    expect(html).toContain("needs a fal.ai key");
    expect(html).toContain("Add your fal.ai key in Settings to use this");
  });
  it("offers how much bigger, marks the choice and says what it means in pixels", () => {
    const html = view({ factor: 4 });
    expect(html).toContain("2× bigger");
    expect(html).toMatch(/aria-checked="true"[^>]*>4× bigger/);
    expect(html).toContain("Width and height each ×4: 16× the pixels.");
  });
  it("disables everything while an upscale is running", () => {
    const html = view({ busy: true });
    expect((html.match(/<button[^>]*disabled/g) ?? []).length).toBe(4);
  });
  it("copes with no tools at all", () => {
    const html = view({ tools: [], tool: "" });
    expect(html).toContain("2× bigger");
  });
});
