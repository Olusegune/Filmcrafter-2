import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorText, type Cut, type CutAction, type CutClip } from "./api";
import { clipAt, clipName, clockTime, cutNotes, frameSeconds, nearest, snapPoints, SNAP_PX } from "./cutMath";
import "./cut.css";

export const CUT_H = 76;                                                     // the lane: a toolbar row and a row of clips

export type CutKey = "split" | "delete" | "ripple_delete" | "trim_in" | "trim_out" | "marker" | "undo" | "redo";

/**
 * The film's cut as the timeline edits it: loads it, makes one edit at a time through the engine (which checks it and keeps the undo history), and answers the keys the Studio sends.
 * Nothing here changes a take or the plan. `time` is the playhead, in seconds.
 */
export function useCut(dir: string, enabled: boolean, time: number) {
  const [cut, setCut] = useState<Cut | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [ripple, setRipple] = useState(false);
  const [snap, setSnap] = useState(true);
  const timeRef = useRef(time);
  timeRef.current = time;

  const load = useCallback(() => { api.editing(dir, "sequence_get").then((c) => { setCut(c); setErr(""); }).catch((e) => setErr(errorText(e))); }, [dir]);
  useEffect(() => {
    if (!enabled) return;
    load();
    window.addEventListener("pf-cut-changed", load);
    return () => window.removeEventListener("pf-cut-changed", load);
  }, [enabled, load]);

  const run = useCallback(async (action: CutAction, data: Record<string, unknown> = {}): Promise<boolean> => {
    setBusy(true); setErr("");
    try { setCut(await api.editing(dir, action, data)); return true; } catch (e) { setErr(errorText(e)); return false; } finally { setBusy(false); }
  }, [dir]);
  const edit = useCallback((op: string, data: Record<string, unknown> = {}) => run("edit", { op, ...data }), [run]);

  const clipFor = useCallback((): CutClip | null => {
    if (!cut) return null;
    const all = cut.sequence.tracks.flatMap((t) => t.clips);
    return all.find((c) => c.id === selected) ?? clipAt(cut, timeRef.current);
  }, [cut, selected]);

  const key = useCallback(async (k: CutKey) => {
    if (!cut) return;
    const t = timeRef.current;
    const c = clipFor();
    if (k === "undo" || k === "redo") { await run(k); return; }
    if (k === "marker") { await edit("marker_set", { at: t }); return; }
    if (k === "split") { await edit("split", { at: t, ...(c && t > c.start_s && t < c.start_s + c.duration_s ? { clip: c.id } : {}) }); return; }
    if (!c) { setErr("Choose a clip first (click it, or put the playhead on it)."); return; }
    if (k === "delete" || k === "ripple_delete") { if (await edit("delete", { clip: c.id, ripple: k === "ripple_delete" })) setSelected(null); return; }
    await edit("trim", { clip: c.id, edge: k === "trim_in" ? "in" : "out", to: t, ripple });
  }, [cut, clipFor, run, edit, ripple]);

  // the keys the Studio handles (it sends them as one event, as it does for the layers' undo)
  const keyRef = useRef(key);
  keyRef.current = key;
  useEffect(() => {
    if (!enabled) return;
    const on = (e: Event) => { void keyRef.current((e as CustomEvent<CutKey>).detail); };
    window.addEventListener("pf-cut-key", on);
    return () => window.removeEventListener("pf-cut-key", on);
  }, [enabled]);

  return { cut, err, setErr, busy, selected, setSelected, ripple, setRipple, snap, setSnap, run, edit, key, reload: load };
}
export type CutState = ReturnType<typeof useCut>;

type Drag = { kind: "in" | "out" | "move" | "roll"; clip: CutClip; at: number; from: number } | null;

/** The lane itself (one row of clips with trim handles) and its toolbar. It sits in the timeline's scrolling area and uses the timeline's zoom (pixels a second). */
export function CutLane({ s, pps, top, time, width, onSeek, free }: { s: CutState; pps: number; top: number; time: number; width: number; onSeek: (t: number) => void; free: { start: number }[] }) {
  const { cut } = s;
  const [drag, setDrag] = useState<Drag>(null);
  const lane = useRef<HTMLDivElement>(null);
  const fs = cut ? frameSeconds(cut) : 1 / 24;

  const timeOf = (clientX: number) => { const r = lane.current?.getBoundingClientRect(); return r ? Math.max(0, (clientX - r.left) / pps) : 0; };
  const snapped = (t: number, except: string | null) => (cut && s.snap ? nearest(snapPoints(cut, except, time), t, SNAP_PX / pps) : t);
  const begin = (e: React.PointerEvent, kind: "in" | "out" | "move" | "roll", clip: CutClip) => {
    e.stopPropagation(); e.preventDefault();
    s.setSelected(clip.id);
    const x0 = e.clientX;
    const origin = kind === "in" ? clip.start_s : kind === "move" ? clip.start_s : clip.start_s + clip.duration_s;
    let at = origin;
    setDrag({ kind, clip, at, from: origin });
    const move = (ev: PointerEvent) => {
      const raw = kind === "move" ? origin + (ev.clientX - x0) / pps : timeOf(ev.clientX);
      at = Math.max(0, snapped(raw, clip.id));
      setDrag({ kind: kind === "out" && ev.altKey ? "roll" : kind, clip, at, from: origin });
    };
    const up = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); window.removeEventListener("keydown", esc);
      setDrag(null);
      if (Math.abs(at - origin) < fs / 2) return;                                // a click, not a drag
      if (kind === "move") void s.edit("move", { clip: clip.id, to: at, ripple: s.ripple });
      else if (kind === "out" && ev.altKey) void s.edit("roll", { clip: clip.id, to: at });
      else void s.edit("trim", { clip: clip.id, edge: kind, to: at, ripple: s.ripple });
    };
    const esc = (ev: KeyboardEvent) => { if (ev.key === "Escape") { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); window.removeEventListener("keydown", esc); setDrag(null); } };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up); window.addEventListener("keydown", esc);
  };

  const nudge = (e: React.KeyboardEvent, c: CutClip) => {
    if (!e.altKey || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
    e.preventDefault(); e.stopPropagation();
    const by = (e.shiftKey ? 1 : fs) * (e.key === "ArrowLeft" ? -1 : 1);
    void s.edit("move", { clip: c.id, to: Math.max(0, c.start_s + by), ripple: s.ripple });
  };

  if (!cut) return <div className="tl-cut" style={{ top, height: CUT_H }}><div className="tl-cutbar"><span className="dim">{s.err || "Reading the cut…"}</span></div></div>;
  const notes = cutNotes(cut, free);
  const locked = cut.sequence.tracks.some((t) => t.locked);
  const sel = cut.sequence.tracks.flatMap((t) => t.clips).find((c) => c.id === s.selected) ?? null;
  const edited = cut.stored;
  return (
    <div className="tl-cut" style={{ top, height: CUT_H, width: Math.max(width, cut.sequence.length_s * pps) }} role="group" aria-label="The cut">
      <div className="tl-cutbar" style={{ width }}>
        <b className="tl-cuttitle">Cut</b>
        <button type="button" className="btn small" onClick={() => void s.key("undo")} disabled={s.busy || !cut.can_undo} title="Undo the last change to the cut, a grade or a saved look (Ctrl+Z)">Undo</button>
        <button type="button" className="btn small" onClick={() => void s.key("redo")} disabled={s.busy || !cut.can_redo} title="Do it again (Ctrl+Shift+Z or Ctrl+Y)">Redo</button>
        <button type="button" className="btn small" onClick={() => void s.key("split")} disabled={s.busy || locked} title="Cut the clip at the playhead (S)">Split</button>
        <button type="button" className="btn small" onClick={() => void s.key("delete")} disabled={s.busy || locked} title="Take the chosen clip out and leave a gap (Delete)">Delete</button>
        <details className="tl-cutmore"><summary>More</summary>
          <div className="tl-cutmenu" onClick={(e) => { if ((e.target as HTMLElement).closest("button")) (e.currentTarget.closest("details") as HTMLDetailsElement | null)?.removeAttribute("open"); }} onKeyDown={(e) => { if (e.key === "Escape") (e.currentTarget.closest("details") as HTMLDetailsElement | null)?.removeAttribute("open"); }}>
            <button type="button" className="btn small" onClick={() => void s.key("ripple_delete")} disabled={s.busy || locked} title="Take the clip out and close the gap (Shift+Delete)">Ripple delete</button>
            <button type="button" className="btn small" onClick={() => void s.key("trim_in")} disabled={s.busy || locked} title="Trim the start of the chosen clip to the playhead (Q)">Trim start to playhead</button>
            <button type="button" className="btn small" onClick={() => void s.key("trim_out")} disabled={s.busy || locked} title="Trim the end of the chosen clip to the playhead (W)">Trim end to playhead</button>
            <button type="button" className="btn small" onClick={() => sel && void s.edit("close_gap", { clip: sel.id })} disabled={s.busy || locked || !sel} title="Bring the chosen clip, and what follows, back to the clip before it">Close the gap before it</button>
            <button type="button" className="btn small" onClick={() => void s.key("marker")} disabled={s.busy} title="Put a marker at the playhead (B)">Marker</button>
            <button type="button" className="btn small" onClick={() => void s.edit("track_set", { track: cut.sequence.tracks[0].id, locked: !locked })} disabled={s.busy} aria-pressed={locked}>{locked ? "Unlock the track" : "Lock the track"}</button>
            <label><input type="checkbox" checked={s.ripple} onChange={(e) => s.setRipple(e.target.checked)} /> Ripple: what follows moves with an edit</label>
            <label><input type="checkbox" checked={s.snap} onChange={(e) => s.setSnap(e.target.checked)} /> Snap to cuts, markers and the playhead</label>
          </div>
        </details>
        {cut.unplaced.length > 0 && <button type="button" className="btn small" onClick={() => void s.run("place_missing")} disabled={s.busy} title="Put every shot that has no clip on the end of the film">Place {cut.unplaced.length === 1 ? "it" : "them"}</button>}
        <span className="tl-cutinfo dim">{edited ? "Edited (Preview plays the cut)" : "As planned"} · {clockTime(cut.sequence.length_s)}{s.ripple ? " · ripple" : ""}</span>
        {s.err && <span className="tl-cuterr" role="alert">{s.err}</span>}
        {!s.err && notes.length > 0 && <span className="tl-cutnote" role="status">{notes[0]}{notes.length > 1 ? ` (+${notes.length - 1} more)` : ""}</span>}
      </div>
      <div className="tl-cutclips" ref={lane} style={{ width: Math.max(width, cut.sequence.length_s * pps) }}>
        {cut.sequence.tracks.map((t) => t.hidden ? null : t.clips.map((c) => {
          const dragging = drag && drag.clip.id === c.id ? drag : null;
          const l = dragging && dragging.kind === "move" ? dragging.at : dragging && dragging.kind === "in" ? dragging.at : c.start_s;
          const r = dragging && (dragging.kind === "out" || dragging.kind === "roll") ? dragging.at : dragging && dragging.kind === "move" ? dragging.at + c.duration_s : c.start_s + c.duration_s;
          return (
            <div key={c.id} className={`tl-clip ${s.selected === c.id ? "on" : ""} ${dragging ? "dragging" : ""} ${t.locked ? "locked" : ""}`} style={{ left: l * pps, width: Math.max(6, (r - l) * pps - 1) }}>
              <button type="button" className="tl-clipbody" aria-pressed={s.selected === c.id} aria-label={clipName(c)} title={`${clipName(c)}. Alt+arrows nudge it a frame (Shift: a second).`}
                      onFocus={() => s.setSelected(c.id)} onClick={(e) => { e.stopPropagation(); s.setSelected(c.id); onSeek(c.start_s); }} onKeyDown={(e) => nudge(e, c)} onPointerDown={(e) => { if (!t.locked && e.button === 0) begin(e, "move", c); }}>
                <span className="tl-clipname">{c.shot}</span>
                {c.source_in > 0 && <span className="tl-clipin">in {clockTime(c.source_in_s)}</span>}
              </button>
              {!t.locked && <span className="tl-handle in" aria-hidden="true" title="Drag to trim the start" onPointerDown={(e) => begin(e, "in", c)} />}
              {!t.locked && <span className="tl-handle out" aria-hidden="true" title="Drag to trim the end (hold Alt to roll the cut)" onPointerDown={(e) => begin(e, "out", c)} />}
            </div>
          );
        }))}
        {cut.sequence.markers.map((m) => (
          <button type="button" key={m.id} className="tl-marker" style={{ left: m.at_s * pps }} aria-label={`Marker ${m.name || ""} at ${clockTime(m.at_s)}`.replace("  ", " ")} title={`${m.name || "Marker"} at ${clockTime(m.at_s)} (click to go there; Delete removes it)`}
                  onClick={(e) => { e.stopPropagation(); onSeek(m.at_s); }} onKeyDown={(e) => { if (e.key === "Delete") { e.preventDefault(); e.stopPropagation(); void s.edit("marker_remove", { marker: m.id }); } }} />
        ))}
        {drag && <div className="tl-dragline" style={{ left: drag.at * pps }} aria-hidden="true"><span>{clockTime(drag.at)}</span></div>}
      </div>
    </div>
  );
}
