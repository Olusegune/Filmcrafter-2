import { useId, useState } from "react";
import type { CatalogItem } from "./api";

/** Kie lists models as "Family · Title" (for example "GPT Image · GPT Image 2.5 Flare - Image To Image"); other providers give a plain title. */
const split = (c: CatalogItem): [string, string] => {
  const i = c.title.indexOf(" · ");
  return i > 0 ? [c.title.slice(0, i), c.title.slice(i + 3)] : [c.category ? c.category.replace(/-/g, " ") : "Models", c.title];
};

/** A short name for a recommended model's button: "Google - Nano Banana 2.1" -> "Nano Banana 2.1", "GPT Image 2.5 Flare - Image To Image" -> "GPT Image 2.5 Flare". */
export const shortName = (c: CatalogItem): string => {
  let t = split(c)[1];
  t = t.replace(/\s*[-–]\s*(?:image\s*to\s*image|image\s*to\s*video|text\s*to\s*video|edit)\s*$/i, "").replace(/^(?:Google|Bytedance)\s*[-–]\s*/i, "").replace(/^bytedance-/i, "").trim();
  return t || c.title;
};

/** What the list says after a model's name: new, cannot see your pictures, good at text. */
export const marks = (c: CatalogItem): string => [c.fresh ? "NEW" : "", c.sees === false ? "text only" : "", c.text ? "clean text" : ""].filter(Boolean).join(" · ");

/**
 * Choose a model. Recommended models come first as buttons; the list below is grouped by family, with each model marked NEW, "text only" (it cannot see your character sheets, so faces and
 * the look can drift: pick an edit / image-to-image model for keyframes) or "clean text" (good at drawing words). A box takes any model id, and "Refresh" asks the provider again
 * for models added today.
 */
export function ModelPicker({ catalog, value, onChange, onBlur, label, id, onRefresh }: {
  catalog: CatalogItem[]; value: string; onChange: (model: string) => void; onBlur?: (value: string) => void; label: string; id?: string; onRefresh?: () => Promise<void> | void;
}) {
  const listId = useId();
  const [textOnly, setTextOnly] = useState(false);
  const [busy, setBusy] = useState(false);
  const shown = textOnly ? catalog.filter((c) => c.text) : catalog;
  const groups = new Map<string, CatalogItem[]>();
  for (const c of shown) {
    const [family] = split(c);
    groups.set(family, [...(groups.get(family) ?? []), c]);
  }
  const ordered = Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
  const known = catalog.some((c) => c.model === value);
  const rec = catalog.filter((c) => c.rec != null).sort((a, b) => (a.rec ?? 0) - (b.rec ?? 0));
  const picked = catalog.find((c) => c.model === value);
  const anyText = catalog.some((c) => c.text);
  return (
    <div className="model-picker">
      {rec.length > 0 && (
        <div className="model-chips" role="group" aria-label="Recommended models">
          <span className="dim">Recommended</span>
          {rec.map((c) => (
            <button key={c.model} type="button" className={`btn sm ${c.model === value ? "primary" : "ghost"}`} aria-pressed={c.model === value}
                    title={`${c.title} (${c.model})${marks(c) ? " · " + marks(c) : ""}`} onClick={() => onChange(c.model)}>
              {shortName(c)}{c.fresh && <span className="mp-new" aria-label="new"> NEW</span>}</button>
          ))}
        </div>
      )}
      {catalog.length > 0 && (
        <select aria-label={`${label} (list)`} value={known ? value : ""} onChange={(e) => e.target.value && onChange(e.target.value)}>
          {!known && <option value="">{value ? `Custom: ${value}` : "Choose a model…"}</option>}
          {ordered.map(([family, items]) => (
            <optgroup key={family} label={`${family} (${items.length})`}>
              {items.map((c) => <option key={c.model} value={c.model}>{split(c)[1]}{marks(c) ? `  ·  ${marks(c)}` : ""}</option>)}
            </optgroup>
          ))}
        </select>
      )}
      {picked && picked.sees === false && (
        <p className="mp-warn" role="note">This model only reads words: it cannot see your character sheets or style pictures, so faces and the look can drift. For keyframes, pick an edit or image-to-image model (marked above).</p>
      )}
      <div className="mp-tools">
        {anyText && <label className="mp-check"><input type="checkbox" checked={textOnly} onChange={(e) => setTextOnly(e.target.checked)} /> Only models good at clean text</label>}
        {onRefresh && <button type="button" className="btn sm ghost" disabled={busy} onClick={async () => { setBusy(true); try { await onRefresh(); } finally { setBusy(false); } }}
                              title="Ask the provider for its current list: shows models added today">{busy ? "Refreshing…" : "Refresh list"}</button>}
      </div>
      <input id={id} className="text-input" list={listId} value={value} onChange={(e) => onChange(e.target.value)} onBlur={(e) => onBlur?.(e.target.value)}
             aria-label={label} placeholder="or type a model id" />
      <datalist id={listId}>{catalog.map((c) => <option key={c.model} value={c.model}>{c.title}</option>)}</datalist>
    </div>
  );
}
