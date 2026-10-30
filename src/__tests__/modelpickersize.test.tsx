import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(() => Promise.resolve(null)), convertFileSrc: (p: string) => p }));

import { marks, ModelPicker } from "../ModelPicker";
import type { CatalogItem } from "../api";

const seedream: CatalogItem = { provider: "fal", model: "bytedance/seedream/v5/pro/edit", title: "Seedream 5.0 Pro Image Editing", category: "image-to-image", rec: 0, max_size: "2K" };
const plain: CatalogItem = { provider: "fal", model: "some/other-edit", title: "Other", category: "image-to-image" };

describe("the largest picture size a model offers", () => {
  it("is part of a model's marks, only when it is known", () => {
    expect(marks(seedream)).toBe("up to 2K");
    expect(marks({ ...seedream, fresh: true, text: true })).toBe("NEW · clean text · up to 2K");
    expect(marks(plain)).toBe("");
  });
  it("shows on the recommended card and in the full list", () => {
    const html = renderToStaticMarkup(<ModelPicker catalog={[seedream, plain]} value="" onChange={() => {}} label="Picture model" />);
    expect(html).toContain("up to 2K");
    expect(html.match(/up to 2K/g)!.length).toBeGreaterThanOrEqual(2);       // the card's line and the card's tooltip, then the list's mark
    expect(html).toContain("Recommended models");
    expect(html).not.toContain("up to 4K");
  });
});
