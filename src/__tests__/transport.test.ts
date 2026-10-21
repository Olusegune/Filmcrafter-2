import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

const studio = readFileSync("src/Studio.tsx", "utf8");
const css = readFileSync("src/studio-shared.css", "utf8");

describe("the player controls", () => {
  it("the skip buttons go to the previous and next shot, and say so", () => {
    expect(studio).toMatch(/aria-label="Previous shot"/);
    expect(studio).toMatch(/aria-label="Next shot"/);
    expect(studio).not.toMatch(/aria-label="Back to start"|aria-label="To end"/);
  });
  it("a film with no sound file plays on its own clock, and scrubbing carries on from the new place", () => {
    expect(studio).toMatch(/clock = useRef/);
    expect(studio).toMatch(/if \(clock\.current\) clock\.current = \{ from: performance\.now\(\), base: c \}/);
    expect(studio).toMatch(/if \(!a\) \{/);
  });
  it("the volume bar is a slim rounded bar filled with the design system's gold (and the scrub bar is rounded too)", () => {
    const rule = css.slice(css.indexOf(".transport .volume input[type=range]:not(.scrub) {"));
    expect(rule).toMatch(/border-radius: 999px/);
    expect(rule).toMatch(/var\(--gold/);
    expect(rule.slice(0, 600)).not.toMatch(/--signal|#64b7ff/);
  });
});
