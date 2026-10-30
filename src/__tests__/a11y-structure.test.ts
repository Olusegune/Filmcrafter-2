import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/** The structure the accessibility scan (PF_A11Y=1 node scripts/docshots-edge.mjs) found wrong, kept right: each is a small rule about how a control is built. */
const src = (f: string) => readFileSync(`src/${f}`, "utf8");

describe("controls are not nested inside controls", () => {
  it("the Lighting runs keep their tick beside the summary, not inside it", () => {
    const l = src("Lighting.tsx");
    const sum = l.slice(l.indexOf("<summary>"), l.indexOf("</summary>"));
    expect(sum).not.toContain("<input");
    expect(l).toContain('className="lt-tick"');
  });
  it("the strip of light, which holds buttons, is a group and not a picture", () => {
    expect(src("Lighting.tsx")).toContain('className="lt-strip" role="group"');
  });
  it("the Advanced button sits beside the inspector's tab list, not inside it", () => {
    const s = src("Studio.tsx");
    const tabs = s.slice(s.indexOf('role="tablist" aria-label="Shot sections"'), s.indexOf('className="insp-adv"'));
    expect(tabs).toContain("</div>");                       // the tab list closes before the button
    expect(s).toContain('className="insp-tabrow"');
  });
});

describe("controls are named by what they show", () => {
  it("a shot block on the film strip is named with its visible text (the id and 4s)", () => {
    expect(src("FilmStrip.tsx")).toContain("aria-label={`${s.id} ${secs[i]}s`}");
  });
  it("a select tile takes its name from its content, with no label that could drift", () => {
    const r = src("SelectReview.tsx");
    const pick = r.slice(r.indexOf('className="sr2-pick"'), r.indexOf('className="sr2-pick"') + 400);
    expect(pick).not.toContain("aria-label");
  });
  it("every dropdown in the Studio's frame and quality section has a name", () => {
    const s = src("Studio.tsx");
    for (const name of ["Aspect ratio", "Quality", "Lip-sync"]) expect(s).toContain(`aria-label="${name}"`);
  });
});
