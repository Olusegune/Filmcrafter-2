import { useCallback, useEffect, useRef, useState } from "react";
import type { Version } from "./api";
import { atEnd, clampTime, compareFacts, fmtClock, needsResync, RATES, stepTime } from "./compareMath";
import * as I from "./icons";

type Side = "off" | "a" | "b";

/**
 * Two takes of one shot, side by side, on ONE clock: play, pause, scrub, step a frame and change the speed for both together, so a difference in the acting, the light or the ending is
 * a difference you can see rather than two videos drifting apart. The clip that is longer sets the clock; the shorter one holds its last frame when it ends.
 */
export function TakeCompare({ left, right, src, busy, locked, onUse, onSwap }: {
  left: Version | null; right: Version | null; src: (v: Version) => string | null; busy: boolean; locked: boolean;
  onUse: (v: Version) => void; onSwap: () => void;
}) {
  const aRef = useRef<HTMLVideoElement>(null);
  const bRef = useRef<HTMLVideoElement>(null);
  const [lenA, setLenA] = useState<number | null>(null);
  const [lenB, setLenB] = useState<number | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState<number>(1);
  const [loop, setLoop] = useState(true);
  const [sound, setSound] = useState<Side>("off");
  const dur = Math.max(lenA ?? 0, lenB ?? 0);
  const srcA = left ? src(left) : null, srcB = right ? src(right) : null;
  const vids = () => [aRef.current, bRef.current].filter((v): v is HTMLVideoElement => !!v);

  // a different take on either side starts over
  useEffect(() => { setLenA(null); setT(0); setPlaying(false); }, [srcA]);
  useEffect(() => { setLenB(null); setT(0); setPlaying(false); }, [srcB]);

  const seek = useCallback((x: number) => {
    const c = clampTime(x, dur);
    for (const v of vids()) v.currentTime = Math.min(c, v.duration || c);
    setT(c);
  }, [dur]);   // eslint-disable-line react-hooks/exhaustive-deps

  const play = useCallback(() => {
    if (atEnd(t, dur)) seek(0);
    for (const v of vids()) v.play().catch(() => {});
    setPlaying(true);
  }, [t, dur, seek]);   // eslint-disable-line react-hooks/exhaustive-deps
  const pause = useCallback(() => { for (const v of vids()) v.pause(); setPlaying(false); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { for (const v of vids()) v.playbackRate = rate; }, [rate, srcA, srcB]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (aRef.current) aRef.current.muted = sound !== "a"; if (bRef.current) bRef.current.muted = sound !== "b"; }, [sound, srcA, srcB]);

  // the clock follows the longer clip while playing; the other is pulled back if it drifts, and at the end both loop or stop together.
  // It runs on every animation frame and also whenever a video reports its time, so a window that is not drawing (hidden, minimised) still keeps the two together.
  const sync = useCallback(() => {
    const longA = (lenA ?? 0) >= (lenB ?? 0);
    const master = longA ? aRef.current : bRef.current, other = longA ? bRef.current : aRef.current;
    if (!master) return;
    const now = master.currentTime;
    setT(now);
    if (other && needsResync(now, other.currentTime, other.duration || now)) other.currentTime = Math.min(now, other.duration || now);
    if (atEnd(now, dur) || master.ended) {
      if (loop) { seek(0); for (const v of vids()) v.play().catch(() => {}); } else { pause(); setT(dur); }
    }
  }, [lenA, lenB, dur, loop, seek, pause]);   // eslint-disable-line react-hooks/exhaustive-deps
  const syncRef = useRef(sync);
  syncRef.current = sync;
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => { syncRef.current(); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const step = (dir: 1 | -1) => { pause(); seek(stepTime(t, dir, dur)); };
  const facts = left && right ? compareFacts(left, right, lenA, lenB) : [];
  const caption = (v: Version | null) => v && (
    <figcaption><b>v{v.n}</b> · <span className="num">{v.model.split("/").slice(-2).join("/")}</span>
      {v.approved ? <span className="chip ready"><I.Check size={10} /> In the video</span>
        : v.state === "ready" && <button className="btn primary sm" disabled={busy || locked} onClick={() => onUse(v)}>Use this one</button>}
      </figcaption>);

  return (
    <div className="tc">
      <div className="vs-compare">
        {([[left, "a", srcA, aRef, setLenA], [right, "b", srcB, bRef, setLenB]] as const).map(([v, which, s, ref, setLen]) => (
          <figure key={which} className="vs-cmp">
            {v && s ? <video key={v.id} ref={ref} src={s} muted loop={false} playsInline preload="auto" onLoadedMetadata={(e) => setLen((e.target as HTMLVideoElement).duration)} onTimeUpdate={() => { if (playing) syncRef.current(); }} onEnded={() => { if (playing) syncRef.current(); }} />
              : <div className="ph big">{v ? "No video to show" : which === "b" ? "Click a version on the right" : "Pick a version"}</div>}
            {caption(v)}
          </figure>))}
      </div>
      {left && right && <>
        <div className="tc-bar" role="group" aria-label="Playback for both takes">
          <button className="btn small" onClick={playing ? pause : play} aria-label={playing ? "Pause both" : "Play both"}>{playing ? "Pause" : "Play"}</button>
          <button className="btn ghost small" onClick={() => step(-1)} aria-label="Back one frame" title="Back one frame">◂ Frame</button>
          <button className="btn ghost small" onClick={() => step(1)} aria-label="Forward one frame" title="Forward one frame">Frame ▸</button>
          <input type="range" className="tc-scrub" min={0} max={dur || 1} step={0.01} value={Math.min(t, dur || 1)} aria-label="Position in both takes"
                 onChange={(e) => { pause(); seek(Number(e.target.value)); }} />
          <span className="num tc-time">{fmtClock(t)} / {fmtClock(dur)}</span>
          <label className="tc-rate">Speed <select value={rate} onChange={(e) => setRate(Number(e.target.value))} aria-label="Speed">{RATES.map((r) => <option key={r} value={r}>{r}×</option>)}</select></label>
          <label className="tc-loop"><input type="checkbox" checked={loop} onChange={(e) => setLoop(e.target.checked)} /> Loop</label>
          <span className="tc-sound" role="group" aria-label="Sound">Sound
            {(["off", "a", "b"] as Side[]).map((k) => <button key={k} className={sound === k ? "on" : ""} aria-pressed={sound === k} onClick={() => setSound(k)} title={k === "off" ? "Silent" : `Hear the ${k === "a" ? "left" : "right"} take's own sound`}>{k === "off" ? "Off" : k === "a" ? "Left" : "Right"}</button>)}</span>
          <button className="btn ghost small" onClick={onSwap} title="Swap the two takes">⇄ Swap</button>
        </div>
        <table className="tc-facts"><tbody>
          <tr><th scope="row" /><th scope="col">Left · v{left.n}</th><th scope="col">Right · v{right.n}</th></tr>
          {facts.map((f) => <tr key={f.label} className={f.differs ? "differs" : ""}><th scope="row">{f.label}</th><td>{f.a}</td><td>{f.b}{f.note ? <span className="dim"> · {f.note}</span> : null}</td></tr>)}
        </tbody></table>
      </>}
    </div>
  );
}
