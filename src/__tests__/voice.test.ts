import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { peaksOf } from "../voiceLogic";

describe("the waveform outline of a recording", () => {
  it("takes the loudest sample of each slice and scales the loudest slice to 1", () => {
    const p = peaksOf([0, 0.1, -0.5, 0.2, 0, 0, 0.25, -0.1], 4);
    expect(p).toEqual([0.2, 1, 0, 0.5]);
  });
  it("keeps silence at zero, handles an empty file and gives as many bars as asked", () => {
    expect(peaksOf(new Float32Array(100), 8)).toEqual(new Array(8).fill(0));
    expect(peaksOf([], 5)).toEqual([0, 0, 0, 0, 0]);
    expect(peaksOf([0.3, 0.6], 0)).toEqual([]);
    expect(peaksOf(new Float32Array(10), 96)).toHaveLength(96);
  });
  it("is drawn beside each recording's player, and the shell may read the user's own files to draw it", () => {
    expect(readFileSync("src/VoiceoverPanel.tsx", "utf8")).toContain("<Waveform src=");
    const csp = JSON.parse(readFileSync("src-tauri/tauri.conf.json", "utf8")).app.security.csp["connect-src"] as string;
    expect(csp).toContain("asset:");
    expect(csp).not.toContain("*");
  });
});

describe("big films", () => {
  it("skip drawing the Make cards and the shot-list scenes that are out of view", () => {
    const css = readFileSync("src/film.css", "utf8");
    expect(css).toMatch(/\.mk-card \{ content-visibility: auto; contain-intrinsic-size: auto \d+px; \}/);
    expect(css).toMatch(/\.sl-scene \{ content-visibility: auto; contain-intrinsic-size: auto \d+px; \}/);
  });
});
