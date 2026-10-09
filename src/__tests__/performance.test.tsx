import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { ShotPerformanceView, type PerfData } from "../Performance";

const perf = (over: Partial<PerfData> = {}): PerfData => ({
  profiles: [{ id: "natural", label: "Natural", blurb: "Truthful, everyday acting. Small gestures." }, { id: "expressive", label: "Expressive", blurb: "Open and readable." }],
  default: "natural", scenes: {}, characters: {}, shots: {}, set: true, dance: {}, ...over });
const view = (p: PerfData, shot = "S01-03") => renderToStaticMarkup(<ShotPerformanceView perf={p} shotId={shot} onProfile={() => {}} onDance={() => {}} />);

describe("the Acting panel of a shot", () => {
  it("says so when the project has no acting style, because then the prompt has no micro-motion", () => {
    const html = view(perf({ set: false }));
    expect(html).toContain("No acting style is chosen for this project yet");
    expect(html).toContain("blinks, breathing or weight shifts");
  });

  it("does not nag once an acting style is chosen", () => {
    expect(view(perf({ set: true }))).not.toContain("No acting style is chosen");
  });

  it("offers dance direction as automatic, always or never, starting on automatic", () => {
    const html = view(perf());
    expect(html).toContain("Dance direction in this shot");
    expect(html).toContain('<option value="auto" selected="">Automatic: only if this shot&#x27;s action is dancing</option>');
    expect(html).toContain('<option value="on">Always: use the dance direction</option>');
    expect(html).toContain('<option value="off">Never: leave the dance direction out</option>');
  });

  it("shows the choice already made for this shot, and not for another", () => {
    const p = perf({ dance: { "S01-03": "off" } });
    expect(view(p, "S01-03")).toContain('<option value="off" selected="">');
    expect(view(p, "S01-04")).toContain('<option value="auto" selected="">');
  });

  it("labels both menus, so a screen reader can tell them apart", () => {
    const html = view(perf());
    expect(html).toContain('aria-label="Acting style for this shot"');
    expect(html).toContain('for="dance-S01-03"');
    expect(html).toContain('id="dance-S01-03"');
  });
});

describe("the one-click button in the Acting panel", () => {
  it("offers Use Natural only when no acting style is chosen and the panel can act on it", () => {
    const none = perf({ set: false });
    const withBtn = renderToStaticMarkup(<ShotPerformanceView perf={none} shotId="S01-03" onProfile={() => {}} onDance={() => {}} onUseNatural={() => {}} />);
    expect(withBtn).toContain("Use Natural for this project");
    expect(view(none)).not.toContain("Use Natural");                                       // no handler, no button
    expect(renderToStaticMarkup(<ShotPerformanceView perf={perf({ set: true })} shotId="S01-03" onProfile={() => {}} onDance={() => {}} onUseNatural={() => {}} />)).not.toContain("Use Natural");
  });
});
