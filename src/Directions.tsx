import { Badge, directionGlyph } from "./glyphs";
import { useEffect, useState } from "react";
import { api, errorText, type Concept, type EngineEvent, type LoadedProject } from "./api";
import { lookName, useStyles } from "./Looks";
import * as I from "./icons";
import { paletteBand } from "./colorWords";
import { openScriptSheet } from "./ScriptSheet";

const LEVEL: Record<string, string> = { performance: "Performance-led", hybrid: "Performance + story", narrative: "Story-led" };

/**
 * PRD §10–13 for songs without a script: three directions -> pick one -> treatment and shot plan.
 * Shown in the Studio until the project has a plan.
 */
export function CreativeDirections({ project, onPlanned, onSettings }: {
  project: LoadedProject; onPlanned: () => void; onSettings: () => void;
}) {
  const styles = useStyles();
  const [concepts, setConcepts] = useState<Concept[]>(project.concepts?.concepts ?? []);
  const [pick, setPick] = useState<number | null>(null);
  const [notes, setNotes] = useState(project.project.onboarding?.concept_notes ?? "");
  const brief = project.project.onboarding?.concept_notes ?? "";
  useEffect(() => { if (brief) setNotes((n) => n.trim() ? n : brief); }, [brief]);   // a brief saved from the script sheet
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const un = api.onEngine((e: EngineEvent) => { if ((e.task === "concepts" || e.task === "treatment") && e.stage) setBusy(cap(e.stage)); });
    return () => { un.then((f) => f()); };
  }, []);

  const imagine = async () => {
    if (!(await api.aiReady())) { onSettings(); return; }
    setError(""); setBusy("Listening to the song…"); setPick(null);
    try { setConcepts((await api.creativeDirections(project.dir, notes)).concepts); } catch (e) { setError(errorText(e)); }
    finally { setBusy(""); }
  };
  const develop = async () => {
    if (pick === null) return;
    setError(""); setBusy("Writing the treatment…");
    try {
      const c = concepts[pick];
      // Adopt the direction's look unless the user already chose one.
      const current = typeof project.project.look === "object" ? project.project.look.style : "auto";
      if (current === "auto" && c.suggested_look && c.suggested_look !== "auto") await api.setLook(project.dir, { style: c.suggested_look });
      await api.writeTreatment(project.dir, pick, notes);
      onPlanned();
    } catch (e) { setError(errorText(e)); setBusy(""); }
  };

  return (
    <div className="directions">
      {concepts.length === 0 ? (
        <div className="dir-intro">
          <h2>How should this song look?</h2>
          <p className="sub">FilmCrafter will propose three different directions for “{project.project.title}”. You choose one, and it
            writes the treatment and plans every shot on the beat.</p>
          <textarea className="text-input" rows={3} placeholder="Optional: anything you want, e.g. “set in Lagos, no dancing, hopeful ending”"
                    value={notes} onChange={(e) => setNotes(e.target.value)} />
          <div className="sheet-actions">
            <button className="btn hero" onClick={imagine} disabled={!!busy}>{busy || "Show me three directions"}</button>
          </div>
        </div>
      ) : (
        <>
          <div className="dir-head">
            <h2>Choose a direction</h2>
            <button className="btn ghost" onClick={imagine} disabled={!!busy}>Three new ideas</button>
          </div>
          <div className="dir-grid" role="radiogroup" aria-label="Directions">
            {concepts.map((c, i) => (
              <div key={i} className={`dir-card ${pick === i ? "on" : ""}`}>
                <input type="radio" className="sr-only" name="direction" id={`dir-${i}`} checked={pick === i} disabled={!!busy} onChange={() => setPick(i)} />
                <label htmlFor={`dir-${i}`} className="dir-label">
                <span className="dir-band" style={{ background: paletteBand(c.palette) }}>
                  <Badge icon={directionGlyph(c.title, c.mood, c.environment, c.premise)} size={20} />
                  <span className="dir-pill">{LEVEL[c.narrative_level] ?? c.narrative_level}</span>
                </span>
                <span className="dir-title">{c.title}</span>
                <span className="dir-premise">{c.premise}</span>
                <span className="dir-hero">“{c.hero_frame}”</span>
                <span className="dir-tags"><span>{c.mood}</span><span>Look: {lookName(styles, { style: c.suggested_look })}</span></span>
                </label>
                <details className="dir-more"><summary>More about this direction</summary>
                  <span className="dir-row"><b>Performance</b> {c.performance_approach}</span>
                  <span className="dir-row"><b>Camera</b> {c.cinematic_style}</span>
                  <span className="dir-row"><b>World</b> {c.environment}</span>
                  <span className="dir-row"><b>Movement</b> {c.movement}</span>
                  <span className="dir-palette">{c.palette.map((p) => <i key={p}>{p}</i>)}</span>
                </details>
              </div>
            ))}
          </div>
          <div className="dir-foot">
            <input className="text-input" placeholder="Notes for the treatment (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} />
            <button className="btn hero" onClick={develop} disabled={pick === null || !!busy}>
              {busy || (pick === null ? "Pick a direction" : `Direct “${concepts[pick].title}”`)}</button>
          </div>
        </>
      )}
      {busy && <div className="progress indet" style={{ marginTop: 12 }}><i /></div>}
      {error && <div className="error-text">{error}</div>}
      <p className="dim" style={{ marginTop: 12 }}><I.Mountain size={12} /> Want a starting point?{" "}
        <button className="link" onClick={() => window.dispatchEvent(new Event("pf-open-directions"))}>Browse the world direction library</button>{" "}
        (Lagos Nights, Bollywood Spectacle, Nordic Noir, Magic Realism and more).</p>
      <p className="dim" style={{ marginTop: 6 }}>Using your own images and clips?{" "}
        <button className="link" disabled={!!busy} onClick={async () => {
          setError(""); try { await api.media(project.dir, "plan", { bars: 4 }); onPlanned(); } catch (e) { setError(errorText(e)); } }}>
          Cut shots on the beat, no AI</button> (free), then place your media on them.</p>
      <p className="dim" style={{ marginTop: 6 }}><I.Script size={12} /> Have a script already?{" "}
        <button className="link" onClick={openScriptSheet}>Add your script</button> and FilmCrafter follows it instead.</p>
    </div>
  );
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1) + "…";
