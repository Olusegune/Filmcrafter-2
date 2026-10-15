import type { SpendLine } from "./api";

const PROVIDER: Record<string, string> = { kie: "Kie.ai", fal: "fal", elevenlabs: "ElevenLabs", openai: "OpenAI", google: "Google", midjourney: "Midjourney" };
export const providerName = (p: string) => PROVIDER[p] ?? p;
const num = (x: number) => (Math.abs(x - Math.round(x)) < 0.005 ? Math.round(x).toLocaleString() : x.toFixed(2));

/** One spending line in plain words. Reported amounts and estimates are never blended: a provider's own figure is "reported", ours is "about ... (estimate)". */
export function lineWords(l: Pick<SpendLine, "unit" | "unit_name" | "reported" | "estimated" | "reported_operations" | "estimated_operations">): string {
  const unit = l.unit === "usd" ? "" : ` ${l.unit_name.replace(/ \(estimated\)/, "")}`;
  const money = (x: number) => (l.unit === "usd" ? `$${x.toFixed(2)}` : `${num(x)}${unit}`);
  const parts: string[] = [];
  if (l.reported_operations > 0) parts.push(`${money(l.reported)} reported`);
  if (l.estimated_operations > 0) parts.push(`about ${money(l.estimated)} (estimate${l.reported_operations > 0 ? `, ${l.estimated_operations} not reported` : ""})`);
  if (!parts.length) parts.push("no amount reported");
  return parts.join(" + ");
}

export const opsWords = (n: number) => `${n.toLocaleString()} ${n === 1 ? "operation" : "operations"}`;

export const limitWords = (limits: Record<string, number>) => Object.entries(limits).map(([u, v]) => `${num(v)} ${u.replace(/_/g, " ")}`).join(", ");
