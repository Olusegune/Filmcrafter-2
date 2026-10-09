import type { Estimate } from "./api";

/** The seconds the model list's prices are for: the engine prices every model for a typical 5-second shot so they can be compared with each other. */
export const LIST_SECONDS = 5;

/** A price in the model list: dollars for a typical 5-second shot (not this shot), or why there is none yet. */
export const listPrice = (usd: number | null): string => usd != null ? `$${usd.toFixed(usd < 0.1 ? 3 : 2)} / ${LIST_SECONDS} s` : "price after first render";

/** The price of this shot on the model just picked: dollars where the provider publishes a price, Kie credits (with a rough dollar figure) where it does not. */
export function shotPrice(est: Estimate | null, fallback: string): string {
  if (est?.usd != null) return `≈ $${est.usd.toFixed(2)}`;
  if (est?.kie_credits_est) return `≈ ${est.kie_credits_est} Kie credits${est.kie_usd_est != null ? ` (about $${est.kie_usd_est.toFixed(2)})` : ""}`;
  return fallback;
}

/** "1.7 s", "4 s": a shot's length for the line that names it. */
export const shotLength = (start: number, end: number): string => {
  const s = Math.max(0, end - start);
  return `${s % 1 === 0 ? s.toFixed(0) : s.toFixed(1)} s`;
};
