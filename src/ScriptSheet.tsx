import { useEffect, useState } from "react";
import { Sheet } from "./Sheet";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type LoadedProject } from "./api";
import * as I from "./icons";
import { ask } from "./ask";

/** Opens the script sheet from anywhere in the Studio (Creative Directions, Materials). */
export const openScriptSheet = () => window.dispatchEvent(new Event("pf-open-script"));

/**
 * Add or replace the project's script from the Studio. The screenplay's scenes and shots are placed on the song.
 * A current plan is archived (its takes stay in the project, but no longer attach to the new shots).
 */
export function ScriptSheet({ project, onClose, onDone }: { project: LoadedProject; onClose: () => void; onDone: () => void }) {
  const [tab, setTab] = useState<"paste" | "upload">("paste");
  const [text, setText] = useState("");
  const [file, setFile] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [noScenes, setNoScenes] = useState(false);
  const plan = project.directed ?? project.production;
  const shots = plan?.scenes.reduce((n, s) => n + s.shots.length, 0) ?? 0;
  const takes = (project.jobs ?? []).filter((j) => j.state === "ready" && j.kind !== "image").length;
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [busy, onClose]);

  const choose = async () => {
    const f = await open({ filters: [{ name: "Script", extensions: ["pdf", "txt", "md", "fountain"] }] });
    if (typeof f === "string") { setFile(f); setError(""); setNoScenes(false); }
  };
  const ready = tab === "paste" ? text.trim().length > 20 : !!file;
  const adopt = async () => {
    if (!project.song_map) { setError("FilmCrafter needs to listen to the song first."); return; }
    if (plan && !await ask(`Replace the current plan (${shots} shots${takes ? `, ${takes} rendered takes` : ""}) with this script?\n\n` +
      "The current plan, its takes and keyframes are archived in the project folder, not deleted.")) return;
    setBusy(true); setError(""); setNoScenes(false);
    try {
      await api.adoptScript(project.dir, tab === "paste" ? { text } : { path: file! });
      onDone();
    } catch (e) {
      const msg = errorText(e);
      setError(msg); setNoScenes(/No scenes/.test(msg) && tab === "paste");
    } finally { setBusy(false); }
  };
  const useAsBrief = async () => {
    const ob = project.project.onboarding ?? { stage: "done" as const, done: [], skipped: [] };
    try { await api.setOnboarding(project.dir, { ...ob, concept: "propose", concept_notes: text.trim().slice(0, 2000) }); onDone(); }
    catch (e) { setError(errorText(e)); }
  };

  return (
    <Sheet label="Add a script" className="script-sheet" onDismiss={() => !busy && onClose()}>
        <div className="vs-head"><h2>{project.project.script ? "Replace the script" : "Add a script"}</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close" disabled={busy}><I.Close size={18} /></button></div>
        <p className="sub">Scenes and shots you've written are followed exactly and placed on the song's beats.
          {project.project.script && <> Current script: <b>{project.project.script}</b>.</>}</p>
        <div className="wiz-tabs" role="tablist" style={{ gridTemplateColumns: "1fr 1fr", marginBottom: 12 }}>
          <button role="tab" aria-selected={tab === "paste"} className={tab === "paste" ? "on" : ""} onClick={() => setTab("paste")}><I.Doc size={17} /> Paste Script</button>
          <button role="tab" aria-selected={tab === "upload"} className={tab === "upload" ? "on" : ""} onClick={() => setTab("upload")}><I.Upload size={17} /> Upload File</button>
        </div>
        {tab === "paste" ? (
          <div className="wiz-editor-wrap">
            <textarea className="wiz-editor mono" autoFocus value={text} onChange={(e) => { setText(e.target.value); setNoScenes(false); }} aria-label="Script"
                      placeholder={"INT. BEDROOM - NIGHT\nCHARACTER(S): Sege, Amara\nSHOTS: SHOT 1: Close on Sege's eye opening. SHOT 2: …"} />
            <div className="wiz-editor-foot"><span>Scene headings (INT./EXT. …) and numbered shots (SHOT 1: …)</span><span className="num">{text.length.toLocaleString()} characters</span></div>
          </div>
        ) : (
          <div className="wiz-card">
            {file ? <div className="wiz-row"><I.Doc size={20} /><b style={{ wordBreak: "break-all" }}>{file.split(/[\\/]/).pop()}</b></div>
              : <p className="dim" style={{ marginTop: 0 }}>A PDF, TXT, Markdown or Fountain screenplay. The original file is not changed.</p>}
            <button className="btn" style={{ marginTop: 10 }} onClick={choose}><I.Upload size={15} /> {file ? "Choose another file" : "Choose script file"}</button>
          </div>
        )}
        {project.song_map && !(project.song_map.lyrics ?? []).length && <p className="dim" style={{ fontSize: 12.5, marginTop: 10 }}>
          <I.Alert size={12} /> This project has no lyrics yet. Scenes are timed most precisely when FilmCrafter can match each scene's
          dialogue to the line where it's sung; without lyrics they are spread across the song.</p>}
        {plan && <p className="dim" style={{ fontSize: 12.5, marginTop: 10 }}><I.Alert size={12} /> This project already has a plan ({shots} shots{takes ? `, ${takes} rendered takes` : ""}).
          It will be archived, not deleted; the new shots start fresh.</p>}
        {error && <div className="error-text" role="alert" style={{ marginTop: 10 }}>{error}</div>}
        {noScenes && <div className="wiz-card wiz-row" style={{ marginTop: 10 }}>
          <span style={{ flex: 1 }}>Use this text as the brief for FilmCrafter's creative directions instead?</span>
          <button className="btn" onClick={useAsBrief}>Use as brief</button></div>}
        <div className="sheet-actions" style={{ marginTop: 14 }}>
          <button className="btn ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn primary" onClick={adopt} disabled={!ready || busy}>{busy ? "Placing scenes on the song…" : "Use this script"}</button>
        </div>
    </Sheet>
  );
}
