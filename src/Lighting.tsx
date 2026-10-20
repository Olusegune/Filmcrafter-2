import { useCallback, useEffect, useMemo, useState } from "react";
import { Sheet } from "./Sheet";
import { api, errorText, fmtTime, type LightShot, type LightingPlan } from "./api";
import * as I from "./icons";
import { applySentence, groupRuns, lightColour, runName, runTick, sceneLine, targets, type LightRun } from "./lightingView";

/** The strip of light across the film: one block per shot, as wide as the shot is long, coloured by the planned light. */
export function LightStrip({ shots, onPick }: { shots: LightShot[]; onPick?: (id: string) => void }) {
  const total = Math.max(0.1, shots.reduce((a, s) => a + Math.max(0.1, s.end - s.start), 0));
  return (
    <div className="lt-strip" role="group" aria-label={`The planned light across ${shots.length} shots`}>
      {shots.map((s) => (
        <button key={s.shot} className={`lt-seg ${s.user_set ? "own" : ""}`} onClick={() => onPick?.(s.shot)}
                style={{ flexGrow: Math.max(0.1, s.end - s.start) / total * 1000, background: lightColour(s) }}
                title={`${s.shot} · ${s.label} · ${s.design.label}, about ${s.design.kelvin} K`} aria-label={`${s.shot}: ${s.label}, ${s.design.label}`} />))}
    </div>
  );
}

/** One run of shots that share a light: a single quiet line, with the reasoning and the exact words one click away. */
function Run({ run, ticked, onToggle, onShow }: { run: LightRun; ticked: ReadonlySet<string>; onToggle: (id: string) => void; onShow: (id: string) => void }) {
  const f = run.first;
  const tick = runTick(run, ticked);
  const toggleAll = () => { const want = tick !== "all"; for (const s of run.shots) if (ticked.has(s.shot) !== want) onToggle(s.shot); };
  return (
    <div className="lt-runrow">
    <input type="checkbox" className="lt-tick" checked={tick === "all"} ref={(el) => { if (el) el.indeterminate = tick === "some"; }} onChange={toggleAll}
           aria-label={`Select ${runName(run)}`} />
    <details className={`lt-run ${tick === "none" ? "" : "on"}`} id={`lt-${f.shot}`}>
      <summary>
        <span className="lt-swatch" style={{ background: lightColour(f) }} aria-hidden="true" />
        <span className="lt-name"><b className="num">{runName(run)}</b><span className="dim num">{fmtTime(f.start)}{run.shots.length > 1 ? ` · ${run.shots.length} shots` : ""}</span></span>
        <span className="chip">{f.label}</span>
        <span className="lt-light">{f.design.label} · {f.design.kelvin} K</span>
        {run.own && <span className="chip warn" title="You chose this light yourself">your choice</span>}
        {run.held && <span className="chip" title="Held at the scene's mood so the light doesn't flicker">held steady</span>}
        <span className="lt-chev" aria-hidden="true" />
      </summary>
      <div className="lt-detail">
        <p className="lt-why">{f.why}</p>
        <p className="lt-words">{f.design.wording}</p>
        <ul className="lt-shots">{run.shots.map((s) => (
          <li key={s.shot}><label><input type="checkbox" checked={ticked.has(s.shot)} onChange={() => onToggle(s.shot)} aria-label={`Select shot ${s.shot}`} /> <b className="num">{s.shot}</b> <span className="dim num">{fmtTime(s.start)}</span></label>
            <button className="link" onClick={() => onShow(s.shot)}>Show</button></li>))}</ul>
      </div>
    </details>
    </div>
  );
}

/** Light the story: the mood the app read in every shot and the light it plans for it, scene by scene. Apply all, or only the shots you tick. */
export function LightingSheet({ dir, onClose, onChanged, onSelect }: { dir: string; onClose: () => void; onChanged?: () => void; onSelect?: (id: string) => void }) {
  const [plan, setPlan] = useState<LightingPlan | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");
  const [err, setErr] = useState("");
  const [canUndo, setCanUndo] = useState(false);
  const load = useCallback(() => api.lighting<LightingPlan>(dir, "plan").then(setPlan).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => { load(); }, [load]);

  const pick = useMemo(() => (plan ? targets(plan, ticked, overwrite) : null), [plan, ticked, overwrite]);
  const toggle = (id: string) => setTicked((t) => { const n = new Set(t); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const run = async (what: "apply" | "undo") => {
    setBusy(true); setErr(""); setDone("");
    try {
      if (what === "apply") {
        const r = await api.lighting<{ changed: string[]; skipped: string[] }>(dir, "apply", { shots: ticked.size ? [...ticked] : undefined, overwrite });
        setDone(`Planned light written to ${r.changed.length} shot${r.changed.length === 1 ? "" : "s"}${r.skipped.length ? `; ${r.skipped.length} you chose yourself were left alone` : ""}. Render a shot again to see its new light.`);
        setCanUndo(r.changed.length > 0); setTicked(new Set());
      } else {
        const r = await api.lighting<{ restored: string[]; more: boolean }>(dir, "undo");
        setDone(`Put back ${r.restored.length} shot${r.restored.length === 1 ? "" : "s"} as they were.`); setCanUndo(r.more);
      }
      await load(); onChanged?.();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };

  const byScene = useMemo(() => {
    const m = new Map<number, LightShot[]>();
    for (const s of plan?.shots ?? []) m.set(s.scene, [...(m.get(s.scene) ?? []), s]);
    return [...m.entries()];
  }, [plan]);

  return (
    <Sheet label="Light the story" className="lighting-sheet" onDismiss={onClose}>
        <div className="rv-head">
          <div>
            <h2>Light the story</h2>
            <p className="sub">The app reads the mood of every shot and plans the light to match. A scene keeps one light unless the mood really turns.</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close /></button>
        </div>
        {!plan && !err && <div className="dim" style={{ padding: 16 }}><span className="spin sm" /> Reading the mood of each shot…</div>}
        {plan && !plan.count && <div className="review-empty">There is no shot plan yet. Press Direct My Video first.</div>}
        {plan && plan.count > 0 && pick && <>
          <LightStrip shots={plan.shots} onPick={(id) => document.getElementById(`lt-${id}`)?.scrollIntoView({ block: "center", behavior: "smooth" })} />
          <div className="lt-legend dim">Each block is one shot, coloured by its light and mood. Click one to jump to it.</div>
          <div className="lt-list">
            {byScene.map(([scene, rows]) => {
              const info = plan.scenes.find((x) => x.scene === scene);
              return (
                <section key={scene} className="lt-scene">
                  <h3 className="lt-scene-h">Scene {scene}<span className="dim">{[info?.heading, info ? sceneLine(info) : ""].filter(Boolean).join(" · ")}</span></h3>
                  {groupRuns(rows).map((run) => <Run key={run.first.shot} run={run} ticked={ticked} onToggle={toggle} onShow={(id) => { onSelect?.(id); onClose(); }} />)}
                </section>);
            })}
          </div>
          <div className="lt-foot">
            <p className="lt-apply" role="status">{applySentence(pick, ticked.size, overwrite)}</p>
            {plan.user_set > 0 && <label className="lt-over"><input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} /> Also replace the {plan.user_set} light{plan.user_set === 1 ? "" : "s"} I chose myself</label>}
            <div className="lt-buttons">
              {canUndo && <button className="btn ghost" disabled={busy} onClick={() => run("undo")}>Undo</button>}
              {ticked.size > 0 && <button className="btn ghost" onClick={() => setTicked(new Set())}>Clear selection</button>}
              <button className="btn primary" disabled={busy || !pick.targets.length} onClick={() => run("apply")}>
                {ticked.size ? `Use for ${pick.targets.length} selected` : `Use the plan for all ${pick.targets.length}`}</button>
            </div>
          </div>
        </>}
        {done && <div className="note ok" role="status"><I.Check size={14} /> {done}</div>}
        {err && <div className="error-text" role="alert">{err}</div>}
    </Sheet>
  );
}
