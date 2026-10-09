import { useEffect, useState } from "react";
import { api, errorText } from "./api";

export type ModelRow = { label: string; provider: string; model: string; price_usd: number | null; verified: boolean; family?: string; strength?: string; consider?: string; watch?: string; sees_references?: boolean | null };
export type ModelList = { video: ModelRow[]; image: ModelRow[]; advice?: string };
type Pins = Partial<Record<"image" | "video", { provider: string; model: string }>>;

/** Pure: the price of one shot or still, in words. */
export function priceText(kind: "image" | "video", price: number | null): string {
  if (price == null) return kind === "image" ? "price after the first render" : "price shown before each render";
  const p = price < 0.1 ? price.toFixed(3) : price.toFixed(2);
  return kind === "video" ? `about $${p} for a 5-second shot` : `about $${p} a picture`;
}

/** Pure: whether this row is the pinned model. */
export const isPinned = (pins: Pins | undefined, kind: "image" | "video", r: Pick<ModelRow, "provider" | "model">): boolean => pins?.[kind]?.provider === r.provider && pins?.[kind]?.model === r.model;

/** Pure: the small tags under a model's name, in the order a person decides by. */
export function modelTags(r: ModelRow, kind: "image" | "video"): string[] {
  return [r.verified ? "proven here" : "not yet proven", ...(kind === "image" && r.sees_references === true ? ["sees your character pictures"] : []), ...(kind === "image" && r.sees_references === false ? ["words only: can't see your pictures"] : [])];
}

/**
 * Choose the model that makes the pictures, or the video, for the whole project, with a sentence on what each is good for. "Let PULSEFRAME choose" follows the cost setting above it.
 * Choosing one fixes it for every shot, which is what keeps people looking the same from picture to picture.
 */
export function ModelChoice({ dir, kind, onChanged }: { dir: string; kind: "image" | "video"; onChanged?: () => void }) {
  const [list, setList] = useState<ModelList | null>(null);
  const [pins, setPins] = useState<Pins>({});
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.routing<ModelList>(dir, "models").then(setList).catch((e) => setErr(errorText(e)));
    api.routing<{ pins?: Pins }>(dir, "status").then((s) => setPins(s.pins ?? {})).catch(() => {});
  }, [dir]);
  const pin = async (row: ModelRow | null) => {
    setBusy(true); setErr("");
    try {
      const s = await api.routing<{ pins?: Pins }>(dir, "set", { pin: row ? { kind, provider: row.provider, model: row.model } : { kind, clear: true } });
      setPins(s.pins ?? {}); onChanged?.();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const rows = list?.[kind] ?? [];
  const none = !pins[kind];
  return (
    <div className="mc" role="radiogroup" aria-label={kind === "image" ? "Picture model" : "Video model"}>
      <button role="radio" aria-checked={none} className={`mc-row mc-auto ${none ? "on" : ""}`} disabled={busy} onClick={() => pin(null)}>
        <b>Let PULSEFRAME choose</b><span className="dim">Follows the cost setting above. The best choice if you are not sure.</span>
      </button>
      {list && rows.length === 0 && <p className="dim">Add a fal.ai, Kie.ai or OpenAI key in Settings to see the models you can use.</p>}
      {rows.map((r) => {
        const on = isPinned(pins, kind, r);
        return (
          <button key={r.provider + r.model} role="radio" aria-checked={on} className={`mc-row ${on ? "on" : ""}`} disabled={busy} onClick={() => pin(r)} title={r.model}>
            <span className="mc-top"><b>{r.label}</b> <span className="dim">· {r.provider}</span><span className="mc-price num">{priceText(kind, r.price_usd)}</span></span>
            <span className="mc-tags">{modelTags(r, kind).map((t) => <span key={t} className={`mp-tag ${t === "proven here" ? "ok" : ""}`}>{t}</span>)}</span>
            {r.strength && <span className="mc-line">{r.strength}</span>}
            {r.consider && <span className="mc-line dim">Consider it: {r.consider}</span>}
            {r.watch && <span className="mc-line dim">Keep in mind: {r.watch}</span>}
          </button>);
      })}
      {kind === "image" && list?.advice && <p className="mc-advice">{list.advice}</p>}
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>
  );
}
