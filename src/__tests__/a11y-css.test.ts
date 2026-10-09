import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

const read = (f: string) => readFileSync(f, "utf8").split("\r\n").join("\n");
const stylesCss = read("src/styles.css"), focusCss = read("src/focus.css"), cornersCss = read("src/corners.css"), mainTsx = read("src/main.tsx");

const css = (f: string) => ({ "styles.css": stylesCss, "focus.css": focusCss, "corners.css": cornersCss })[f] as string;

const lum = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a: string, b: string) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const token = (name: string) => css("styles.css").match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))![1];

describe("colour and keyboard guarantees", () => {
  it("quiet text (--smoke) is readable on every panel colour, at least 4.5:1", () => {
    for (const bg of ["obsidian", "carbon", "graphite", "slate"]) expect(ratio(token("smoke"), token(bg))).toBeGreaterThanOrEqual(4.5);
  });

  it("every control shows a ring when reached by keyboard, from one rule that never outranks a control's own style", () => {
    const f = css("focus.css");
    expect(f).toMatch(/:where\([^)]*button[^)]*a\[href\][^)]*\):focus-visible\s*\{[^}]*outline:\s*2px solid/);
    expect(f).toContain('[role="tab"]');
    expect(f).toContain('[tabindex="0"]');
  });

  it("buttons are softly rounded, not square and not pills", () => {
    const c = css("corners.css");
    const px = (n: string) => parseInt(c.match(new RegExp(`--${n}:\\s*(\\d+)px`))![1], 10);
    for (const n of ["r-btn", "r-control", "r-small"]) { expect(px(n)).toBeGreaterThanOrEqual(3); expect(px(n)).toBeLessThanOrEqual(8); }
  });

  it("loads the focus net before the corner rules", () => {
    const m = mainTsx;
    expect(m.indexOf("focus.css")).toBeGreaterThan(-1);
    expect(m.indexOf("focus.css")).toBeLessThan(m.indexOf("corners.css"));
  });
});
