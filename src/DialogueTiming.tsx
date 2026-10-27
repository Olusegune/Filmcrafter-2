import { useEffect, useRef, useState } from "react";
import { api, type SoundPlan } from "./api";
import { barStyle, scaleOf } from "./timingWords";

type Row = SoundPlan["shots"][number];
const SWATCH = ["#e8b45c", "#7fb6e8", "#c78fe0", "#7fe0b0", "#e08f8f", "#e0d27f", "#8fa7e0", "#e0a07f"];

/**
 * Dialogue timing: for every shot with a voice, a strip that shows the picture, where each person's voice falls in it (as the film's mix lays it out), the J cut before and the L cut after,
 * and a warning when the voices run past the end. Play reads the shot's recordings aloud in order, so a scene can be heard as a table read. A voice with no recording yet is hatched: its
 * length is an estimate from its words. It only reads; nothing is changed or made.
 */
export function DialogueTiming({ dir, shots, onGo }: { dir: string; shots: Row[]; onGo: (shot: string) => void }) {
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const run = useRef(0);
  useEffect(() => () => { run.current++; audio.current?.pause(); }, []);
  const stop = () => { run.current++; audio.current?.pause(); setPlaying(null); };
  const play = async (row: Row) => {
    stop();
    const mine = ++run.current;
    setPlaying(row.shot);
    for (const seg of row.timing.segments) {
      if (!seg.file || run.current !== mine) continue;
      const a = new Audio(api.mediaUrl(`${dir}/${seg.file}`));
      audio.current = a;
      await new Promise<void>((done) => { a.onended = () => done(); a.onerror = () => done(); a.play().catch(() => done()); });
    }
    if (run.current === mine) setPlaying(null);
  };
  const withVoices = shots.filter((s) => s.timing.segments.length);
  if (!withVoices.length) return <p className="why">No shot has a voice or a line to place yet.</p>;
  const scale = scaleOf(withVoices.map((s) => ({ lead: s.timing.lead, seconds: s.seconds, tail: s.timing.tail, end: s.timing.end })));
  return (
    <ul className="dt-list" aria-label="When each voice falls in each shot">
      {withVoices.map((s) => {
        const names = [...new Set(s.timing.segments.map((x) => x.speaker))];
        return (
          <li key={s.shot} className={`dt-item ${s.timing.over > 0.05 ? "over" : ""}`}>
            <div className="dt-head"><b>{s.shot}</b> <span className="dim">{s.title} · {s.seconds.toFixed(1)} s{s.timing.lead ? ` · starts ${s.timing.lead} s early` : ""}{s.timing.tail ? ` · runs ${s.timing.tail} s on` : ""}</span>
              <span style={{ flex: 1 }} />
              {s.timing.segments.some((x) => x.file) && <button className="link" onClick={() => (playing === s.shot ? stop() : void play(s))}>{playing === s.shot ? "Stop" : "Play the voices"}</button>}
              <button className="link" onClick={() => onGo(s.shot)}>Go to {s.shot}</button></div>
            <div className="dt-strip" role="img" aria-label={`${s.shot}: ${s.timing.segments.map((x) => `${x.speaker} from ${x.start.toFixed(1)} to ${(x.start + x.seconds).toFixed(1)} s${x.estimated ? " (estimated)" : ""}`).join("; ")}${s.timing.over > 0.05 ? `. The voices run ${s.timing.over} s past the end.` : ""}`}>
              <span className="dt-pic" style={barStyle(scale, 0, s.seconds)} />
              {s.timing.tail > 0 && <span className="dt-tail" style={barStyle(scale, s.seconds, s.timing.tail)} />}
              {s.timing.segments.map((x, i) => (
                <span key={i} className={`dt-seg ${x.estimated ? "est" : ""}`} style={{ ...barStyle(scale, x.start, x.seconds), ["--vc" as string]: SWATCH[names.indexOf(x.speaker) % SWATCH.length] }} title={`${x.speaker}: ${x.seconds.toFixed(1)} s${x.estimated ? ", estimated from the words" : ""}`}>{x.speaker}</span>))}
            </div>
            {s.timing.over > 0.05 && <p className="why dt-warn">The voices run {s.timing.over.toFixed(1)} s past the end of the shot{s.timing.tail ? " and its tail" : ""}: they are cut there.</p>}
          </li>);
      })}
    </ul>
  );
}
