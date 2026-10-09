import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(), convertFileSrc: (p: string) => p }));

import { CheaperRetry, confirmText, optionLine, usd, type RetryOption } from "../CheaperRetry";
import type { Job } from "../api";

const opt = (over: Partial<RetryOption> = {}): RetryOption => ({ provider: "fal", model: "fal/cheap", label: "Wan 2.2 Turbo", price_usd: 0.2, cheaper: true, saves_usd: 0.8, strength: "Low price.", warning: "", ...over });
const job = (over: Partial<Job> = {}): Job => ({ id: "j1", shot_id: "S01-04", plan: "production", provider: "kie", model: "kie/failed", kind: "video", state: "failed", ...over }) as Job;

describe("the cheaper retry wording", () => {
  it("writes small prices with three places and larger ones with two", () => {
    expect(usd(0.04)).toBe("$0.040");
    expect(usd(0.5)).toBe("$0.50");
    expect(usd(2)).toBe("$2.00");
  });
  it("shows an option with what it saves when that is known", () => {
    expect(optionLine(opt())).toBe("Wan 2.2 Turbo · about $0.20 (saves $0.80)");
    expect(optionLine(opt({ saves_usd: null }))).toBe("Wan 2.2 Turbo · about $0.20");
    expect(optionLine(opt({ saves_usd: 0 }))).toBe("Wan 2.2 Turbo · about $0.20");
  });
  it("asks with the shot, the model and the price, and repeats the one-model warning for pictures", () => {
    const q = confirmText(opt(), "S01-04");
    expect(q).toContain("S01-04");
    expect(q).toContain("Wan 2.2 Turbo");
    expect(q).toContain("$0.20");
    expect(q).toContain("failed render stays");
    expect(q).not.toContain("one picture model");
    expect(confirmText(opt({ warning: "Use one picture model for the whole project." }), "S01-04")).toContain("Use one picture model");
  });
});

describe("where the button appears", () => {
  const dir = "d";
  it("is offered on a failed video", () => {
    expect(renderToStaticMarkup(<CheaperRetry dir={dir} job={job()} onJobs={() => {}} />)).toContain("Try a cheaper model");
  });
  it("is not offered on a render that is not failed, was already retried, or is not a shot", () => {
    for (const j of [job({ state: "ready" }), job({ state: "uncertain" }), job({ retried_as: "j2" }), job({ kind: "asset" })]) {
      expect(renderToStaticMarkup(<CheaperRetry dir={dir} job={j} onJobs={() => {}} />)).toBe("");
    }
  });
});
