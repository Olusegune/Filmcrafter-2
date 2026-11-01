import { useCallback, useEffect, useMemo, useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { Sheet } from "./Sheet";
import { api, errorText, type PresetApplied, type PresetCatalog, type PresetChange, type PresetPlan, type PresetRow, type PresetStack, type SeriesEpisode, type SeriesField, type SeriesReport, type SeriesState } from "./api";
import * as I from "./icons";
import "./presets.css";

const KEY_NAME: Record<string, string> = { look: "Visual style", acting: "Acting", grade: "Colour grade", editing: "Editing style", delivery: "Delivery", aspect: "Frame shape", duration_hint_s: "Length to aim for" };
const STATUS: Record<PresetChange["status"], string> = { new: "New", same: "Already so", yours: "Yours, kept", replace: "Replace mine", unavailable: "Not available" };
const FILTERS: [string, string][] = [["all", "All"], ["favorites", "Favorites"], ["mine", "Mine"], ["production", "Production"], ["visual", "Visual"], ["performance", "Acting"], ["editing", "Editing"], ["color", "Colour"], ["delivery", "Delivery"]];

/** A setting as a short phrase a person can read. */
export function say(key: string, v: unknown): string {
  if (v === null || v === undefined || v === "") return "nothing chosen";
  if (key === "grade") { const g = v as Record<string, unknown>; const bits = Object.entries(g).filter(([, x]) => typeof x === "number").map(([k, x]) => `${k} ${(x as number) > 0 ? "+" : ""}${x}`); return bits.length ? bits.join(", ") : "no grade"; }
  if (key === "delivery") { const d = v as { export: string; safe: { bottom: number }; captions: boolean }; return `${d.export} version, ${d.captions ? "captions on" : "captions off"}, ${Math.round((d.safe?.bottom ?? 0) * 100)}% kept clear at the bottom`; }
  if (key === "duration_hint_s") return `about ${v} seconds`;
  return String(v);
}

/** One suggestion or one thing you wrote: the badge says which, and only your own words are ever marked as yours. */
function SuggestRow({ id, label, field, onSave, onReset, busy }: { id: string; label: string; field: SeriesField; onSave: (v: string) => void; onReset?: () => void; busy?: boolean }) {
  const [text, setText] = useState(field.value);
  useEffect(() => setText(field.value), [field.value, field.source]);
  const dirty = text !== field.value;
  const mine = field.source === "you";
  return (
    <div className={`ps-field ${mine ? "mine" : ""}`}>
      <div className="ps-field-head"><label htmlFor={`ps-${id}`}>{label}</label><span className={`ps-badge ${mine ? "mine" : ""}`}>{mine ? "Yours" : field.value ? "Suggestion" : "Empty"}</span></div>
      <textarea id={`ps-${id}`} rows={2} className="text-input" maxLength={400} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="ps-field-actions">
        {dirty && <button type="button" className="btn small primary" disabled={busy} onClick={() => onSave(text)}>Save</button>}
        {!dirty && !mine && field.value && <button type="button" className="btn small" disabled={busy} onClick={() => onSave(field.value)} title="Keep the suggestion as your own">Keep this</button>}
        {!dirty && mine && onReset && <button type="button" className="btn small ghost" disabled={busy} onClick={onReset}>Back to the suggestion</button>}
        {dirty && <button type="button" className="btn small ghost" onClick={() => setText(field.value)}>Undo</button>}
      </div>
    </div>
  );
}

/**
 * Creative presets: pick a few (they stack), see exactly what each setting would become, and apply. A choice you already made is kept unless you tick it; nothing is regenerated and no provider is
 * called, and the last application can be undone. The series tab makes an editable plan for a micro-drama; the vertical tab chooses what a phone-shaped version keeps of each wide shot. Free and local.
 */
export function PresetsSheet({ dir, onClose, onChanged }: { dir: string; onClose: () => void; onChanged?: () => void }) {
  const [tab, setTab] = useState<"library" | "series" | "vertical">("library");
  const [cat, setCat] = useState<PresetCatalog | null>(null);
  const [stack, setStack] = useState<string[]>([]);
  const [pending, setPending] = useState<string[]>([]);                    // chosen when the film was made on Home; shown as the stack, and applied only when you say so
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [plan, setPlan] = useState<PresetPlan | null>(null);
  const [replace, setReplace] = useState<string[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");

  const call = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | null> => { setBusy(true); setErr(""); try { return await fn(); } catch (e) { setErr(errorText(e)); return null; } finally { setBusy(false); } }, []);
  const refresh = useCallback(() => api.presets(dir, "catalog").then((c) => { setCat(c); return c; }), [dir]);
  useEffect(() => { void call(() => refresh().then((c) => { setStack(c.stack.length ? c.stack : c.pending ?? []); setPending(c.stack.length ? [] : c.pending ?? []); })); }, [call, refresh]);

  const byId = useMemo(() => new Map((cat?.presets ?? []).map((p) => [p.id, p])), [cat]);
  const shown = (cat?.presets ?? []).filter((p) => {
    if (filter === "favorites" && !p.favorite) return false;
    if (filter === "mine" && !p.mine) return false;
    if (!["all", "favorites", "mine"].includes(filter) && p.type !== filter) return false;
    const t = q.trim().toLowerCase();
    return !t || `${p.name} ${p.description} ${p.use} ${p.group}`.toLowerCase().includes(t);
  });
  const toggle = (id: string) => { setPlan(null); setMsg(""); setStack((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id])); };
  const move = (i: number, by: number) => { setPlan(null); setStack((s) => { const n = [...s]; const j = i + by; if (j < 0 || j >= n.length) return s; [n[i], n[j]] = [n[j], n[i]]; return n; }); };
  const preview = async () => { setMsg(""); const p = await call(() => api.presets<PresetPlan>(dir, "plan", { stack, replace })); if (p) setPlan(p); };
  useEffect(() => { if (plan) void api.presets<PresetPlan>(dir, "plan", { stack, replace }).then(setPlan).catch(() => {}); }, [replace]);   // eslint-disable-line react-hooks/exhaustive-deps
  const apply = async () => {
    const r = await call(() => api.presets<PresetApplied>(dir, "apply", { stack, replace }));
    if (!r) return;
    setMsg(`Applied: ${r.changed.map((k) => KEY_NAME[k] ?? k).join(", ") || "nothing new"}.${r.kept.length ? ` Kept yours: ${r.kept.map((k) => KEY_NAME[k] ?? k).join(", ")}.` : ""} Undo puts it back.`);
    setPlan(null); setReplace([]); await refresh(); onChanged?.();
  };
  const undo = async () => { const r = await call(() => api.presets<{ restored: string[]; kept_as_changed_since: string[] }>(dir, "undo")); if (!r) return; setMsg(`Put back: ${r.restored.map((k) => KEY_NAME[k] ?? k).join(", ") || "nothing"}.${r.kept_as_changed_since.length ? ` Left as you changed it since: ${r.kept_as_changed_since.map((k) => KEY_NAME[k] ?? k).join(", ")}.` : ""}`); setPlan(null); await refresh(); onChanged?.(); };
  const keep = async () => { if (!name.trim()) return; const r = await call(() => api.presets<{ saved: string; catalog: PresetCatalog }>(dir, "save_mine", { name, ...(stack.length ? { stack } : {}) })); if (r) { setCat(r.catalog); setName(""); setMsg(`Kept as "${byIdName(r.catalog, r.saved)}".`); } };
  const byIdName = (c: PresetCatalog, id: string) => c.presets.find((p) => p.id === id)?.name ?? id;
  const star = async (p: PresetRow) => { const c = await call(() => api.presets(dir, "favorite", { id: p.id, on: !p.favorite })); if (c) setCat(c); };
  const exportOne = async (p: PresetRow) => { const f = await save({ defaultPath: `${p.id}.json`, filters: [{ name: "Preset", extensions: ["json"] }] }); if (typeof f === "string") { const r = await call(() => api.presets<{ path: string }>(dir, "export", { id: p.id, path: f })); if (r) setMsg(`Saved ${p.name} as a file.`); } };
  const importOne = async () => { const f = await open({ multiple: false, filters: [{ name: "Preset", extensions: ["json"] }] }); if (typeof f === "string") { const r = await call(() => api.presets<{ imported: string; name: string; catalog: PresetCatalog }>(dir, "import_file", { path: f })); if (r) { setCat(r.catalog); setMsg(`Added "${r.name}" to your presets.`); } } };
  const remove = async (p: PresetRow) => { const c = await call(() => api.presets(dir, "delete_mine", { id: p.id })); if (c) { setCat(c); setStack((s) => s.filter((x) => x !== p.id)); } };
  const doable = plan?.changes.some((c) => c.status === "new" || c.status === "replace");

  return (
    <Sheet label="Presets" className="ps-sheet" onDismiss={onClose}>
      <div className="vs-head"><h2>Presets <span className="dim pd-sub">named settings you can stack</span></h2><div style={{ flex: 1 }} />
        <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
      <div className="pd-tabs" role="tablist" aria-label="Presets">
        {([["library", "Library"], ["series", "Series plan"], ["vertical", "Vertical version"]] as const).map(([id, text]) => (
          <button key={id} type="button" role="tab" id={`ps-tab-${id}`} aria-selected={tab === id} aria-controls={`ps-panel-${id}`} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{text}</button>))}
      </div>
      {err && <p className="error-text" role="alert">{err}</p>}
      {msg && <p className="ps-msg" role="status">{msg}</p>}
      {pending.length > 0 && <p className="ps-msg" role="status">You chose {pending.map((id) => byId.get(id)?.name ?? id).join(", ")} when you made this film. It is already in your stack: press <b>Preview what this changes</b>, and nothing is changed until you apply it.</p>}
      {tab === "library" && (
        <div role="tabpanel" id="ps-panel-library" aria-labelledby="ps-tab-library" className="ps-grid">
          <div className="ps-left">
            <p className="sub">Pick one or more presets and they stack: a later one wins over an earlier one, and a choice you already made beats them all. Nothing changes until you press Apply, nothing is regenerated and nothing is charged.</p>
            <div className="ps-tools">
              <label className="ps-search">Search <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="micro-drama, storybook, vertical…" /></label>
              <div className="ps-filters" role="group" aria-label="Show">
                {FILTERS.map(([id, t]) => <button key={id} type="button" className={filter === id ? "on" : ""} aria-pressed={filter === id} onClick={() => setFilter(id)}>{t}</button>)}
              </div>
              <button type="button" className="btn small" onClick={importOne} disabled={busy}>Add a preset file…</button>
            </div>
            {!cat ? <p className="dim">Loading…</p> : shown.length === 0 ? <p className="dim">No preset matches.</p> : (
              <ul className="ps-cards">
                {shown.map((p) => (
                  <li key={p.id} className={`ps-card ${p.in_stack || stack.includes(p.id) ? "on" : ""}`} aria-label={p.name}>
                    {p.thumbnail ? <img src={`/${p.thumbnail}`} alt="" loading="lazy" /> : <div className="ps-noimg" aria-hidden="true">{p.type}</div>}
                    <div className="ps-body">
                      <div className="ps-title"><b>{p.name}</b><button type="button" className="ps-star" aria-pressed={p.favorite} aria-label={`${p.favorite ? "Unmark" : "Mark"} ${p.name} as a favorite`} onClick={() => void star(p)}>{p.favorite ? "★" : "☆"}</button></div>
                      <p className="dim ps-kind">{p.group}{p.recent ? " · used recently" : ""}</p>
                      <p className="ps-desc">{p.description}</p>
                      {p.includes.length > 0 && <p className="dim ps-inc">Stacks: {p.includes.map((i) => byId.get(i)?.name ?? i).join(", ")}</p>}
                      <div className="ps-actions">
                        <button type="button" className={`btn small ${stack.includes(p.id) ? "primary" : ""}`} aria-pressed={stack.includes(p.id)} onClick={() => toggle(p.id)}>{stack.includes(p.id) ? "In your stack" : "Add to stack"}</button>
                        <button type="button" className="btn small ghost" onClick={() => void exportOne(p)} aria-label={`Save ${p.name} as a file`}>Save as file…</button>
                        {p.mine && <button type="button" className="btn small ghost" onClick={() => void remove(p)} aria-label={`Delete ${p.name}`}>Delete</button>}
                      </div>
                    </div>
                  </li>))}
              </ul>)}
          </div>
          <aside className="ps-stack" aria-label="Your stack">
            <h3 className="perf-h">Your stack</h3>
            {stack.length === 0 ? <p className="dim">Add a preset to start. A production preset already stacks the visual, acting, editing, colour and delivery presets that suit it.</p> : (
              <ol className="ps-order">
                {stack.map((id, i) => (
                  <li key={id}><span>{byId.get(id)?.name ?? id}</span>
                    <button type="button" className="btn small ghost" disabled={i === 0} aria-label={`Move ${byId.get(id)?.name ?? id} earlier`} onClick={() => move(i, -1)}>↑</button>
                    <button type="button" className="btn small ghost" disabled={i === stack.length - 1} aria-label={`Move ${byId.get(id)?.name ?? id} later`} onClick={() => move(i, 1)}>↓</button>
                    <button type="button" className="btn small ghost" aria-label={`Take ${byId.get(id)?.name ?? id} out of the stack`} onClick={() => toggle(id)}>×</button></li>))}
              </ol>)}
            <div className="ps-buttons">
              <button type="button" className="btn small" disabled={busy || stack.length === 0} onClick={() => void preview()}>Preview what this changes</button>
              <button type="button" className="btn small ghost" disabled={busy || !cat || cat.applied === 0} onClick={() => void undo()} title="Put back what the last application changed">Undo the last application</button>
            </div>
            {plan && (
              <section className="ps-plan" aria-label="What would change">
                <table>
                  <thead><tr><th scope="col">Setting</th><th scope="col">Now</th><th scope="col">Would be</th><th scope="col"> </th></tr></thead>
                  <tbody>
                    {plan.changes.map((c) => (
                      <tr key={c.key} className={`st-${c.status}`}>
                        <th scope="row">{KEY_NAME[c.key] ?? c.key}</th><td>{say(c.key, c.now)}</td><td>{say(c.key, c.to)}<span className="dim"> ({byId.get(c.by)?.name ?? c.by})</span></td>
                        <td><span className={`ps-chip ${c.status}`}>{STATUS[c.status]}</span>
                          {(c.status === "yours" || c.status === "replace") && <label className="ps-rep"><input type="checkbox" checked={replace.includes(c.key)} onChange={(e) => setReplace((r) => (e.target.checked ? [...r, c.key] : r.filter((k) => k !== c.key)))} /> Replace mine</label>}
                          {c.why && <span className="dim"> {c.why}</span>}</td>
                      </tr>))}
                  </tbody>
                </table>
                {plan.notes.map((n) => <p key={n} className="dim ps-note">{n}</p>)}
                <button type="button" className="btn small primary" disabled={busy || !doable} onClick={() => void apply()}>Apply</button>
                {!doable && <span className="dim"> Nothing new to apply.</span>}
              </section>)}
            <div className="ps-keep">
              <label>Keep this as my own preset <input type="text" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="My look" /></label>
              <button type="button" className="btn small" disabled={busy || !name.trim()} onClick={() => void keep()} title={stack.length ? "Keep the settings of the stack above" : "Keep the choices this film has made"}>Keep</button>
            </div>
          </aside>
        </div>)}
      {tab === "series" && <div role="tabpanel" id="ps-panel-series" aria-labelledby="ps-tab-series"><SeriesTab dir={dir} presets={cat?.presets.filter((p) => p.series) ?? []} episodes={cat?.setup?.episodes} /></div>}
      {tab === "vertical" && <div role="tabpanel" id="ps-panel-vertical" aria-labelledby="ps-tab-vertical"><VerticalTab dir={dir} /></div>}
    </Sheet>
  );
}

/** The micro-drama plan: made free from an idea, every part editable, suggestions marked until they are yours. */
function SeriesTab({ dir, presets, episodes }: { dir: string; presets: PresetRow[]; episodes?: number }) {
  const [st, setSt] = useState<SeriesState | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [rep, setRep] = useState<SeriesReport | null>(null);
  const [idea, setIdea] = useState("");
  const [eps, setEps] = useState(episodes ?? 10);                         // the number chosen when the film was made on Home, if any
  const [secs, setSecs] = useState(90);
  const [preset, setPreset] = useState("vertical_micro_drama");
  const [msg, setMsg] = useState("");
  const call = useCallback(async (action: Parameters<typeof api.series>[1], data: Record<string, unknown> = {}) => {
    setBusy(true); setErr("");
    try { const r = await api.series<unknown>(dir, action, data); if (action === "report") setRep(r as SeriesReport); else if (action !== "export_markdown") { setSt(r as SeriesState); setRep(null); } return r; } catch (e) { setErr(errorText(e)); return null; } finally { setBusy(false); }
  }, [dir]);
  useEffect(() => { void call("get"); }, [call]);
  const plan = st?.plan ?? null;
  const setEp = (n: number, data: Record<string, unknown>) => call("set_episode", { n, ...data });
  const exportDoc = async () => { const f = await save({ defaultPath: "series-plan.md", filters: [{ name: "Document", extensions: ["md"] }] }); if (typeof f === "string" && (await call("export_markdown", { path: f }))) setMsg("Saved the plan as a document."); };
  if (!st) return err ? <p className="error-text" role="alert">{err}</p> : <p className="dim">Loading…</p>;
  return (
    <div className="ps-series">
      {err && <p className="error-text" role="alert">{err}</p>}
      {msg && <p className="ps-msg" role="status">{msg}</p>}
      <p className="sub">{st.note}</p>
      {!plan ? (
        <form className="ps-form" onSubmit={(e) => { e.preventDefault(); void call("create", { idea, episodes: eps, seconds: secs, preset }); }}>
          <label>Your idea, in a sentence or two <textarea className="text-input" rows={3} maxLength={1200} value={idea} onChange={(e) => setIdea(e.target.value)} placeholder="A young nurse discovers her hospital is hiding a name." /></label>
          <div className="ps-row">
            <label>Episodes <input type="number" min={1} max={60} value={eps} onChange={(e) => setEps(Number(e.target.value))} /></label>
            <label>Each about <select value={secs} onChange={(e) => setSecs(Number(e.target.value))}>{[60, 90, 120].map((s) => <option key={s} value={s}>{s} seconds</option>)}</select></label>
            <label>Kind of story <select value={preset} onChange={(e) => setPreset(e.target.value)}>{presets.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          </div>
          <button type="submit" className="btn primary" disabled={busy || !idea.trim()}>Make the plan (free)</button>
        </form>
      ) : (
        <>
          <p className="dim">{plan.episodes.length} episodes, about {Math.round(plan.episodes.reduce((a, e) => a + e.seconds, 0) / 60)} minutes in all. Length is advice, never a limit.</p>
          <div className="ps-seasonrow">
            <SuggestRow id="s-logline" label="Logline" field={plan.season.logline} busy={busy} onSave={(v) => void call("set_season", { logline: v })} />
            <SuggestRow id="s-tone" label="Tone" field={plan.season.tone} busy={busy} onSave={(v) => void call("set_season", { tone: v })} />
            <SuggestRow id="s-rules" label="The world's rules" field={plan.season.rules} busy={busy} onSave={(v) => void call("set_season", { rules: v })} />
            <SuggestRow id="s-ending" label="How the season ends" field={plan.season.ending} busy={busy} onSave={(v) => void call("set_season", { ending: v })} />
          </div>
          <div className="ps-buttons">
            <label>Episodes <input type="number" min={1} max={60} value={plan.episodes.length} onChange={(e) => void call("resize", { episodes: Number(e.target.value) })} /></label>
            <button type="button" className="btn small" disabled={busy} onClick={() => void call("report")}>Check the plan</button>
            <button type="button" className="btn small" disabled={busy} onClick={() => void exportDoc()}>Save as a document…</button>
          </div>
          {rep && (
            <section className="ps-report" aria-label="Plan check">
              <p>{rep.written} of {rep.episodes} episodes have something you wrote. {rep.cliffhangers} end on a cliffhanger. {rep.budget_total_usd !== null ? `Episode budgets add up to $${rep.budget_total_usd.toFixed(2)}${rep.season_budget_usd !== null ? ` of $${rep.season_budget_usd.toFixed(2)}` : ""}.` : "No budget is set (nothing is spent by this plan)."}</p>
              <ul>{rep.notes.slice(0, 12).map((n, i) => <li key={i} className={n.level}>{n.what}</li>)}</ul>
              {rep.notes.length > 12 && <p className="dim">…and {rep.notes.length - 12} more.</p>}
            </section>)}
          <ol className="ps-eps">
            {plan.episodes.map((e) => <EpisodeCard key={e.n} e={e} busy={busy} onSet={(d) => void setEp(e.n, d)} onReset={(k) => void call("reset_field", { n: e.n, key: k })} />)}
          </ol>
        </>)}
    </div>
  );
}

function EpisodeCard({ e, busy, onSet, onReset }: { e: SeriesEpisode; busy: boolean; onSet: (d: Record<string, unknown>) => void; onReset: (k: string) => void }) {
  const row = (k: "hook" | "escalation" | "turning_point" | "ending" | "continuity", label: string) => <SuggestRow id={`e${e.n}-${k}`} label={label} field={e[k]} busy={busy} onSave={(v) => onSet({ [k]: v })} onReset={() => onReset(k)} />;
  return (
    <li className="ps-ep">
      <details>
        <summary><b>{e.title}</b> <span className="dim">{e.seconds} s · {e.role}{e.cliffhanger ? " · cliffhanger" : ""}</span></summary>
        <div className="ps-epbody">
          {row("hook", "Hook")}{row("escalation", "Escalation")}{row("turning_point", "Turning point")}{row("ending", "Ending")}{row("continuity", "Continuity: who and where must match")}
          <div className="ps-row">
            <label><input type="checkbox" checked={e.cliffhanger} onChange={(ev) => onSet({ cliffhanger: ev.target.checked })} /> Ends on a cliffhanger</label>
            <label>Seconds <input type="number" min={10} max={3600} value={e.seconds} onChange={(ev) => onSet({ seconds: Number(ev.target.value) })} /></label>
            <label>Budget cap ($, optional) <input type="number" min={0} step={0.5} value={e.budget_usd ?? ""} onChange={(ev) => onSet({ budget_usd: ev.target.value === "" ? null : Number(ev.target.value) })} /></label>
          </div>
        </div>
      </details>
    </li>
  );
}

/** What a phone-shaped version keeps of each wide shot. The film keeps its own shape; the vertical version is a separate export. */
function VerticalTab({ dir }: { dir: string }) {
  const [st, setSt] = useState<PresetStack | null>(null);
  const [shots, setShots] = useState<{ id: string; scene: number | null }[]>([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.presets<PresetStack>(dir, "stack_get").then(setSt).catch((e) => setErr(errorText(e)));
    api.grading(dir, "state").then((g) => setShots(g.shots)).catch(() => setShots([]));
  }, [dir]);
  const set = async (shot: string, x: number | null) => { setErr(""); try { setSt(await api.presets<PresetStack>(dir, "reframe_set", { shot, x })); } catch (e) { setErr(errorText(e)); } };
  if (!st) return err ? <p className="error-text" role="alert">{err}</p> : <p className="dim">Loading…</p>;
  const dv = st.delivery;
  return (
    <div className="ps-vertical">
      {err && <p className="error-text" role="alert">{err}</p>}
      <p className="sub">Your film keeps its own shape. The vertical version is made as a separate file (Export, then <b>TikTok / Reels 9:16</b>), and the original is never changed. For each shot below you can choose which part of the wide picture the phone version keeps.</p>
      <p className="dim">{dv ? `Delivery: ${say("delivery", dv)}.` : "No delivery preset has been applied. Captions in a vertical version are kept clear of the bottom only once one is (for example Vertical social 9:16)."}</p>
      {shots.length === 0 ? <p className="dim">This film has no shots yet.</p> : (
        <ul className="ps-reframe">
          {shots.map((s) => {
            const v = st.reframe[s.id] ?? 0.5;
            return (
              <li key={s.id}>
                <label htmlFor={`rf-${s.id}`}>{s.id}</label>
                <span className="dim">left</span>
                <input id={`rf-${s.id}`} type="range" min={0} max={1} step={0.05} value={v} aria-valuetext={v === 0.5 ? "the middle" : `${Math.round(v * 100)}% from the left`} onChange={(e) => void set(s.id, Number(e.target.value))} onDoubleClick={() => void set(s.id, null)} />
                <span className="dim">right</span>
                <output htmlFor={`rf-${s.id}`}>{v === 0.5 ? "middle" : `${Math.round(v * 100)}%`}</output>
              </li>);
          })}
        </ul>)}
    </div>
  );
}
