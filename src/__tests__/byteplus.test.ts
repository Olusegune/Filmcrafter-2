import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(() => Promise.resolve(null)), convertFileSrc: (p: string) => p }));

import { AUTO_IMAGE_MODEL } from "../api";
import { PROVIDER_NAME } from "../Render";

describe("BytePlus as a picture provider", () => {
  it("has a name, and Seedream 5.0 Pro as its automatic picture model", () => {
    expect(PROVIDER_NAME.byteplus).toBe("BytePlus");
    expect(AUTO_IMAGE_MODEL.byteplus).toBe("dola-seedream-5-0-pro-260628");
  });
  it("is the only new provider for pictures: the others are unchanged", () => {
    expect(Object.keys(AUTO_IMAGE_MODEL).sort()).toEqual(["byteplus", "fal", "google", "kie", "openai"]);
    expect(AUTO_IMAGE_MODEL.kie).toBe("google/nano-banana-edit");
  });
});
