import { describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => `asset://${p}` }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

import { errorText, fmtTime } from "../api";
import { STATUS } from "../Board";

describe("fmtTime", () => {
  it("formats minutes and hundredths", () => {
    expect(fmtTime(0)).toBe("0:00.00");
    expect(fmtTime(64.42)).toBe("1:04.42");
    expect(fmtTime(191.44)).toBe("3:11.44");
  });
});

describe("errorText", () => {
  it("passes engine strings through and unwraps errors", () => {
    expect(errorText("Add your fal.ai key in Settings first.")).toBe("Add your fal.ai key in Settings first.");
    expect(errorText(new Error("boom"))).toBe("boom");
    expect(errorText({})).toBe("Something went wrong.");
  });
});

describe("shot status labels", () => {
  it("covers every storyboard state the engine reports", () => {
    for (const s of ["planned", "queued", "generating", "ready", "failed", "needs_review", "locked"] as const) {
      expect(STATUS[s].label.length).toBeGreaterThan(0);
    }
  });
});

import { niceName } from "../Wizard";
describe("reference names from file names", () => {
  it("drops filler words and title-cases", () => {
    expect(niceName("C:/x/character_amara.png")).toBe("Amara");
    expect(niceName("young-sege_ref_v2.jpg")).toBe("Young Sege");
    expect(niceName("sets_and_props.png")).toBe("Sets And Props");
    expect(niceName("character.png")).toBe("character");
  });
});

import { planningDefault } from "../Settings";
describe("local planning model default", () => {
  const models = ["gemma-3-12b-it", "llava-v1.6-mistral-7b", "qwen2.5-14b-instruct", "deepseek-r1:14b", "nomic-embed-text"];
  const vision = ["gemma-3-12b-it", "llava-v1.6-mistral-7b"];
  it("prefers a strong text model over vision, embedding and slow reasoning models", () => {
    expect(planningDefault("", models, vision)).toBe("qwen2.5-14b-instruct");
    expect(planningDefault("gemma-3-12b-it", models, vision)).toBe("qwen2.5-14b-instruct");   // stale/vision choice replaced
    expect(planningDefault("deepseek-r1:14b", models, vision)).toBe("deepseek-r1:14b");        // a valid text choice is kept
    expect(planningDefault("", ["gemma-3-12b-it"], ["gemma-3-12b-it"])).toBe("gemma-3-12b-it"); // only option
  });
});
