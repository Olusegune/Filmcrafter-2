import { useEffect, useState } from "react";

/**
 * J and L cuts for a shot's dialogue. A **J cut** lets the line start a little before its picture appears (you hear the next person before you see them); an **L cut** lets the line carry on over the
 * next picture (you stay with the speaker's voice while the film shows the listener). Both are how real films cut a conversation. It is applied when the film is put together: the recording is not
 * changed and the picture stays exactly where it is. Free: nothing is sent anywhere.
 */
export function SoundCut({ lead, tail, max, onChange }: { lead: number; tail: number; max: number; onChange: (v: { lead?: number; tail?: number }) => void }) {
  const [l, setL] = useState(lead);
  const [t, setT] = useState(tail);
  useEffect(() => { setL(lead); setT(tail); }, [lead, tail]);
  const commit = (k: "lead" | "tail", v: number) => onChange({ [k]: v });
  return (
    <section className="sound-cut" aria-label="J and L cuts">
      <h4>Sound and picture <span className="dim">J and L cuts for this shot's dialogue</span></h4>
      <label className="field"><span>The line starts before the picture: {l.toFixed(1)} s <span className="dim">(a J cut)</span></span>
        <input type="range" min={0} max={max} step={0.1} value={l} aria-label="How long the line leads its picture" onChange={(e) => setL(Number(e.target.value))} onPointerUp={() => commit("lead", l)} onKeyUp={() => commit("lead", l)} /></label>
      <label className="field"><span>The line carries on over the next picture: {t.toFixed(1)} s <span className="dim">(an L cut)</span></span>
        <input type="range" min={0} max={max} step={0.1} value={t} aria-label="How long the line trails into the next picture" onChange={(e) => setT(Number(e.target.value))} onPointerUp={() => commit("tail", t)} onKeyUp={() => commit("tail", t)} /></label>
      <p className="dim">Used when the film is exported. The recording and the picture are not changed.</p>
    </section>
  );
}
