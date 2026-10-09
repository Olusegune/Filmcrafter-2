import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(() => Promise.resolve(null)), convertFileSrc: (p: string) => p }));

import { isPinned, ModelChoice, modelTags, priceText, type ModelRow } from "../ModelChoice";

const row = (over: Partial<ModelRow> = {}): ModelRow => ({ label: "Nano Banana", provider: "kie", model: "google/nano-banana-edit", price_usd: 0.03, verified: true, ...over });

describe("how a model is described", () => {
  it("writes the price of a picture and of a shot", () => {
    expect(priceText("image", 0.03)).toBe("about $0.030 a picture");
    expect(priceText("image", 0.25)).toBe("about $0.25 a picture");
    expect(priceText("video", 1.5)).toBe("about $1.50 for a 5-second shot");
    expect(priceText("image", null)).toBe("price after the first render");
    expect(priceText("video", null)).toBe("price shown before each render");
  });
  it("says whether it is proven and whether a picture model can see your pictures", () => {
    expect(modelTags(row(), "image")).toEqual(["proven here"]);
    expect(modelTags(row({ verified: false, sees_references: true }), "image")).toEqual(["not yet proven", "sees your character pictures"]);
    expect(modelTags(row({ sees_references: false }), "image")).toContain("words only: can't see your pictures");
    expect(modelTags(row({ sees_references: true }), "video")).toEqual(["proven here"]);       // only picture models are described this way
  });
  it("knows which model is pinned for which kind", () => {
    const pins = { image: { provider: "kie", model: "google/nano-banana-edit" } };
    expect(isPinned(pins, "image", row())).toBe(true);
    expect(isPinned(pins, "video", row())).toBe(false);
    expect(isPinned(pins, "image", row({ provider: "fal" }))).toBe(false);
    expect(isPinned(undefined, "image", row())).toBe(false);
  });
});

describe("the picker", () => {
  it("starts on 'Let FilmCrafter choose' and is a radio group named for what it picks", () => {
    const img = renderToStaticMarkup(<ModelChoice dir="d" kind="image" />);
    expect(img).toContain('role="radiogroup"');
    expect(img).toContain("Picture model");
    expect(img).toContain("Let FilmCrafter choose");
    expect(img).toContain('aria-checked="true"');
    expect(renderToStaticMarkup(<ModelChoice dir="d" kind="video" />)).toContain("Video model");
  });
});
