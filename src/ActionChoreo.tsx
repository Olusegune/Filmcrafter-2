import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { api, errorText, type ActionList, type ActionPlan, type ActionTypes, type ShotsView } from "./api";
import * as I from "./icons";
import { Sheet } from "./Sheet";
import { actionWords, beatLabel, momentumWords } from "./choreoWords";

/**
 * "Action scene": plan a fight, chase or sports moment as short shots a video model can really make. It plans and shows; nothing is sent anywhere and nothing is bought. Adding the plan to the
 * film creates NEW shots after a shot you choose: no existing shot is changed.
 */
export function ActionChoreo({ dir, shots, characters, onClose, onAdded }: { dir: string; shots: ShotsView; characters: string[]; onClose: () => void; onAdded: () => void }) {
  const [kinds, setKinds] = useState<ActionTypes | null>(null);
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [earlier, setEarlier] = useState<ActionList["plans"]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const scenes = shots.scenes.map((s) => s.number);
  const [form, setForm] = useState({ type: "fight", scene: scenes[0] ?? 1, a: "", b: "", beats: 8, intensity: "grounded", outcome: "a_wins", place: "", weapon: "", variation: 0 });
  const [after, setAfter] = useState("");
  const sceneShots = useMemo(() => shots.shots.filter((s) => s.scene === form.scene), [shots, form.scene]);
  const sceneNames = useMemo(() => [...new Set([...sceneShots.flatMap((s) => s.characters), ...characters])], [sceneShots, characters]);
  const kind = kinds?.types.find((t) => t.id === form.type);
  useEffect(() => { api.filmChoreography<ActionTypes>("types", dir).then(setKinds).catch((e) => setErr(errorText(e))); api.filmChoreography<ActionList>("list", dir).then((l) => setEarlier(l.plans)).catch(() => {}); }, [dir]);
  useEffect(() => { setAfter(sceneShots[sceneShots.length - 1]?.id ?? ""); }, [sceneShots]);

  const split = (v: string) => v.split(/[,;&]|\band\b/).map((x) => x.trim()).filter(Boolean);
  const make = async (variation = form.variation) => {
    setBusy("plan"); setErr("");
    try { setPlan(await api.filmChoreography<ActionPlan>("generate", dir, { type: form.type, scene: form.scene, side_a: split(form.a), side_b: split(form.b), beats: form.beats, intensity: form.intensity, outcome: form.outcome, place: form.place, weapon: form.weapon, variation })); setForm((f) => ({ ...f, variation })); }
    catch (e) { setErr(errorText(e)); }
    setBusy("");
  };
  const edit = async (n: number, patch: Record<string, unknown>) => {
    if (!plan) return;
    try { setPlan(await api.filmChoreography<ActionPlan>("update", dir, { id: plan.id, beats: [{ n, ...patch }] })); } catch (e) { setErr(errorText(e)); }
  };
  const add = async () => {
    if (!plan) return;
    setBusy("add"); setErr("");
    try { const r = await api.filmChoreography<{ plan: ActionPlan; added: string[] }>("apply", dir, { id: plan.id, after }); setPlan(r.plan); onAdded(); } catch (e) { setErr(errorText(e)); }
    setBusy("");
  };
  const open = async (id: string) => { try { setPlan(await api.filmChoreography<ActionPlan>("get", dir, { id })); } catch (e) { setErr(errorText(e)); } };

  return createPortal(                                               // on the page itself: the Shots screen has its own layout, which would push a dialog off-centre
    <Sheet label="Action scene" className="ac" onDismiss={() => !busy && onClose()}>
      <div className="vs-head"><h2>Action scene</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
      {err && <p className="why ac-warn" role="alert">{err}</p>}
      {!plan && kinds && <>
        <p className="ac-lead">Plan a fight, a chase or a sports moment as a run of short shots. Video models draw one clear thing well and long sequences badly, so the plan cuts the action the way an action editor does: the place first, then a swing and its landing in separate shots, a cut to a hand or a face, and the upper hand swinging from one side to the other. It is free and nothing is sent anywhere.</p>
        <div className="ac-kinds" role="radiogroup" aria-label="Kind of action">
          {kinds.types.map((t) => <button key={t.id} role="radio" aria-checked={form.type === t.id} className={`ac-kind ${form.type === t.id ? "on" : ""}`} onClick={() => setForm({ ...form, type: t.id })}>
            <b>{t.label}</b><span>{t.blurb}</span></button>)}
        </div>
        <div className="ac-grid">
          <label className="field"><span>In which scene</span><select className="text-input" value={form.scene} onChange={(e) => setForm({ ...form, scene: Number(e.target.value) })}>{scenes.map((n) => <option key={n} value={n}>Scene {n}</option>)}</select></label>
          <label className="field"><span>{form.type === "chase" || form.type === "vehicle" ? "Who runs (or drives)" : form.type === "sport" ? "The player" : "First side"}</span>
            <input className="text-input" list="ac-names" value={form.a} onChange={(e) => setForm({ ...form, a: e.target.value })} placeholder={sceneNames[0] ?? "A name"} /></label>
          <label className="field"><span>{form.type === "chase" || form.type === "vehicle" ? "Who follows" : form.type === "sport" ? "The opponent (optional)" : "Other side"}</span>
            <input className="text-input" list="ac-names" value={form.b} onChange={(e) => setForm({ ...form, b: e.target.value })} placeholder={sceneNames[1] ?? "A name"} /></label>
          <datalist id="ac-names">{sceneNames.map((n) => <option key={n} value={n} />)}</datalist>
          <label className="field"><span>How it ends</span><select className="text-input" value={form.outcome} onChange={(e) => setForm({ ...form, outcome: e.target.value })}>{kinds.outcomes.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}</select></label>
          <label className="field"><span>How it feels</span><select className="text-input" value={form.intensity} onChange={(e) => setForm({ ...form, intensity: e.target.value })}>{kinds.intensity.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}</select></label>
          <label className="field"><span>How many shots: {form.beats}</span><input type="range" min={kinds.limits.min_beats} max={kinds.limits.max_beats} value={form.beats} onChange={(e) => setForm({ ...form, beats: Number(e.target.value) })} aria-label="How many shots" /></label>
          {(form.type === "armed" || form.type === "vehicle") && <label className="field"><span>{form.type === "armed" ? "The weapon" : "The vehicle"}</span><input className="text-input" value={form.weapon} onChange={(e) => setForm({ ...form, weapon: e.target.value })} placeholder={form.type === "armed" ? "a staff" : "the car"} /></label>}
          <label className="field"><span>Where (optional)</span><input className="text-input" value={form.place} onChange={(e) => setForm({ ...form, place: e.target.value })} placeholder="the scene's place" /></label>
        </div>
        {kind && <p className="why">Good for: {kind.good_for}</p>}
        <div className="cv-actions"><button className="btn primary" disabled={!!busy || !form.a.trim()} onClick={() => void make(0)}>{busy === "plan" ? "Planning…" : "Plan it"}</button>
          <span className="why">Free. The same choices always give the same plan; <b>Try another</b> gives a different one.</span></div>
        {earlier.length > 0 && <details className="ac-earlier"><summary>Earlier plans ({earlier.length})</summary><ul>{earlier.map((p) => <li key={p.id}><button className="link" onClick={() => void open(p.id)}>{actionWords(p.type)} in scene {p.scene}, {p.beats} shots, {p.seconds} s{p.status === "applied" ? " (in the film)" : ""}</button></li>)}</ul></details>}
      </>}
      {plan && <>
        <p className="ac-lead"><b>{actionWords(plan.type)}</b> in scene {plan.scene}: {plan.beats.length} shots, about {plan.seconds} seconds. {plan.status === "applied" ? <>Added to the film as {plan.applied.join(", ")}.</> : "Change any line, then add it to the film."}</p>
        <p className="why"><b>Geography.</b> {plan.geography}</p>
        <ol className="ac-beats">{plan.beats.map((b) => (
          <li key={b.n} className={`ac-beat ${b.kind}`}>
            <div className="ac-head"><b>{b.n}. {beatLabel(b.kind)}</b><span className="dim">{b.framing}, {b.movement}, {b.seconds} s</span><span className={`ac-mom ${b.momentum}`}>{momentumWords(b.momentum, plan.sides.a[0], plan.sides.b[0])}</span></div>
            {plan.status === "applied" ? <p className="ac-text">{b.text}</p>
              : <textarea className="text-input" rows={2} defaultValue={b.text} aria-label={`Shot ${b.n} text`} onBlur={(e) => { if (e.target.value.trim() && e.target.value !== b.text) void edit(b.n, { text: e.target.value }); }} />}
            <div className="dim ac-sound">Sound: {b.sound}</div>
          </li>))}</ol>
        {plan.warnings.map((w) => <p key={w} className="why">{w}</p>)}
        {plan.status !== "applied" && <div className="cv-actions">
          <label className="ac-after">Add after <select className="text-input" value={after} onChange={(e) => setAfter(e.target.value)}>{sceneShots.map((s) => <option key={s.id} value={s.id}>{s.id}{s.title && s.title !== "New shot" ? ` · ${s.title}` : ""}</option>)}</select></label>
          <button className="btn primary" disabled={!!busy} onClick={() => void add()}>{busy === "add" ? "Adding…" : `Add these ${plan.beats.length} shots to the film`}</button>
          <button className="btn" disabled={!!busy} onClick={() => void make(form.variation + 1)}>Try another</button>
          <button className="btn ghost" disabled={!!busy} onClick={() => setPlan(null)}>Back</button>
          <span className="why">New shots only: no existing shot is changed.</span></div>}
        {plan.status === "applied" && <div className="cv-actions"><button className="btn primary" onClick={onClose}>Done</button><button className="btn" onClick={() => setPlan(null)}>Plan another</button></div>}
      </>}
    </Sheet>,
    document.body,
  );
}
