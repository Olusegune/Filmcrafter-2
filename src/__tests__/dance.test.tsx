import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

import { DanceReport } from "../ChoreoSheet";
import type { DanceCheck } from "../api";

const report = (over: Partial<DanceCheck> = {}): DanceCheck => ({ dance_shots: 3, clean: 1, note: "", shots: [
  { shot: "S01-04", start: 4, end: 8, framing: "wide shot", issues: [] },
  { shot: "S02-02", start: 20, end: 21, framing: "close-up", issues: [{ kind: "close", text: "The frame is close-up.", fix: "Use a wide frame." }, { kind: "short", text: "Only 1.0 s.", fix: "Make it longer." }] },
  { shot: "S03-01", start: 30.3, end: 34, framing: "full shot", issues: [{ kind: "off_beat", text: "The cut lands 0.20 s off.", fix: "Move it to 30.50 s." }] }], ...over });

describe("the dance-ready report", () => {
  it("says how many dance shots are ready and lists only the ones that need a change, with the fix beside each problem", () => {
    const html = renderToStaticMarkup(<DanceReport report={report()} />);
    expect(html).toContain("1 of 3");
    expect(html).toContain("the rest need a change");
    expect(html).toContain("S02-02");
    expect(html).toContain("S03-01");
    expect(html).not.toContain("S01-04");
    expect(html).toContain("The frame is close-up.");
    expect(html).toContain("Use a wide frame.");
    expect(html).toContain("Move it to 30.50 s.");
  });
  it("says so when every dance shot is ready", () => {
    const html = renderToStaticMarkup(<DanceReport report={report({ dance_shots: 1, clean: 1, shots: [{ shot: "S01-04", start: 4, end: 8, framing: "", issues: [] }] })} />);
    expect(html).toContain("1 of 1");
    expect(html).toContain("are ready to be danced in");
  });
  it("explains what to do when there is no dance shot, and does not claim any are ready", () => {
    const html = renderToStaticMarkup(<DanceReport report={report({ dance_shots: 0, clean: 0, shots: [], note: "No shot is a dance shot yet: write a choreography plan." })} />);
    expect(html).toContain("0 of 0");
    expect(html).toContain("No shot is a dance shot yet");
    expect(html).not.toContain("are ready to be danced in");
  });
});
