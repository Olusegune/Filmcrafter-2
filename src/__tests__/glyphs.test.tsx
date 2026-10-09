import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import * as I from "../icons";
import * as G from "../glyphs";

describe("pictures for the direction cards", () => {
  const cases: [string, string, unknown][] = [
    ["French New Wave", "France · 1960s cinema Jump cuts, street shooting", I.Film],
    ["Americana Road Movie", "USA · road movie Open highways, diners, motel neon", G.Road],
    ["One-Take Performance", "Music video tradition. The whole song as one continuous move", G.Mic],
    ["Handmade Stop Motion", "Craft animation tradition. Felt, clay and paper worlds", G.Scissors],
    ["Wuxia Poetry", "China · martial-arts cinema. Swordplay as dance", G.Sword],
    ["Lagos Nights", "Nigeria · Afrobeats video. Warm, glossy city nights", G.Moon],
  ];
  it.each(cases)("%s gets the picture that suits it", (name, about, icon) => {
    expect(G.directionGlyph(name, about)).toBe(icon);
  });

  it("every one of the six in the library gets a different picture from the rest, none the plain globe", () => {
    const got = cases.map(([n, a]) => G.directionGlyph(n, a));
    expect(new Set(got).size).toBe(6);
    expect(got).not.toContain(G.Globe);
  });

  it("falls back to the globe, and copes with nothing at all", () => {
    expect(G.directionGlyph("Something else entirely", "no clue words")).toBe(G.Globe);
    expect(G.directionGlyph()).toBe(G.Globe);
    expect(G.directionGlyph(undefined, null, "")).toBe(G.Globe);
  });

  it("matches on a creative direction's own words too", () => {
    expect(G.directionGlyph("The Long Goodbye", "tender", "a rooftop at dusk")).toBe(G.Heart);
    expect(G.directionGlyph("Carnival of Colours", "joyful dance in the street")).toBe(I.Dance);
  });
});

describe("pictures for the looks", () => {
  it.each([["feature-3d", I.Cube], ["stylized-3d", I.Cube], ["claymation", G.Scissors], ["stop-motion", G.Scissors], ["anime", G.Star], ["live-action", I.Camera], ["hand-drawn-2d", I.Wand], ["painterly", G.Brush]])(
    "%s", (id, icon) => { expect(G.lookGlyph(id)).toBe(icon); });
  it("falls back to a film frame", () => { expect(G.lookGlyph("something-new")).toBe(I.Film); });
});

describe("the badge and the new glyphs", () => {
  it("holds the picture in a square badge that a screen reader skips", () => {
    const html = renderToStaticMarkup(<G.Badge icon={G.Mic} />);
    expect(html).toContain('class="glyph-badge"');
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain("<svg");
  });
  it("every new glyph draws something and is hidden from screen readers", () => {
    for (const k of ["Mic", "Moon", "Sun", "Globe", "Road", "Sword", "Scissors", "Heart", "Star", "Brush", "Flame", "Leaf", "Skyline", "Cutout"] as const) {
      const html = renderToStaticMarkup(G[k]({ size: 16 }));
      expect(html, k).toMatch(/<(path|circle|rect)/);
      expect(html, k).toContain('aria-hidden="true"');
      expect(html, k).toContain('width="16"');
    }
  });
});
