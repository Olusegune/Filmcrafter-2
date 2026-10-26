import { useCallback, useEffect, useState } from "react";
import { api, errorText, type CompositionGuideData } from "./api";

/**
 * "Composition": where the people sit in the frame (thirds, headroom, look room), in plain words, with the thirds grid drawn and the points marked. The same words are added to the picture and
 * video requests for this shot. It reads the shot and changes nothing in it; one switch turns the wording off for the film. Free: nothing is sent anywhere.
 */
export function CompositionGuide({ dir, shot, version }: { dir: string; shot: string; version: string }) {
  const [g, setG] = useState<CompositionGuideData | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.filmComposition<CompositionGuideData>("guide", dir, { shot }).then((x) => { setG(x); setErr(""); }).catch((e) => setErr(errorText(e))), [dir, shot]);
  useEffect(() => { void load(); }, [load, version]);            // when the framing, angle or blocking changes, the guide is read again
  if (!g) return err ? <p className="error-text" role="alert">{err}</p> : null;
  const W = 192, H = 108;
  return (
    <section className="comp" aria-label="Composition">
      <h4>Composition <span className="dim">where they sit in the frame</span></h4>
      <div className="comp-body">
        <svg className="comp-grid" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="The frame divided into thirds, with where the people sit">
          <rect x="0.5" y="0.5" width={W - 1} height={H - 1} fill="none" stroke="currentColor" strokeOpacity="0.5" />
          {g.grid.map((t) => <g key={t}><line x1={t * W} y1="0" x2={t * W} y2={H} stroke="currentColor" strokeOpacity="0.28" /><line x1="0" y1={t * H} x2={W} y2={t * H} stroke="currentColor" strokeOpacity="0.28" /></g>)}
          {g.horizon != null && <line x1="0" y1={g.horizon * H} x2={W} y2={g.horizon * H} stroke="#e8b45c" strokeWidth="1.5" strokeDasharray="4 3" />}
          {g.points.map((p) => <g key={p.name}><circle cx={p.x * W} cy={p.y * H} r="5" fill="#e8b45c" /><text x={Math.min(W - 4, p.x * W + 8)} y={p.y * H + 3} fontSize="8" fill="currentColor" textAnchor={p.x > 0.7 ? "end" : "start"}>{p.name}</text></g>)}
        </svg>
        <ul className="comp-lines">{g.lines.map((l) => <li key={l.text}>{l.text} <span className="dim" title={l.why}>Why?</span><span className="sr-only"> {l.why}</span></li>)}</ul>
      </div>
      <label className="ly-check"><input type="checkbox" checked={g.in_prompt} onChange={(e) => void api.filmComposition("set", dir, { on: e.target.checked }).then(load).catch((x) => setErr(errorText(x)))} /> Ask for this composition when pictures and video are made (for the whole film; left out when a storyboard panel sets the framing)</label>
      {err && <p className="error-text" role="alert">{err}</p>}
    </section>
  );
}
