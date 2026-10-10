import { useState } from "react";
import type { ShotContract } from "./api";
import * as I from "./icons";

type Proposal = Record<string, unknown>;

/** What the helper suggested for one shot: the acting, the camera and the light as three choices, each with its reason. Nothing is applied until you press Use. */
export function ShotSuggestionSheet({ shot, proposal, current, onClose, onUse }: { shot: string; proposal: Proposal; current: ShotContract; onClose: () => void; onUse: (patch: Record<string, unknown>) => void }) {
  const beats = (proposal.beats as Record<string, string>[]) ?? [];
  const acting = !!(proposal.emotional_intention || beats.length || proposal.micro_animation);
  const cam = proposal.camera as Record<string, string> | undefined;
  const lit = proposal.lighting as { description?: string; why?: string } | undefined;
  const haveActing = !!(current.performance.emotional_intention || current.performance.beats.length || current.performance.micro_animation);
  const haveCam = !!(current.camera.angle !== "eye level" || current.camera.lens || current.camera.focus || current.camera.why);
  const haveLit = !!current.lighting.description;
  const [on, setOn] = useState({ acting: !haveActing, camera: !haveCam, light: !haveLit });
  const use = () => {
    const patch: Record<string, unknown> = {};
    if (on.acting && acting) patch.performance = { ...(proposal.emotional_intention ? { emotional_intention: proposal.emotional_intention } : {}), ...(beats.length ? { beats } : {}), ...(proposal.micro_animation ? { micro_animation: proposal.micro_animation } : {}) };
    if (on.camera && cam) patch.camera = cam;
    if (on.light && lit) patch.lighting = lit;
    onUse(patch);
  };
  const count = [on.acting && acting, on.camera && !!cam, on.light && !!lit].filter(Boolean).length;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass as-sheet" role="dialog" aria-label={`Suggestions for shot ${shot}`} onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2><I.Sparkle size={16} /> Suggestions for shot {shot}</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">Written from the story and your Bible. Choose what to use; what you already set is marked and kept unless you tick the suggestion. You can change any of it afterwards.</p>
        <div className="as-rows">
          {acting && <label className={`as-row ${on.acting ? "on" : ""}`}><input type="checkbox" checked={on.acting} onChange={(e) => setOn({ ...on, acting: e.target.checked })} />
            <span className="as-label">Feeling and acting{haveActing && <em> · you have set this already</em>}</span>
            <div className="as-body">{proposal.emotional_intention ? <p><b>The audience should feel:</b> {String(proposal.emotional_intention)}</p> : null}
              {beats.map((b, i) => <p key={i}><b>{b.character || "Someone"}:</b> {b.what}. <span className="dim">Wants {b.want || "nothing stated"}; hides {b.hiding || "nothing stated"}; {[b.start, b.turn, b.end].filter(Boolean).join(" → ")}.</span></p>)}
              {proposal.micro_animation ? <p className="dim">Small motion: {String(proposal.micro_animation)}</p> : null}</div></label>}
          {cam && <label className={`as-row ${on.camera ? "on" : ""}`}><input type="checkbox" checked={on.camera} onChange={(e) => setOn({ ...on, camera: e.target.checked })} />
            <span className="as-label">Camera{haveCam && <em> · you have set this already</em>}</span>
            <div className="as-body"><p>{[cam.framing, cam.angle, cam.lens, cam.movement, cam.focus && `${cam.focus} focus`].filter(Boolean).join(" · ")}</p>{cam.why && <p className="dim">{cam.why}</p>}</div></label>}
          {lit && <label className={`as-row ${on.light ? "on" : ""}`}><input type="checkbox" checked={on.light} onChange={(e) => setOn({ ...on, light: e.target.checked })} />
            <span className="as-label">Light{haveLit && <em> · you have set this already</em>}</span>
            <div className="as-body"><p>{lit.description}</p>{lit.why && <p className="dim">{lit.why}</p>}</div></label>}
        </div>
        <div className="sheet-actions"><button className="btn ghost" onClick={onClose}>Not now</button><button className="btn primary" onClick={use} disabled={count === 0}>Use {count} {count === 1 ? "part" : "parts"}</button></div>
      </div>
    </div>
  );
}
