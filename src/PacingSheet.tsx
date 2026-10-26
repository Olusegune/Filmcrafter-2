import { useEffect, useState } from "react";
import { api, errorText, type PacingReport } from "./api";
import * as I from "./icons";
import { Sheet } from "./Sheet";
import { levelWords, rhythmHeight } from "./pacingWords";

/**
 * "Pacing": the rhythm of the film's cuts, scene by scene, and the places where it works against the story, each with a reason and a suggestion. It reads the shots as they are and changes
 * nothing; a finding can take you to its shot. Free: nothing is sent anywhere.
 */
export function PacingSheet({ dir, onClose, onGo }: { dir: string; onClose: () => void; onGo: (shot: string) => void }) {
  const [r, setR] = useState<PacingReport | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.filmPacing(dir).then(setR).catch((e) => setErr(errorText(e))); }, [dir]);
  const longest = r ? Math.max(...r.scenes.flatMap((s) => s.bars.map((b) => b.seconds)), 1) : 1;
  return (
    <Sheet label="Pacing" className="pc" onDismiss={onClose}>
      <div className="vs-head"><h2>Pacing</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
      {err && <p className="why" role="alert">{err}</p>}
      {!r && !err && <p className="why">Reading the cuts…</p>}
      {r && <>
        <p className="pc-lead">{r.film.shots} shots, {Math.round(r.film.seconds)} seconds. The average shot is <b>{r.film.asl} s</b> (shortest {r.film.shortest} s, longest {r.film.longest} s).
          {r.counts.fix + r.counts.look + r.counts.note === 0 ? " Nothing stands out: the rhythm looks even." : <> <b>{r.counts.fix}</b> to fix, <b>{r.counts.look}</b> worth a look, <b>{r.counts.note}</b> notes.</>}</p>
        <div className="pc-scenes" role="list" aria-label="The rhythm of each scene">
          {r.scenes.map((s) => (
            <div key={s.number} className="pc-scene" role="listitem">
              <div className="pc-name">Scene {s.number} <span className="dim">{s.shots} shots, {s.seconds} s, average {s.asl} s</span></div>
              <div className="pc-bars" aria-hidden="true">{s.bars.map((b) => <button key={b.id} className="pc-bar" style={{ height: `${rhythmHeight(b.seconds, longest)}%` }} title={`${b.id}: ${b.seconds} s`} onClick={() => onGo(b.id)} />)}</div>
            </div>))}
        </div>
        {r.findings.length > 0 && <ul className="pc-list">{r.findings.map((f, i) => (
          <li key={i} className={`pc-item ${f.level}`}>
            <span className="pc-level">{levelWords(f.level)}</span>
            <div className="pc-main"><b>{f.what}</b><p className="why">{f.why}</p><p className="why"><i>{f.tip}</i></p></div>
            {f.shot && <button className="btn ghost sm" onClick={() => onGo(f.shot!)}>Go to {f.shot}</button>}
          </li>))}</ul>}
        <p className="why">{r.note}</p>
      </>}
      <div className="cv-actions"><button className="btn" onClick={onClose}>Close</button></div>
    </Sheet>
  );
}
