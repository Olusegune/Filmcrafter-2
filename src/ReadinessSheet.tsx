import { useCallback, useEffect, useState } from "react";
import { api, errorText, type Readiness, type ReadinessItem } from "./api";
import * as I from "./icons";
import { Sheet } from "./Sheet";
import { SoundPlan } from "./SoundPlan";
import { goLabel, levelWords } from "./readinessWords";

/**
 * "Is this film ready?": everything still open, in the order a film is made, each with the reason and a button that takes you there. A shot that is too short for its line can be lengthened
 * here in one click (and put back). It only reads: nothing is made or bought, and a step that costs money sends you to the place where its price is shown first.
 */
export function ReadinessSheet({ dir, onClose, onGo, onChanged }: { dir: string; onClose: () => void; onGo: (item: ReadinessItem) => void; onChanged?: () => void }) {
  const [r, setR] = useState<Readiness | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [undo, setUndo] = useState<{ shot: string; was: number } | null>(null);
  const [plan, setPlan] = useState(false);
  const load = useCallback(() => api.filmReadiness(dir).then(setR).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => { void load(); }, [load]);
  const setSeconds = async (shot: string, seconds: number) => {
    setBusy(true); setErr("");
    try { await api.shots("set", dir, { id: shot, patch: { generation: { duration: seconds } } }); await load(); onChanged?.(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const lengthen = async (it: ReadinessItem) => { if (!it.fix) return; await setSeconds(it.fix.shot, it.fix.seconds); setUndo({ shot: it.fix.shot, was: it.fix.was }); };
  return (
    <Sheet label="Is this film ready?" className="rd" onDismiss={onClose}>
      <div className="vs-head"><h2>Is this film ready?</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
      {err && <p className="why" role="alert">{err}</p>}
      {!r && !err && <p className="why">Looking over the film…</p>}
      {undo && <p className="why rd-undo" role="status">{undo.shot} was lengthened. <button className="link" disabled={busy} onClick={async () => { await setSeconds(undo.shot, undo.was); setUndo(null); }}>Put it back to {undo.was} s</button></p>}
      {r && <>
        <p className="rd-lead">{r.ready ? "Yes: nothing is left to do before you export." : <>{r.counts.fix > 0 && <><b>{r.counts.fix}</b> to fix, </>}<b>{r.counts.look}</b> worth doing, <b>{r.counts.note}</b> to know.</>}</p>
        <ol className="rd-list">
          {r.items.map((it, i) => (
            <li key={i} className={`rd-item ${it.level}`}>
              <span className="rd-level">{levelWords(it.level)}</span>
              <div className="rd-main"><b>{it.what}</b><p className="why">{it.why}</p></div>
              <div className="rd-acts">
                {it.fix && <button className="btn sm" disabled={busy} onClick={() => lengthen(it)} title={`Sets ${it.fix.shot} to ${it.fix.seconds} s. You can put it back.`}>{it.fix.label}</button>}
                <button className="btn ghost sm" onClick={() => (it.go === "soundplan" ? setPlan(true) : onGo(it))}>{goLabel(it.go)}</button>
              </div>
            </li>))}
        </ol>
        {r.unread.length > 0 && <p className="why">Not read this time: {r.unread.join(", ")}.</p>}
        <p className="why">{r.note}</p>
      </>}
      <div className="cv-actions"><button className="btn" onClick={onClose}>Close</button></div>
      {plan && <SoundPlan dir={dir} onClose={() => { setPlan(false); void load(); }} onGo={(id) => { setPlan(false); onGo({ step: "voices", level: "note", what: "", why: "", go: "shots", shot: id, fix: null }); }} />}
    </Sheet>
  );
}
