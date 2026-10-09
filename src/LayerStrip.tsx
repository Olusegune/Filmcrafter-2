import { type Overlay } from "./api";

const clock = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;

/**
 * Where the selected layer is in the song: a bar for the time it is on screen, a diamond for each keyframe, and the playhead. Click anywhere to move the playhead
 * there; click a diamond to go to that keyframe. Shown under the player while the Layers panel has a layer selected.
 */
export function LayerStrip({ layer, duration, time, onSeek }: { layer: Overlay; duration: number; time: number; onSeek: (t: number) => void }) {
  if (!layer.placed || layer.start == null || layer.end == null || !(duration > 0)) return null;
  const pct = (t: number) => `${Math.max(0, Math.min(100, (t / duration) * 100))}%`;
  const at = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(Math.max(0, Math.min(duration, ((e.clientX - r.left) / r.width) * duration)));
  };
  return (
    <div className="layer-strip" role="group" aria-label={`Timeline of ${layer.name || layer.text || "the selected layer"}`}>
      <span className="ls-name">{layer.name || layer.text || "Layer"}</span>
      <div className="ls-track" onClick={at} title="Click to move the playhead">
        <i className="ls-span" style={{ left: pct(layer.start), width: `calc(${pct(layer.end)} - ${pct(layer.start)})` }} />
        {(layer.keys ?? []).map((k, i) => (
          <button key={i} className="ls-key" style={{ left: pct(layer.start! + k.t) }} title={`Keyframe at ${clock(layer.start! + k.t)}`}
                  onClick={(e) => { e.stopPropagation(); onSeek(Math.min(duration, layer.start! + k.t)); }} aria-label={`Keyframe ${i + 1} at ${clock(layer.start! + k.t)}`} />))}
        <i className="ls-now" style={{ left: pct(time) }} />
      </div>
      <span className="ls-time num dim">{clock(layer.start)} – {clock(layer.end)}</span>
    </div>
  );
}
