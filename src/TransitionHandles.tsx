import { useEffect, useRef, useState } from "react";
import { api, errorText, type BoardShot } from "./api";
import { MAX_TRANSITION_S, MIN_TRANSITION_S, TRANSITION_LIST, transitionGlyph, transitionInfo, transitionSeconds } from "./transitions";
import "./lanes.css";

const GROUPS = ["Basic", "Wipe", "Move"] as const;

/** The choice for one cut: a transition, how long it takes, and whether to use it on more cuts. Pure display: the handle does the saving. */
export function TransitionPicker({ shot, prev, busy, err, scene, onPick, onLength, onApply, onClose }: {
  shot: BoardShot; prev: BoardShot; busy: boolean; err: string; scene: number;
  onPick: (id: string) => void; onLength: (s: number) => void; onApply: (scope: "scene" | "all") => void; onClose: () => void;
}) {
  const kind = shot.transition ?? "cut";
  const len = transitionSeconds(kind, shot.transition_s, shot.end - shot.start);
  const [v, setV] = useState(len);
  useEffect(() => setV(len), [len]);
  const done = () => Math.abs(v - len) > 0.004 && onLength(Math.round(v * 20) / 20);
  return (
    <div className="tr-pop" role="dialog" aria-label={`Transition into ${shot.id}`} onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } }}>
      <b>{prev.id} → {shot.id}</b>
      {GROUPS.map((g) => (
        <div key={g} role="group" aria-label={g}>
          <div className="dim" style={{ fontSize: 10.5, letterSpacing: ".08em", textTransform: "uppercase", margin: "2px 0 4px" }}>{g}</div>
          <div className="tr-grid">
            {TRANSITION_LIST.filter((t) => t.group === g).map((t) => (
              <button key={t.id} disabled={busy} aria-pressed={t.id === kind} onClick={() => onPick(t.id)} title={t.label}>
                <span aria-hidden>{transitionGlyph(t.id)}</span> {t.label.replace("Wipe to the ", "Wipe ").replace("Slide off to the ", "Slide ").replace("Slide off ", "Slide ").replace("Whip to the ", "Whip ")}
              </button>))}
          </div>
        </div>))}
      {kind !== "cut" && (
        <label className="tr-row">Length
          <input type="range" min={MIN_TRANSITION_S} max={MAX_TRANSITION_S} step={0.05} value={v} disabled={busy} aria-label="Transition length in seconds"
                 onChange={(e) => setV(Number(e.target.value))} onPointerUp={done} onKeyUp={done} onBlur={done} />
          <span className="num">{v.toFixed(2)} s</span></label>)}
      {kind !== "cut" && <p className="dim" style={{ margin: 0 }}>The old picture is taken away over the first {v.toFixed(2)} s of {shot.id}; no shot is moved in time.</p>}
      <div className="tr-row">
        <button className="btn small ghost" disabled={busy} onClick={() => onApply("scene")} title={`Use ${transitionInfo(kind).label.toLowerCase()} on every cut inside scene ${scene}`}>Apply to this scene</button>
        <button className="btn small ghost" disabled={busy} onClick={() => onApply("all")} title="Use it on every cut in the film">Apply to every cut</button>
      </div>
      {err && <p className="error-text" role="alert" style={{ margin: 0 }}>{err}</p>}
    </div>
  );
}

/** A small handle at every cut between shots, on the timeline: shows the transition and opens the picker. */
export function TransitionHandles({ dir, shots, pps, top, onChanged }: { dir: string; shots: BoardShot[]; pps: number; top: number; onChanged: () => void }) {
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [at, setAt] = useState<{ left: number; bottom: number; max: number }>({ left: 0, bottom: 0, max: 400 });
  const ref = useRef<HTMLDivElement>(null);
  const ordered = [...shots].sort((a, b) => a.start - b.start);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(null); };
    window.addEventListener("pointerdown", away);
    return () => window.removeEventListener("pointerdown", away);
  }, [open]);
  const run = async (ids: string[], kind: string, seconds?: number | null) => {
    setBusy(true); setErr("");
    try { await api.media(dir, "transition", { shots: ids, transition: kind, seconds }); onChanged(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const idx = open ? ordered.findIndex((s) => s.id === open) : -1;
  const shot = idx > 0 ? ordered[idx] : null;
  return (
    <div className="tl-trans" ref={ref} style={{ top }} aria-label="Transitions between shots">
      {ordered.slice(1).map((s, i) => {
        const kind = s.transition ?? "cut";
        const info = transitionInfo(kind);
        return (
          <button key={s.id} className={`tr-handle ${kind === "cut" ? "" : "set"}`} style={{ left: s.start * pps }} aria-expanded={open === s.id} aria-haspopup="dialog"
                  aria-label={`Transition into ${s.id}: ${info.label}`} title={`${ordered[i].id} → ${s.id}: ${info.label}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    const r = e.currentTarget.getBoundingClientRect();
                    setAt({ left: Math.max(8, Math.min(window.innerWidth - 268, r.left + r.width / 2 - 125)), bottom: window.innerHeight - r.top + 6, max: Math.max(220, r.top - 16) });   // opens upward: the timeline is at the bottom of the window
                    setErr(""); setOpen(open === s.id ? null : s.id);
                  }}>{transitionGlyph(kind)}</button>);
      })}
      {shot && (
        <div style={{ position: "fixed", left: at.left, bottom: at.bottom, maxHeight: at.max, overflowY: "auto", zIndex: 60, borderRadius: 12 }}>
          <TransitionPicker shot={shot} prev={ordered[idx - 1]} busy={busy} err={err} scene={shot.scene}
                            onClose={() => setOpen(null)}
                            onPick={(id) => run([shot.id], id)}
                            onLength={(s) => run([shot.id], shot.transition ?? "cut", s)}
                            onApply={(scope) => run(ordered.slice(1).filter((x) => scope === "all" || (x.scene === shot.scene && ordered[ordered.indexOf(x) - 1].scene === shot.scene)).map((x) => x.id),
                                                    shot.transition ?? "cut", shot.transition_s)} />
        </div>)}
    </div>
  );
}
