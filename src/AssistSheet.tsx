import { useState } from "react";
import { api, errorText, type AssistKind, type BibleView } from "./api";
import { ask } from "./ask";
import * as I from "./icons";

type Proposal = Record<string, unknown>;
const LABEL: Record<string, string> = {
  role: "Role in the story", age: "Age", physical: "Physical traits", relationships: "Relationships", arc: "Emotional arc", voice: "Voice", notes: "Notes", description: "What it is",
  entrances: "Entrances", exits: "Exits", doors: "Doors", windows: "Windows", landmarks: "Landmarks", furniture: "Furniture", blocking: "Where actors can stand", camera_zones: "Where the camera can go",
  lighting: "Lighting", day_night: "Day or night", world: "The world", tone: "Tone", rules: "Rules the film keeps", avoid: "Avoid", visual: "Visual", cinematography: "Cinematography", acting: "Acting",
  colour: "Colour", continuity: "Continuity", lane: "Visual style", traits: "What defines this look",
};

/** The flat list of things a suggestion offers: [group, key, text, the text you have now]. */
export function rows(kind: AssistKind, p: Proposal, b: BibleView, id?: string | null): { group: string; key: string; label: string; text: string; mine: string }[] {
  const out: { group: string; key: string; label: string; text: string; mine: string }[] = [];
  const add = (group: string, key: string, text: unknown, mine: string) => { if (typeof text === "string" && text.trim()) out.push({ group, key, label: LABEL[key] ?? key, text, mine: mine.trim() }); };
  if (kind === "character") {
    const c = b.characters.find((x) => x.id === id);
    for (const k of ["role", "age", "physical", "relationships", "arc", "voice", "notes"]) add("", k, p[k], String((c as unknown as Record<string, string>)?.[k] ?? ""));
  } else if (kind === "environment") {
    const e = b.environments.find((x) => x.id === id);
    for (const k of ["description", "notes"]) add("", k, p[k], String((e as unknown as Record<string, string>)?.[k] ?? ""));
    for (const [k, v] of Object.entries((p.spatial as Record<string, string>) ?? {})) add("spatial", k, v, e?.spatial?.[k] ?? "");
  } else if (kind === "prop") {
    add("", "notes", p.notes, b.props.find((x) => x.id === id)?.notes ?? "");
  } else {
    for (const [k, v] of Object.entries((p.rules as Record<string, string>) ?? {})) add("rules", k, v, b.rules[k] ?? "");
    for (const [k, v] of Object.entries((p.philosophy as Record<string, string>) ?? {})) add("philosophy", k, v, b.philosophy[k] ?? "");
    const st = (p.style as Record<string, string>) ?? {};
    add("style", "lane", st.lane, b.style.lane); add("style", "traits", st.traits, b.style.traits);
  }
  return out;
}

/** Ask for a suggestion: shows what will be sent and the price, and only goes ahead after a yes. Returns the suggestion, or null. */
export async function askForHelp(dir: string, kind: AssistKind, id: string | null, name: string): Promise<Proposal | null> {
  const est = await api.assist("estimate", dir, { kind, id });
  const price = est.local ? "free (your own model writes it)" : `about $${est.usd.toFixed(est.usd < 0.01 ? 4 : 3)}`;
  if (!await ask(`Write suggestions for ${name}?\n\nThis sends ${est.sends} to your writing AI. Price: ${price}.\nNothing in your Bible changes until you choose what to use.`, { ok: "Write suggestions" })) return null;
  return (await api.assist("suggest", dir, { kind, id })).proposal;
}

/**
 * What the writing helper suggested, next to what you have. Tick what you want; what you already wrote is marked as yours and is only replaced if you tick it.
 */
export function AssistSheet({ dir, kind, id, name, proposal, bible, onClose, onApplied }: { dir: string; kind: AssistKind; id: string | null; name: string; proposal: Proposal; bible: BibleView; onClose: () => void; onApplied: (v: BibleView) => void }) {
  const list = rows(kind, proposal, bible, id);
  const wardrobe = ((proposal.wardrobe as { name: string; notes: string }[]) ?? []).filter((w) => w.name);
  const states = ((proposal.states as { label: string; age: string; notes: string }[]) ?? []).filter((s) => s.label);
  const [text, setText] = useState<Record<string, string>>(() => Object.fromEntries(list.map((r) => [`${r.group}.${r.key}`, r.text])));
  const [on, setOn] = useState<Record<string, boolean>>(() => ({ ...Object.fromEntries(list.map((r) => [`${r.group}.${r.key}`, !r.mine])), ...Object.fromEntries(wardrobe.map((w) => [`w:${w.name}`, true])), ...Object.fromEntries(states.map((s) => [`s:${s.label}`, true])) }));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const chosen = list.filter((r) => on[`${r.group}.${r.key}`]).length + wardrobe.filter((w) => on[`w:${w.name}`]).length + states.filter((s) => on[`s:${s.label}`]).length;

  const apply = async () => {
    setBusy(true); setErr("");
    try {
      const pick = (g: string) => Object.fromEntries(list.filter((r) => r.group === g && on[`${g}.${r.key}`]).map((r) => [r.key, text[`${g}.${r.key}`]]));
      let v: BibleView | null = null;
      if (kind === "world") {
        v = await api.bible("update_rules", dir, { rules: pick("rules"), philosophy: pick("philosophy"), style: pick("style") });
      } else {
        const own = pick("");
        const item: Record<string, unknown> = { id, ...own };
        if (kind === "environment") item.spatial = pick("spatial");
        v = await api.bible("upsert", dir, { kind, item });
        if (kind === "character") {
          for (const w of wardrobe.filter((x) => on[`w:${x.name}`])) v = await api.bible("add_wardrobe", dir, { id, name: w.name, notes: w.notes });
          for (const s of states.filter((x) => on[`s:${x.label}`])) { try { v = await api.bible("add_state", dir, { kind, id, label: s.label, notes: s.notes, age: s.age }); } catch { /* a state with that name is already there */ } }
        }
      }
      onApplied(v!);
    } catch (e) { setErr(errorText(e)); setBusy(false); }
  };

  return (
    <div className="overlay" onClick={busy ? undefined : onClose}>
      <div className="sheet glass as-sheet" role="dialog" aria-label={`Suggestions for ${name}`} onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2><I.Sparkle size={16} /> Suggestions for {name}</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">Written from your story. Tick what you want to use and change any words first. What you already wrote is marked <b>yours</b> and stays unless you tick the suggestion.</p>
        {list.length === 0 && wardrobe.length === 0 && states.length === 0 && <p className="dim">Nothing new to suggest: the writing helper had no more to add.</p>}
        <div className="as-rows">
          {list.map((r) => { const k = `${r.group}.${r.key}`; return (
            <label key={k} className={`as-row ${on[k] ? "on" : ""}`}>
              <input type="checkbox" checked={!!on[k]} onChange={(e) => setOn({ ...on, [k]: e.target.checked })} />
              <span className="as-label">{r.label}{r.mine && <em> · yours: {r.mine.length > 70 ? r.mine.slice(0, 70) + "…" : r.mine}</em>}</span>
              {r.key === "lane" ? <b className="as-lane">{text[k]}</b> : <textarea className="text-input" rows={2} value={text[k]} onChange={(e) => setText({ ...text, [k]: e.target.value })} />}
            </label>); })}
          {wardrobe.length > 0 && <div className="as-group"><h3>Outfits</h3>{wardrobe.map((w) => <label key={w.name} className="as-row on"><input type="checkbox" checked={!!on[`w:${w.name}`]} onChange={(e) => setOn({ ...on, [`w:${w.name}`]: e.target.checked })} /><span className="as-label"><b>{w.name}</b> <em>{w.notes}</em></span></label>)}</div>}
          {states.length > 0 && <div className="as-group"><h3>Other states</h3>{states.map((s) => <label key={s.label} className="as-row on"><input type="checkbox" checked={!!on[`s:${s.label}`]} onChange={(e) => setOn({ ...on, [`s:${s.label}`]: e.target.checked })} /><span className="as-label"><b>{s.label}</b> <em>{[s.age && `age ${s.age}`, s.notes].filter(Boolean).join(" · ")}</em></span></label>)}</div>}
        </div>
        {err && <p className="error-text" role="alert">{err}</p>}
        <div className="sheet-actions"><button className="btn ghost" onClick={onClose} disabled={busy}>Not now</button>
          <button className="btn primary" onClick={apply} disabled={busy || chosen === 0}>{busy ? "Adding…" : `Use ${chosen} ${chosen === 1 ? "suggestion" : "suggestions"}`}</button></div>
      </div>
    </div>
  );
}
