import { useEffect, useState } from "react";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { api, errorText, fmtTime, type EditorPackage, type ExportResult } from "./api";
import { CaptionsPanel } from "./Captions";
import { OverlaysPanel } from "./Overlays";
import * as I from "./icons";
import { EXPORT_FORMATS, formatFor } from "./exportFormats";

const PRESETS = EXPORT_FORMATS;

/** Simple presets. The film's timeline is the clock; every cut lands on its frame. */
export function ExportSheet({ dir, projectAspect, shots, rendered, onClose }: {
  dir: string; projectAspect?: string; shots: number; rendered: number; onClose: () => void;
}) {
  const natural = formatFor(projectAspect);
  const [preset, setPreset] = useState(natural);
  const [progress, setProgress] = useState<{ stage: string; p: number; detail?: string } | null>(null);
  const [result, setResult] = useState<ExportResult | null>(null);
  const [error, setError] = useState("");
  const [pkg, setPkg] = useState<EditorPackage | null>(null);
  const [sending, setSending] = useState("");
  const [sum, setSum] = useState<null | { video: number; still: number; none: number; stale: number; major: number; minor: number }>(null);
  useEffect(() => {   // before exporting: what's in the cut, and what's still open
    Promise.all([api.golden<{ video: string[]; still: string[]; none: string[]; stale: string[] }>(dir, "status"),
                 api.supervisor<{ summary: { major: number; minor: number } }>(dir, "list").catch(() => null)])
      .then(([g, s]) => setSum({ video: g.video.length, still: g.still.length, none: g.none.length, stale: g.stale.length,
                                 major: s?.summary.major ?? 0, minor: s?.summary.minor ?? 0 })).catch(() => {});
  }, [dir]);

  useEffect(() => {
    const un = api.onEngine((e) => {
      if (e.task === "export" && e.stage) setProgress({ stage: e.stage, p: (e.progress as number) ?? 0, detail: e.detail as string });
    });
    return () => { un.then((f) => f()); };
  }, []);

  const toEditor = async (target: "premiere" | "resolve") => {
    if (!result) return;
    setError(""); setSending(target);
    try { const r = await api.editorExport(dir, target, result.path); setPkg(r); await revealItemInDir(r.path).catch(() => {}); }
    catch (e) { setError(errorText(e)); } finally { setSending(""); }
  };
  const run = async () => {
    setPkg(null); setError(""); setResult(null); setProgress({ stage: "starting", p: 0 });
    try { setResult(await api.exportProject(dir, preset)); } catch (e) { setError(errorText(e)); }
    finally { setProgress(null); }
  };

  const draft = rendered < shots;
  return (
    <div className="overlay" onClick={progress ? undefined : onClose}>
      <div className="sheet glass" role="dialog" aria-label="Export" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
          <div>
            <h2>Export</h2>
            <p className="sub">{rendered} of {shots} shots rendered.
              {draft ? " Shots without a take appear as storyboard cards, so this will be a draft cut." : " Ready for a final export."}</p>
          </div>
          {!progress && <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close /></button>}
        </div>

        {sum && !result && <div className={`exp-sum ${sum.major || sum.none || sum.stale ? "warn" : "ok"}`}>
          <div className="exp-counts"><span><b>{sum.video}</b> video</span><span><b>{sum.still}</b> moving stills</span>
            <span><b>{sum.none}</b> storyboard cards</span></div>
          {(sum.major > 0 || sum.stale > 0) ? <div>{sum.major > 0 && <>{sum.major} serious finding{sum.major === 1 ? "" : "s"} still open. </>}
            {sum.stale > 0 && <>{sum.stale} video{sum.stale === 1 ? " was" : "s were"} made from an older keyframe. </>}
            <button className="link" onClick={() => { onClose(); window.dispatchEvent(new Event("pf-open-supervisor")); }}>Review in the Supervisor</button> or export as it is.</div>
            : <div>Nothing serious is open{sum.minor ? ` (${sum.minor} minor notes)` : ""}.</div>}
        </div>}
        <div className="preset-grid" role="radiogroup" aria-label="Format">
          {PRESETS.map((p) => (
            <button key={p.id} role="radio" aria-checked={preset === p.id} className={`preset ${preset === p.id ? "on" : ""}`}
                    onClick={() => setPreset(p.id)} disabled={!!progress}>
              <span className="frame" style={{ aspectRatio: String(p.ar) }} />
              <span className="pl">{p.label}{p.id === natural && <span className="rec"> · project</span>}</span>
              <span className="ps">{p.sub}</span>
            </button>
          ))}
        </div>
        {!progress && <CaptionsPanel dir={dir} />}
        {!progress && <OverlaysPanel dir={dir} />}
        {preset !== natural && <p className="dim" style={{ marginTop: 10 }}>Shots are framed for {projectAspect ?? "16:9"}; this format crops them to fill the frame.</p>}

        {progress && (
          <div style={{ marginTop: 18 }}>
            <div className="dim">{progress.stage === "assembling" ? `Assembling ${progress.detail ?? ""}` : cap(progress.stage)}</div>
            <div className="progress"><i style={{ width: `${Math.round(progress.p * 100)}%` }} /></div>
          </div>
        )}
        {result && (
          <div className="export-done">
            <div className="status-ok"><I.Check size={16} /> Exported {result.draft ? "draft " : ""}— {result.width}×{result.height}, {result.fps} fps, {fmtTime(result.duration)}</div>
            <div className="dim" style={{ wordBreak: "break-all", marginTop: 6 }}>{result.path}</div>
            {result.loudness && <div className="dim" title="Integrated loudness of the whole film in LUFS, its loudness range in LU, and its highest peak">
              Loudness {result.loudness.lufs} LUFS{result.loudness.true_peak_db != null ? `, peak ${result.loudness.true_peak_db} dB` : ""}.
              {result.loudness.lufs > -11 ? " Louder than most streaming sites play (about -14 LUFS), so they will turn it down." : result.loudness.lufs < -20 ? " Quiet next to most films (streaming sites play at about -14 LUFS)." : " Close to what streaming sites play (about -14 LUFS)."}</div>}
            {!!result.captions && <div className="dim">Captions drawn{result.subtitles ? <>; subtitles file written: <span style={{ wordBreak: "break-all" }}>{result.subtitles}</span></> : "."}</div>}
            {!!result.overlays && <div className="dim">{result.overlays} on-screen text{result.overlays === 1 ? "" : "s"} drawn.</div>}
            {result.overlay_error && <div className="error-text">On-screen text wasn't added: {result.overlay_error} The film itself is fine.</div>}
            <div className="editor-send">
              <span className="dim">Edit it further:</span>
              <button className="btn sm" disabled={!!sending} onClick={() => toEditor("premiere")} title="Writes one import file: a bin with this film and its shots as timelines">
                {sending === "premiere" ? "Preparing…" : "Send to Premiere Pro"}</button>
              <button className="btn sm" disabled={!!sending} onClick={() => toEditor("resolve")} title="Writes one import file: a media pool with this film and its shots as timelines">
                {sending === "resolve" ? "Preparing…" : "Send to DaVinci Resolve"}</button>
            </div>
            {pkg && <div className="editor-done">
              <div className="status-ok"><I.Check size={16} /> Import file for {pkg.app} is ready</div>
              <div className="dim">{pkg.steps}</div>
              <div className="dim">{pkg.sequences === 2 ? `Two timelines: the finished film, and ${pkg.shot_clips} shot${pkg.shot_clips === 1 ? "" : "s"} laid out to re-edit` : "One timeline: the finished film"}.
                {pkg.missing.length > 0 ? ` ${pkg.missing.length} shot${pkg.missing.length === 1 ? " has" : "s have"} no take yet and ${pkg.missing.length === 1 ? "is" : "are"} left out of the shots timeline.` : ""}
                {" "}The files are used where they are: keep them in place, or relink in {pkg.app} if you move them.</div>
              <button className="link" onClick={() => revealItemInDir(pkg.path)}>Show the import file</button>
            </div>}
          </div>
        )}
        {error && <div className="error-text">{error}</div>}

        <div className="sheet-actions">
          {result && <button className="btn" onClick={() => revealItemInDir(result.path)}>Show in folder</button>}
          <button className="btn primary" onClick={run} disabled={!!progress}>{progress ? "Exporting…" : result ? "Export again" : "Export video"}</button>
        </div>
      </div>
    </div>
  );
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
