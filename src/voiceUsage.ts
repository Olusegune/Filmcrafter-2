import type { LedgerEntry, VoiceUsage } from "./api";

/** Said to the person whenever a cost cannot be known beforehand: never a made-up number. */
export const COST_UNKNOWN = "ElevenLabs does not publish how many characters this uses, so the amount is unknown. It is taken from your plan. By continuing you accept an amount you cannot see beforehand.";

export type Charge = { action: string; provider: string; cost: string; slot?: string; note?: string };

/** The words of the confirmation asked before anything that can use the provider's plan: what will happen, with whom, what it costs (or that it is unknown), and whether a voice slot is taken. */
export const confirmWords = (c: Charge): string =>
  [c.action, "", `Provider: ${c.provider}`, `Cost: ${c.cost}`, c.slot ? `Voice slot: ${c.slot}` : "Voice slot: none is taken", ...(c.note ? ["", c.note] : [])].join("\n");

const n = (x: number) => Math.round(x).toLocaleString();
const ops = (x: number) => `${x.toLocaleString()} operation${x === 1 ? "" : "s"}`;

/**
 * One calm sentence about what voice generation has used. A number is shown as "reported" only when ElevenLabs's own reply carried it; an estimate is always called an estimate and is never
 * the headline. Nothing is said before anything was done.
 */
export const usageWords = (by: VoiceUsage["by_unit"] | undefined): string => {
  const c = by?.elevenlabs_credits, slots = by?.voice_slot;
  const parts: string[] = [];
  if (c && c.operations > 0) {
    if (c.reported > 0) {
      parts.push(`Voice generation: ${n(c.reported)} ElevenLabs credits reported`
        + (c.unreported_operations > 0 ? `, plus ${ops(c.unreported_operations)} with no amount reported (about ${n(c.estimated_unreported)} credits, estimated)` : ""));
    } else {
      parts.push(`Voice generation: ${ops(c.operations)} so far. ElevenLabs has not reported amounts for them (estimated at about ${n(c.estimated_unreported || c.estimated)} credits)`);
    }
  }
  if (slots && slots.operations > 0) parts.push(`${slots.operations.toLocaleString()} voice slot${slots.operations === 1 ? "" : "s"} taken through FilmCrafter`);
  return parts.join(". ");
};

const ACTION: Record<string, string> = { speak: "Speak a line", preview: "Hear a sample", design: "Design voices", design_save: "Keep a designed voice", clone: "Clone a voice" };

/** An operation in words, for the list of ones whose outcome is unknown. */
export const attemptWords = (e: Pick<LedgerEntry, "action" | "person" | "shot" | "at">): string => {
  const when = new Date(e.at * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return `${ACTION[e.action] ?? e.action}${e.shot ? ` ${e.shot}` : ""}${e.person ? ` (${e.person})` : ""}, ${when}`;
};

export const STATUS_WORDS: Record<LedgerEntry["status"], string> = {
  prepared: "prepared", confirmed: "confirmed", submitted: "sent, waiting", completed: "done", refused: "refused (not charged)", failed_before_submission: "never sent (not charged)", uncertain: "outcome unknown",
};
