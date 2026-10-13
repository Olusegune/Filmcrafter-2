import { useState } from "react";
import { api, errorText, type ExportResult } from "./api";
import * as I from "./icons";

/**
 * A quick look at part of the film: from the playhead for a few seconds, at small size, with its layers, captions and sound. Free (nothing is sent anywhere)
 * and quick (small, and only that part is put together). Plays here; the file is kept under exports/previews in the project.
 */
export function PreviewSheet({ dir, from, duration, onClose }: { dir: string; from: number; duration: number; onClose: () => void }) {
  const [length, setLength] = useState(10);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [made, setMade] = useState<ExportResult | null>(null);
  const start = Math.max(0, Math.min(from, Math.max(0, duration - 1)));
  const end = Math.min(duration, start + length);

  const go = async () => {
    setBusy(true); setErr(""); setMade(null);
    try { setMade(await api.exportPreview(dir, start, end)); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass preview-sheet" role="dialog" aria-label="Preview" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Preview</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">A small, quick version of {start.toFixed(1)} s to {end.toFixed(1)} s with its layers, captions and sound. Free: nothing is sent anywhere. It shows the shots as they are now (slates where nothing is rendered).</p>
        <div className="if-row">
          <label className="field"><span>Length</span>
            <select className="text-input" value={length} onChange={(e) => setLength(Number(e.target.value))}>{[5, 10, 20, 30].map((n) => <option key={n} value={n}>{n} seconds</option>)}</select></label>
          <button className="btn primary" disabled={busy} onClick={go}><I.Play size={14} /> {busy ? "Making the preview…" : made ? "Make it again" : "Make the preview"}</button></div>
        {err && <p className="error-text" role="alert">{err}</p>}
        {made?.overlay_error && <p className="error-text">The layers were not drawn: {made.overlay_error}</p>}
        {made && <video className="pv-video" src={api.mediaUrl(made.path)} controls autoPlay playsInline />}
      </div>
    </div>
  );
}
