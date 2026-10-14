import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorText, type SceneResult, type ScenePlan, type TableRead } from "./api";
import { ask } from "./ask";
import * as I from "./icons";
import { notifyVoice, useVoiceStatus } from "./voiceHooks";
import { suggestedCap } from "./soundWords";
import { confirmWords } from "./voiceUsage";

type Mode = "voice" | "read";

const STATE_WORDS: Record<string, string> = { missing: "needs a voice line", recorded: "your recording", spoken: "spoken by ElevenLabs", no_voice: "no voice chosen" };
const credits = (n: number) => `${Math.round(n).toLocaleString()} credit${Math.round(n) === 1 ? "" : "s"}`;

/** The scenes that have someone speaking, in order. */
export function useScenes(dir: string): number[] {
  const { st } = useVoiceStatus(dir);
  return useMemo(() => [...new Set((st?.shots ?? []).filter((s) => s.people.some((p) => p.lines.length)).map((s) => s.scene))].sort((a, b) => a - b), [st]);
}

/**
 * Voice a whole scene, then listen to it before any video is made. Voicing: see who speaks and who has a voice, see the one price for every missing line, set a spending cap, say yes once;
 * a line that fails does not undo the ones that worked, and if a charge is unclear nothing more is sent. Table read: the scene's dialogue in order, with the pauses you choose.
 */
export function VoiceScene({ dir, scene: first, mode: firstMode = "voice", onClose }: { dir: string; scene?: number; mode?: Mode; onClose: () => void }) {
  const scenes = useScenes(dir);
  const [scene, setScene] = useState<number | null>(first ?? null);
  const [mode, setMode] = useState<Mode>(firstMode);
  useEffect(() => { if (scene === null && scenes.length) setScene(scenes[0]); }, [scene, scenes]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !document.querySelector(".ask, [role=alertdialog]")) { e.stopImmediatePropagation(); onClose(); } };
    window.addEventListener("keydown", k, true);
    return () => window.removeEventListener("keydown", k, true);
  }, [onClose]);
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass vsc" role="dialog" aria-label="Voice a scene" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>{mode === "voice" ? "Voice a scene" : "Listen to a scene"}</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <div className="vsc-bar">
          <div className="vr-who" role="tablist" aria-label="What to do">
            <button role="tab" aria-selected={mode === "voice"} className={mode === "voice" ? "on" : ""} onClick={() => setMode("voice")}>Voice the lines</button>
            <button role="tab" aria-selected={mode === "read"} className={mode === "read" ? "on" : ""} onClick={() => setMode("read")}>Table read</button>
          </div>
          <label className="cv-model">Scene <select value={scene ?? ""} onChange={(e) => setScene(Number(e.target.value))}>{scenes.map((n) => <option key={n} value={n}>Scene {n}</option>)}</select></label>
        </div>
        {scene === null ? <p className="dim">No scene has spoken lines yet.</p> : mode === "voice" ? <Voicing key={`v${scene}`} dir={dir} scene={scene} onRead={() => setMode("read")} /> : <Read key={`r${scene}`} dir={dir} scene={scene} />}
      </div>
    </div>
  );
}

function Voicing({ dir, scene, onRead }: { dir: string; scene: number; onRead: () => void }) {
  const [plan, setPlan] = useState<ScenePlan | null>(null);
  const [cap, setCap] = useState("");
  const [res, setRes] = useState<SceneResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.voiceDirect<ScenePlan>("scene_plan", dir, { scene }).then((p) => { setPlan(p); setCap((c) => c || (p.missing ? String(suggestedCap(p.estimate.credits)) : "")); }).catch((e) => setErr(errorText(e))), [dir, scene]);
  useEffect(() => { void load(); }, [load]);
  if (!plan) return <p className="dim">{err || "Reading the scene…"}</p>;
  const capN = Number(cap);
  const tooLow = plan.missing > 0 && (!(capN > 0) || capN < plan.estimate.credits);
  const go = async () => {
    setErr(""); setBusy(true);
    try {
      const ok = await ask(confirmWords({ action: `Voice scene ${scene}: ${plan.missing} line${plan.missing === 1 ? "" : "s"}, each in its person's voice?`, provider: "ElevenLabs",
        cost: `about ${credits(plan.estimate.credits)} (${plan.estimate.characters.toLocaleString()} characters); you set a cap of ${credits(capN)}`,
        note: "Lines you already recorded are not touched. A line that fails does not undo the others, and if a charge is unclear nothing more is sent. Every take is kept." }), { ok: "Voice the scene" });
      if (!ok) return;
      setRes(await api.voiceDirect<SceneResult>("scene_voice", dir, { scene, confirmed: true, cap_credits: capN }));
      notifyVoice(); await load();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="vsc-body">
      <section>
        <h3>Who speaks</h3>
        <ul className="vsc-people">{plan.speakers.map((s) => <li key={s.key}><b>{s.name}</b> <span className="dim">{s.lines} line{s.lines === 1 ? "" : "s"} · {s.has_voice ? `voice: ${s.voice || "chosen"}${s.approved ? " (approved)" : ""}` : "no voice yet: choose one on the Voiceover screen or in Sound & Music"}</span></li>)}</ul>
      </section>
      <section>
        <h3>The lines</h3>
        <ul className="vsc-lines">{plan.lines.map((l) => <li key={`${l.shot}-${l.key}`} className={l.state}>
          <span className="vsc-who">{l.speaker} <span className="dim">{l.shot}</span></span><q>{l.text}</q>
          <span className="dim">{STATE_WORDS[l.state]}{l.state === "missing" && l.credits !== undefined ? ` · ${l.cached ? "already spoken, free" : credits(l.credits)}` : ""}{l.spoken_version ? " · your spoken version" : ""}</span></li>)}</ul>
      </section>
      {plan.missing > 0 ? <section className="vsc-go">
        <p>{plan.missing} line{plan.missing === 1 ? "" : "s"} to voice: <b>about {credits(plan.estimate.credits)}</b> of your ElevenLabs plan <span className="dim">({plan.estimate.characters.toLocaleString()} characters; billed to your plan, not in dollars here)</span>.</p>
        <label className="field vsc-cap"><span>Spending cap for this scene (credits)</span>
          <input type="number" min={1} value={cap} onChange={(e) => setCap(e.target.value)} aria-label="Spending cap in credits" /></label>
        {tooLow && cap !== "" && <p className="error-text">The cap is below the price. Nothing is sent unless the cap covers it.</p>}
        <div className="cv-actions"><button className="btn primary" disabled={busy || tooLow} onClick={() => void go()}><I.Sparkle size={14} /> {busy ? "Voicing…" : "Voice the scene…"}</button>
          <span className="dim">You are asked once more, with the price, before anything is sent.</span></div>
        {plan.no_voice.length > 0 && <p className="dim">{plan.no_voice.join(", ")} {plan.no_voice.length === 1 ? "has" : "have"} no voice yet, so those lines are left out.</p>}
      </section> : <p className="dim">{plan.lines.some((l) => l.state === "no_voice") ? "The lines that are left need a voice first." : "Every line in this scene has a voice."}</p>}
      {res && <section className="vsc-res" aria-label="Results">
        <h3>What happened</h3>
        <ul>{res.results.map((r) => <li key={`${r.shot}-${r.speaker}`} className={r.ok ? "ok" : "bad"}>{r.ok ? "Done" : r.attempted ? "Did not work" : "Not tried"}: {r.speaker} in {r.shot}{r.ok ? ` · ${credits(r.credits ?? 0)}` : r.why ? ` · ${r.why}` : ""}</li>)}</ul>
        <p>{res.done} voiced{res.failed ? `, ${res.failed} failed` : ""} · {credits(res.spent_credits)} used of your cap of {credits(res.cap)}.</p>
        {res.stopped && <p className="error-text" role="alert">{res.stopped}</p>}
        {res.done > 0 && <button className="btn" onClick={onRead}>Listen to the scene</button>}
      </section>}
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>
  );
}

function Read({ dir, scene }: { dir: string; scene: number }) {
  const [t, setT] = useState<TableRead | null>(null);
  const [pause, setPause] = useState(0.6);
  const [now, setNow] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const stop = useRef(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => { api.voiceDirect<TableRead>("table_read", dir, { scene }).then(setT).catch((e) => setErr(errorText(e))); }, [dir, scene]);
  const halt = useCallback(() => { stop.current = true; window.clearTimeout(timer.current); audio.current?.pause(); setNow(null); }, []);
  useEffect(() => halt, [halt]);
  const play = (from: number) => {
    if (!t) return;
    stop.current = false;
    const step = (i: number) => {
      if (stop.current) return;
      if (i >= t.lines.length) { setNow(null); return; }
      const l = t.lines[i];
      setNow(i);
      if (!l.file) { timer.current = window.setTimeout(() => step(i + 1), 800); return; }                       // a line with no voice yet: a short silence, then on
      const a = new Audio(api.mediaUrl(`${dir}/${l.file}`));
      audio.current = a;
      a.onended = () => { timer.current = window.setTimeout(() => step(i + 1), pause * 1000); };
      a.onerror = () => step(i + 1);
      void a.play().catch(() => step(i + 1));
    };
    step(from);
  };
  if (!t) return <p className="dim">{err || "Gathering the lines…"}</p>;
  return (
    <div className="vsc-body">
      <p className="dim">The scene's dialogue in order, with the recordings and spoken lines you already have. It costs nothing and makes no video.</p>
      <div className="vsc-play">
        {now === null ? <button className="btn primary" disabled={t.lines.length === t.silent} onClick={() => play(0)}><I.Play size={13} /> Play the scene</button>
          : <button className="btn" onClick={halt}><I.Pause size={13} /> Stop</button>}
        <label className="vsc-pause">Pause between lines <input type="range" min={0} max={3} step={0.1} value={pause} onChange={(e) => setPause(Number(e.target.value))} aria-label="Pause between lines" /> <span className="num">{pause.toFixed(1)} s</span></label>
        <span className="dim">{t.seconds ? `${t.seconds.toFixed(1)} s of voice` : "no voice yet"}{t.silent ? ` · ${t.silent} line${t.silent === 1 ? "" : "s"} without a voice` : ""}</span>
      </div>
      <ul className="vsc-lines">{t.lines.map((l, i) => <li key={`${l.shot}-${l.key}`} className={`${now === i ? "now" : ""} ${l.file ? "" : "missing"}`}>
        <button className="vchip-play" disabled={!l.file} onClick={() => { halt(); play(i); }} aria-label={`Play from ${l.speaker}'s line`}><I.Play size={11} /></button>
        <span className="vsc-who">{l.speaker} <span className="dim">{l.shot}</span></span><q>{l.text}</q>
        <span className="dim">{l.file ? `${(l.seconds ?? 0).toFixed(1)} s · ${l.source === "elevenlabs" ? "spoken by ElevenLabs" : "your recording"}` : "no voice yet"}</span></li>)}</ul>
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>
  );
}
