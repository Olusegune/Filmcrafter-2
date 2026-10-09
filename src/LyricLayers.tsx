import { useEffect, useState } from "react";
import { api, errorText, type LayerStyle, type Overlay } from "./api";
import * as I from "./icons";

/**
 * Lyrics as layers: one text layer for every timed lyric line, each on screen for its line, all in one group. Make them again to replace the group, or remove
 * the group. They are ordinary layers afterwards. They look like the layer you have selected, a saved style, or the choices here.
 */
export function LyricLayersSheet({ dir, moves, selected, styles, hasGroup, onClose, onChanged }: {
  dir: string; moves: [string, string][]; selected: Overlay | null; styles: LayerStyle[]; hasGroup: boolean; onClose: () => void; onChanged: () => void;
}) {
  const [anim, setAnim] = useState("typewriter");
  const [position, setPosition] = useState("bottom");
  const [size, setSize] = useState(0.07);
  const [color, setColor] = useState("#ffffff");
  const [upper, setUpper] = useState(false);
  const [look, setLook] = useState<"here" | "layer" | "style">("here");
  const [style, setStyle] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  useEffect(() => { if (look === "style" && !style && styles[0]) setStyle(styles[0].name); }, [look, style, styles]);

  const make = async () => {
    setBusy("make"); setErr(""); setNote("");
    try {
      const spec: Record<string, unknown> = { position, upper };
      if (look === "layer" && selected) spec.from_layer = selected.id;
      else if (look === "style" && style) spec.style = style;
      else Object.assign(spec, { anim, size, color });
      const r = await api.layerKit<{ made: number; captions_on: boolean }>(dir, "lyrics", spec);
      setNote(`Made ${r.made} layers, one for each lyric line.${r.captions_on ? " Lyric captions are also on (Export > Lyric captions): turn them off if you do not want the words twice." : ""}`);
      window.dispatchEvent(new Event("pf-overlays-changed")); onChanged();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const remove = async () => {
    setBusy("remove"); setErr(""); setNote("");
    try { const r = await api.layerKit<{ removed: number }>(dir, "lyrics_remove"); setNote(`Removed ${r.removed} lyric layers.`); window.dispatchEvent(new Event("pf-overlays-changed")); onChanged(); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass lyric-layers" role="dialog" aria-label="Lyrics as layers" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Lyrics as layers</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">One text layer for every timed lyric line, each on screen for its line. Free: drawn when you export. They are ordinary layers afterwards, so you can restyle, move or delete any of them.</p>
        <fieldset className="ic-back"><legend>How they look</legend>
          <label className="ic-opt"><input type="radio" name="lylook" checked={look === "here"} onChange={() => setLook("here")} /> Choose here</label>
          <label className="ic-opt"><input type="radio" name="lylook" disabled={!selected || selected.kind !== "text"} checked={look === "layer"} onChange={() => setLook("layer")} />
            Like the selected layer{selected?.kind === "text" ? ` (${selected.name || selected.text.slice(0, 24)})` : " (select a text layer first)"}</label>
          <label className="ic-opt"><input type="radio" name="lylook" disabled={!styles.length} checked={look === "style"} onChange={() => setLook("style")} /> A saved style</label>
          {look === "style" && <select className="text-input" value={style} onChange={(e) => setStyle(e.target.value)}>{styles.map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}</select>}
        </fieldset>
        {look === "here" && <div className="ly-two">
          <label className="field"><span>Movement</span><select className="text-input" value={anim} onChange={(e) => setAnim(e.target.value)}>{moves.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></label>
          <label className="field"><span>Colour</span><input type="color" value={color} onChange={(e) => setColor(e.target.value)} /></label>
          <label className="field"><span>Size</span><input type="range" min={0.03} max={0.15} step={0.005} value={size} onChange={(e) => setSize(Number(e.target.value))} /></label></div>}
        <div className="ly-two">
          <label className="field"><span>Where</span><select className="text-input" value={position} onChange={(e) => setPosition(e.target.value)}>
            <option value="top">Top</option><option value="middle">Middle</option><option value="bottom">Bottom</option></select></label>
          <label className="ly-check"><input type="checkbox" checked={upper} onChange={(e) => setUpper(e.target.checked)} /> Capital letters</label></div>
        {err && <p className="error-text" role="alert">{err}</p>}
        {note && <p className="dim" role="status">{note}</p>}
        <div className="if-actions">
          {hasGroup && <button className="btn ghost" disabled={!!busy} onClick={remove}>Remove the lyric layers</button>}
          <div style={{ flex: 1 }} />
          <button className="btn ghost" onClick={onClose}>Close</button>
          <button className="btn primary" disabled={!!busy} onClick={make}>{busy === "make" ? "Making…" : hasGroup ? "Make them again" : "Make the layers"}</button></div>
      </div>
    </div>
  );
}
