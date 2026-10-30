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
  t = t.replace(/\s*[-–]\s*(?:image\s*to\s*image|image\s*to\s*video|text\s*to\s*video|edit)\s*$/i, "").replace(/^(?:Google|Bytedance)\s*[-–]\s*/i, "").replace(/^bytedance-/i, "").replace(/^Bytedance\s+(?=Seedance)/i, "").trim();
  return t || c.title;
};

/** What the list says after a model's name: new, cannot see your pictures, good at text. */
export const marks = (c: CatalogItem): string => [c.fresh ? "NEW" : "", c.sees === false ? "text only" : "", c.text ? "clean text" : "", c.max_size ? `up to ${c.max_size}` : ""].filter(Boolean).join(" · ");

/**
 * Choose a model. Recommended models come first as cards (name, family, and NEW / "text only" / "clean text" marks). "All models" opens a searchable list grouped by family; "text only"
 * models cannot see your character sheets, so faces and the look can drift: pick an edit / image-to-image model for keyframes. A box takes any model id, and "Refresh" asks the provider
 * again for models added today.
 */
export function ModelPicker({ catalog, value, onChange, onBlur, label, id, onRefresh }: {
  catalog: CatalogItem[]; value: string; onChange: (model: string) => void; onBlur?: (value: string) => void; label: string; id?: string; onRefresh?: () => Promise<void> | void;
}) {
  const listId = useId();
  const [textOnly, setTextOnly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [find, setFind] = useState("");
  const q = find.trim().toLowerCase();
  const shown = catalog.filter((c) => (!textOnly || c.text) && (!q || `${c.title} ${c.model}`.toLowerCase().includes(q)));
  const groups = new Map<string, CatalogItem[]>();
  for (const c of shown) {
    const [family] = split(c);
    groups.set(family, [...(groups.get(family) ?? []), c]);
  }
  const ordered = Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
  const rec = catalog.filter((c) => c.rec != null).sort((a, b) => (a.rec ?? 0) - (b.rec ?? 0));
  const picked = catalog.find((c) => c.model === value);
  const anyText = catalog.some((c) => c.text);
  const card = (c: CatalogItem) => {
    const on = c.model === value;
    return (
      <button key={c.model} type="button" className={`mp2-card ${on ? "on" : ""}`} aria-pressed={on} title={`${c.title} (${c.model})${marks(c) ? " · " + marks(c) : ""}`} onClick={() => onChange(c.model)}>
        <span className="mp2-name">{shortName(c)}{c.fresh && <span className="mp-new" aria-label="new"> NEW</span>}</span>
        <span className="mp2-sub">{split(c)[0]}{c.sees === false ? " · text only" : ""}{c.text ? " · clean text" : ""}{c.max_size ? ` · up to ${c.max_size}` : ""}</span>
        {on && <span className="mp2-check" aria-hidden="true">✓</span>}
      </button>);
  };
  return (
    <div className="model-picker mp2">
      <div className="mp2-head"><span className="mp2-label">{label}</span><span className="mp2-now" title={value}>{picked ? shortName(picked) : value || "none chosen"}</span></div>
      {rec.length > 0 && (
        <div className="mp2-cards" role="group" aria-label="Recommended models">{rec.map(card)}</div>
      )}
      {picked && picked.sees === false && (
        <p className="mp-warn" role="note">This model only reads words: it cannot see your character sheets or style pictures, so faces and the look can drift. For keyframes, pick an edit or image-to-image model (marked above).</p>
      )}
      {catalog.length > 0 && (
        <details className="mp2-all">
          <summary>All models <span className="dim">{catalog.length}</span></summary>
          <input className="text-input mp2-find" type="search" value={find} onChange={(e) => setFind(e.target.value)} placeholder="Search models" aria-label={`Search ${label.toLowerCase()}`} />
          <div className="mp2-list" role="listbox" aria-label={`${label} (list)`}>
            {ordered.length === 0 && <p className="dim">Nothing matches.</p>}
            {ordered.map(([family, items]) => (
              <div key={family} className="mp2-group">
                <h4>{family} <span className="dim">{items.length}</span></h4>
                {items.map((c) => (
                  <button key={c.model} type="button" role="option" aria-selected={c.model === value} className={`mp2-row ${c.model === value ? "on" : ""}`} onClick={() => onChange(c.model)} title={c.model}>
                    <span>{split(c)[1]}</span>{marks(c) && <small>{marks(c)}</small>}</button>))}
              </div>))}
          </div>
          <div className="mp-tools">
            {anyText && <label className="mp-check"><input type="checkbox" checked={textOnly} onChange={(e) => setTextOnly(e.target.checked)} /> Only models good at clean text</label>}
            {onRefresh && <button type="button" className="btn sm ghost" disabled={busy} onClick={async () => { setBusy(true); try { await onRefresh(); } finally { setBusy(false); } }}
                                  title="Ask the provider for its current list: shows models added today">{busy ? "Refreshing…" : "Refresh list"}</button>}
          </div>
        </details>
      )}
      <details className="mp2-id">
        <summary>Type a model id</summary>
        <input id={id} className="text-input" list={listId} value={value} onChange={(e) => onChange(e.target.value)} onBlur={(e) => onBlur?.(e.target.value)}
               aria-label={label} placeholder="or type a model id" />
        <datalist id={listId}>{catalog.map((c) => <option key={c.model} value={c.model}>{c.title}</option>)}</datalist>
      </details>
    </div>
  );
}
