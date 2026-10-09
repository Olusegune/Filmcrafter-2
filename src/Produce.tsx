import { useCallback, useEffect, useMemo, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { api, errorText, fmtTime, type Concept, type EngineEvent, type LoadedProject, type PlanCharacter, type PlanPlace, type PlanProp, type ProducerPlanView } from "./api";
import { Cta, PanelHead, Pill } from "./Dock";
import { lookName, useStyles } from "./Looks";
import { Pictures } from "./ProducePictures";
import { ask as confirmAsk } from "./ask";
import * as I from "./icons";

const STEPS = [
  { id: 1, label: "Direction", icon: <I.Wand size={16} /> },
  { id: 2, label: "Cast & world", icon: <I.User size={16} /> },
  { id: 3, label: "Shots", icon: <I.Film size={16} /> },
  { id: 4, label: "Build", icon: <I.Rocket size={16} /> },
  { id: 5, label: "Pictures", icon: <I.ImageIcon size={16} /> },
];
const CAST = [["small", "Small cast", "2 to 4 people"], ["medium", "Medium", "4 to 7 people"], ["large", "Large cast", "7 to 12 people"]] as const;
const DANCE = [["none", "No dancing"], ["some", "Some"], ["lots", "A lot"]] as const;
const CLASSES = ["featured dance", "group dance choreography", "gesture-led performance", "acting only, restrained", "acting only, expressive", "acting only, dramatic", "acting only, energetic"];
const IDEAS = ["Make the lead more theatrical", "Use fewer locations", "Smaller cast", "Add a dance break for the chorus", "Make it feel warmer", "Less dancing, more acting"];
const LEVEL: Record<string, string> = { performance: "Performance-led", hybrid: "Performance + story", narrative: "Story-led" };
const hexes = (s: string) => Array.from(s.matchAll(/#[0-9a-fA-F]{6}\b/g)).map((m) => m[0]);

/**
 * Create the production from the song: the Producer plans the cast, outfits, props, places, movement and shots as a PULSEFRAME package,
 * you shape it, and it is imported exactly like a package from the Producer plugin. Four steps, resumable at any time; the only paid calls
 * are the planning calls (cents), and no picture or video is made here.
 */
export function Produce({ project, onStudio, onHome, onSettings }: {
  project: LoadedProject; onStudio: (makePictures: boolean) => void; onHome: () => void; onSettings: () => void;
}) {
  const dir = project.dir;
  const styles = useStyles();
  const [plan, setPlan] = useState<ProducerPlanView | null>(null);
  const [step, setStep] = useState(1);
  const [concepts, setConcepts] = useState<Concept[]>(project.concepts?.concepts ?? []);
  const [pick, setPick] = useState<number | null>(null);
  const [notes, setNotes] = useState(project.project.onboarding?.concept_notes ?? "");
  const [cast, setCast] = useState<"small" | "medium" | "large">("medium");
  const [dance, setDance] = useState<"none" | "some" | "lots">("some");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [asking, setAsking] = useState("");

  const apply = useCallback((v: ProducerPlanView) => {
    setPlan(v);
    if (v.brief?.cast) setCast(v.brief.cast as "small" | "medium" | "large");
    if (v.brief?.dance) setDance(v.brief.dance as "none" | "some" | "lots");
    if (typeof v.brief?.direction_index === "number") setPick(v.brief.direction_index);
    if (v.brief?.notes) setNotes((n) => n || v.brief.notes!);
  }, []);
  useEffect(() => {
    api.producerPlan(dir, "get").then((v) => {
      apply(v);
      const home = v.stage === "built" ? 4 : v.stage === "shots" ? 3 : v.stage === "assets" ? 2 : 1;
      let last = 0; try { last = Number(localStorage.getItem(`pf-produce-step:${dir}`)) || 0; } catch { /* optional */ }
      setStep(last >= 1 && last <= (v.stage === "built" ? 5 : home) ? last : home);   // back to the step you were on, never past what is done
    }).catch((e) => setError(errorText(e)));
  }, [dir, apply]);
  useEffect(() => {
    const un = api.onEngine((e: EngineEvent) => { if ((e.task === "producer_plan" || e.task === "concepts") && e.stage) setBusy(String(e.stage).replace(/^./, (c) => c.toUpperCase()) + "…"); });
    return () => { un.then((f) => f()); };
  }, []);

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setError(""); setNote("");
    try { await fn(); } catch (e) { setError(errorText(e)); } finally { setBusy(""); }
  };
  const ready = async () => { if (await api.aiReady()) return true; onSettings(); return false; };
  const imagine = () => run("Listening to the song…", async () => {
    if (!(await ready())) return;
    setPick(null);
    setConcepts((await api.creativeDirections(dir, notes)).concepts);
  });
  const design = () => run("Designing the cast and world…", async () => {
    if (!(await ready())) return;
    apply(await api.producerPlan(dir, "assets", { index: pick !== null && pick >= 0 ? pick : null, notes, cast, dance }));
    setStep(2);
  });
  /** Autopilot for the planning: cast and world, then the shots, in one go. It stops where your decisions are: you still review the cast and approve each section of shots. */
  const planAll = () => run("Planning everything…", async () => {
    if (!(await ready())) return;
    apply(await api.producerPlan(dir, "assets", { index: pick !== null && pick >= 0 ? pick : null, notes, cast, dance }));
    setBusy("Planning the shots…");
    apply(await api.producerPlan(dir, "shots"));
    setStep(2);
    setNote("Everything is planned. Look over the cast and world, then check the shots and approve each section. Nothing has cost more than the planning calls.");
  });
  const revise = () => run("Revising the plan…", async () => {
    if (!(await ready())) return;
    apply(await api.producerPlan(dir, "revise", { instruction: asking }));
    setAsking("");
    setNote("Revised. The shots need planning again to match.");
  });
  const shots = () => run("Planning the shots…", async () => {
    if (!(await ready())) return;
    apply(await api.producerPlan(dir, "shots"));
    setStep(3);
  });
  const edit = async (group: string, id: string, patch: Record<string, unknown>) => {
    setError("");
    try { apply(await api.producerPlan(dir, "edit", { group, id, patch })); } catch (e) { setError(errorText(e)); }
  };
  const remove = async (group: string, id: string, name: string) => {
    if (!(await confirmAsk(`Remove ${name} from the plan?\n\nShots that use it keep going without it.`, { ok: "Remove", danger: true }))) return;
    setError("");
    try { apply(await api.producerPlan(dir, "remove", { group, id })); } catch (e) { setError(errorText(e)); }
  };
  useEffect(() => { try { localStorage.setItem(`pf-produce-step:${dir}`, String(step)); } catch { /* optional */ } }, [dir, step]);
  const ask = (group: string, id: string, instruction: string) => run("Revising the card…", async () => {
    if (!(await ready())) return;
    apply(await api.producerPlan(dir, "revise", { instruction, only: { group, id } }));
    setNote("Revised that card only. Everything else is as it was.");
  });
  const exportIt = async () => {
    setError(""); setNote("");
    try {
      const dest = await save({ defaultPath: `${project.project.title.replace(/[^\w .-]+/g, "").trim() || "production"}.pfproducer`, filters: [{ name: "PULSEFRAME Producer package", extensions: ["pfproducer"] }] });
      if (!dest) return;
      setBusy("Saving the package…");
      const r = await api.producerPlan<{ path: string; pictures: number; bytes: number }>(dir, "export", { dest });
      setNote(`Saved ${r.path} (${(r.bytes / 1048576).toFixed(1)} MB, ${r.pictures} picture${r.pictures === 1 ? "" : "s"}). Open it from Home with Import production package.`);
    } catch (e) { setError(errorText(e)); } finally { setBusy(""); }
  };
  const editShot = async (id: string, patch: Record<string, unknown>) => {
    setError("");
    try { apply(await api.producerPlan(dir, "edit_shot", { id, patch })); } catch (e) { setError(errorText(e)); }
  };
  const approveSections = async (sections: string[], on: boolean) => {
    setError("");
    try { apply(await api.producerPlan(dir, "approve", { sections, on })); } catch (e) { setError(errorText(e)); }
  };
  const allApproved = !!plan && plan.shots.length > 0 && new Set(plan.shots.map((x) => x.section)).size === plan.approved.length;
  const build = () => run("Building the project…", async () => {
    let force = false;
    if (plan?.has_renders) {
      if (!(await confirmAsk("This project already has renders.\n\nBuilding replaces its shot plan (the old plan is kept as a backup file), so existing renders may no longer line up with the new shots.", { ok: "Build anyway", danger: true }))) return;
      force = true;
    }
    const r = await api.producerPlan<{ view: ProducerPlanView }>(dir, "build", { force });
    apply(r.view);
    setStep(4);
  });

  const a = plan?.assets ?? null;
  const personName = useMemo(() => Object.fromEntries((a?.characters ?? []).map((c) => [c.id, c.name])), [a]);
  const stale = !!plan?.shots_stale;
  const canGo = (n: number) => n === 1 || (n === 2 && !!a) || (n === 3 && !!plan?.shots.length) || (n === 4 && !!plan?.shots.length) || (n === 5 && plan?.stage === "built" && !stale);

  return (
    <div className="produce">
      <header className="pr-top">
        <button className="pr-back" onClick={onHome}><I.ArrowLeft size={16} /> Home</button>
        <div className="pr-title"><span className="pr-eyebrow"><I.Sparkle size={13} /> Create from song</span><h1>{project.project.title}</h1></div>
        <nav className="pr-steps" aria-label="Steps">
          {STEPS.map((s) => (
            <button key={s.id} className={`pr-step ${step === s.id ? "on" : ""} ${(s.id === 2 && a) || (s.id === 3 && plan?.shots.length && !stale) || (s.id === 4 && plan?.stage === "built") ? "done" : ""}`}
                    aria-current={step === s.id ? "step" : undefined} disabled={!canGo(s.id) || !!busy} onClick={() => setStep(s.id)}>
              <span className="pr-step-ic">{(s.id === 2 && a) || (s.id === 4 && plan?.stage === "built") ? <I.Check size={14} /> : s.icon}</span><span>{s.label}</span>
            </button>))}
        </nav>
        {plan?.stage === "built" && <button className="btn small" onClick={exportIt} disabled={!!busy} title="Save this production, with its pictures, as a .pfproducer file"><I.Upload size={13} /> Export</button>}
        <button className="link pr-skip" onClick={() => onStudio(false)} disabled={!!busy} title="Leave this and work in the Studio the usual way">Skip to the Studio</button>
      </header>

      <main className="pr-body">
        {error && <div className="note warn" role="alert"><I.Alert size={14} /> <span>{error}</span></div>}
        {note && !error && <div className="note"><I.Info size={14} /> <span>{note}</span></div>}
        {(plan?.supplied?.length ?? 0) > 0 && step < 4 && <div className="note ok"><I.Check size={14} /> <span>Using the pictures you gave for {plan!.supplied.slice(0, 5).join(", ")}{plan!.supplied.length > 5 ? ` and ${plan!.supplied.length - 5} more` : ""}: they are kept exactly as they are.</span></div>}

        {step === 1 && (
          <section className="pr-sec">
            <PanelHead icon={<I.Wand size={18} />} title="Choose a direction" hint="PULSEFRAME listens to your song and proposes three different looks for the whole production. Pick one, or write your own below." />
            {plan?.script && concepts.length === 0 && pick === null ? (
              <div className="pr-script">
                <span className="pr-callout-ic"><I.Doc size={20} /></span>
                <div>
                  <b>Your script is the brief{plan.script.name ? `: ${plan.script.name}` : ""}</b>
                  <span>{plan.script.characters || plan.script.scenes ? `PULSEFRAME found ${plan.script.characters} character${plan.script.characters === 1 ? "" : "s"} and ${plan.script.scenes} scene${plan.script.scenes === 1 ? "" : "s"}. ` : ""}The cast, places and shots are designed from what you wrote, so there is nothing to choose. Add notes below if you want to steer it.</span>
                  <button className="link" onClick={imagine} disabled={!!busy}>or see three other directions instead</button>
                </div>
              </div>
            ) : concepts.length === 0 ? (
              <div className="pr-intro">
                <textarea className="text-input" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)}
                          placeholder="Anything you want it to be, e.g. “a Lagos family satire, warm and funny, theatrical mother, no dancing for the kids”" />
                <div className="pr-row">
                  <button className="btn hero" onClick={imagine} disabled={!!busy}>{busy || "Show me three directions"}</button>
                  <button className="link" onClick={() => setPick(-1)} disabled={!!busy}>or just use my description</button>
                </div>
              </div>
            ) : (
              <>
                <div className="dir-grid" role="radiogroup" aria-label="Directions">
                  {concepts.map((c, i) => (
                    <button key={i} role="radio" aria-checked={pick === i} className={`dir-card ${pick === i ? "on" : ""}`} onClick={() => setPick(i)} disabled={!!busy}>
                      <span className="dir-level">{LEVEL[c.narrative_level] ?? c.narrative_level}</span>
                      <span className="dir-title">{c.title}</span>
                      <span className="dir-premise">{c.premise}</span>
                      <span className="dir-hero">“{c.hero_frame}”</span>
                      <span className="dir-row"><b>Mood</b> {c.mood}</span>
                      <span className="dir-row"><b>Performance</b> {c.performance_approach}</span>
                      <span className="dir-row"><b>World</b> {c.environment}</span>
                      <span className="dir-row"><b>Movement</b> {c.movement}</span>
                      <span className="dir-palette">{c.palette.map((p) => <i key={p}>{p}</i>)}</span>
                      <span className="dir-look">Look: {lookName(styles, { style: c.suggested_look })}</span>
                    </button>))}
                </div>
                <div className="pr-row"><button className="link" onClick={imagine} disabled={!!busy}>Three new ideas</button></div>
              </>
            )}
            <div className="pr-opts">
              <div><label className="pr-label">Cast size</label>
                <div className="seg" role="group" aria-label="Cast size">{CAST.map(([id, label, sub]) => <button key={id} className={cast === id ? "on" : ""} title={sub} onClick={() => setCast(id)}>{label}</button>)}</div>
                <span className="dim">{CAST.find((c) => c[0] === cast)![2]}</span></div>
              <div><label className="pr-label">Dancing</label>
                <div className="seg" role="group" aria-label="Amount of dancing">{DANCE.map(([id, label]) => <button key={id} className={dance === id ? "on" : ""} onClick={() => setDance(id)}>{label}</button>)}</div>
                <span className="dim">{dance === "none" ? "Acting and performance only." : dance === "some" ? "A few featured moments." : "Choreography is a big part."}</span></div>
              <div className="pr-notes"><label className="pr-label">Notes for the Producer <span className="dim">(optional)</span></label>
                <input className="text-input" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Who is in it, where, what must happen, what to avoid" /></div>
            </div>
          </section>
        )}

        {step === 2 && a && (
          <section className="pr-sec">
            <PanelHead icon={<I.User size={18} />} title="Cast, places and world" hint="Edit any card, or tell the Producer what to change. Nothing is made yet: these are the designs the pictures will be made from." />
            <div className="pr-revise">
              <input className="text-input" value={asking} onChange={(e) => setAsking(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && asking.trim() && !busy) revise(); }}
                     placeholder="Tell the Producer what to change, e.g. “make the mother more theatrical”" aria-label="Revise the plan" />
              <button className="btn" onClick={revise} disabled={!!busy || !asking.trim()}><I.Wand size={14} /> Revise</button>
              <div className="pr-ideas">{IDEAS.map((t) => <button key={t} className="pr-idea" onClick={() => setAsking(t)} disabled={!!busy}>{t}</button>)}</div>
            </div>

            <h3 className="pr-h"><I.User size={15} /> People <span className="dim">{a.characters.length}</span></h3>
            <div className="pr-grid">{a.characters.map((c) => <PersonCard key={c.id} c={c} onEdit={(p) => edit("characters", c.id, p)} onAsk={(t) => ask("characters", c.id, t)} busy={!!busy} onRemove={() => remove("characters", c.id, c.name)}
                                                                         dancer={a.choreography.find((e) => e.character_id === c.id)?.moves.length ?? 0} />)}</div>

            <h3 className="pr-h"><I.Mountain size={15} /> Places <span className="dim">{a.environments.length}</span></h3>
            <div className="pr-grid">{a.environments.map((e) => <PlaceCard key={e.id} e={e} base={a.environments.find((x) => x.id === e.variant_of)?.name}
                                                                      onEdit={(p) => edit("environments", e.id, p)} onAsk={(t) => ask("environments", e.id, t)} busy={!!busy} onRemove={() => remove("environments", e.id, e.name)} />)}</div>

            <h3 className="pr-h"><I.Cube size={15} /> Props <span className="dim">{a.props.length}</span></h3>
            <div className="pr-grid">{a.props.map((p) => <PropCard key={p.id} p={p} owner={personName[p.owner]} people={a.characters}
                                                                   onEdit={(x) => edit("props", p.id, x)} onAsk={(t) => ask("props", p.id, t)} busy={!!busy} onRemove={() => remove("props", p.id, p.name)} />)}</div>

            {a.choreography.some((c) => c.moves.length) && <>
              <h3 className="pr-h"><I.Dance size={15} /> Movement</h3>
              <div className="pr-grid">{a.choreography.filter((c) => c.moves.length).map((c) => (
                <details key={c.id} className="pr-card">
                  <summary><span className="pr-card-t">{personName[c.character_id]}</span><Pill>{c.classification}</Pill><span className="dim">{c.moves.length} moves</span></summary>
                  <ol className="pr-moves">{c.moves.map((m) => <li key={m.id}><b>{m.name}</b> <span className="dim">· {m.song_section}</span><br /><span>{m.action}</span></li>)}</ol>
                  <p className="dim">To change the movement, tell the Producer above (for example “more footwork for the aunties”).</p>
                </details>))}</div>
            </>}

            <h3 className="pr-h"><I.Light size={15} /> World and rules</h3>
            <WorldCard a={a} onEdit={(p) => edit("world", "", p)} />
          </section>
        )}

        {step === 3 && plan && (
          <section className="pr-sec">
            <PanelHead icon={<I.Film size={18} />} title={`${plan.shots.length} shots, laid on your song`} tag={stale ? "Needs planning again" : undefined} tone="warn"
                       hint="Each shot sits on the real lyric line it belongs to, using what PULSEFRAME heard in your song. You can adjust any shot in the Studio." />
            {stale && <div className="note warn"><I.Alert size={14} /> <span>The cast changed after these shots were planned. Plan the shots again so they match.</span></div>}
            {plan.warnings.map((w) => <div key={w} className="note warn"><I.Alert size={14} /> <span>{w}</span></div>)}
            <ShotList plan={plan} busy={!!busy} onEdit={editShot} onApprove={approveSections} />
          </section>
        )}

        {step === 4 && plan && (
          <section className="pr-sec">
            {plan.stage === "built" && !stale ? (
              <div className="pr-done">
                <div className="pr-done-ic"><I.Check size={28} /></div>
                <h2>Your production is in the project</h2>
                <p className="dim">The cast, outfits, props, places, world rules, movement and {plan.counts.shots} shots are all in place, exactly as if the Producer plugin had made the package.</p>
                <div className="pr-counts">
                  <span><b>{plan.counts.people}</b> people</span><span><b>{plan.counts.places}</b> places</span><span><b>{plan.counts.props}</b> props</span>
                  <span><b>{plan.counts.dancers}</b> {plan.counts.dancers === 1 ? "dancer" : "dancers"}</span><span><b>{plan.counts.shots}</b> {plan.counts.shots === 1 ? "shot" : "shots"}</span>
                </div>
                {(plan.report?.without_images?.length ?? 0) > 0
                  ? <div className="note"><I.ImageIcon size={14} /> <span><b>{plan.report!.without_images!.length} pictures</b> still to make: the cast sheets, props, places and dance sheets. Each has a written image prompt, and you see the price before anything is sent.</span></div>
                  : <div className="note ok"><I.Check size={14} /> <span>Every character, prop and place already has a picture.</span></div>}
                <div className="pr-row">
                  {(plan.report?.without_images?.length ?? 0) > 0
                    ? <Cta icon={<I.ImageIcon size={16} />} onClick={() => setStep(5)}>Make the pictures</Cta> : null}
                  <Cta tone={(plan.report?.without_images?.length ?? 0) > 0 ? "quiet" : "warm"} icon={<I.Studio size={16} />} onClick={() => onStudio(false)}>Open in the Studio</Cta>
                </div>
              </div>
            ) : (
              <>
                <PanelHead icon={<I.Rocket size={18} />} title="Build the project" hint="This writes your plan as a Producer package and imports it into this project. It is free and quick, and it makes no pictures or videos." />
                <ul className="pr-list">
                  <li><I.Check size={14} /> {plan.counts.people} people and their outfits, {plan.counts.places} places and {plan.counts.props} props go to the Reference library with their locked rules.</li>
                  <li><I.Check size={14} /> The world, palette and never-show rules go to the Production Bible.</li>
                  <li><I.Check size={14} /> {plan.counts.dancers} {plan.counts.dancers === 1 ? "dancer gets" : "dancers get"} movement notes; everyone else gets an acting profile.</li>
                  <li><I.Check size={14} /> {plan.counts.shots} shots are placed on your song's lyric lines.</li>
                </ul>
                {plan.has_renders && <div className="note warn"><I.Alert size={14} /> <span>This project already has renders. Building replaces its shot plan (the old one is kept as a backup).</span></div>}
                {stale && <div className="note warn"><I.Alert size={14} /> <span>Plan the shots again first: the cast changed.</span></div>}
              </>
            )}
          </section>
        )}
        {step === 5 && plan?.stage === "built" && <Pictures dir={dir} onDone={() => onStudio(false)} onError={setError} />}
        {busy && <div className="progress indet" style={{ marginTop: 14 }}><i /></div>}
      </main>

      <footer className="pr-foot">
        <button className="btn ghost" onClick={() => setStep(Math.max(1, step - 1))} disabled={step === 1 || !!busy}><I.ArrowLeft size={14} /> Back</button>
        <span className="pr-foot-note dim">{busy ? busy : plan?.model ? `Planned with ${plan.model}. ` : ""}{!busy && step <= 3 ? "Planning costs a few cents with OpenAI and nothing with a local model." : ""}</span>
        <div style={{ flex: 1 }} />
        {step === 1 && <button className="btn" disabled={!!busy || ((pick === null || pick < 0) && !notes.trim() && !plan?.script)} onClick={planAll}
                               title="Design the cast and world and plan every shot in one go. You still review the cast and approve each section of shots."><I.Rocket size={14} /> Plan it all for me</button>}
        {step === 1 && <Cta icon={<I.Sparkle size={16} />} busy={!!busy} disabled={(pick === null || pick < 0) && !notes.trim() && !plan?.script} onClick={design}>{pick !== null && pick >= 0 && concepts[pick] ? `Design “${concepts[pick].title}”` : plan?.script && pick === null ? "Design it from my script" : "Design the cast and world"}</Cta>}
        {step === 2 && <>
          {a && plan?.shots.length && !stale ? <button className="btn ghost" onClick={() => setStep(3)} disabled={!!busy}>Keep the shots <I.ArrowRight size={14} /></button> : null}
          <Cta icon={<I.Film size={16} />} busy={!!busy} onClick={shots}>{plan?.shots.length ? "Plan the shots again" : "Plan the shots"}</Cta></>}
        {step === 3 && <>
          <button className="btn ghost" onClick={shots} disabled={!!busy}><I.Refresh size={14} /> Plan again</button>
          <Cta icon={<I.Rocket size={16} />} busy={!!busy} disabled={stale || !allApproved} title={allApproved ? undefined : "Approve every section first"} onClick={() => setStep(4)}>{allApproved ? "Next: build" : "Approve every section to continue"}</Cta></>}
        {step === 4 && !(plan?.stage === "built" && !stale) && <Cta icon={<I.Rocket size={16} />} busy={!!busy} disabled={stale || !plan?.shots.length || !allApproved} onClick={build}>Build the project</Cta>}
        {step === 4 && plan?.stage === "built" && !stale && <span className="dim">Built {plan.built ? new Date(plan.built * 1000).toLocaleTimeString() : ""}</span>}
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------- cards

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="pr-field"><span>{label}</span>{children}</label>;
}

function AskCard({ name, onAsk, busy }: { name: string; onAsk: (t: string) => void; busy: boolean }) {
  const [t, setT] = useState("");
  const go = () => { if (t.trim() && !busy) { onAsk(t.trim()); setT(""); } };
  return (
    <div className="pr-ask">
      <input className="text-input" value={t} onChange={(e) => setT(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") go(); }} aria-label={`Ask the Producer to change ${name}`}
             placeholder={`Ask the Producer to change ${name}…`} />
      <button className="btn small" onClick={go} disabled={busy || !t.trim()}><I.Wand size={13} /> Ask</button>
    </div>);
}

function PersonCard({ c, dancer, onEdit, onAsk, busy, onRemove }: { c: PlanCharacter; dancer: number; onEdit: (p: Partial<PlanCharacter>) => void; onAsk: (t: string) => void; busy: boolean; onRemove: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`pr-card ${open ? "open" : ""}`}>
      <div className="pr-card-head">
        <span className="pr-avatar" aria-hidden>{c.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase()}</span>
        <div className="pr-card-id"><b className="pr-card-t">{c.name}</b><span className="dim">{c.role}</span></div>
        <div style={{ flex: 1 }} />
        {c.library_id && <Pill tone="ok" icon={<I.Check size={11} />} title="You gave a picture for this person">Your picture</Pill>}
        <button className="link" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Done" : "Edit"}</button>
      </div>
      <div className="pr-tags"><Pill>{c.classification}</Pill>{dancer > 0 && <Pill icon={<I.Dance size={11} />}>{dancer} moves</Pill>}</div>
      {!open ? <>
        <ul className="pr-bullets">{c.identity.map((x) => <li key={x}>{x}</li>)}</ul>
        <p className="pr-line"><I.Shirt size={13} /> {c.outfit}</p>
        {c.performance && <p className="pr-line"><I.Mask size={13} /> {c.performance}</p>}
      </> :<div className="pr-edit">
        <AskCard name={c.name} onAsk={onAsk} busy={busy} />
        <Field label="Name"><input className="text-input" defaultValue={c.name} onBlur={(e) => e.target.value !== c.name && onEdit({ name: e.target.value })} /></Field>
        <Field label="Role"><input className="text-input" defaultValue={c.role} onBlur={(e) => e.target.value !== c.role && onEdit({ role: e.target.value })} /></Field>
        <Field label="Never changes (one per line)"><textarea className="text-input" rows={4} defaultValue={c.identity.join("\n")} onBlur={(e) => onEdit({ identity: e.target.value.split("\n") as never })} /></Field>
        <Field label="The one outfit"><textarea className="text-input" rows={2} defaultValue={c.outfit} onBlur={(e) => e.target.value !== c.outfit && onEdit({ outfit: e.target.value })} /></Field>
        <Field label="How they act and move"><textarea className="text-input" rows={2} defaultValue={c.performance} onBlur={(e) => e.target.value !== c.performance && onEdit({ performance: e.target.value })} /></Field>
        <Field label="Kind of performance"><select value={c.classification} onChange={(e) => onEdit({ classification: e.target.value })}>{CLASSES.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <button className="link danger" onClick={onRemove}><I.Trash size={13} /> Remove from the plan</button>
      </div>}
    </div>
  );
}

function PlaceCard({ e, base, onEdit, onAsk, busy, onRemove }: { e: PlanPlace; base?: string; onEdit: (p: Partial<PlanPlace>) => void; onAsk: (t: string) => void; busy: boolean; onRemove: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`pr-card ${open ? "open" : ""}`}>
      <div className="pr-card-head"><span className="pr-avatar sq" aria-hidden><I.Mountain size={16} /></span>
        <div className="pr-card-id"><b className="pr-card-t">{e.name}</b>{base && <span className="dim">another dressing of {base}</span>}</div>
        <div style={{ flex: 1 }} />{e.library_id && <Pill tone="ok" icon={<I.Check size={11} />}>Your picture</Pill>}
        <button className="link" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Done" : "Edit"}</button></div>
      {!open ? <><p className="pr-line">{e.layout}</p><p className="pr-line dim"><I.Light size={13} /> {e.light}</p></> : <div className="pr-edit">
        <AskCard name={e.name} onAsk={onAsk} busy={busy} />
        <Field label="Name"><input className="text-input" defaultValue={e.name} onBlur={(x) => x.target.value !== e.name && onEdit({ name: x.target.value })} /></Field>
        <Field label="What is where (never changes)"><textarea className="text-input" rows={4} defaultValue={e.layout} onBlur={(x) => x.target.value !== e.layout && onEdit({ layout: x.target.value })} /></Field>
        <Field label="Light and colour"><textarea className="text-input" rows={2} defaultValue={e.light} onBlur={(x) => x.target.value !== e.light && onEdit({ light: x.target.value })} /></Field>
        <button className="link danger" onClick={onRemove}><I.Trash size={13} /> Remove from the plan</button></div>}
    </div>
  );
}

function PropCard({ p, owner, people, onEdit, onAsk, busy, onRemove }: { p: PlanProp; owner?: string; people: PlanCharacter[]; onEdit: (x: Partial<PlanProp>) => void; onAsk: (t: string) => void; busy: boolean; onRemove: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`pr-card ${open ? "open" : ""}`}>
      <div className="pr-card-head"><span className="pr-avatar sq" aria-hidden><I.Cube size={16} /></span>
        <div className="pr-card-id"><b className="pr-card-t">{p.name}</b>{owner && <span className="dim">{owner}'s</span>}</div>
        <div style={{ flex: 1 }} />{p.library_id && <Pill tone="ok" icon={<I.Check size={11} />}>Your picture</Pill>}
        <button className="link" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Done" : "Edit"}</button></div>
      {!open ? <p className="pr-line">{p.description}</p> : <div className="pr-edit">
        <AskCard name={p.name} onAsk={onAsk} busy={busy} />
        <Field label="Name"><input className="text-input" defaultValue={p.name} onBlur={(x) => x.target.value !== p.name && onEdit({ name: x.target.value })} /></Field>
        <Field label="Size, material, colour"><textarea className="text-input" rows={2} defaultValue={p.description} onBlur={(x) => x.target.value !== p.description && onEdit({ description: x.target.value })} /></Field>
        <Field label="Whose it is"><select value={p.owner} onChange={(x) => onEdit({ owner: x.target.value })}><option value="">Nobody in particular</option>{people.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        <button className="link danger" onClick={onRemove}><I.Trash size={13} /> Remove from the plan</button></div>}
    </div>
  );
}

function WorldCard({ a, onEdit }: { a: NonNullable<ProducerPlanView["assets"]>; onEdit: (p: Record<string, unknown>) => void }) {
  const text = (k: "visual_style" | "world" | "always" | "never_show", label: string, rows = 3) => (
    <Field label={label}><textarea className="text-input" rows={rows} defaultValue={a[k]} onBlur={(e) => e.target.value !== a[k] && onEdit({ [k]: e.target.value })} /></Field>);
  return (
    <div className="pr-card open pr-world">
      {text("visual_style", "Visual style (added to every picture and video)", 3)}
      {text("world", "The world and tone")}
      {text("always", "Always true in every shot")}
      <Field label="Palette"><div className="pr-swatches">{hexes(a.palette).map((h) => <i key={h} style={{ background: h }} title={h} />)}</div>
        <textarea className="text-input" rows={3} defaultValue={a.palette} onBlur={(e) => e.target.value !== a.palette && onEdit({ palette: e.target.value })} /></Field>
      {text("never_show", "Never show")}
      <Field label="World rules (one per line, at most 8)"><textarea className="text-input" rows={5} defaultValue={a.rules.join("\n")} onBlur={(e) => onEdit({ rules: e.target.value.split("\n") })} /></Field>
    </div>
  );
}

function ShotList({ plan, busy, onEdit, onApprove }: { plan: ProducerPlanView; busy: boolean; onEdit: (id: string, patch: Record<string, unknown>) => void; onApprove: (sections: string[], on: boolean) => void }) {
  const groups = useMemo(() => {
    const out: { name: string; shots: typeof plan.shots }[] = [];
    for (const s of plan.shots) {
      const g = out[out.length - 1];
      if (g && g.name === s.section) g.shots.push(s); else out.push({ name: s.section, shots: [s] });
    }
    return out;
  }, [plan]);
  const done = groups.filter((g) => plan.approved.includes(g.name)).length;
  const firstOpen = groups.findIndex((g) => !plan.approved.includes(g.name));
  return (
    <div className="pr-shots">
      <div className="pr-approve-bar">
        <div><b>{done} of {groups.length} sections approved</b><span className="dim"> Read each section against your song, fix any shot, then approve it. Building needs every section approved.</span></div>
        <div className="pr-approve-meter" aria-hidden><i style={{ width: `${groups.length ? (done / groups.length) * 100 : 0}%` }} /></div>
        <button className="btn" disabled={busy || done === groups.length} onClick={() => onApprove(groups.map((g) => g.name), true)}><I.Check size={14} /> Approve all</button>
      </div>
      {groups.map((g, i) => {
        const ok = plan.approved.includes(g.name);
        const moves = plan.moves?.[g.name] ?? [];
        return (
          <details key={`${g.name}${i}`} className={`pr-sec-group ${ok ? "ok" : ""}`} open={i === firstOpen || (firstOpen < 0 && i === 0)}>
            <summary>
              <span className={`pr-sec-state ${ok ? "ok" : ""}`}>{ok ? <I.Check size={13} /> : <span>{i + 1}</span>}</span>
              <b>{g.name}</b><span className="dim num">{fmtTime(g.shots[0].start).slice(0, -3)} to {fmtTime(g.shots[g.shots.length - 1].end).slice(0, -3)}</span>
              <span className="dim">{g.shots.length} shot{g.shots.length === 1 ? "" : "s"}</span>
              <span style={{ flex: 1 }} />
              <button className={`btn small ${ok ? "" : "primary"}`} disabled={busy} onClick={(e) => { e.preventDefault(); onApprove([g.name], !ok); }}>{ok ? "Approved · undo" : "Approve section"}</button>
            </summary>
            {moves.length > 0 && (
              <details className="pr-moves-box"><summary><I.Dance size={14} /> Movement in this section <span className="dim">{moves.length} move{moves.length === 1 ? "" : "s"}</span></summary>
                <ul>{moves.map((m, k) => <li key={k}><b>{m.who}</b>: {m.name}. <span className="dim">{[m.action, m.footwork && `feet: ${m.footwork}`, m.arms && `arms: ${m.arms}`].filter(Boolean).join(" · ")}</span></li>)}</ul>
                <p className="dim">To change the movement, tell the Producer on the Cast &amp; world step.</p></details>)}
            <ul className="pr-shotlist">{g.shots.map((s) => <ShotRow key={s.id} s={s} plan={plan} busy={busy} onEdit={(p) => onEdit(s.id, p)} />)}</ul>
          </details>);
      })}
    </div>
  );
}

function ShotRow({ s, plan, busy, onEdit }: { s: ProducerPlanView["shots"][number]; plan: ProducerPlanView; busy: boolean; onEdit: (p: Record<string, unknown>) => void }) {
  const [open, setOpen] = useState(false);
  const a = plan.assets!;
  const toggle = (key: "people_ids" | "prop_ids", id: string) => { const cur = s[key]; onEdit({ [key === "people_ids" ? "character_ids" : "prop_ids"]: cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id] }); };
  const text = (k: "action" | "performance" | "framing" | "camera" | "lighting", label: string, rows = 0) => (
    <Field label={label}>{rows ? <textarea className="text-input" rows={rows} defaultValue={s[k]} onBlur={(e) => e.target.value !== s[k] && onEdit({ [k]: e.target.value })} />
      : <input className="text-input" defaultValue={s[k]} onBlur={(e) => e.target.value !== s[k] && onEdit({ [k]: e.target.value })} />}</Field>);
  return (
    <li>
      <span className="pr-time num">{fmtTime(s.start).slice(0, -3)}</span>
      <div className="pr-shot">
        {s.cue && <span className="lyric-q">{s.cue}</span>}
        <p>{s.action}</p>
        <div className="pr-tags"><Pill icon={<I.Camera size={11} />}>{[s.framing, s.camera].filter(Boolean).join(" · ")}</Pill><Pill icon={<I.Mountain size={11} />}>{s.place}</Pill>
          {s.people.map((p) => <Pill key={p} icon={<I.User size={11} />}>{p}</Pill>)}{s.props.map((p) => <Pill key={p} icon={<I.Cube size={11} />}>{p}</Pill>)}
          <button className="link" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Done" : "Edit shot"}</button></div>
        {open && <div className="pr-edit pr-shot-edit">
          {text("action", "What the camera sees", 2)}{text("performance", "How the people act", 2)}
          <div className="pr-two">{text("framing", "Shot size and lens")}{text("camera", "Camera movement")}</div>
          {text("lighting", "Light")}
          <Field label="Where"><select value={s.place_id} onChange={(e) => onEdit({ environment_id: e.target.value })} disabled={busy}>{a.environments.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
          <Field label="Who is in it"><div className="pr-chips">{a.characters.map((c) => <button key={c.id} className={`pr-idea ${s.people_ids.includes(c.id) ? "on" : ""}`} onClick={() => toggle("people_ids", c.id)}>{c.name}</button>)}</div></Field>
          <Field label="Props"><div className="pr-chips">{a.props.map((c) => <button key={c.id} className={`pr-idea ${s.prop_ids.includes(c.id) ? "on" : ""}`} onClick={() => toggle("prop_ids", c.id)}>{c.name}</button>)}</div></Field>
          <p className="dim">Camera and lighting can also be chosen by name for each shot in the Studio once the project is built.</p>
        </div>}
      </div>
    </li>
  );
}
