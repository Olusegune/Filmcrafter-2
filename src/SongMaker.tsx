import { useState } from "react";
import { api, errorText, type SongMade, type SongPlan } from "./api";
import * as I from "./icons";
import { ask } from "./ask";

const MODELS = [["music_v2_5", "Music v2.5 (newest)"], ["music_v2", "Music v2"], ["music_v1", "Music v1"]] as const;

/**
 * Make a song with ElevenLabs Music: from your tagged lyrics (each [Verse]/[Chorus] becomes a section that sings your words) or from a
 * description. It runs on your own ElevenLabs plan, so there is no price to show: you hear the result and choose whether to use it.
 */
export function SongMaker({ onUse, onClose, startLyrics = "" }: {
  onUse: (song: { path: string; title: string; lyrics: string }) => void; onClose: () => void; startLyrics?: string;
}) {
  const [mode, setMode] = useState<"lyrics" | "describe">(startLyrics.trim() ? "lyrics" : "describe");
  const [title, setTitle] = useState("My song");
  const [style, setStyle] = useState("");
  const [avoid, setAvoid] = useState("");
  const [lyrics, setLyrics] = useState(startLyrics);
  const [prompt, setPrompt] = useState("");
  const [seconds, setSeconds] = useState(90);
  const [instrumental, setInstrumental] = useState(false);
  const [model, setModel] = useState<string>(MODELS[0][0]);
  const [plan, setPlan] = useState<SongPlan | null>(null);
  const [made, setMade] = useState<(SongMade & { lyrics: string }) | null>(null);   // lyrics: what the song was made from, even if the box is edited later
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");

  const data = () => ({ mode, lyrics, style, avoid, prompt, seconds, instrumental, model });
  const preview = async () => {
    setErr(""); setBusy("plan");
    try { setPlan(await api.songgen<SongPlan>("plan", { lyrics, style, avoid })); } catch (e) { setErr(errorText(e)); setPlan(null); } finally { setBusy(""); }
  };
  const make = async () => {
    const asked = mode === "lyrics" ? `about ${plan?.seconds ?? "?"} seconds` : `${seconds} seconds`;
    if (!await ask(`Make a song (${asked}) with ElevenLabs Music?\n\nThis uses credits from your own ElevenLabs plan (the music API needs a paid plan). `
      + "FilmCrafter can't see the price in advance, and it takes a minute or two. You'll hear the result before using it.")) return;
    setErr(""); setBusy("make"); setMade(null);
    const from = mode === "lyrics" ? lyrics : "";
    try { setMade({ ...(await api.songgen<SongMade>("make", data())), lyrics: from }); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };

  return (
    <div className="overlay" onClick={() => !busy && onClose()}>
      <div className="sheet glass" role="dialog" aria-label="Make a song" onClick={(e) => e.stopPropagation()} style={{ width: "min(640px, calc(100vw - 48px))", maxHeight: "86vh", overflow: "auto" }}>
        <div className="vs-head"><h2>Make a song with ElevenLabs Music</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" disabled={!!busy} onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">Optional: FilmCrafter works from any song you bring. This composes one on your ElevenLabs plan, from your lyrics or a description. Listen first; nothing
          is added to a project until you choose it.</p>
        <div className="seg" role="group" aria-label="How to make it">
          <button className={mode === "lyrics" ? "on" : ""} onClick={() => setMode("lyrics")}>From my lyrics</button>
          <button className={mode === "describe" ? "on" : ""} onClick={() => setMode("describe")}>Describe it</button>
        </div>
        <label className="field"><span>Title</span><input className="text-input" value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} /></label>
        <label className="field"><span>Style (separate with commas)</span>
          <input className="text-input" value={style} placeholder="Afrobeat, highlife, gospel choir, theatrical" onChange={(e) => setStyle(e.target.value)} /></label>
        {mode === "lyrics" ? <>
          <label className="field"><span>Your lyrics, with a tag above each part: [Verse 1], [Chorus], [Bridge]…</span>
            <textarea className="text-input" rows={10} value={lyrics} onChange={(e) => { setLyrics(e.target.value); setPlan(null); }} placeholder={"[Verse 1]\nNine months I carry you,\n…\n\n[Chorus]\nI AM YOUR MOTHER!"} /></label>
          <label className="field"><span>Keep out (optional)</span><input className="text-input" value={avoid} placeholder="metal, autotune" onChange={(e) => setAvoid(e.target.value)} /></label>
          <div className="ov-add"><button className="btn sm" disabled={!!busy || !lyrics.trim()} onClick={preview}>{busy === "plan" ? "…" : "Show the plan"}</button></div>
          {plan && <div className="dim" style={{ margin: "8px 0" }}>
            <b>{plan.sections.length} sections, about {Math.floor(plan.seconds / 60)}:{String(plan.seconds % 60).padStart(2, "0")}</b>
            <ul className="dc-sources">{plan.sections.map((s, i) => <li key={i}>{s.name}: {s.lines ? `${s.lines} line${s.lines === 1 ? "" : "s"}` : "instrumental"}, {s.seconds}s</li>)}</ul>
            {plan.warnings.map((w) => <div key={w} className="si-problems"><span>{w}</span></div>)}
          </div>}
        </> : <>
          <label className="field"><span>What should it be like?</span>
            <textarea className="text-input" rows={4} value={prompt} placeholder="A warm, proud highlife anthem about a mother who thinks she runs the world" onChange={(e) => setPrompt(e.target.value)} /></label>
          <label className="field"><span>Length: {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</span>
            <input type="range" min={10} max={300} step={5} value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} /></label>
          <label className="ov-check"><input type="checkbox" checked={instrumental} onChange={(e) => setInstrumental(e.target.checked)} /> No vocals (instrumental)</label>
        </>}
        <label className="field"><span>Model</span>
          <select className="text-input" value={model} onChange={(e) => setModel(e.target.value)}>{MODELS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
        {err && <p className="error-text" role="alert">{err}</p>}
        {busy === "make" && <p className="dim" role="status"><span className="spin sm" /> ElevenLabs is composing… this takes a minute or two. Keep FilmCrafter open.</p>}
        {made && <div className="export-done">
          <div className="status-ok"><I.Check size={16} /> Made a {Math.floor(made.seconds / 60)}:{String(Math.round(made.seconds % 60)).padStart(2, "0")} song</div>
          <audio controls src={api.mediaUrl(made.path)} style={{ width: "100%", marginTop: 6 }} />
        </div>}
        <div className="sheet-actions">
          <button className="btn ghost" disabled={!!busy} onClick={onClose}>Close</button>
          <button className="btn" disabled={!!busy || (mode === "lyrics" ? !lyrics.trim() : !prompt.trim() && !style.trim())} onClick={make}>{made ? "Make another" : "Make the song…"}</button>
          {made && <button className="btn primary" disabled={!!busy} onClick={() => onUse({ path: made.path, title: title.trim() || "My song", lyrics: made.lyrics })}>Use this song</button>}
        </div>
      </div>
    </div>
  );
}
