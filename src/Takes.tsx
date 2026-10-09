import { useEffect, useState } from "react";
import { api, errorText, type Job } from "./api";
import * as I from "./icons";
import { ShotSound } from "./ShotSound";
import { openUpscale } from "./UpscaleSheet";

const isVideo = (p: string) => /\.(mp4|mov|webm|m4v)$/i.test(p);
const modelName = (j: Job) => j.model.split("/").slice(-1)[0];
const when = (t: number) => new Date(t * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

/**
 * Every finished take of a shot, side by side: play any of them and choose the one that goes in the video (and so the timeline).
 * Like the versions strip on the Keyframe tab, but for video.
 */
export function Takes({ dir, shotId, takes, approved, onUse, onLipSync }: { dir: string; shotId: string; takes: Job[]; approved: string | null; onUse: () => void; onLipSync?: (take: Job) => void }) {
  const [sel, setSel] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { setSel(null); setErr(""); }, [shotId]);
  const ordered = [...takes].sort((a, b) => b.created - a.created);
  const shown = ordered.find((j) => j.id === sel) ?? ordered.find((j) => j.id === approved) ?? ordered[0];
  if (!shown || !shown.output) return null;
  const inVideo = shown.id === approved;
  const lipSource = shown.kind === "lipsync" ? takes.find((t) => t.id === shown.source_job && t.kind !== "lipsync") : undefined;   // a lip-synced take is run again from the take it was made from
  const use = async () => {
    setBusy(true); setErr("");
    try { await api.library(dir, "approve", { shot: shotId, job: shown.id }); onUse(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const src = (j: Job) => api.mediaUrl(`${dir}/${j.output}`);
  return (
    <section className="takes-pick" aria-label="Takes of this shot">
      <div className="tk-head"><I.Film size={15} /> <b>Takes</b> <span className="dim">{ordered.length} finished · choose the one for the video</span></div>
      <div className={`tk-player ${inVideo ? "in" : ""}`}>
        {isVideo(shown.output)
          ? <video key={shown.id} src={src(shown)} controls loop playsInline preload="metadata" />
          : <img key={shown.id} src={src(shown)} alt={`Take of ${shotId}`} />}
        {inVideo && <span className="tk-badge"><I.Check size={11} /> In the video</span>}
      </div>
      <div className="tk-meta">
        <span className="num">{modelName(shown)}</span><span className="dim">{when(shown.created)}</span>
        {shown.cost != null && <span className="dim num">{shown.cost} {shown.cost_unit === "credits" ? "credits" : ""}</span>}
        {shown.kind === "lipsync" && <span className="chip">Lip-synced</span>}
      </div>
      {ordered.length > 1 && (
        <div className="tk-strip" role="listbox" aria-label="Takes">
          {ordered.map((j, i) => (
            <button key={j.id} role="option" aria-selected={j.id === shown.id} className={`tk-thumb ${j.id === shown.id ? "sel" : ""}`} onClick={() => setSel(j.id)}
                    title={`${modelName(j)} · take ${ordered.length - i}${j.id === approved ? " (in the video)" : ""}`}>
              {j.output && isVideo(j.output) ? <video src={`${src(j)}#t=0.3`} muted preload="metadata" playsInline /> : <img src={src(j)} alt="" />}
              <span className="tk-n">{ordered.length - i}</span>
              {j.id === approved && <i className="tk-dot" />}
            </button>))}
        </div>)}
      <div className="tk-actions">
        {inVideo ? <span className="tk-using"><I.Check size={14} /> This take is in the video and on the timeline.</span>
          : <button className="btn primary" onClick={use} disabled={busy}><I.Check size={14} /> Use this take in the video</button>}
        {onLipSync && (shown.kind !== "lipsync" || lipSource) &&
          <button className="btn" onClick={() => onLipSync(lipSource ?? shown)} title="Re-sync the mouth to the isolated vocal under this shot (priced by the second; you confirm first)">
            <I.Wave size={14} /> {lipSource ? "Lip-sync again from the original take" : "Lip-sync this take"}</button>}
        {shown.state === "ready" && shown.output && <button className="btn" onClick={() => openUpscale({ kind: "take", shot: shotId, job: shown.id })} title="Make this take sharper and larger (Topaz video)"><I.Sparkle size={14} /> Upscale…</button>}
        {onLipSync && shown.kind === "lipsync" && !lipSource && <span className="dim">This take is already lip-synced; its original take is gone.</span>}
      </div>
      <ShotSound dir={dir} shotId={shotId} />
      {err && <p className="error-text">{err}</p>}
    </section>
  );
}
