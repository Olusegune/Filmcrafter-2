import { useCallback, useEffect, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type ShowItem, type ShowStatus } from "./api";
import { ask } from "./ask";

const AUDIO = ["mp3", "wav", "m4a", "flac", "aac", "ogg"];
const money = (n: number) => `$${n.toFixed(2)}`;

/** Add an intermission card, or change one: its title, a line under it, and how long it is shown. */
export function CardSheet({ dir, act, item, onClose }: { dir: string; act: number; item?: ShowItem; onClose: (changed: boolean) => void }) {
  const [title, setTitle] = useState(item?.title ?? "Intermission");
  const [subtitle, setSubtitle] = useState(item?.subtitle ?? "");
  const [seconds, setSeconds] = useState(item?.seconds ?? 8);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      if (item) await api.show("set_card", dir, { item: item.id, title, subtitle, seconds });
      else await api.show("add_intermission", dir, { title, subtitle, seconds, act });
      onClose(true);
    } catch (x) { setErr(errorText(x)); setBusy(false); }
  };
  return (
    <div className="overlay" onClick={() => onClose(false)}>
      <form className="sheet glass" onClick={(e) => e.stopPropagation()} onSubmit={save} style={{ width: "min(520px, calc(100vw - 48px))" }}>
        <h2>{item ? "Intermission card" : "Add an intermission"}</h2>
        <p className="dim">A title card, white on black, that fades in and out. It is made when you export the show, so it costs nothing. Put music under it with <b>Sound</b>.</p>
        {err && <p className="error-text" role="alert">{err}</p>}
        <label className="field"><span>Title</span><input className="text-input" autoFocus value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} /></label>
        <label className="field"><span>A line under it (optional)</span><input className="text-input" value={subtitle} maxLength={120} placeholder="e.g. Please return to your seats" onChange={(e) => setSubtitle(e.target.value)} /></label>
        <label className="field"><span>Shown for (seconds, 2 to 60)</span><input className="text-input" type="number" min={2} max={60} step={0.5} value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} /></label>
        <div className="sheet-actions"><button type="button" className="btn ghost" onClick={() => onClose(false)}>Cancel</button>
          <button className="btn primary" type="submit" disabled={busy}>{item ? "Save" : "Add"}</button></div>
      </form>
    </div>
  );
}

/** Ambience or music that loops under one spoken scene or intermission, at a set level. Mixed in when the show is exported. */
export function AmbienceSheet({ dir, item, onClose }: { dir: string; item: ShowItem; onClose: () => void }) {
  const [cur, setCur] = useState(item.ambience);
  const [db, setDb] = useState(item.ambience?.volume_db ?? -18);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const call = async (data: Record<string, unknown>) => {
    setBusy(true); setErr("");
    try {
      const r = await api.show("set_ambience", dir, { item: item.id, ...data });
      setCur(r.acts.flatMap((a) => a.items).find((i) => i.id === item.id)?.ambience);
    } catch (x) { setErr(errorText(x)); } finally { setBusy(false); }
  };
  const choose = async () => {
    const f = await open({ filters: [{ name: "Audio", extensions: AUDIO }] });
    if (typeof f === "string") await call({ file: f, volume_db: db });
  };
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass" onClick={(e) => e.stopPropagation()} style={{ width: "min(520px, calc(100vw - 48px))" }}>
        <h2>Sound under {item.title}</h2>
        <p className="dim">An audio file (rain, a crowd, an underscore, intermission music) loops under this {item.kind === "scene" ? "scene's dialogue" : "card"} for its whole length. The scene's own track is not changed; the mix is made when you export.</p>
        {err && <p className="error-text" role="alert">{err}</p>}
        <p>{cur?.file ? <>Using <b>{cur.file.split("/").pop()}</b></> : "No sound added."}</p>
        <label className="field"><span>Level: {db} dB (quieter ← → louder)</span>
          <input type="range" min={-40} max={0} step={1} value={db} onChange={(e) => setDb(Number(e.target.value))}
                 onMouseUp={() => cur?.file && call({ volume_db: db })} onKeyUp={() => cur?.file && call({ volume_db: db })} /></label>
        <div className="sheet-actions">
          {cur?.file && <button className="btn ghost" disabled={busy} onClick={() => call({ clear: true })}>Remove</button>}
          <button className="btn" disabled={busy} onClick={choose}>{cur?.file ? "Change audio…" : "Choose audio…"}</button>
          <button className="btn primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}

/** The show's spending cap, where it stands, and a rough cost for what is left at the rate so far. */
export function BudgetSheet({ dir, budget, onClose }: { dir: string; budget: ShowStatus["budget"]; onClose: () => void }) {
  const [cap, setCap] = useState(budget.cap_usd ? String(budget.cap_usd) : "");
  const [err, setErr] = useState("");
  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setErr("");
    try { await api.show("set_budget", dir, { usd: cap.trim() ? Number(cap) : null }); onClose(); } catch (x) { setErr(errorText(x)); }
  };
  return (
    <div className="overlay" onClick={onClose}>
      <form className="sheet glass" onClick={(e) => e.stopPropagation()} onSubmit={save} style={{ width: "min(520px, calc(100vw - 48px))" }}>
        <h2>Show budget</h2>
        <p>Spent so far across every number and scene: <b>{money(budget.spent_usd)}</b> (Kie credits counted at their published rate).</p>
        {budget.rate_per_shot !== null && <p className="dim">About {money(budget.rate_per_shot)} per rendered shot so far. {budget.remaining_shots} shot{budget.remaining_shots === 1 ? "" : "s"} still to render
          {budget.estimate_remaining_usd !== null && <>, roughly {money(budget.estimate_remaining_usd)} more at that rate</>}. A guide only: free ComfyUI renders will bring it down.</p>}
        {err && <p className="error-text" role="alert">{err}</p>}
        <label className="field"><span>Budget cap in US dollars (empty for none)</span>
          <input className="text-input" inputMode="decimal" autoFocus value={cap} placeholder="e.g. 250" onChange={(e) => setCap(e.target.value)} /></label>
        <p className="dim">The cap is shown on the show screen and stops the show's overnight render when it is reached. Every render in a number or scene still asks you to confirm its price first.</p>
        <div className="sheet-actions"><button type="button" className="btn ghost" onClick={onClose}>Cancel</button><button className="btn primary" type="submit">Save</button></div>
      </form>
    </div>
  );
}

type NightState = { msg: string; item?: string } | null;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Overnight for the whole show: each directed number and scene in order on ComfyUI (the way a single video's overnight
 *  works), stopping if the show's budget is reached, then the whole show is exported. Needs FilmCrafter and ComfyUI left running. */
export function useShowOvernight(dir: string, items: ShowItem[], reload: () => Promise<void>, exportShow: () => Promise<void>, say: (t: string) => void) {
  const [night, setNight] = useState<NightState>(null);
  const stop = useRef(false);
  const current = useRef<string | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; stop.current = true; }; }, []);

  const start = useCallback(async () => {
    const todo = items.filter((i) => i.kind !== "intermission" && i.shots > 0 && i.rendered < i.shots);
    const skipped = items.filter((i) => i.kind !== "intermission" && i.shots === 0);
    if (!todo.length) { say("Nothing to render overnight: direct each number and scene first (Open it, then Direct)."); return; }
    if (!await ask(`Render overnight: ${todo.length} number${todo.length === 1 ? "" : "s"} and scene${todo.length === 1 ? "" : "s"}, one after another, on your ComfyUI.\n\n`
      + (skipped.length ? `Not directed yet, so skipped: ${skipped.map((i) => i.title).join(", ")}.\n\n` : "")
      + "Leave FilmCrafter and ComfyUI running. It stops if the show's budget is reached, then exports the show. Start?")) return;
    stop.current = false;
    let failed = "";
    try {
      for (const it of todo) {
        if (stop.current || !alive.current) break;
        const s = await api.show<ShowStatus>("status", dir);
        if (s.budget.over) { failed = `Stopped: the show's budget (${money(s.budget.cap_usd ?? 0)}) is reached.`; break; }
        current.current = it.path;
        setNight({ msg: `Starting ${it.title}…`, item: it.id });
        let r = await api.overnight<{ needs_confirm?: boolean; keyframes?: number; provider?: string; usd?: number | null }>(it.path, "start");
        if (r.needs_confirm) {
          const price = r.usd != null ? ` ≈ ${money(r.usd)}` : "";
          if (!await ask(`${it.title}: ${r.keyframes} keyframe${r.keyframes === 1 ? "" : "s"} on ${r.provider}${price}. Continue?`)) continue;
          r = await api.overnight(it.path, "start", true);
        }
        for (;;) {
          await sleep(8000);
          if (stop.current || !alive.current) { await api.overnight(it.path, "stop").catch(() => {}); break; }
          const o = await api.overnight<{ active?: boolean; with_video: number; shots: number; error?: string }>(it.path, "status");
          if (alive.current) setNight({ msg: `${it.title}: ${o.with_video} of ${o.shots} videos`, item: it.id });
          if (!o.active) { if (o.error) failed = `${it.title}: ${o.error}`; break; }
        }
        if (alive.current) await reload();
      }
      if (alive.current && !stop.current && !failed) { setNight({ msg: "Exporting the show…" }); await exportShow(); }
    } catch (e) { failed = errorText(e); }
    current.current = null;
    if (alive.current) { setNight(null); await reload().catch(() => {}); if (failed) say(failed); else if (stop.current) say("Overnight stopped."); }
  }, [dir, items, reload, exportShow, say]);

  const halt = useCallback(async () => {
    stop.current = true;
    if (current.current) await api.overnight(current.current, "stop").catch(() => {});
  }, []);
  return { night, start, halt };
}
