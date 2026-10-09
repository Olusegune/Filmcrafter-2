import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type Choreography, type DanceCheck, type EngineEvent, type LoadedProject } from "./api";
import * as I from "./icons";
import { ask } from "./ask";

/** The dance-ready check: which dance shots can really be danced in. Free, on this computer. */
export function DanceReport({ report, onSeek }: { report: DanceCheck; onSeek?: (t: number) => void }) {
  const bad = report.shots.filter((r) => r.issues.length);
  return (
    <div className="dance-report" role="region" aria-label="Dance-ready check">
      <p><b>{report.clean} of {report.dance_shots}</b> dance shot{report.dance_shots === 1 ? "" : "s"} {report.clean === report.dance_shots && report.dance_shots > 0 ? "are ready to be danced in." : "ready; the rest need a change:"}</p>
      {report.note && <p className="dim">{report.note}</p>}
      <ul>
        {bad.map((r) => (
          <li key={r.shot}><button className="chip num" onClick={() => onSeek?.(r.start)} title="Go to this shot">{r.shot}</button>
            <div>{r.issues.map((i) => <div key={i.kind}>{i.text} <span className="dim">{i.fix}</span></div>)}</div></li>))}
      </ul>
    </div>);
}

export const openChoreoSheet = () => window.dispatchEvent(new Event("pf-open-choreo"));

const MODES: { id: NonNullable<Choreography["mode"]>; label: string }[] = [
  { id: "ai", label: "FilmCrafter designs it" }, { id: "upload", label: "From my dance sheet" },
  { id: "written", label: "From my notes" }, { id: "style", label: "Style only" }, { id: "none", label: "No dancing" },
];

/**
 * Choreography Engine in the Studio: the setup (sheet, notes, style) and the designed, shot-by-shot plan.
 * The plan's pose goes into keyframe prompts and its motion into video prompts for the shots marked dancing.
 */
export function ChoreoSheet({ project, onClose, onChanged }: { project: LoadedProject; onClose: () => void; onChanged: () => void }) {
  const [c, setC] = useState<Choreography | null>(null);
  const [styles, setStyles] = useState<string[]>([]);
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [dance, setDance] = useState<DanceCheck | null>(null);
  const plan = project.directed ?? project.production;
  const shotsById = new Map((plan?.scenes ?? []).flatMap((s) => s.shots).map((s) => [s.id, s]));
  useEffect(() => {
    api.getChoreography(project.dir).then(setC).catch((e) => setError(errorText(e)));
    api.choreographyStyles().then((s) => setStyles(s.styles)).catch(() => {});
    const un = api.onEngine((e: EngineEvent) => { if (e.task === "choreo" && e.stage) setBusy(e.stage.charAt(0).toUpperCase() + e.stage.slice(1) + "…"); });
    return () => { un.then((f) => f()); };
  }, [project.dir]);
  if (!c) return null;

  const save = async (patch: Partial<Choreography>) => {
    const next = { ...c, ...patch };
    setC(next);
    try { setC(await api.setChoreography(project.dir, { ...next, mode: next.mode ?? "none" })); } catch (e) { setError(errorText(e)); }
  };
  const addSheet = async () => {
    const f = await open({ multiple: true, filters: [{ name: "Dance sheet or reference", extensions: ["pdf", "txt", "md", "mp4", "mov", "png", "jpg", "jpeg", "webp"] }] });
    if (!f) return;
    const files = [...c.files];
    for (const p of Array.isArray(f) ? f : [f]) {
      try { files.push((await api.importReference(project.dir, p)).ref.replace(/^project:/, "")); } catch (e) { setError(errorText(e)); }
    }
    save({ files, mode: "upload" });
  };
  const design = async () => {
    if (!(await api.aiReady())) { setError("Add your OpenAI key in Settings, or choose a local model (Ollama or LM Studio): the Choreography Engine needs an AI to design the movement."); return; }
    setBusy("Choreographing…"); setError("");
    try { const p = await api.designChoreography(project.dir, brief); setC({ ...c, plan: p }); onChanged(); }
    catch (e) { setError(errorText(e)); } finally { setBusy(""); }
  };
  const clear = async () => {
    if (!await ask("Remove the designed choreography? Shots go back to acting-led unless your notes or style apply.")) return;
    try { setC(await api.clearChoreography(project.dir)); onChanged(); } catch (e) { setError(errorText(e)); }
  };
  const p = c.plan;
  const dancingShots = p ? Object.entries(p.shots) : [];

  return (
    <div className="overlay" onClick={() => !busy && onClose()}>
      <div className="sheet glass choreo-sheet" role="dialog" aria-label="Choreography" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Choreography</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close" disabled={!!busy}><I.Close size={18} /></button></div>
        <p className="sub">For characters who dance. The Choreography Engine designs movement from the song's tempo, sections and energy,
          your lyrics and script, and your dance sheet or notes, then places it shot by shot: a pose for each keyframe, the motion for each video.</p>

        <div className="wiz-modes" role="radiogroup" aria-label="Source of the movement" style={{ marginBottom: 12 }}>
          {MODES.map((m) => <button key={m.id} role="radio" aria-checked={c.mode === m.id} className={c.mode === m.id ? "on" : ""}
                                    onClick={() => save({ mode: m.id })}>{m.label}</button>)}
        </div>

        {c.mode !== "none" && <div className="choreo-setup">
          <label className="wiz-label" htmlFor="cs-style">Style</label>
          <select id="cs-style" className="text-input" value={c.style ?? ""} onChange={(e) => save({ style: e.target.value || null })}>
            <option value="">Let the song decide</option>{styles.map((s) => <option key={s}>{s}</option>)}
          </select>
          <div className="wiz-row" style={{ marginTop: 10, justifyContent: "space-between" }}>
            <span className="dim">{c.files.length ? `${c.files.length} sheet/reference file${c.files.length > 1 ? "s" : ""}: ${c.files.map((f) => f.split("/").pop()).join(", ")}`
              : "No dance sheet. PDF, TXT or MD sheets are read; videos and images are used as style references."}</span>
            <button className="btn small" onClick={addSheet}><I.Upload size={14} /> Add sheet…</button>
          </div>
          <label className="wiz-label" htmlFor="cs-brief" style={{ marginTop: 10 }}>Anything for this design (optional)</label>
          <input id="cs-brief" className="text-input" value={brief} onChange={(e) => setBrief(e.target.value)}
                 placeholder="e.g. only Amara dances; keep the verses still; big group moment on the last chorus" />
          <div className="wiz-row" style={{ marginTop: 12 }}>
            <button className="btn primary" onClick={design} disabled={!!busy || !plan}>
              {busy || (p ? "Redesign choreography" : "Design choreography")}</button>
            {p && <button className="btn ghost" onClick={clear} disabled={!!busy}>Remove plan</button>}
            <span className="dim" style={{ fontSize: 12 }}>{plan ? "Uses OpenAI (a few cents). Nothing is rendered." : "Plan the shots first."}</span>
          </div>
        </div>}

        {error && <div className="error-text" role="alert" style={{ marginTop: 10 }}>{error}</div>}
        {c.mode !== "none" && <div className="wiz-row" style={{ marginTop: 12 }}>
          <button className="btn small" onClick={async () => { setError(""); try { setDance(await api.dance(project.dir)); } catch (e) { setError(errorText(e)); } }}>Check the dance shots (free)</button>
          <span className="dim" style={{ fontSize: 12 }}>Whole body in frame, long enough for a move, cut on the beat. Nothing is rendered or sent.</span></div>}
        {dance && <DanceReport report={dance} />}

        {p && c.mode !== "none" && <div className="choreo-plan">
          <div className="choreo-concept"><b>{p.source === "sheet" ? "Designed from your sheet and cues" : "Designed from the music and story"}</b> · {p.dancers.join(", ") || "no dancers"} · {Math.round(p.bpm)} BPM
            <p>{p.concept}</p></div>
          <h4>By section</h4>
          <div className="choreo-sections">
            {p.sections.map((s) => (
              <div key={s.section} className="choreo-sec"><div className="wiz-row"><b>{s.section}</b><span className="dim">{s.feel}</span></div>
                <ul>{s.counts.map((k, i) => <li key={i}><span className="num">{k.counts}</span>{k.move}</li>)}</ul></div>
            ))}
          </div>
          <h4>Dancing shots ({dancingShots.length})</h4>
          <div className="choreo-shots">
            {dancingShots.map(([id, m]) => (
              <div key={id} className="choreo-shot"><span className="chip num">{id}</span>
                <div><div><span className="dim">Pose</span> {m.pose}</div><div><span className="dim">Motion</span> {m.motion}</div>
                  <div className="dim" style={{ fontSize: 11.5 }}>{shotsById.get(id)?.framing ?? ""}</div></div></div>
            ))}
            {!dancingShots.length && <p className="dim">No shot dances in this plan: the video stays acting-led.</p>}
          </div>
          <p className="dim" style={{ fontSize: 12 }}>New keyframes and renders of these shots use this movement. Existing takes don't change until you re-render them.
            Video models follow it as direction: style, energy and key moves, not every step exactly.</p>
        </div>}
      </div>
    </div>
  );
}

/** Inspector: what this shot's prompts get from the choreography (nothing when the shot is acting-led). */
export function ShotChoreo({ dir, shotId }: { dir: string; shotId: string }) {
  const [c, setC] = useState<Choreography | null>(null);
  useEffect(() => {
    const load = () => api.getChoreography(dir).then(setC).catch(() => {});
    load();
    window.addEventListener("pf-choreo-changed", load);
    return () => window.removeEventListener("pf-choreo-changed", load);
  }, [dir]);
  const m = c?.plan?.shots?.[shotId];
  if (!m || c?.mode === "none") return null;
  return (
    <div className="insp-section">
      <h4>Choreography</h4>
      <div className="kv"><span className="k">Pose</span><span className="v">{m.pose}</span>
        <span className="k">Motion</span><span className="v">{m.motion}</span></div>
      <button className="link" style={{ fontSize: 12, marginTop: 6 }} onClick={openChoreoSheet}>Edit choreography</button>
    </div>
  );
}
