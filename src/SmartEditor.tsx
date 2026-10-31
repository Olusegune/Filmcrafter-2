import { useCallback, useEffect, useState } from "react";
import { Sheet } from "./Sheet";
import { api, errorText, type Suggestions, type Suggestion } from "./api";
import * as I from "./icons";
import "./smart.css";

const saved = (s: number) => (s >= 0 ? `Saves ${s.toFixed(1)} s` : `Adds ${(-s).toFixed(1)} s`);

/**
 * The Smart Editor: suggestions for the cut, each with what it would change, why it may help, the clips it touches and a real before and after preview. Nothing changes until you accept
 * one (one undo takes it back); one you refuse stays away. Free and local: it only reads the film and writes the cut when you accept.
 */
export function SmartEditorSheet({ dir, onClose, onChanged }: { dir: string; onClose: () => void; onChanged?: () => void }) {
  const [recipes, setRecipes] = useState<{ id: string; label: string; for: string; built: boolean }[]>([]);
  const [recipe, setRecipe] = useState("restrained_drama");
  const [res, setRes] = useState<Suggestions | null>(null);
  const [text, setText] = useState("");
  const [said, setSaid] = useState("");
  const [shown, setShown] = useState<{ id: string; before: string; after: string } | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [done, setDone] = useState("");

  const suggest = useCallback(async (r: string) => {
    setBusy("Looking at the cut…"); setErr(""); setSaid("");
    try { setRes(await api.smartEditor<Suggestions>(dir, "suggest", { recipe: r })); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  }, [dir]);
  useEffect(() => {
    api.smartEditor<{ recipes: typeof recipes; default: string }>(dir, "recipes").then((r) => { setRecipes(r.recipes); setRecipe(r.default); void suggest(r.default); }).catch((e) => setErr(errorText(e)));
  }, [dir, suggest]);

  const act = async (action: "accept" | "reject" | "preview", p: Suggestion) => {
    setBusy(action === "preview" ? "Making the preview…" : ""); setErr(""); setDone("");
    try {
      if (action === "preview") { const r = await api.smartEditor<{ before: string; after: string }>(dir, "preview", { id: p.id, recipe }); setShown({ id: p.id, before: r.before, after: r.after }); }
      else {
        await api.smartEditor(dir, action, { id: p.id, recipe });
        setShown(null);
        if (action === "accept") { setDone(`Done: ${p.title}. Ctrl+Z puts it back.`); onChanged?.(); window.dispatchEvent(new Event("pf-cut-changed")); }
        else setDone("Left out. It will not be suggested again unless you ask for it back.");
        setRes((r) => r && { ...r, proposals: r.proposals.filter((x) => x.id !== p.id) });
        if (action === "accept") await suggest(recipe);
      }
    } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const ask = async () => {
    if (!text.trim()) return;
    setBusy("Reading your request…"); setErr(""); setDone(""); setShown(null);
    try { const r = await api.smartEditor<Suggestions & { understood: boolean; message: string }>(dir, "ask", { text }); setRes(r); setSaid(r.message); if (r.recipe?.id) setRecipe(r.recipe.id); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const again = async () => { setErr(""); await api.smartEditor(dir, "reset_rejected").then(() => suggest(recipe)).catch((e) => setErr(errorText(e))); };

  return (
    <Sheet label="Smart Editor" className="se-sheet" onDismiss={onClose}>
      <div className="vs-head"><h2>Smart Editor <span className="dim pd-sub">suggestions for the cut</span></h2><div style={{ flex: 1 }} />
        <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
      <p className="sub">It reads the cut, the dialogue, and the beats and directions you wrote, and suggests a few edits it can explain. It never changes your film until you accept one, a pause you asked for is left alone, and one undo takes an accepted suggestion back. Free; nothing is sent anywhere.</p>
      {err && <p className="error-text" role="alert">{err}</p>}
      {done && <p className="se-done" role="status">{done}</p>}
      <div className="se-bar">
        <label>Editing style
          <select value={recipe} onChange={(e) => { setRecipe(e.target.value); void suggest(e.target.value); }} disabled={!!busy}>
            {recipes.map((r) => <option key={r.id} value={r.id} disabled={!r.built}>{r.label}{r.built ? "" : " (not built yet)"}</option>)}
          </select></label>
        <form className="se-ask" onSubmit={(e) => { e.preventDefault(); void ask(); }}>
          <label>Or ask in your own words
            <input type="text" value={text} maxLength={300} placeholder="Tighten this scene" onChange={(e) => setText(e.target.value)} /></label>
          <button type="submit" className="btn small" disabled={!!busy || !text.trim()}>Ask</button>
        </form>
      </div>
      {recipes.find((r) => r.id === recipe)?.for && <p className="dim se-for">{recipes.find((r) => r.id === recipe)!.for}</p>}
      {said && <p className="se-said" role="status">{said}</p>}
      {busy && <p className="dim" role="status">{busy}</p>}
      {!busy && res && res.proposals.length === 0 && <p className="dim">{res.kept.length ? "Nothing to suggest: what could be tighter was kept on purpose (below)." : "Nothing to suggest for this cut in this style. That is a good sign, not a gap."}</p>}
      <ul className="se-list">
        {res?.proposals.map((p) => (
          <li key={p.id} className="se-card" aria-label={p.title}>
            <div className="se-head"><h3>{p.title}</h3><span className="se-chip">{saved(p.saves)}</span></div>
            <p><b>What:</b> {p.what}</p>
            <p className="dim"><b>Why:</b> {p.why}</p>
            <p className="dim se-clips">Clips: {p.shots.join(", ")}</p>
            {shown?.id === p.id && (
              <div className="se-previews">
                <figure><video controls src={api.mediaUrl(`${dir}/${shown.before}`)} aria-label="Before" /><figcaption>Before</figcaption></figure>
                <figure><video controls src={api.mediaUrl(`${dir}/${shown.after}`)} aria-label="After the suggestion" /><figcaption>After</figcaption></figure>
              </div>)}
            <div className="se-actions">
              <button type="button" className="btn small" disabled={!!busy} onClick={() => void act("preview", p)}>Preview before and after</button>
              <button type="button" className="btn small primary" disabled={!!busy} onClick={() => void act("accept", p)}>Accept</button>
              <button type="button" className="btn small ghost" disabled={!!busy} onClick={() => void act("reject", p)}>Not this one</button>
            </div>
          </li>))}
      </ul>
      {res && res.kept.length > 0 && (
        <section className="se-kept" aria-label="Left alone on purpose">
          <h4 className="pd-h">Left alone on purpose</h4>
          <ul>{res.kept.map((k) => <li key={k.clip}>{k.why}</li>)}</ul>
        </section>)}
      <p className="dim se-foot"><button type="button" className="link" onClick={() => void again()}>Show the ones I said no to again</button></p>
    </Sheet>
  );
}
