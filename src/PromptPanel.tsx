import { useEffect, useRef, useState } from "react";
import { api, errorText, type PromptIssue, type PromptPreview, type PromptRecipe, type PromptWrite, type TakePrompt } from "./api";
import * as I from "./icons";

/** The overrides a take is queued with, from the prompt choice and the one-line direction. Pure. */
export function promptOverrides(p: TakePrompt, direction: string): Record<string, unknown> {
  if (p.mode === "mine" && p.text.trim()) return { _prompt: p.text.trim(), ...(p.only ? { _prompt_only: true } : {}) };
  return direction.trim() ? { _note: direction.trim() } : {};
}

export const LEVEL_LABEL: Record<PromptIssue["level"], string> = { problem: "Fix this", warn: "Check this", tip: "Tip" };

/** Counts how much of the model's limit the words use, in words people read. */
export function counter(chars: number, limit: number): string { return limit ? `${chars} of ${limit} characters` : `${chars} characters`; }

const useDebounced = <T,>(value: T, ms: number): T => {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
};

/**
 * The prompt for a take. Either FilmCrafter writes it from the shot (and you may add one line of direction), or you write it: what happens between the first picture and the last.
 * When you write it you get help: "Write it for me" turns plain words into a prompt that works (with the AI brain if one is set up), recipes for the shots two pictures make possible
 * (a figure dissolving into light, someone ageing, a shot that flows to the next), a live check of what is likely to go wrong, and the exact words that will be sent.
 */
export function PromptPanel({ dir, shot, provider, model, prompt, onPrompt, direction, onDirection, frames }: {
  dir: string; shot: string; provider: string; model: string; prompt: TakePrompt; onPrompt: (p: TakePrompt) => void; direction: string; onDirection: (t: string) => void; frames: boolean;
}) {
  const mine = prompt.mode === "mine";
  const [issues, setIssues] = useState<PromptIssue[]>([]);
  const [limit, setLimit] = useState(0);
  const [recipes, setRecipes] = useState<PromptRecipe[] | null>(null);
  const [helper, setHelper] = useState(false);
  const [intent, setIntent] = useState("");
  const [writing, setWriting] = useState(false);
  const [written, setWritten] = useState<PromptWrite | null>(null);
  const [before, setBefore] = useState<string | null>(null);
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [showSent, setShowSent] = useState(false);
  const [err, setErr] = useState("");
  const text = useDebounced(prompt.text, 450);
  const saved = useRef(prompt);
  saved.current = prompt;

  useEffect(() => {   // remember the choice with the shot
    const t = setTimeout(() => { api.compose(dir, "prompt_set", { shot, mode: saved.current.mode, text: saved.current.text, only: saved.current.only }).catch(() => {}); }, 600);
    return () => clearTimeout(t);
  }, [dir, shot, prompt.mode, prompt.text, prompt.only]);
  useEffect(() => {   // the live check
    if (!mine) { setIssues([]); return; }
    let live = true;
    api.compose<{ issues: PromptIssue[]; limit: number }>(dir, "prompt_lint", { shot, text, provider, model }).then((r) => { if (live) { setIssues(r.issues); setLimit(r.limit); } }).catch(() => {});
    return () => { live = false; };
  }, [dir, shot, text, mine, provider, model]);
  useEffect(() => {   // what will really be sent
    if (!showSent) return;
    let live = true;
    api.compose<PromptPreview>(dir, "prompt_preview", { shot, provider, model, mode: prompt.mode, text, only: prompt.only, note: direction }).then((r) => { if (live) setPreview(r); }).catch((e) => live && setErr(errorText(e)));
    return () => { live = false; };
  }, [dir, shot, showSent, provider, model, prompt.mode, text, prompt.only, direction]);
  useEffect(() => { setWritten(null); setBefore(null); setRecipes(null); setHelper(false); setIntent(""); setPreview(null); }, [shot]);

  const set = (patch: Partial<TakePrompt>) => onPrompt({ ...prompt, ...patch });
  const openRecipes = async () => { if (!recipes) setRecipes(await api.compose<PromptRecipe[]>(dir, "prompt_recipes", { shot }).catch(() => [])); else setRecipes(null); };
  const use = (t: string) => { setBefore(prompt.text); set({ mode: "mine", text: t }); };
  const write = async () => {
    setWriting(true); setErr("");
    try { const r = await api.compose<PromptWrite>(dir, "prompt_write", { shot, intent, provider, model }); setWritten(r); use(r.prompt); }
    catch (e) { setErr(errorText(e)); } finally { setWriting(false); }
  };

  return (
    <section className="pp" aria-label="The prompt for this take">
      <div className="pp-choice" role="radiogroup" aria-label="Who writes the prompt">
        <button role="radio" aria-checked={!mine} className={!mine ? "on" : ""} onClick={() => set({ mode: "auto" })}>FilmCrafter writes it from the shot</button>
        <button role="radio" aria-checked={mine} className={mine ? "on" : ""} onClick={() => set({ mode: "mine" })}>I'll write it</button>
      </div>
      {!mine && <>
        <label className="fr-label" htmlFor="pp-direction">One line of direction <span className="dim">(optional, added to the prompt)</span></label>
        <textarea id="pp-direction" className="text-input" rows={2} maxLength={600} value={direction} onChange={(e) => onDirection(e.target.value)} placeholder="e.g. a slow push in; she never looks at the camera" />
        <p className="dim pp-hint">Want full control of what happens? Choose <b>I'll write it</b>: it is the best way to get a shot where something changes between the two pictures.</p>
      </>}
      {mine && <>
        <p className="pp-guide">{frames ? "The two pictures already show how the shot looks at the start and the end. Use your words for what happens between them: who does what, in order, and what changes." : "Say what happens in the shot: who does what, in order. The reference pictures show how people and places look."}</p>
        <textarea id="pp-text" className="text-input pp-text" rows={7} value={prompt.text} aria-label="Your prompt" onChange={(e) => set({ text: e.target.value })}
                  placeholder={frames ? "e.g. Little Sege hugs Older Sege. A bright light glows in Older Sege's chest and Little Sege dissolves into it, drawn into his heart. The light fades and Older Sege stands calm." : "What happens in this shot"} />
        <div className="pp-bar"><span className="dim" aria-live="polite">{counter(new TextEncoder().encode(prompt.text.trim()).length, limit)}</span>
          {before !== null && <button className="link" onClick={() => { set({ text: before }); setBefore(null); }}>Undo the last insert</button>}</div>
        <div className="pp-tools">
          <button className="btn small" onClick={() => setHelper((v) => !v)} aria-expanded={helper}><I.Wand size={13} /> Write it for me</button>
          <button className="btn ghost small" onClick={openRecipes} aria-expanded={!!recipes}>Recipes for shots like this</button>
        </div>
        {helper && <div className="pp-helper">
          <label className="fr-label" htmlFor="pp-intent">Say it in your own words, however rough</label>
          <textarea id="pp-intent" className="text-input" rows={3} value={intent} onChange={(e) => setIntent(e.target.value)}
                    placeholder="e.g. little Sege is hugging older Sege, then a bright light comes out of older Sege's chest and little Sege disappears" />
          <button className="btn primary small" disabled={writing || !intent.trim()} onClick={write}>{writing ? "Writing…" : "Write the prompt"}</button>
          {written && <div className="pp-written" role="status">
            <p><b>{written.source === "ai" ? "Written by your AI brain." : "Put into order by a template."}</b> {written.why}</p>
            {written.tips.map((t) => <p key={t} className="dim">Tip: {t}</p>)}</div>}
        </div>}
        {recipes && <ul className="pp-recipes" aria-label="Recipes">
          {recipes.map((r) => <li key={r.id}><div><b>{r.title}</b><span className="dim">{r.blurb}</span></div><button className="btn small" onClick={() => { use(r.text); setRecipes(null); }}>Use this</button></li>)}</ul>}
        {issues.length > 0 && <ul className="pp-issues" aria-label="Checks">
          {issues.map((i) => <li key={i.text} className={i.level}><i>{LEVEL_LABEL[i.level]}</i> {i.text}</li>)}</ul>}
        <label className="pp-only"><input type="checkbox" checked={prompt.only} onChange={(e) => set({ only: e.target.checked })} /> Use only my words
          <span className="dim"> (leaves out FilmCrafter's camera, setting, light, wardrobe and character lines; the look and the no-text rule always stay)</span></label>
      </>}
      <details className="pp-sent" open={showSent} onToggle={(e) => setShowSent((e.target as HTMLDetailsElement).open)}>
        <summary>Show exactly what will be sent</summary>
        {preview ? <>
          <pre className="pp-final">{preview.prompt}</pre>
          <p className="dim">{counter(preview.chars, preview.limit)}{preview.left_out.length ? ` · left out to fit: ${preview.left_out.length} line${preview.left_out.length === 1 ? "" : "s"}` : ""}</p></> : <p className="dim">Reading…</p>}
      </details>
      {err && <p className="error-text" role="alert">{err}</p>}
    </section>
  );
}
