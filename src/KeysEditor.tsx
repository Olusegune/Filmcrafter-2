import { type Overlay } from "./api";
import { EASES, KEY_PROPS, MAX_KEYS, evalKeys, upsertKey, type Ease, type Key, type KeyProp } from "./overlayKeys";

const LABEL: Record<KeyProp, string> = { x: "X", y: "Y", scale: "Scale", rotation: "Turn", opacity: "Opacity" };
const STEP: Record<KeyProp, number> = { x: 0.01, y: 0.01, scale: 0.05, rotation: 5, opacity: 0.05 };

/** A number that is saved when you leave the box; empty means the key does not set it. */
function Num({ value, step, onCommit }: { value: number | undefined; step: number; onCommit: (v: number | undefined) => void }) {
  return <input className="text-input ke-num" type="number" step={step} defaultValue={value == null ? "" : Math.round(value * 1000) / 1000} placeholder="–" key={value ?? "none"}
                onBlur={(e) => { const v = e.target.value.trim() === "" ? undefined : Number(e.target.value); if (v !== value && !(Number.isNaN(v))) onCommit(v); }} />;
}

/**
 * Keyframes for the selected layer: a few moments, each with a position, size, turn and opacity, and how to get to the next one. With keyframes the layer follows them
 * instead of its Movement. "Add keyframe here" records the layer as it looks at the playhead; with keyframes on, dropping the layer on the player sets a key too.
 */
export function KeysEditor({ sel, time, save }: { sel: Overlay; time: number; save: (keys: Key[]) => void }) {
  const keys = sel.keys ?? [];
  const start = sel.start ?? 0, end = sel.end ?? start + 4, span = Math.max(0.1, end - start);
  const rel = Math.min(Math.max(time - start, 0), span);
  const here = time >= start && time <= end;
  const add = () => {
    const now = evalKeys(keys, rel);
    save(upsertKey(keys, rel, { x: now.x ?? sel.x, y: now.y ?? sel.y, scale: now.scale ?? 1, rotation: now.rotation ?? 0, opacity: now.opacity ?? 1 }));
  };
  const change = (i: number, patch: Partial<Key>) => save(keys.map((k, j) => {
    if (j !== i) return k;
    const next = { ...k, ...patch } as Key;
    for (const p of KEY_PROPS) if (next[p] === undefined) delete next[p];
    return next;
  }).sort((a, b) => a.t - b.t));
  return (
    <div className="ke">
      <div className="ke-head"><b>Keyframes</b><span className="dim">{keys.length ? `${keys.length} of ${MAX_KEYS}` : "none"}</span><div style={{ flex: 1 }} />
        <button className="btn small" disabled={!here || keys.length >= MAX_KEYS} onClick={add} title={here ? "Record the layer as it looks at the playhead" : "Move the playhead inside this layer's time first"}>+ Keyframe here</button>
        {keys.length > 0 && <button className="btn small ghost" onClick={() => save([])}>Clear</button>}</div>
      {keys.length === 0 && <p className="dim">Move the playhead inside this layer, change nothing, and add a keyframe; move on in time, add another, and drag the layer on the player to a new place. It then travels between them.</p>}
      {keys.length > 0 && <>
        <div className="ke-track" aria-hidden>
          {keys.map((k, i) => <i key={i} className="ke-dot" style={{ left: `${Math.min(100, (k.t / span) * 100)}%` }} />)}
          {here && <i className="ke-now" style={{ left: `${(rel / span) * 100}%` }} />}</div>
        <p className="dim">The layer follows these instead of its Movement. X and Y are where its centre is (0 to 1 across the frame); Scale and Opacity multiply its own; Turn adds degrees. Leave a box empty to leave that setting alone.</p>
        {keys.map((k, i) => (
          <div key={`${i}-${k.t}`} className="ke-row">
            <label className="ke-cell"><span>At (s)</span><Num value={k.t} step={0.1} onCommit={(v) => v != null && change(i, { t: Math.max(0, v) })} /></label>
            {KEY_PROPS.map((p) => <label key={p} className="ke-cell"><span>{LABEL[p]}</span><Num value={k[p]} step={STEP[p]} onCommit={(v) => change(i, { [p]: v } as Partial<Key>)} /></label>)}
            <label className="ke-cell ke-wide"><span>Then</span>
              <select className="text-input" value={k.ease ?? "ease_in_out"} onChange={(e) => change(i, { ease: e.target.value as Ease })}>
                {EASES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></label>
            <button className="icon-btn" title="Remove this keyframe" onClick={() => save(keys.filter((_, j) => j !== i))}>×</button>
          </div>))}</>}
    </div>
  );
}
