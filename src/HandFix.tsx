import { useEffect, useRef, useState } from "react";
import { Sheet } from "./Sheet";
import { api, errorText } from "./api";
import { ask } from "./ask";

export type Box = [number, number, number, number];
type Suggestion = { box: Box; why: string };
type Plan = { model: { label: string; price_usd: number | null }; variants: number; usd_est: number };

const clamp01 = (n: number) => Math.min(1, Math.max(0, n));
export const MIN_BOX = 0.03;

/** Pure: a box from two corners given as fractions, put in order and kept inside the picture. */
export function boxFromCorners(ax: number, ay: number, bx: number, by: number): Box {
  const [x0, x1] = [clamp01(ax), clamp01(bx)].sort((p, q) => p - q);
  const [y0, y1] = [clamp01(ay), clamp01(by)].sort((p, q) => p - q);
  return [x0, y0, x1, y1];
}

/** Pure: whether a box is big enough to be a hand (and not a slip of the mouse). */
export const usableBox = (b: Box | null): b is Box => !!b && b[2] - b[0] >= MIN_BOX && b[3] - b[1] >= MIN_BOX;

/** Pure: a box as CSS percentages for the overlay. */
export const boxStyle = (b: Box) => ({ left: `${b[0] * 100}%`, top: `${b[1] * 100}%`, width: `${(b[2] - b[0]) * 100}%`, height: `${(b[3] - b[1]) * 100}%` });

/** Pure: the price line. */
export function priceLine(p: Plan | null, versions: number): string {
  if (!p) return "";
  const each = p.usd_est / Math.max(1, p.variants);
  const total = each * versions;
  return `${versions} version${versions === 1 ? "" : "s"} on ${p.model.label}: about $${total < 0.1 ? total.toFixed(3) : total.toFixed(2)}`;
}

const EDGES: { i: 0 | 1 | 2 | 3; label: string }[] = [{ i: 0, label: "Left edge" }, { i: 2, label: "Right edge" }, { i: 1, label: "Top edge" }, { i: 3, label: "Bottom edge" }];

/**
 * Fix only the bad hand. Mark the hand on the keyframe (drag a box, or let FilmCrafter suggest one), and only that part is redrawn; the rest of the picture stays exactly as it is.
 * The result waits beside the old keyframe: nothing is replaced until you use it.
 */
export function HandFix({ dir, shot, image, onClose, onQueued }: { dir: string; shot: string; image: string; onClose: () => void; onQueued?: () => void }) {
  const stage = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<Box | null>(null);
  const [drag, setDrag] = useState<[number, number] | null>(null);
  const [found, setFound] = useState<Suggestion[]>([]);
  const [note, setNote] = useState("");
  const [versions, setVersions] = useState(2);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [info, setInfo] = useState("");

  useEffect(() => { api.handFix<Plan>(dir, "plan", { shot, variants: 1 }).then(setPlan).catch((e) => setErr(errorText(e))); }, [dir, shot]);

  const at = (e: React.PointerEvent): [number, number] => {
    const r = stage.current!.getBoundingClientRect();
    return [clamp01((e.clientX - r.left) / r.width), clamp01((e.clientY - r.top) / r.height)];
  };
  const down = (e: React.PointerEvent) => { (e.target as Element).setPointerCapture?.(e.pointerId); const p = at(e); setDrag(p); setBox([p[0], p[1], p[0], p[1]]); };
  const move = (e: React.PointerEvent) => { if (drag) { const p = at(e); setBox(boxFromCorners(drag[0], drag[1], p[0], p[1])); } };
  const up = () => setDrag(null);

  const find = async () => {
    if (!(await ask("Look for the hands that are drawn wrongly in this keyframe.\n\nCost: about two cents, with your AI brain's vision model. Nothing is changed.\n\nLook?"))) return;
    setBusy("find"); setErr(""); setInfo("");
    try {
      const r = await api.handFix<{ boxes: Suggestion[] }>(dir, "locate", { shot });
      setFound(r.boxes);
      if (r.boxes.length) setBox(r.boxes[0].box); else setInfo("No hand looked wrong to the check. Draw a box yourself if you can see one.");
    } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const nudge = (i: 0 | 1 | 2 | 3, v: number) => { const b = (box ?? [0.3, 0.3, 0.6, 0.6]).slice() as Box; b[i] = clamp01(v); setBox(boxFromCorners(b[0], b[1], b[2], b[3])); };

  const go = async () => {
    if (!usableBox(box)) return;
    let p: Plan;
    try { p = await api.handFix<Plan>(dir, "plan", { shot, variants: versions }); setPlan(p); } catch (e) { setErr(errorText(e)); return; }
    if (!(await ask(`Redraw only the marked part of ${shot}'s keyframe, ${priceLine(p, versions)}.\n\nThe rest of the picture and your current keyframe are not touched. The new versions wait until you choose to use one.\n\nStart?`))) return;
    setBusy("go"); setErr("");
    try { await api.handFix(dir, "queue", { shot, box, note, variants: versions }); onQueued?.(); window.dispatchEvent(new Event("pf-open-keyframe-tools")); onClose(); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };

  return (
    <Sheet label={`Fix a hand in ${shot}`} className="hf-sheet" onDismiss={onClose}>
        <div className="rv-head"><div><h2>Fix a hand</h2><p className="sub">Mark the hand. Only that part is redrawn; the rest of {shot} stays exactly as it is.</p></div></div>
        <div className="hf-stage" ref={stage} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
          <img src={api.mediaUrl(`${dir}/${image}`)} alt={`The keyframe of ${shot}`} draggable={false} />
          {found.map((f, i) => <button key={i} type="button" className="hf-found" style={boxStyle(f.box)} title={f.why} aria-label={`Suggested hand ${i + 1}: ${f.why}`}
                                        onPointerDown={(e) => e.stopPropagation()} onClick={() => setBox(f.box)} />)}
          {box && <div className={`hf-box ${usableBox(box) ? "" : "faint"}`} style={boxStyle(box)} />}
        </div>
        <div className="hf-row">
          <button className="btn ghost small" disabled={!!busy} onClick={find}>{busy === "find" ? "Looking…" : "Find the hands for me"}</button>
          <span className="dim">{usableBox(box) ? "Drag again to change the box." : "Drag on the picture around the hand (or both hands, if they hold each other)."}</span>
        </div>
        {found.length > 0 && <ul className="hf-found-list">{found.map((f, i) => <li key={i}><button className="link" onClick={() => setBox(f.box)}>Hand {i + 1}</button> <span className="dim">{f.why}</span></li>)}</ul>}
        {info && <p className="dim" role="status">{info}</p>}
        <details className="hf-adjust"><summary>Adjust with sliders</summary>
          {EDGES.map((e) => <label key={e.i} className="hf-slide">{e.label}<input type="range" min={0} max={100} value={Math.round((box?.[e.i] ?? (e.i < 2 ? 0.3 : 0.6)) * 100)} onChange={(ev) => nudge(e.i, Number(ev.target.value) / 100)} aria-label={e.label} /></label>)}
        </details>
        <label className="fr-label" htmlFor="hf-note">Anything to add? <span className="dim">(optional, e.g. “the right hand is the wrong one”)</span></label>
        <input id="hf-note" className="text-input" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
        <div className="hf-row hf-go">
          <label className="dim">Versions <select value={versions} onChange={(e) => setVersions(Number(e.target.value))} aria-label="Versions to make">{[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
          <span className="dim">{priceLine(plan, versions)}</span>
          <div style={{ flex: 1 }} />
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={!usableBox(box) || !!busy} onClick={go}>{busy === "go" ? "Starting…" : "Fix this hand"}</button>
        </div>
        {err && <p className="error-text" role="alert">{err}</p>}
    </Sheet>
  );
}
