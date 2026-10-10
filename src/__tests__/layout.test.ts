import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import studio from "../Studio.tsx?raw";

const unix = (s: string) => s.split("\r\n").join("\n");
const sharedCss = unix(readFileSync("src/studio-shared.css", "utf8"));
const stylesCss = unix(readFileSync("src/styles.css", "utf8"));

/** Layout bugs found by looking at the real screens, kept from coming back. These read the style rules, since no test renders real pixels (scripts/ui-audit.js does that, by hand). */
describe("layout regressions", () => {
  it("the full-screen exit hint sits below the progress bar, not on top of Export and the price", () => {
    const rule = sharedCss.match(/\.focus-exit \{[^}]*\}/)![0];
    const top = Number(rule.match(/top:\s*(\d+)px/)![1]);
    expect(top).toBeGreaterThanOrEqual(56);                                       // the progress bar is about 50 px tall
    expect(rule).toContain("background");                                         // and it is readable over any frame
    expect(sharedCss).toMatch(/\.focus-exit:focus-visible \{ opacity: 1; \}/);    // reachable from the keyboard
  });

  it("on a narrow window the inspector slims down, the title leaves the top bar and the secondary buttons fold into More", () => {
    const rule = stylesCss.slice(stylesCss.indexOf("@media (max-width: 1320px) {\n  .inspector"));
    expect(rule).toContain(".inspector { width: 340px; }");
    expect(rule).toContain(".topbar > div:first-child { display: none; }");
    expect(studio).toContain("useNarrow(1320)");
    expect(studio).toContain(">More ▾<");
  });

  it("the timeline never takes more than about 60% of the window, so the player keeps its room, and never so short that shot pictures are slivers", () => {
    expect(studio).toContain("Math.min(height, Math.round(window.innerHeight * 0.6))");
    expect(studio).toContain("CARD_MIN");
  });

  it("the top bar folds when its buttons really overflow (measured, on resize and on window resize), not at one fixed width", () => {
    expect(studio).toContain("function useBarFold(");
    expect(studio).toContain("el.scrollWidth > el.clientWidth + 1");
    expect(studio).toContain('window.addEventListener("resize", check)');
    expect(studio).toContain("const narrowBar = narrowWindow || folded;");
  });

  it("the full-screen view hides the test-shot note along with the rest of the chrome", () => {
    expect(sharedCss).toContain(".studio.focus .g-test { display: none; }");
  });
});
