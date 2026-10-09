import { describe, expect, it } from "vitest";
import type { Estimate } from "../api";
import { LIST_SECONDS, listPrice, shotLength, shotPrice } from "../price";

const est = (over: Partial<Estimate> = {}): Estimate => ({ provider: "fal", model: "m", shots: 1, usd: null, usd_known: 0, unknown: 0, basis: "", ...over });

describe("model prices", () => {
  it("a price in the model list says it is for a typical 5-second shot, so it is not mistaken for this shot's price", () => {
    expect(LIST_SECONDS).toBe(5);
    expect(listPrice(0.7)).toBe("$0.70 / 5 s");
    expect(listPrice(0.056)).toBe("$0.056 / 5 s");                 // small prices keep their third digit
    expect(listPrice(null)).toBe("price after first render");
  });

  it("the price of the picked model is for this shot, in dollars where the provider publishes one", () => {
    expect(shotPrice(est({ usd: 0.56 }), "x")).toBe("≈ $0.56");
    expect(shotPrice(est({ usd: 0 }), "x")).toBe("≈ $0.00");        // a free model is a price, not a missing one
  });

  it("a Kie price is in credits with a rough dollar figure, the same two units the rest of the app uses", () => {
    expect(shotPrice(est({ provider: "kie", kie_credits_est: 99, kie_usd_est: 0.49 }), "x")).toBe("≈ 99 Kie credits (about $0.49)");
    expect(shotPrice(est({ provider: "kie", kie_credits_est: 99 }), "x")).toBe("≈ 99 Kie credits");        // an older engine gives no dollar figure
  });

  it("falls back to the list wording while the estimate is loading or unknown", () => {
    expect(shotPrice(null, "price after first render")).toBe("price after first render");
    expect(shotPrice(est(), "price after first render")).toBe("price after first render");
  });

  it("names the shot's length", () => {
    expect(shotLength(8.48, 10.18)).toBe("1.7 s");
    expect(shotLength(0, 4)).toBe("4 s");
    expect(shotLength(5, 4)).toBe("0 s");                          // a damaged plan never shows a negative length
  });
});
