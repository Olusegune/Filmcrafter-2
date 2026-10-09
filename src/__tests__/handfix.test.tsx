import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(() => new Promise(() => {})), convertFileSrc: (p: string) => p }));

import { boxFromCorners, boxStyle, HandFix, MIN_BOX, priceLine, usableBox } from "../HandFix";

describe("marking a hand", () => {
  it("puts two corners in order and keeps them inside the picture", () => {
    expect(boxFromCorners(0.6, 0.7, 0.2, 0.3)).toEqual([0.2, 0.3, 0.6, 0.7]);
    expect(boxFromCorners(-0.5, 0.2, 1.5, 2)).toEqual([0, 0.2, 1, 1]);
    expect(boxFromCorners(0.5, 0.5, 0.5, 0.5)).toEqual([0.5, 0.5, 0.5, 0.5]);
  });
  it("calls a box a hand only when it is big enough", () => {
    expect(usableBox(null)).toBe(false);
    expect(usableBox([0.5, 0.5, 0.5, 0.5])).toBe(false);
    expect(usableBox([0.1, 0.1, 0.1 + MIN_BOX / 2, 0.9])).toBe(false);
    expect(usableBox([0.1, 0.1, 0.1 + MIN_BOX, 0.1 + MIN_BOX])).toBe(true);
    expect(usableBox([0.2, 0.3, 0.6, 0.7])).toBe(true);
  });
  it("draws the box as percentages of the picture", () => {
    expect(boxStyle([0.25, 0.5, 0.75, 1])).toEqual({ left: "25%", top: "50%", width: "50%", height: "50%" });
  });
});

describe("the price", () => {
  const plan = { model: { label: "Nano Banana", price_usd: 0.03 }, variants: 1, usd_est: 0.03 };
  it("scales with the number of versions and says what model", () => {
    expect(priceLine(plan, 1)).toBe("1 version on Nano Banana: about $0.030");
    expect(priceLine(plan, 3)).toBe("3 versions on Nano Banana: about $0.090");
    expect(priceLine({ ...plan, usd_est: 0.3 }, 2)).toBe("2 versions on Nano Banana: about $0.60");
  });
  it("is empty until the price is known", () => {
    expect(priceLine(null, 2)).toBe("");
  });
});

describe("the dialog", () => {
  it("opens on the keyframe with nothing marked and the fix switched off", () => {
    const html = renderToStaticMarkup(<HandFix dir="d" shot="S01-04" image="media/kf.png" onClose={() => {}} />);
    expect(html).toContain('role="dialog"');
    expect(html).toContain("Fix a hand");
    expect(html).toContain("Find the hands for me");
    expect(html).toContain("Adjust with sliders");
    expect(html).toContain("d/media/kf.png");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Fix this hand<\/button>/);
    expect(html).toContain("the rest of S01-04 stays exactly as it is");
  });
});
