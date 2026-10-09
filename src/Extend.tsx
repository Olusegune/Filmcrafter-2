import { useEffect, useState } from "react";
import { api, errorText, type Job, type Shot } from "./api";
import { ACTIVE as ACTIVE_STATES } from "./queueMath";
import * as I from "./icons";

export type ExtendInfo = {
  shot: string; can_extend: boolean; reason?: string; advice: string[]; shot_seconds: number; take_seconds?: number; short_seconds?: number; model_longest?: number | null;
  take?: string; source_take?: string; provider?: string; model?: string; suggest_seconds?: number | null; will_cover?: number; estimate_usd?: number | null; lip_synced?: boolean;
};

const secs = (n: number) => `${Math.round(n * 10) / 10} s`;

/** The words for what Extend would do, from the engine's numbers. Pure. */
export function extendSentence(i: ExtendInfo): string {
  if (!i.can_extend || i.take_seconds == null || i.suggest_seconds == null) return "";
  const left = Math.max(0, i.shot_seconds - i.take_seconds - i.suggest_seconds);
  return `This shot is ${secs(i.shot_seconds)} but its take is ${secs(i.take_seconds)}, so the last ${secs(i.short_seconds ?? 0)} just hold the final frame. ` +
    `Extending renders ${secs(i.suggest_seconds)} more, starting from the take's last frame, and joins it on` +
    (left > 0.25 ? `; ${secs(left)} would still be short.` : ", which covers the shot.");
}

/** On the shot's Video tab: when the take is shorter than the shot, render the missing seconds as a continuation and join them. Shows the price first; the old take stays in your video until you swap. */
export function ExtendCard({ dir, shot, jobs, onQueued }: { dir: string; shot: Shot; jobs: Job[]; onQueued: (j: Job[]) => void }) {
  const [info, setInfo] = useState<ExtendInfo | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState("");
  const busy = jobs.some((j) => j.shot_id === shot.id && ACTIVE_STATES.includes(j.state) && j.kind !== "image");
  const sig = jobs.filter((j) => j.shot_id === shot.id).map((j) => j.id + j.state).join();
  useEffect(() => {
    let live = true;
    setErr("");
    api.frames<ExtendInfo>(dir, "extend_info", { shot: shot.id }).then((r) => live && setInfo(r)).catch(() => live && setInfo(null));
    return () => { live = false; };
  }, [dir, shot.id, sig]);
  if (!info || (!info.can_extend && !info.advice.length)) return null;
  const go = async () => {
    setConfirm(false); setErr("");
    try { onQueued(await api.queueRender(dir, [shot.id], info.provider!, info.model!, { _extend_of: info.take, _extend_seconds: info.suggest_seconds }, [])); }
    catch (e) { setErr(errorText(e)); }
  };
  return (
    <div className="extend-card">
      <div className="ex-head"><b>{info.can_extend ? "Extend this take" : "About this shot"}</b></div>
      {info.can_extend && <p className="dim">{extendSentence(info)}</p>}
      {info.advice.map((a) => <p key={a} className="ex-advice"><I.Alert size={13} /> {a}</p>)}
      {info.can_extend && !confirm && <button className="btn small" disabled={busy} onClick={() => setConfirm(true)}>
        {busy ? "Rendering…" : `Extend by ${secs(info.suggest_seconds ?? 0)}…`}</button>}
      {confirm && <div className="sup-confirm" role="alertdialog" aria-label="Confirm extending">
        <span>Render <b>{secs(info.suggest_seconds ?? 0)}</b> more on <b>{info.model?.split("/").slice(-2).join("/")}</b>
          {info.estimate_usd != null ? <>, about <b>${info.estimate_usd.toFixed(2)}</b></> : ", price shown by the provider afterwards"}.
          Your current take stays in the video until you swap the longer one in (Review → New versions, or Takes → Use this one).</span>
        <button className="btn primary small" onClick={go}>Extend</button>
        <button className="btn ghost small" onClick={() => setConfirm(false)}>Cancel</button></div>}
      {err && <div className="error-text" role="alert">{err}</div>}
    </div>
  );
}
