import { useCallback, useEffect, useState } from "react";
import { Sheet } from "./Sheet";
import { api, errorText, type ColourMatchState } from "./api";
import * as I from "./icons";

/**
 * Colour match: shots made by AI can differ in brightness and colour from one to the next. Look at the shots, see which are off, and have the export nudge them towards the
 * typical shot (or one you choose). The takes are never changed; the nudge happens only when the film is put together, and it can be switched off at any time. Free and local.
 */
export function ColourMatchSheet({ dir, onClose }: { dir: string; onClose: () => void }) {
  const [st, setSt] = useState<ColourMatchState | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [strength, setStrength] = useState(0.7);
  const [all, setAll] = useState(false);               // by default only the shots that stand out are listed
  const load = useCallback(() => api.colourMatch(dir, "state").then((s) => { setSt(s); setStrength(s.strength); }).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => { load(); }, [load]);

  const run = async (what: string, action: "analyze" | "set" | "clear", data: Record<string, unknown> = {}) => {
    setBusy(what); setErr("");
    try { const s = await api.colourMatch(dir, action, data); setSt(s); setStrength(s.strength); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const looked = !!st?.analysed;
  return (
    <Sheet label="Colour match" className="colour-match" onDismiss={onClose}>
        <div className="vs-head"><h2>Colour match</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">Shots can differ in brightness and colour from one to the next. This looks at the take each shot uses and, when you turn it on, nudges the shots that stand out towards the typical shot when the
          film is put together. Your takes are never changed. Free: nothing is sent anywhere.</p>
        <div className="if-row">
          <button className="btn primary" disabled={!!busy} onClick={() => run("look", "analyze", { strength })}>{busy === "look" ? "Looking…" : looked ? "Look again" : "Look at the shots"}</button>
          {looked && <label className="ly-check"><input type="checkbox" checked={st!.enabled} disabled={!!busy} onChange={(e) => run("on", "set", { enabled: e.target.checked })} /> Use it when exporting ({st!.adjusted} shot{st!.adjusted === 1 ? "" : "s"} nudged)</label>}
          {looked && <button className="btn ghost small" disabled={!!busy} onClick={() => run("clear", "clear")}>Clear</button>}</div>
        {looked && <div className="if-row">
          <label className="field cm-strength"><span>How much to nudge ({Math.round(strength * 100)}%)</span>
            <input type="range" min={0.1} max={1} step={0.05} value={strength} onChange={(e) => setStrength(Number(e.target.value))} onPointerUp={() => run("strength", "set", { strength })} onKeyUp={() => run("strength", "set", { strength })} /></label>
          <label className="field"><span>Match to</span>
            <select className="text-input" value={st!.reference ?? ""} onChange={(e) => run("ref", "set", { reference: e.target.value })}>
              <option value="">The typical shot</option>{st!.rows.map((r) => <option key={r.shot} value={r.shot}>{r.shot}</option>)}</select></label></div>}
        {err && <p className="error-text" role="alert">{err}</p>}
        {looked && !st!.rows.some((r) => r.adjusted) && <p className="cm-ok">Your shots already match well. Nothing needs nudging.</p>}
        {looked && <ul className="cm-list">
          {st!.rows.filter((r) => all || r.adjusted || r.is_reference).map((r) => (
            <li key={r.shot} className={r.adjusted ? "off" : ""}>
              <span className="num">{r.shot}</span>
              <span className="cm-bar"><i style={{ width: `${Math.min(100, r.distance * 250)}%` }} /></span>
              <span className="dim">{r.is_reference ? "reference" : r.adjusted ? `${r.bright > 0 ? "brighter" : "darker"} than the typical shot: nudged` : "close enough"}</span>
            </li>))}
        </ul>}
        {looked && st!.rows.some((r) => !r.adjusted && !r.is_reference) && <button className="link cm-more" onClick={() => setAll((v) => !v)}>{all ? "Show only the shots that stand out" : `Show all ${st!.rows.length} shots`}</button>}
        {looked && <p className="dim">Check the result with <b>Preview</b> under the player, or an export. Turn it off to see the film as the takes are.</p>}
    </Sheet>
  );
}
