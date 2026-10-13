import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type CustomFrameMade, type CustomFrameState } from "./api";
import { ask } from "./ask";
import * as I from "./icons";

type Mode = "generate" | "colour" | "picture" | "clip";
const MODES: { id: Mode; label: string; hint: string; free: boolean }[] = [
  { id: "generate", label: "Generate it", hint: "Describe it; render it like any shot, with the model and quality you choose", free: false },
  { id: "colour", label: "Colour card", hint: "A colour or gradient", free: true },
  { id: "picture", label: "My picture", hint: "With a slow camera move", free: true },
  { id: "clip", label: "My clip", hint: "Cut at the end of the frame, repeats if shorter", free: true },
];
const MOVES = [["zoom_in", "Zoom in"], ["zoom_out", "Zoom out"], ["pan_left", "Pan left"], ["pan_right", "Pan right"], ["none", "Still"]];
const clock = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;

/**
 * Insert a frame into the timeline: a new shot of the length you choose, next to a shot you pick. It uses time the film already has (the empty
 * stretch beside that shot first; only what is still missing is cut from the shot, which keeps a second), so nothing after it moves.
 */
export function InsertFrameSheet({ dir, shot, onClose, onDone }: { dir: string; shot?: string; onClose: () => void; onDone: (id: string) => void }) {
  const [st, setSt] = useState<CustomFrameState | null>(null);
  const [anchor, setAnchor] = useState(shot ?? "");
  const [where, setWhere] = useState<"before" | "after">("after");
  const [length, setLength] = useState(3);
  const [mode, setMode] = useState<Mode>("generate");
  const [prompt, setPrompt] = useState("");
  const [file, setFile] = useState("");
  const [c1, setC1] = useState("#101820");
  const [c2, setC2] = useState("#101820");
  const [motion, setMotion] = useState("zoom_in");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.customFrame(dir, "state").then((s) => { setSt(s); setAnchor((a) => a || s.shots[0]?.id || ""); }).catch((e) => setErr(errorText(e)));
  }, [dir]);

  const choose = async () => {
    const exts = mode === "clip" ? ["mp4", "mov", "webm", "m4v", "mkv"] : ["png", "jpg", "jpeg", "webp"];
    const f = await open({ filters: [{ name: mode === "clip" ? "Video clip" : "Picture", extensions: exts }] });
    if (typeof f === "string") setFile(f);
  };
  const ready = mode === "generate" ? !!prompt.trim() : mode === "colour" ? true : !!file;
  const go = async () => {
    setBusy(true); setErr("");
    try {
      const r = await api.customFrame<CustomFrameMade>(dir, "insert", {
        shot: anchor, where, length, mode, prompt: mode === "generate" ? prompt : undefined,
        file: file || undefined, color: c1, color2: c2, motion,
      });
      onDone(r.shot);
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const added = (st?.shots ?? []).filter((s) => s.custom || s.intro);
  const remove = async (id: string) => {
    if (!await ask(`Remove the frame ${id}? Time it took from a neighbouring shot goes back to it. Its picture or video files stay until you use Clean up.`, { ok: "Remove the frame", danger: true })) return;
    setBusy(true); setErr("");
    try { await api.customFrame(dir, "remove", { shot: id }); setSt(await api.customFrame(dir, "state")); onDone(""); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const a = st?.shots.find((s) => s.id === anchor);

  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass insert-frame" role="dialog" aria-label="Insert a frame" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Insert a frame</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">A new shot in the film: a card, a held picture, your own clip or something generated. It takes time the film already has, so nothing after it
          moves and the film stays in sync. It is an ordinary shot afterwards: edit its prompt, camera and model, render takes and review it like any other.</p>
        <div className="if-row">
          <label className="field"><span>Put it</span>
            <select className="text-input" value={where} onChange={(e) => setWhere(e.target.value as "before" | "after")}>
              <option value="before">before</option><option value="after">after</option></select></label>
          <label className="field if-grow"><span>shot</span>
            <select className="text-input" value={anchor} onChange={(e) => setAnchor(e.target.value)}>
              {(st?.shots ?? []).map((s) => <option key={s.id} value={s.id}>{s.id} · {clock(s.start)} to {clock(s.end)}{s.intro || s.custom ? " (added)" : ""}</option>)}</select></label>
          <label className="field"><span>Length (s)</span>
            <input className="text-input" type="number" min={st?.min ?? 0.5} max={st?.max ?? 15} step={0.5} value={length} onChange={(e) => setLength(Number(e.target.value))} /></label>
        </div>
        {a && <p className="dim">Next to {a.id}, which lasts {(a.end - a.start).toFixed(1)} s. If the film has no empty stretch there, the missing time is cut from {a.id} (it keeps at least a second).</p>}
        <div className="if-modes" role="tablist" aria-label="What the frame shows">
          {MODES.map((m) => (
            <button key={m.id} role="tab" aria-selected={mode === m.id} className={`if-mode ${mode === m.id ? "on" : ""}`} onClick={() => setMode(m.id)} title={m.hint}>
              <b>{m.label}</b><span className="dim">{m.free ? "Free" : "Priced when rendered"}</span></button>))}
        </div>
        {mode === "generate" && <>
          <label className="field"><span>What it shows</span>
            <textarea className="text-input" rows={3} maxLength={600} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Golden light drifts across burgundy velvet, slow push-in" /></label>
          <div className="if-row"><button className="btn sm ghost" onClick={choose}>{file ? "Change starting picture…" : "Starting picture (optional)…"}</button>
            {file && <span className="dim">{file.split(/[\\/]/).pop()} <button className="link" onClick={() => setFile("")}>clear</button></span>}</div>
          <p className="dim">You choose the model and see the price when you render it, like any shot. A starting picture becomes its approved keyframe.</p></>}
        {mode === "colour" && <div className="if-row"><label className="field"><span>Top</span><input type="color" value={c1} onChange={(e) => setC1(e.target.value)} /></label>
          <label className="field"><span>Bottom</span><input type="color" value={c2} onChange={(e) => setC2(e.target.value)} /></label></div>}
        {(mode === "picture" || mode === "clip") && <div className="if-row">
          <button className="btn sm" onClick={choose}>{file ? "Change…" : mode === "clip" ? "Choose a clip…" : "Choose a picture…"}</button>
          {file && <span className="dim">{file.split(/[\\/]/).pop()}</span>}
          {mode === "picture" && <label className="field"><span>Camera move</span>
            <select className="text-input" value={motion} onChange={(e) => setMotion(e.target.value)}>{MOVES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></label>}</div>}
        {added.length > 0 && <div className="if-added"><b>Frames you added</b>
          {added.map((s) => <div key={s.id} className="if-added-row"><span className="num">{s.id}</span><span className="dim">{clock(s.start)} to {clock(s.end)}</span><div style={{ flex: 1 }} />
            <button className="btn small ghost danger" disabled={busy} onClick={() => remove(s.id)}><I.Trash size={13} /> Remove</button></div>)}</div>}
        {err && <p className="error-text" role="alert">{err}</p>}
        <div className="if-actions"><div style={{ flex: 1 }} />
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!ready || busy || !anchor} onClick={go}>{busy ? "Adding…" : "Insert the frame"}</button></div>
      </div>
    </div>
  );
}
