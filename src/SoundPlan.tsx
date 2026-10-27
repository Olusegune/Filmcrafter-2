import { useCallback, useEffect, useState } from "react";
import { api, errorText, type SoundPlan as Plan } from "./api";
import * as I from "./icons";
import { Sheet } from "./Sheet";
import { DialogueTiming } from "./DialogueTiming";
import { creditsWords, routeOrder, routeWords, settingWords, videoCostWords } from "./soundPlanWords";

/**
 * "Sound plan": for every shot with dialogue, how its voice will be made and why, in one list. It reads the film as it is and spends nothing. The only thing it can change is a shot's own
 * "someone on screen speaks this" setting, and only when you press a button: Apply marks the voice-over shots "nobody on screen speaks" (so they are made silent and no lip-sync is asked for).
 */
export function SoundPlan({ dir, onClose, onGo }: { dir: string; onClose: () => void; onGo: (shot: string) => void }) {
  const [r, setR] = useState<Plan | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [tier, setTier] = useState<"draft" | "final">("draft");
  const [msg, setMsg] = useState("");
  const [view, setView] = useState<"plan" | "timing">("plan");
  const load = useCallback(() => api.filmAudioPlan("report", dir, { tier }).then(setR).catch((e) => setErr(errorText(e))), [dir, tier]);
  useEffect(() => { load(); }, [load]);
  const run = async (action: "apply" | "set", data: Record<string, unknown> = {}) => {
    setBusy(true); setErr(""); setMsg("");
    try {
      const x = await api.filmAudioPlan(action, dir, { ...data, tier });
      setR(x);
      if (action === "apply") setMsg(x.changed?.length ? `${x.changed.length} voice-over shot${x.changed.length === 1 ? "" : "s"} marked: nobody on screen speaks.` : "Nothing needed changing.");
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const rows = r ? [...r.shots].sort((a, b) => routeOrder(a.route) - routeOrder(b.route)) : [];
  const toApply = r ? r.shots.filter((s) => s.route === "voice_over" && s.setting === "auto").length : 0;
  return (
    <Sheet label="Sound plan" className="sp-plan" onDismiss={onClose}>
      <div className="vs-head"><h2>Sound plan</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
      {err && <p className="why" role="alert">{err}</p>}
      {!r && !err && <p className="why">Reading the film…</p>}
      {r && <>
        <p className="sp-lead">
          {r.model_known ? <>The video model is <b>{r.model}</b>, which {r.model_takes_recording ? "can be given a recording to follow" : "cannot be given a recording"}{r.model_makes_sound ? " and can make its own sound" : ""}.</> : <>The video model is not chosen yet, so the plan assumes recordings are laid over the picture at export.</>}
          {" "}{r.lines_to_speak ? <><b>{r.lines_to_speak}</b> line{r.lines_to_speak === 1 ? "" : "s"} still need a voice (speaking them with your voices would use {creditsWords(r.tts_credits, r.tts_unpriced)}).</> : "Every line has its voice."}
        </p>
        {videoCostWords(r.video_cost) && <p className="why sp-cost">{videoCostWords(r.video_cost)}</p>}
        <div className="sp-tier" role="group" aria-label="How many tries to allow for">
          <span className="dim">Tries to allow for</span>
          <button className={`btn ghost sm ${tier === "draft" ? "on" : ""}`} aria-pressed={tier === "draft"} onClick={() => setTier("draft")}>Draft</button>
          <button className={`btn ghost sm ${tier === "final" ? "on" : ""}`} aria-pressed={tier === "final"} onClick={() => setTier("final")}>Final</button>
          <span className="dim">about {r.tries} per shot ({Math.round(r.keep_rate * 100)}% kept)</span>
        </div>
        <div className="sp-tier" role="tablist" aria-label="What to show">
          <button role="tab" aria-selected={view === "plan"} className={`btn ghost sm ${view === "plan" ? "on" : ""}`} onClick={() => setView("plan")}>How each voice is made</button>
          <button role="tab" aria-selected={view === "timing"} className={`btn ghost sm ${view === "timing" ? "on" : ""}`} onClick={() => setView("timing")}>When each voice falls</button>
        </div>
        {msg && <p className="why" role="status">{msg}</p>}
        {view === "timing" ? <DialogueTiming dir={dir} shots={r.shots} onGo={onGo} /> : <ul className="sp-list">
          {rows.map((s) => (
            <li key={s.shot} className={`sp-item ${s.route}`}>
              <span className="sp-route">{routeWords(s.route)}</span>
              <div className="sp-main">
                <b>{s.shot} <span className="dim">{s.title}</span></b>
                <p className="why">{s.why}</p>
                {s.lines.length > 0 && <p className="why sp-lines">{s.lines.map((l, i) => <span key={i} className={l.has_voice ? "" : "sp-missing"}>{l.speaker}{l.voice_over ? " (V.O.)" : ""}: {l.line}{" "}</span>)}</p>}
                {s.warnings.map((w, i) => <p key={i} className="why sp-warn">{w}</p>)}
                {s.route !== "none" && (
                  <label className="sp-set">On-screen speaking:{" "}
                    <select value={s.setting} disabled={busy} onChange={(e) => run("set", { shot: s.shot, value: e.target.value })} aria-label={`Who speaks on screen in ${s.shot}`}>
                      {["auto", "on", "off"].map((v) => <option key={v} value={v}>{settingWords(v)}</option>)}
                    </select>
                    {s.differs && <span className="dim"> (a voice-over is best set to “nobody on screen speaks”)</span>}
                  </label>)}
              </div>
              <button className="btn ghost sm" onClick={() => onGo(s.shot)}>Go to {s.shot}</button>
            </li>))}
        </ul>}
        <p className="why">{r.note}</p>
      </>}
      <div className="cv-actions">
        {r && toApply > 0 && <button className="btn" disabled={busy} onClick={() => run("apply")} title="Marks the voice-over shots as nobody on screen speaks. Shots you set yourself are left alone.">Mark {toApply} voice-over shot{toApply === 1 ? "" : "s"} as silent on screen</button>}
        <button className="btn ghost" onClick={onClose}>Close</button>
      </div>
    </Sheet>
  );
}
