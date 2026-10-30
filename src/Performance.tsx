import { useCallback, useEffect, useState } from "react";
import { Sheet } from "./Sheet";
import { api, errorText } from "./api";
import * as I from "./icons";
import { PanelHead } from "./Dock";
import { ArcSection, BeatsPanel, GesturesSection } from "./ActingDepth";
import { ArcFlags, NudgeRow, PeopleProfiles, SceneNotes } from "./PerformanceDirector";

export type PerfData = { profiles: { id: string; label: string; blurb: string }[]; default: string;
  scenes: Record<string, string>; characters: Record<string, string>; shots: Record<string, string>; set: boolean };

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
  const [tab, setTab] = useState<"scenes" | "people" | "style">("scenes");
  const [arcTick, setArcTick] = useState(0);                       // the arc check reads again after the arc is edited
  const set = async (data: Record<string, unknown>) => { setErr(""); try { await setPerf(data); onChanged(); } catch (e) { setErr(errorText(e)); } };
  const label = (id: string) => perf?.profiles.find((x) => x.id === id)?.label ?? id;
  const TABS: ["scenes" | "people" | "style", string][] = [["scenes", "Scenes"], ["people", "People"], ["style", "Style & arcs"]];
  return (
    <Sheet label="Acting and Performance Director" className="perf-sheet" onDismiss={onClose}>
        <div className="vs-head"><h2>Acting <span className="dim pd-sub">Performance Director</span></h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <div className="pd-tabs" role="tablist" aria-label="Acting">
          {TABS.map(([id, text]) => <button key={id} type="button" role="tab" id={`pd-tab-${id}`} aria-selected={tab === id} aria-controls={`pd-panel-${id}`} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{text}</button>)}
        </div>
        {tab === "scenes" && <div role="tabpanel" id="pd-panel-scenes" aria-labelledby="pd-tab-scenes"><SceneNotes dir={dir} onChanged={onChanged} /></div>}
        {tab === "people" && <div role="tabpanel" id="pd-panel-people" aria-labelledby="pd-tab-people"><PeopleProfiles dir={dir} onChanged={onChanged} /></div>}
        {tab === "style" && <div role="tabpanel" id="pd-panel-style" aria-labelledby="pd-tab-style">
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
            <ArcSection dir={dir} onChanged={() => { onChanged(); setArcTick((t) => t + 1); }} />
            <ArcFlags key={arcTick} dir={dir} /></details>
          <details className="perf-more"><summary>Signature gestures <span className="dim">the small habits that make a character themselves</span></summary>
            <GesturesSection dir={dir} onChanged={onChanged} /></details>
        </>}
        </div>}
    </Sheet>
  );
}

/** In the shot panel: this shot's acting profile. */
export function ShotPerformance({ dir, shotId, onChanged }: { dir: string; shotId: string; onChanged: () => void }) {
  const { perf, setPerf } = usePerformance(dir);
  if (!perf) return null;
  return <>
    <ShotPerformanceView perf={perf} shotId={shotId}
                         onProfile={async (v) => { await setPerf({ shots: { [shotId]: v } }); onChanged(); }}
                         onUseNatural={async () => { await setPerf({ default: "natural" }); onChanged(); }} />
    <BeatsPanel dir={dir} shotId={shotId} onChanged={onChanged} />
    <NudgeRow dir={dir} shotId={shotId} onChanged={onChanged} />
  </>;
}

/** What is drawn: the acting profile for this shot. */
export function ShotPerformanceView({ perf, shotId, onProfile, onUseNatural }: { perf: PerfData; shotId: string; onProfile: (v: string) => void; onUseNatural?: () => void }) {
  return (
    <section className="panel">
      <PanelHead icon={<I.Mask size={18} />} title="Acting" tag="Free" tone="free" hint="How the performers play this shot." />
      {!perf.set && <p className="dim perf-none" role="note">No acting style is chosen for this project yet, so prompts carry no blinks, breathing or weight shifts. Choose one under Acting on the left.
        {onUseNatural && <> <button className="btn small" onClick={onUseNatural}>Use Natural for this project</button></>}</p>}
      <select className="perf-shot" value={perf.shots[shotId] ?? "inherit"} aria-label="Acting style for this shot" onChange={(e) => onProfile(e.target.value)}>
        <option value="inherit">Inherit (scene, character or video)</option>
        {perf.profiles.map((p) => <option key={p.id} value={p.id}>{p.label}: {p.blurb.split(".")[0]}</option>)}
      </select>
    </section>
  );
}
