import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => `asset://${p}` }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));

import type { Overlay } from "../api";
import { KeysEditor } from "../KeysEditor";
import { LayerStrip } from "../LayerStrip";
import { PreviewSheet } from "../PreviewSheet";
import { ColourMatchSheet } from "../ColourMatch";
import icons from "../shapeIcons.json";

const layer = (over: Partial<Overlay> = {}): Overlay => ({ id: "ov_1", kind: "text", text: "Hello", source: "manual", start: 2, end: 8, x: 0.5, y: 0.5, size: 0.08, width: 0.5, color: "#ffffff",
  fade: 0.4, enabled: true, placed: true, reason: "", explicit: true, explicit_end: true, ...over });

describe("keyframe editor", () => {
  it("explains how to start when a layer has none, and only offers a keyframe while the playhead is inside the layer", () => {
    const inside = renderToStaticMarkup(<KeysEditor sel={layer()} time={4} save={() => {}} />);
    expect(inside).toContain("Keyframes");
    expect(inside).toContain("none");
    expect(inside).toContain("Move the playhead inside this layer");
    expect(inside).not.toMatch(/<button[^>]*disabled[^>]*>\+ Keyframe here/);
    const outside = renderToStaticMarkup(<KeysEditor sel={layer()} time={20} save={() => {}} />);
    expect(outside).toMatch(/<button[^>]*disabled[^>]*>\+ Keyframe here/);
  });
  it("lists each keyframe with its time, the five settings and how it gets to the next, and can clear them", () => {
    const keys = [{ t: 0, x: 0.2, y: 0.5, scale: 1, opacity: 1, ease: "linear" as const }, { t: 3, x: 0.8, rotation: 90 }];
    const html = renderToStaticMarkup(<KeysEditor sel={layer({ keys })} time={4} save={() => {}} />);
    expect((html.match(/class="ke-row"/g) ?? []).length).toBe(2);
    for (const word of ["At (s)", "X", "Y", "Scale", "Turn", "Opacity", "Then", "Smooth", "Steady", "Jump at the next key"]) expect(html).toContain(word);
    expect(html).toContain("2 of 12");
    expect(html).toContain(">Clear</button>");
    expect(html).toContain("follows these instead of its Movement");
  });
  it("stops offering keyframes at twelve", () => {
    const keys = Array.from({ length: 12 }, (_, i) => ({ t: i * 0.5, x: 0.5 }));
    expect(renderToStaticMarkup(<KeysEditor sel={layer({ keys })} time={3} save={() => {}} />)).toMatch(/<button[^>]*disabled[^>]*>\+ Keyframe here/);
  });
});

describe("icon set", () => {
  it("has twelve icons, each a few closed shapes inside the unit box", () => {
    const names = Object.keys(icons);
    expect(names).toHaveLength(12);
    for (const n of names) {
      const polys = (icons as Record<string, { label: string; polys: number[][][] }>)[n].polys;
      expect(polys.length).toBeGreaterThan(0);
      for (const p of polys) {
        expect(p.length).toBeGreaterThanOrEqual(3);
        for (const [x, y] of p) { expect(x).toBeGreaterThanOrEqual(-0.001); expect(x).toBeLessThanOrEqual(1.001); expect(y).toBeGreaterThanOrEqual(-0.001); expect(y).toBeLessThanOrEqual(1.001); }
      }
    }
  });
});

describe("layer timeline strip", () => {
  it("shows the layer's time on the song, a diamond for each keyframe and the playhead", () => {
    const html = renderToStaticMarkup(<LayerStrip layer={layer({ start: 10, end: 20, keys: [{ t: 0, x: 0.2 }, { t: 5, x: 0.8 }] })} duration={100} time={15} onSeek={() => {}} />);
    expect(html).toContain("Timeline of Hello");
    expect(html).toContain("left:10%");                                                   // the bar starts at 10 s of 100
    expect((html.match(/class="ls-key"/g) ?? []).length).toBe(2);
    expect(html).toContain("Keyframe 2 at 0:15.0");
    expect(html).toContain("left:15%");                                                   // the playhead
    expect(html).toContain("0:10.0 – 0:20.0");
  });
  it("shows nothing for a layer that is not placed in time or a song with no length", () => {
    expect(renderToStaticMarkup(<LayerStrip layer={layer({ placed: false, start: null, end: null })} duration={100} time={0} onSeek={() => {}} />)).toBe("");
    expect(renderToStaticMarkup(<LayerStrip layer={layer()} duration={0} time={0} onSeek={() => {}} />)).toBe("");
  });
});

describe("preview and colour match windows", () => {
  it("offers a preview from the playhead and says what it is", () => {
    const html = renderToStaticMarkup(<PreviewSheet dir="/p" from={12.34} duration={100} onClose={() => {}} />);
    expect(html).toContain("12.3 s to 22.3 s");                                       // ten seconds by default
    expect(html).toContain("Make the preview");
    expect(html).toContain("Free: nothing is sent anywhere");
    for (const n of ["5 seconds", "10 seconds", "20 seconds", "30 seconds"]) expect(html).toContain(n);
  });
  it("keeps a preview inside the film", () => {
    expect(renderToStaticMarkup(<PreviewSheet dir="/p" from={99.5} duration={100} onClose={() => {}} />)).toContain("99.0 s to 100.0 s");
  });
  it("starts by asking to look at the shots, and promises the takes are never changed", () => {
    const html = renderToStaticMarkup(<ColourMatchSheet dir="/p" onClose={() => {}} />);
    expect(html).toContain("Look at the shots");
    expect(html).toContain("Your takes are never changed");
  });
});

describe("reduced motion", () => {
  it("is on only when the computer asks for less motion", async () => {
    const { reducedMotion } = await import("../overlayMotion");
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce") }));
    expect(reducedMotion()).toBe(true);
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    expect(reducedMotion()).toBe(false);
    vi.unstubAllGlobals();
  });
});
