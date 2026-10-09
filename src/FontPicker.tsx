import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type FontList } from "./api";

const cache = new Map<string, Promise<FontList>>();    // one list per project, shared by every picker on screen
export const loadFonts = (dir: string) => {
  let p = cache.get(dir);
  if (!p) { p = api.fonts(dir, "list"); cache.set(dir, p); p.catch(() => cache.delete(dir)); }
  return p;
};

/**
 * Choose the typeface for captions or on-screen text: the default, a font installed on this computer, or a font file of your own
 * (copied into the project, so the film still exports if the font is later uninstalled). `inherit` names what an empty choice means.
 */
export function FontPicker({ dir, value, onChange, inherit = "Default (Segoe UI Bold)", allowAdd = true, label = "Font" }: {
  dir: string; value: string; onChange: (id: string) => void; inherit?: string; allowAdd?: boolean; label?: string;
}) {
  const [list, setList] = useState<FontList | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    const reload = () => loadFonts(dir).then(setList).catch(() => setList({ installed: [], project: [], default: "" }));
    reload();
    window.addEventListener("pf-fonts-changed", reload);
    return () => window.removeEventListener("pf-fonts-changed", reload);
  }, [dir]);

  const add = async () => {
    setErr("");
    const f = await open({ filters: [{ name: "Font", extensions: ["ttf", "otf"] }] });
    if (typeof f !== "string") return;
    try {
      const r = await api.fonts<{ id: string }>(dir, "add", { file: f });
      cache.delete(dir);
      window.dispatchEvent(new Event("pf-fonts-changed"));
      onChange(r.id);
    } catch (e) { setErr(errorText(e)); }
  };

  const known = !value || !!list?.installed.some((f) => f.id === value) || !!list?.project.some((f) => f.id === value);
  return (
    <label className="font-pick">{label}
      <select value={value} aria-label={label} onChange={(e) => onChange(e.target.value)}>
        <option value="">{inherit}</option>
        {list && !known && <option value={value}>{value.split(":")[1] ?? value} (missing: using the default)</option>}
        {list && list.project.length > 0 && <optgroup label="Added to this project">
          {list.project.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</optgroup>}
        {list && list.installed.length > 0 && <optgroup label="Installed on this computer">
          {list.installed.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</optgroup>}
      </select>
      {allowAdd && <button type="button" className="link" onClick={add} title="Use a .ttf or .otf file of your own">Add a font file…</button>}
      {err && <span className="error-text" role="alert">{err}</span>}
    </label>
  );
}
