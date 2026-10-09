import { useEffect, useState } from "react";
import { api, errorText, type EngineEvent, type UpscaleRun, type UpscaleTool } from "./api";
import { ask } from "./ask";
import * as I from "./icons";

export type UpscaleRequest = { kind: "keyframe" | "take"; shot: string; job?: string };
export const openUpscale = (req: UpscaleRequest) => window.dispatchEvent(new CustomEvent("pf-open-upscale", { detail: req }));

/** What each choice means, in words: the tool, how much bigger, what it costs. Pure display. */
export function UpscaleChoices({ tools, tool, factor, busy, onTool, onFactor }: {
  tools: UpscaleTool[]; tool: string; factor: number; busy: boolean; onTool: (id: string) => void; onFactor: (n: number) => void;
}) {
  const t = tools.find((x) => x.id === tool);
  return (
    <div className="up-choices">
      <div role="radiogroup" aria-label="Upscaler" className="up-tools">
        {tools.map((x) => (
          <button key={x.id} role="radio" aria-checked={x.id === tool} disabled={busy || !x.ready} className={`up-tool ${x.id === tool ? "on" : ""}`} onClick={() => onTool(x.id)}
                  title={x.ready ? x.blurb : `Add your ${x.provider === "kie" ? "Kie.ai" : "fal.ai"} key in Settings to use this`}>
            <b>{x.label}</b><span>{x.ready ? x.blurb : `needs a ${x.provider === "kie" ? "Kie.ai" : "fal.ai"} key`}</span></button>))}
      </div>
      <div role="radiogroup" aria-label="How much bigger" className="up-factors">
        {(t?.factors ?? [2, 4]).map((n) => <button key={n} role="radio" aria-checked={n === factor} disabled={busy} className={`btn small ${n === factor ? "primary" : "ghost"}`} onClick={() => onFactor(n)}>{n}× bigger</button>)}
        <span className="dim">Width and height each ×{factor}: {factor * factor}× the pixels.</span>
      </div>
    </div>
  );
}

/** Upscale a shot's approved keyframe, or one of its finished takes. The result replaces it for the film, the original is kept, and Undo brings it back. */
export function UpscaleSheet({ dir, req, onClose, onChanged }: { dir: string; req: UpscaleRequest; onClose: () => void; onChanged: () => void }) {
  const media = req.kind === "keyframe" ? "image" : "video";
  const [tools, setTools] = useState<UpscaleTool[]>([]);
  const [tool, setTool] = useState("");
  const [factor, setFactor] = useState(2);
  const [busy, setBusy] = useState("");
  const [done, setDone] = useState<UpscaleRun | null>(null);
  const [past, setPast] = useState<UpscaleRun[]>([]);
  const [err, setErr] = useState("");
  const load = () => api.upscale<{ runs: UpscaleRun[] }>(dir, "status", { shot: req.shot }).then((r) => setPast(r.runs.filter((x) => x.kind === req.kind && x.state === "ready"))).catch(() => {});
  useEffect(() => {
    api.upscale<{ tools: UpscaleTool[] }>(dir, "tools", { media }).then((r) => { setTools(r.tools); setTool((r.tools.find((x) => x.ready) ?? r.tools[0])?.id ?? ""); }).catch((e) => setErr(errorText(e)));
    load();
    const un = api.onEngine((e: EngineEvent) => { if (e.task === "upscale" && e.stage) setBusy(e.stage.charAt(0).toUpperCase() + e.stage.slice(1) + "…"); });
    return () => { un.then((f) => f()); };
  }, [dir, req.shot, req.job]);   // eslint-disable-line react-hooks/exhaustive-deps
  const chosen = tools.find((x) => x.id === tool);
  const go = async () => {
    if (!chosen) return;
    const what = req.kind === "keyframe" ? `${req.shot}'s approved keyframe` : `this take of ${req.shot}`;
    if (!await ask(`Upscale ${what} ${factor}× with ${chosen.label}? ${chosen.provider === "kie" ? "Kie.ai bills it in credits" : "fal.ai bills it"}; the price is shown on your provider's dashboard, not here. The original is kept and you can undo it.`, { ok: "Upscale" })) return;
    setBusy("Sending…"); setErr(""); setDone(null);
    try {
      const r = await api.upscale<UpscaleRun>(dir, "run", { tool, kind: req.kind, shot: req.shot, job: req.job, factor });
      if (r.state === "failed") setErr(r.error ?? "The upscale failed."); else { setDone(r); onChanged(); }
      load();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const undo = async () => {
    setBusy("Undoing…"); setErr("");
    try { await api.upscale(dir, "revert", { shot: req.shot, kind: req.kind }); setDone(null); onChanged(); await load(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  return (
    <div className="overlay" onClick={() => !busy && onClose()}>
      <div className="sheet glass up-sheet" role="dialog" aria-label="Upscale" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2><I.Sparkle size={18} /> Upscale {req.kind === "keyframe" ? "the keyframe" : "this take"} of {req.shot}</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close" disabled={!!busy}><I.Close size={18} /></button></div>
        <p className="sub">Sharper and larger: Topaz and Recraft on Kie.ai, and more on fal.ai. {req.kind === "keyframe"
          ? "The upscaled picture becomes the keyframe for this shot (takes already made from it stay as they are)."
          : "The upscaled video is added as a new take of this shot and used in the film; the original take is kept."}</p>
        {tools.length === 0 && !err ? <p className="dim">Looking for upscalers…</p> : <UpscaleChoices tools={tools} tool={tool} factor={factor} busy={!!busy} onTool={setTool} onFactor={setFactor} />}
        {tools.length > 0 && !tools.some((x) => x.ready) && <p className="mp-warn" role="note">No upscaler is ready: add your Kie.ai or fal.ai key in Settings.</p>}
        <div className="wiz-row" style={{ marginTop: 12 }}>
          <button className="btn primary" onClick={go} disabled={!!busy || !chosen?.ready}>{busy || `Upscale ${factor}×`}</button>
          {past.length > 0 && <button className="btn ghost" onClick={undo} disabled={!!busy} title="Go back to the picture or take that was upscaled">Undo the last upscale</button>}
          <span className="dim" style={{ fontSize: 12 }}>Magnific has its own account and API and is not connected; Topaz and Clarity cover the same ground.</span>
        </div>
        {done && <div className="note ok" role="status"><I.Check size={14} /> Done. {req.kind === "keyframe" ? "This is now the keyframe for the shot." : "The upscaled take is now the one in the film."}</div>}
        {err && <div className="error-text" role="alert" style={{ marginTop: 8 }}>{err}</div>}
      </div>
    </div>
  );
}
