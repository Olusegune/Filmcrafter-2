import { useEffect, useMemo, useRef, useState } from "react";
import type { VoicePerson, VoiceShot, VoiceStatus } from "./api";
import { notifyVoice, useCast } from "./voiceHooks";
import { VoiceMaker } from "./CastVoices";
import { LineStudio } from "./LineStudio";
import { api } from "./api";
import { Waveform } from "./Waveform";

export const VLANE_H = 30;
export const VHEAD_H = 26;          // the band's header row: its name, how many lines are voiced, and Show all
export const VOICE_ROWS = 3;         // lanes shown before "Show all"
export const VOICE_ROWS_MAX = 8;
const GAP = 0.25;          // seconds between two people's recordings in one shot (the engine's own gap)
const SWATCH = ["#e8b45c", "#7fb6e8", "#c78fe0", "#7fe0b0", "#e08f8f", "#e0d27f", "#8fa7e0", "#e0a07f"];

/** Who speaks in the film, in the order they first do. */
export const speakers = (st: VoiceStatus | null): { key: string; name: string }[] => {
  const seen = new Map<string, string>();
  for (const s of st?.shots ?? []) for (const p of s.people ?? []) if (!seen.has(p.key)) seen.set(p.key, p.name);
  return [...seen.entries()].map(([key, name]) => ({ key, name }));
};

/** Where in a shot a person's recording starts: after the people who speak before them (as the film's sound is laid out). */
export const offsetIn = (shot: VoiceShot, key: string): number => {
  let t = 0;
  for (const p of shot.people ?? []) {
    if (p.key === key) return t;
    if (p.recording) t += p.recording.seconds + GAP;
  }
  return t;
};

/**
 * The Voices band under the shots in Edit mode. A header row says how many lines have a voice and opens the band to show everyone; below it one lane for each person who speaks, in a
 * fixed-height area that scrolls on its own (so no one is ever out of reach). A filled clip is a recording (its real waveform); a dashed one is a line with no voice yet, with the words in it.
 * Click a clip for the line editor, drop a file on a clip to give it to that person, click a name to choose, design or clone their voice.
 */
export function VoiceLanes({ dir, st, shots, pps, top, view, rows, open, onToggle }: {
  dir: string; st: VoiceStatus | null; shots: { id: string; start: number; end: number }[]; pps: number; top: number; view: [number, number];
  rows: number; open: boolean; onToggle: () => void;
}) {
  const { cast } = useCast(dir);
  const [studio, setStudio] = useState<{ shot: string; who: string } | null>(null);
  const [making, setMaking] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const scroller = useRef<HTMLDivElement | null>(null);
  const people = useMemo(() => speakers(st), [st]);
  const where = useMemo(() => Object.fromEntries(shots.map((s) => [s.id, s])), [shots]);
  const check = () => { const el = scroller.current; setMore(!!el && el.scrollTop + el.clientHeight < el.scrollHeight - 2); };
  useEffect(() => { check(); }, [people.length, rows, open]);       // eslint-disable-line react-hooks/exhaustive-deps
  if (!people.length) return null;
  const colour = (i: number) => SWATCH[i % SWATCH.length];
  const pin = view[0] + 8;                                          // names stay in view as the timeline scrolls sideways
  const summary = st ? (st.people ? `${st.recorded} of ${st.people} lines voiced` : "") : "";

  return (
    <div className="vl" style={{ top }} aria-label="Voices on the timeline">
      <div className="vl-head" style={{ left: pin }}>
        <b>Voices</b><span className="dim">{summary}</span>
        {people.length > VOICE_ROWS && <button className="link" onClick={onToggle} aria-expanded={open}>{open ? "Show fewer" : `Show all ${people.length}`}</button>}
      </div>
      <div className={`vl-scroll ${more ? "more" : ""}`} ref={scroller} onScroll={check} style={{ maxHeight: rows * VLANE_H }}>
        {people.map((p, i) => {
          const voice = cast?.people[p.key];
          return (
            <div key={p.key} className="vl-lane" style={{ height: VLANE_H, ["--vc" as string]: colour(i) }}>
              <button className={`vl-name ${voice ? "has" : ""}`} style={{ left: pin }} onClick={() => setMaking(p.name)} title={voice ? `${p.name}'s voice: ${voice.voice_name || "chosen"}. Click to change it.` : `Give ${p.name} a voice (from your ElevenLabs library, designed, or cloned from you)`}>
                <i className="vl-dot" /><b>{p.name}</b>{!voice && <span className="vl-plus" aria-label="no voice yet">+</span>}</button>
              {(st?.shots ?? []).filter((s) => (s.people ?? []).some((q) => q.key === p.key)).map((s) => {
                const b = where[s.id];
                const person = s.people.find((q) => q.key === p.key) as VoicePerson;
                if (!b || b.end * pps < view[0] - 200 || b.start * pps > view[1] + 200) return null;
                const left = (b.start + offsetIn(s, p.key)) * pps + 1;
                const room = Math.max(10, (b.end - b.start) * pps - 3);
                const w = person.recording ? Math.max(10, Math.min(person.recording.seconds * pps - 2, Math.max(room, person.recording.seconds * pps))) : room;
                const gen = person.recording?.source === "elevenlabs";
                return (
                  <button key={s.id} data-shot-id={s.id} data-voice-person={p.name} onClick={(e) => { e.stopPropagation(); setStudio({ shot: s.id, who: p.name }); }}
                          className={`vl-clip ${person.recording ? "rec" : "gap"} ${gen ? "gen" : ""} ${w <= 56 ? "narrow" : ""}`} style={{ left, width: w }}
                          title={person.recording ? `${p.name} in ${s.id}: ${person.recording.seconds.toFixed(1)}s${gen ? ", spoken by ElevenLabs" : ", your recording"}. Click to direct it, or drop another file here.` : `${p.name} in ${s.id} has no voice yet: “${person.lines.join(" ")}”. Click, or drop a file here.`}
                          aria-label={`${w > 56 ? (person.recording ? (gen ? "spoken. " : "") : `${person.lines.join(" ") || "no line"}. `) : ""}${p.name}, ${s.id}: ${person.recording ? "recorded" : "no voice yet"}`}>
                    {person.recording ? <Waveform src={api.mediaUrl(`${dir}/${person.recording.file}`)} /> : null}
                    {w > 56 && <span className="vl-text">{person.recording ? (gen ? "spoken" : "") : person.lines.join(" ") || "no line"}</span>}
                  </button>);
              })}
            </div>);
        })}
      </div>
      {studio && <LineStudio dir={dir} shotId={studio.shot} who={studio.who} onClose={() => setStudio(null)} />}
      {making && cast && <VoiceMaker dir={dir} person={making} cast={cast} plan={null} onClose={() => setMaking(null)} onDone={() => { setMaking(null); notifyVoice(); }} />}
    </div>);
}
