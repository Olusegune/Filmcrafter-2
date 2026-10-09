import { useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type Overlay } from "./api";
import { FontPicker } from "./FontPicker";
import { IntroCardSheet } from "./IntroCard";

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const num = (v: string) => (v.trim() === "" ? null : Number(v));

/**
 * On-screen text: signs, titles, captions and logos drawn over the finished film when you export. Each one is shown from a start to an
 * end (or through a part of a song section, such as chorus1), fades in and out, and sits where you put it.
 */
export function OverlaysPanel({ dir, onCount }: { dir: string; onCount?: (n: number) => void }) {
  const [items, setItems] = useState<Overlay[] | null>(null);
  const [err, setErr] = useState("");
  const [preview, setPreview] = useState<{ id: string; path: string } | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [card, setCard] = useState(false);
  useEffect(() => { if (items) window.dispatchEvent(new Event("pf-overlays-changed")); }, [items]);   // the Studio player follows
  const load = useCallback(async () => { const r = await api.overlays(dir, "list"); setItems(r); onCount?.(r.filter((o) => o.enabled && o.placed).length); }, [dir, onCount]);
  useEffect(() => { load().catch((e) => setErr(errorText(e))); }, [load]);

  const call = async (action: "add" | "update" | "remove", data: Record<string, unknown>) => {
    setErr("");
    try { const r = await api.overlays(dir, action, data); setItems(r); onCount?.(r.filter((o) => o.enabled && o.placed).length); setPreview(null); }
    catch (e) { setErr(errorText(e)); }
  };
  const show = async (o: Overlay) => {
    setErr("");
    try { const r = await api.overlays<{ path: string }>(dir, "preview", { id: o.id }); setPreview({ id: o.id, path: r.path }); }
    catch (e) { setErr(errorText(e)); }
  };
  const addImage = async () => {
    const f = await open({ filters: [{ name: "Picture or text sign", extensions: ["png", "jpg", "jpeg", "webp", "svg"] }] });
    if (typeof f === "string") await call("add", { image: f, y: 0.86, width: 0.5, start: 0, end: 4 });
  };

  return (
    <details className="ov-panel">
      <summary><b>On-screen text</b> <span className="dim">{items ? `${items.filter((o) => o.enabled).length} on` : ""}</span></summary>
      <p className="dim">Text and signs drawn over the film when you export (a title, a sign, a caption, a logo). Models can't spell, so text that must read
        correctly is added here. Timed by seconds, or by a song section such as <code>chorus1</code>, <code>verse2</code>, <code>pre1</code>, <code>bridge</code> or <code>final</code>.</p>
      {err && <p className="error-text" role="alert">{err}</p>}
      {items?.length === 0 && <p className="dim">None yet.</p>}
      <ul className="ov-list">
        {(items ?? []).map((o) => (
          <li key={o.id} className={`ov-row ${o.enabled ? "" : "off"}`}>
            <div className="ov-head">
              <label title="Draw this when exporting"><input type="checkbox" checked={o.enabled} onChange={(e) => call("update", { id: o.id, enabled: e.target.checked })} /></label>
              <button className="link ov-name" onClick={() => setOpenId(openId === o.id ? null : o.id)} aria-expanded={openId === o.id}>
                {o.text || o.file?.split("/").pop() || (o.kind === "fill" ? "Colour backdrop" : "Picture")}</button>
              <span className={o.placed ? "dim num" : "si-problems"}>{o.placed ? `${clock(o.start!)} – ${clock(o.end!)}${o.section ? ` · ${o.section}` : ""}` : `not placed: ${o.reason}`}</span>
            </div>
            {openId === o.id && (
              <div className="ov-edit">
                {o.kind === "text" && <label className="field"><span>Text</span>
                  <textarea className="text-input" rows={2} defaultValue={o.text} maxLength={300} onBlur={(e) => e.target.value !== o.text && call("update", { id: o.id, text: e.target.value })} /></label>}
                <div className="ov-grid">
                  <label>Section<input className="text-input" defaultValue={o.section ?? ""} placeholder="chorus1" onBlur={(e) => call("update", { id: o.id, section: e.target.value })} /></label>
                  <label>Start (s)<input className="text-input" inputMode="decimal" defaultValue={o.explicit && o.start != null ? o.start : ""} placeholder="from section"
                                         onBlur={(e) => call("update", { id: o.id, start: num(e.target.value) })} /></label>
                  <label>End (s)<input className="text-input" inputMode="decimal" defaultValue={o.explicit_end && o.end != null ? o.end : ""} placeholder="auto"
                                       onBlur={(e) => call("update", { id: o.id, end: num(e.target.value) })} /></label>
                  <label>Fade (s)<input className="text-input" inputMode="decimal" defaultValue={o.fade} onBlur={(e) => call("update", { id: o.id, fade: Number(e.target.value) })} /></label>
                </div>
                <div className="ov-grid">
                  <label>Across {Math.round(o.x * 100)}%<input type="range" min={0} max={100} defaultValue={Math.round(o.x * 100)} onPointerUp={(e) => call("update", { id: o.id, x: Number(e.currentTarget.value) / 100 })} onKeyUp={(e) => call("update", { id: o.id, x: Number(e.currentTarget.value) / 100 })} /></label>
                  <label>Down {Math.round(o.y * 100)}%<input type="range" min={0} max={100} defaultValue={Math.round(o.y * 100)} onPointerUp={(e) => call("update", { id: o.id, y: Number(e.currentTarget.value) / 100 })} onKeyUp={(e) => call("update", { id: o.id, y: Number(e.currentTarget.value) / 100 })} /></label>
                  {o.kind === "text"
                    ? <label>Size {Math.round(o.size * 100)}%<input type="range" min={2} max={30} defaultValue={Math.round(o.size * 100)} onPointerUp={(e) => call("update", { id: o.id, size: Number(e.currentTarget.value) / 100 })} onKeyUp={(e) => call("update", { id: o.id, size: Number(e.currentTarget.value) / 100 })} /></label>
                    : <label>Width {Math.round(o.width * 100)}%<input type="range" min={5} max={100} defaultValue={Math.round(o.width * 100)} onPointerUp={(e) => call("update", { id: o.id, width: Number(e.currentTarget.value) / 100 })} onKeyUp={(e) => call("update", { id: o.id, width: Number(e.currentTarget.value) / 100 })} /></label>}
                  {o.kind === "text" && <label>Colour<input type="color" defaultValue={o.color} onBlur={(e) => call("update", { id: o.id, color: e.target.value })} /></label>}
                  {o.kind === "text" && <FontPicker dir={dir} value={o.font ?? ""} onChange={(id) => call("update", { id: o.id, font: id })} />}
                </div>
                <div className="sheet-actions" style={{ marginTop: 6 }}>
                  <button className="btn sm ghost" onClick={() => call("remove", { id: o.id })}>Remove</button>
                  <button className="btn sm" onClick={() => show(o)}>Preview</button>
                </div>
                {preview?.id === o.id && <img className="ov-preview" src={api.mediaUrl(`${dir}/${preview.path}`) + `?t=${Date.now()}`} alt={`Preview of ${o.text}`} />}
              </div>)}
          </li>
        ))}
      </ul>
      <div className="ov-add">
        <button className="btn sm" onClick={() => call("add", { kind: "text", text: "Your text", y: 0.86, start: 0, end: 4 })}>+ Text</button>
        <button className="btn sm" onClick={addImage}>+ Picture or sign…</button>
        <button className="btn sm" onClick={() => setCard(true)}>Intro title card…</button>
      </div>
      {card && <IntroCardSheet dir={dir} onClose={() => setCard(false)} onChanged={() => load().catch(() => {})} />}
    </details>
  );
}
