import { useState } from "react";
import { api, type ModelInput } from "./api";
import "./acting.css";

const ROLE_NAME: Record<string, string> = { first_frame: "First frame", reference: "Reference", end_frame: "End frame", audio: "Your recording" };

/**
 * What the video model is given for this shot, as pictures in the order it gets them: the first frame, each reference picture, the end frame, and your recording of the voice.
 * A picture the model will not take (it refuses references beside a first frame, or takes only so many) is shown dimmed and marked, so nothing is guesswork.
 */
export function GivenToModel({ dir, inputs }: { dir: string; inputs: ModelInput[] }) {
  const [big, setBig] = useState<string | null>(null);
  if (!inputs.length) return null;
  const sent = inputs.filter((i) => i.sent).length;
  return (
    <section className="mi" aria-label="What the model is given">
      <h4>What the model is given <span className="dim">· {sent} of {inputs.length} used</span></h4>
      <ul className="mi-row">
        {inputs.map((i, k) => (
          <li key={k} className={`mi-item ${i.sent ? "" : "off"} role-${i.role}`}>
            {i.path
              ? <button className="mi-thumb" onClick={() => setBig(big === i.path ? null : i.path)} aria-label={`${i.label}${i.sent ? "" : " (not used by this model)"}: show larger`} aria-pressed={big === i.path}>
                  <img src={api.mediaUrl(`${dir}/${i.path}`)} alt="" draggable={false} /></button>
              : <span className="mi-thumb mi-audio" aria-hidden>♪</span>}
            <span className="mi-role">{ROLE_NAME[i.role] ?? i.role}</span>
            <span className="mi-label" title={i.label}>{i.label}</span>
            {!i.sent && <span className="mi-off">not used: this model won't take it here</span>}
          </li>))}
      </ul>
      {big && <img className="mi-big" src={api.mediaUrl(`${dir}/${big}`)} alt="The picture, larger" onClick={() => setBig(null)} />}
    </section>
  );
}
