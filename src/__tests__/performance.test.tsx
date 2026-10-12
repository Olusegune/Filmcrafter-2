import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { ShotPerformanceView, type PerfData } from "../Performance";

const perf = (over: Partial<PerfData> = {}): PerfData => ({
  profiles: [{ id: "natural", label: "Natural", blurb: "Truthful, everyday acting. Small gestures." }, { id: "expressive", label: "Expressive", blurb: "Open and readable." }],
  default: "natural", scenes: {}, characters: {}, shots: {}, set: true, ...over });
const view = (p: PerfData, shot = "S01-03") => renderToStaticMarkup(<ShotPerformanceView perf={p} shotId={shot} onProfile={() => {}} />);

describe("the Acting panel of a shot", () => {
  it("says so when the project has no acting style, because then the prompt has no micro-motion", () => {
    const html = view(perf({ set: false }));
    expect(html).toContain("No acting style is chosen for this project yet");
    expect(html).toContain("blinks, breathing or weight shifts");
  });

  it("does not nag once an acting style is chosen", () => {
    expect(view(perf({ set: true }))).not.toContain("No acting style is chosen");
  });

  it("has one menu, for this shot's acting style, named for a screen reader, and no dance menu", () => {
    const html = view(perf());
    expect(html).toContain('aria-label="Acting style for this shot"');
    expect(html).not.toMatch(/[Dd]ance/);
    expect((html.match(/<select/g) ?? []).length).toBe(1);
  });

  it("shows the style chosen for this shot, and inherits for another", () => {
    const p = perf({ shots: { "S01-03": "expressive" } });
    expect(view(p, "S01-03")).toContain('<option value="expressive" selected="">');
    expect(view(p, "S01-04")).toContain('<option value="inherit" selected="">');
  });
});

describe("the one-click button in the Acting panel", () => {
  it("offers Use Natural only when no acting style is chosen and the panel can act on it", () => {
    const none = perf({ set: false });
    const withBtn = renderToStaticMarkup(<ShotPerformanceView perf={none} shotId="S01-03" onProfile={() => {}} onUseNatural={() => {}} />);
    expect(withBtn).toContain("Use Natural for this project");
    expect(view(none)).not.toContain("Use Natural");                                       // no handler, no button
    expect(renderToStaticMarkup(<ShotPerformanceView perf={perf({ set: true })} shotId="S01-03" onProfile={() => {}} onUseNatural={() => {}} />)).not.toContain("Use Natural");
  });
});
