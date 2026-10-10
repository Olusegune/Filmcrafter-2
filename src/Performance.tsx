import { useCallback, useEffect, useState } from "react";
import { api, errorText } from "./api";
import * as I from "./icons";
import { PanelHead } from "./Dock";
import { ArcSection, BeatsPanel, GesturesSection } from "./ActingDepth";

export type PerfData = { profiles: { id: string; label: string; blurb: string }[]; default: string;
  scenes: Record<string, string>; characters: Record<string, string>; shots: Record<string, string>; set: boolean;
  /** shots whose dance direction was chosen: always ("on") or never ("off"); any other shot decides from its own text */
  dance?: Record<string, "on" | "off"> };

export function usePerformance(dir: string) {
  const [p, setP] = useState<PerfData | null>(null);
  const load = useCallback(() => api.performance<PerfData>(dir, "get").then(setP).catch(() => {}), [dir]);
  useEffect(() => { load(); }, [load]);
  const set = useCallback(async (data: Record<string, unknown>) => setP(await api.performance<PerfData>(dir, "set", data)), [dir]);
  return { perf: p, setPerf: set, reloadPerf: load };
}

const BIG: Record<string, number> = { restrained: 1, natural: 2, expressive: 3, dramatic: 4, energetic: 5 };   // how big the acting is, for the little meter on each card
const overrides = (p: PerfData) => Object.values(p.characters).filter((v) => v !== "inherit").length + Object.values(p.scenes).filter((v) => v !== "inherit").length;

/** Acting: the project's performance profile, with overrides per scene and per character. */
export function PerformanceSheet({ dir, scenes, characters, onClose, onChanged }: {
  dir: string; scenes: { number: number; heading: string }[]; characters: string[]; onClose: () => void; onChanged: () => void;
}) {
  const { perf, setPerf } = usePerformance(dir);
  const [err, setErr] = useState("");
  const set = async (data: Record<string, unknown>) => { setErr(""); try { await setPerf(data); onChanged(); } catch (e) { setErr(errorText(e)); } };
  const label = (id: string) => perf?.profiles.find((x) => x.id === id)?.label ?? id;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass perf-sheet" role="dialog" aria-label="Acting" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Acting</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">How big the performances are, with the small living motion between actions: blinks, breathing, weight shifts. It goes into every new keyframe and video prompt. Free to change.</p>
        {err && <div className="error-text">{err}</div>}
        {!perf ? <div className="dim">Loading…</div> : <>
          <h3 className="perf-h">For the whole video</h3>
          <div className="perf-cards" role="radiogroup">{perf.profiles.map((p) => (
            <button key={p.id} role="radio" aria-checked={perf.set && perf.default === p.id}
                    className={`perf-card ${perf.set && perf.default === p.id ? "on" : ""}`} onClick={() => set({ default: p.id })}>
              <span className="perf-meter" aria-hidden="true">{[1, 2, 3, 4, 5].map((n) => <i key={n} className={n <= (BIG[p.id] ?? 2) ? "on" : ""} />)}</span>
              <b>{p.label}</b><span>{p.blurb}</span></button>))}</div>
          {!perf.set && <p className="dim">Not chosen yet: prompts carry each shot's own acting direction, but no blinks, breathing or weight shifts, until you pick one.</p>}
          <details className="perf-more" open={Object.keys(perf.characters).some((k) => perf.characters[k] !== "inherit") || Object.keys(perf.scenes).some((k) => perf.scenes[k] !== "inherit")}>
            <summary>Different for one character or scene{overrides(perf) ? <span className="dim"> ({overrides(perf)} set)</span> : null}</summary>
          <div className="perf-grid">
            <div>
              <h3 className="perf-h">By character</h3>
              {characters.length === 0 ? <p className="dim">No characters in the plan.</p> : characters.map((n) => (
                <div key={n} className="perf-row"><span>{n}</span>
                  <select value={perf.characters[n] ?? "inherit"} onChange={(e) => set({ characters: { [n]: e.target.value } })}>
                    <option value="inherit">Same as the video ({label(perf.default)})</option>
                    {perf.profiles.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></div>))}
            </div>
            <div>
              <h3 className="perf-h">By scene</h3>
              {scenes.map((s) => (
                <div key={s.number} className="perf-row"><span className="perf-scene"><span className="num">{s.number}</span> {s.heading}</span>
                  <select value={perf.scenes[String(s.number)] ?? "inherit"} onChange={(e) => set({ scenes: { [s.number]: e.target.value } })}>
                    <option value="inherit">Inherit</option>
                    {perf.profiles.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></div>))}
            </div>
          </div>
          <p className="dim">A shot's own choice (in its panel) wins, then the scene, then the character, then the whole video.</p></details>
          <details className="perf-more"><summary>Emotional arc <span className="dim">how each character's feeling travels through the film</span></summary>
            <ArcSection dir={dir} onChanged={onChanged} /></details>
          <details className="perf-more"><summary>Signature gestures <span className="dim">the small habits that make a character themselves</span></summary>
            <GesturesSection dir={dir} onChanged={onChanged} /></details>
        </>}
      </div>
    </div>
  );
}

/** In the shot panel: this shot's acting profile. */
export function ShotPerformance({ dir, shotId, onChanged, film }: { dir: string; shotId: string; onChanged: () => void; film?: boolean }) {
  const { perf, setPerf } = usePerformance(dir);
  if (!perf) return null;
  return <>
    <ShotPerformanceView perf={perf} shotId={shotId} noDance={film}
                         onProfile={async (v) => { await setPerf({ shots: { [shotId]: v } }); onChanged(); }}
                         onDance={async (v) => { await setPerf({ dance: { [shotId]: v } }); onChanged(); }}
                         onUseNatural={async () => { await setPerf({ default: "natural" }); onChanged(); }} />
    <BeatsPanel dir={dir} shotId={shotId} onChanged={onChanged} />
  </>;
}

/** What is drawn: the acting profile for this shot, and whether it gets the project's dance direction. */
export function ShotPerformanceView({ perf, shotId, onProfile, onDance, onUseNatural, noDance }: { perf: PerfData; shotId: string; noDance?: boolean; onProfile: (v: string) => void; onDance: (v: string) => void; onUseNatural?: () => void }) {
  return (
    <section className="panel">
      <PanelHead icon={<I.Mask size={18} />} title="Acting" tag="Free" tone="free" hint="How the performers play this shot." />
      {!perf.set && <p className="dim perf-none" role="note">No acting style is chosen for this project yet, so prompts carry no blinks, breathing or weight shifts. Choose one under Acting on the left.
        {onUseNatural && <> <button className="btn small" onClick={onUseNatural}>Use Natural for this project</button></>}</p>}
      <select className="perf-shot" value={perf.shots[shotId] ?? "inherit"} aria-label="Acting style for this shot" onChange={(e) => onProfile(e.target.value)}>
        <option value="inherit">Inherit (scene, character or video)</option>
        {perf.profiles.map((p) => <option key={p.id} value={p.id}>{p.label}: {p.blurb.split(".")[0]}</option>)}
      </select>
      {!noDance && <label className="dim perf-dance-label" htmlFor={`dance-${shotId}`}>Dance direction in this shot</label>}
      {!noDance && <select id={`dance-${shotId}`} className="perf-shot" value={perf.dance?.[shotId] ?? "auto"} onChange={(e) => onDance(e.target.value)}>
        <option value="auto">Automatic: only if this shot's action is dancing</option>
        <option value="on">Always: use the dance direction</option>
        <option value="off">Never: leave the dance direction out</option>
      </select>}
    </section>
  );
}
