import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { BARS, envelope, LivingWave, playheadAt, waveBars } from "../LivingWave";

describe("the waveform over the drop card", () => {
  it("is shaped like a song: a quiet start, a loud chorus, a dip, a louder last chorus", () => {
    expect(envelope(0.02)).toBeLessThan(0.4);
    expect(envelope(0.44)).toBeGreaterThan(envelope(0.16));
    expect(envelope(0.58)).toBeLessThan(envelope(0.44));
    expect(envelope(0.82)).toBeGreaterThan(envelope(0.44));
    for (let x = 0; x <= 1.0001; x += 0.05) { expect(envelope(x)).toBeGreaterThan(0); expect(envelope(x)).toBeLessThanOrEqual(1); }
  });

  it("gives the same picture for the same moment, and a different one a moment later", () => {
    expect(waveBars(2.5)).toEqual(waveBars(2.5));
    expect(waveBars(2.5)).not.toEqual(waveBars(2.75));
  });

  it("keeps every bar visible and inside the frame, at any time and awake or not", () => {
    for (const awake of [false, true]) for (const t of [0, 0.1, 0.25, 1.37, 8.9, 123.456, 1e5]) {
      const b = waveBars(t, BARS, awake);
      expect(b).toHaveLength(BARS);
      for (const v of b) { expect(v).toBeGreaterThanOrEqual(0.04); expect(v).toBeLessThanOrEqual(1); }
    }
  });

  it("is taller when a song is dragged over it", () => {
    const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
    let calm = 0, awake = 0;
    for (let t = 0; t < 4; t += 0.05) { calm += sum(waveBars(t)); awake += sum(waveBars(t, BARS, true)); }
    expect(awake).toBeGreaterThan(calm * 1.15);
  });

  it("breathes on the beat: the bars are fullest a little after each half second at 120 BPM", () => {
    const at = (t: number) => waveBars(t).reduce((x, y) => x + y, 0);
    expect(at(1.0)).toBeGreaterThan(at(1.0 + 0.13) * 0.999);                 // on the beat vs between beats, with the slow wobble held nearly still
  });

  it("sweeps the playhead from the left edge to the right edge, then starts again, faster when awake", () => {
    expect(playheadAt(0)).toBe(0);
    expect(playheadAt(4.5)).toBeCloseTo(0.5, 5);
    expect(playheadAt(9)).toBe(0);
    expect(playheadAt(2.25, true)).toBeCloseTo(0.5, 5);
    for (let t = 0; t < 40; t += 0.37) { const p = playheadAt(t); expect(p).toBeGreaterThanOrEqual(0); expect(p).toBeLessThan(1); }
  });

  it("is one picture with a plain description, sized as asked", () => {
    const html = renderToStaticMarkup(<LivingWave width={300} height={80} />);
    expect(html).toContain("<canvas");
    expect(html).toContain('role="img"');
    expect(html).toContain("A song turning into a film frame");
    expect(html).toContain("width:300px;height:80px");
  });
});
