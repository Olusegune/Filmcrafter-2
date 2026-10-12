import { useEffect, useMemo, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type CastEstimate, type CastPlan, type CastPreview, type CastVoice, type ElevenVoice, type VoiceShot } from "./api";
import { ask } from "./ask";
import { notifyVoice, useCast } from "./voiceHooks";
import * as I from "./icons";

const AUDIO = ["wav", "mp3", "m4a", "flac", "aac", "ogg"];
const EXAMPLES = [
  "A warm, tired woman in her sixties with a gentle northern accent, kind and unhurried.",
  "A bright, curious girl of about ten, quick and a little breathless, American.",
  "A low, calm man in his forties, dry humour, deliberate, slight Scottish accent.",
  "A nervous teenage boy whose voice cracks when he is excited.",
];

const plural = (n: number, w: string) => `${n.toLocaleString()} ${w}${n === 1 ? "" : "s"}`;

/** What speaking some lines would use of the ElevenLabs plan, in words (characters and credits, never dollars: ElevenLabs bills the person's own plan). */
export const priceWords = (e: Pick<CastEstimate, "characters" | "credits">) =>
  e.characters === 0 ? "Already spoken in this voice, so it costs nothing." : `${plural(e.characters, "character")}, about ${plural(e.credits, "credit")} of your ElevenLabs plan (billed by ElevenLabs, not in dollars here).`;

/** Speak one written line in the person's voice for a shot: the price is shown and a yes is asked for first; a line already spoken in that voice is free and needs no yes. Returns false if the person said no. */
export async function speakLine(dir: string, shot: string, who: string): Promise<boolean> {
  const est = await api.castVoice<CastEstimate>("estimate", dir, { items: [{ shot, speaker: who }] });
  const row = est.rows[0];
  if (!row.ok) throw new Error(row.why);
  if (!row.cached && !(await ask(`Speak ${row.shot} as ${row.speaker}?\n\n“${row.text}”\n\n${priceWords(est)}`, { ok: "Speak it" }))) return false;
  await api.castVoice("speak", dir, { shot, speaker: who, confirmed: true });
  notifyVoice();
  return true;
}

/**
 * Voices for your characters, made right here with ElevenLabs: choose one from your ElevenLabs library, design a new one from a description, or clone one from your own recording.
 * Then a written line can be spoken in it (the price is shown first), as a stand-in until your own recording replaces it.
 */
export function CastVoices({ dir, shots }: { dir: string; shots: VoiceShot[] }) {
  const { cast, reload } = useCast(dir);
  const [plan, setPlan] = useState<CastPlan | null>(null);
  const [planErr, setPlanErr] = useState("");
  const [making, setMaking] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [heard, setHeard] = useState<string | null>(null);

  const people = useMemo(() => {
    const m = new Map<string, string>();
    for (const s of shots) for (const p of s.people ?? []) if (!m.has(p.key)) m.set(p.key, p.name);
    return [...m.entries()].map(([key, name]) => ({ key, name }));
  }, [shots]);

  useEffect(() => {
    if (!cast?.key) return;
    api.castVoice("status", dir, { plan: true }).then((r) => { setPlan(r.plan); setPlanErr(r.plan_error); }).catch(() => {});
  }, [dir, cast?.key, cast?.people]);

  const todo = useMemo(() => shots.flatMap((s) => (s.people ?? []).filter((p) => !p.recording && p.lines.length && cast?.people[p.key]).map((p) => ({ shot: s.id, speaker: p.name }))), [shots, cast]);

  const run = async (label: string, f: () => Promise<void>) => { setErr(""); setBusy(label); try { await f(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); } };

  const hear = (name: string) => run("hear", async () => {
    const words = `Hello, I'm ${name}. This is how I sound.`;
    if (!(await ask(`Hear ${name}'s voice say a short sentence?\n\n“${words}”\n\nThis uses ${plural(words.length, "character")} of your ElevenLabs plan (a sentence you have heard before is free).`, { ok: "Hear it" }))) return;
    const r = await api.castVoice<{ file: string }>("preview", dir, { person: name, text: words, confirmed: true });
    setHeard(r.file);
    new Audio(api.mediaUrl(`${dir}/${r.file}`)).play().catch(() => {});
  });

  const speakAll = () => run("all", async () => {
    const est = await api.castVoice<CastEstimate>("estimate", dir, { items: todo });
    const good = est.rows.filter((r) => r.ok);
    if (!good.length) throw new Error("Nothing can be spoken yet: " + (est.rows.find((r) => !r.ok) as { why: string } | undefined)?.why);
    if (!(await ask(`Speak ${plural(good.length, "line")} that have no recording yet, each in its person's voice?\n\n${priceWords(est)}\n\nYour own recordings replace these any time (the spoken ones are kept in the film's voice/_removed folder).`, { ok: "Speak them" }))) return;
    for (const r of good) { await api.castVoice("speak", dir, { shot: r.shot, speaker: r.speaker, confirmed: true }); notifyVoice(); }
  });

  if (!cast) return null;
  if (!cast.key) return (
    <section className="cv" aria-label="Voices for your characters">
      <h3>Voices for your characters</h3>
      <p className="dim">Add your ElevenLabs key in <b>Settings</b> and you can choose, design or clone a voice for each character here, then have the written lines spoken in it.</p>
    </section>);

  return (
    <section className="cv" aria-label="Voices for your characters">
      <div className="cv-head"><h3>Voices for your characters</h3>
        {plan && <span className="dim cv-plan">{plan.tier || "Your"} plan · {plan.left.toLocaleString()} characters left{plan.can_clone ? " · cloning on" : " · cloning needs a higher plan"}{plan.slots ? ` · ${plan.slots_used}/${plan.slots} voices` : ""}</span>}
        {!plan && planErr && <span className="error-text cv-plan">{planErr}</span>}</div>
      {people.length === 0 && <p className="dim">Nobody speaks in this film yet.</p>}
      {people.map((p) => {
        const v: CastVoice | undefined = cast.people[p.key];
        return (
          <div key={p.key} className="cv-row">
            <b>{p.name}</b>
            <span className={`cv-voice ${v ? "has" : ""}`}>{v ? <><I.Mic size={12} /> {v.voice_name || "A voice"} <em>{v.made === "design" ? "designed" : v.made === "clone" ? "cloned" : "from your library"}</em></> : "No voice yet"}</span>
            <span className="cv-btns">
              <button className="btn sm" disabled={!!busy} onClick={() => setMaking(p.name)}>{v ? "Change voice…" : "Give a voice…"}</button>
              {v && <button className="link" disabled={!!busy} onClick={() => void hear(p.name)}>Hear it</button>}
              {v && <button className="link" disabled={!!busy} onClick={() => run("clear", async () => { await api.castVoice("clear", dir, { person: p.name }); notifyVoice(); reload(); })}>Remove</button>}
            </span>
          </div>);
      })}
      {todo.length > 0 && <div className="cv-all"><button className="btn primary sm" disabled={!!busy} onClick={() => void speakAll()}><I.Sparkle size={14} /> {busy === "all" ? "Speaking…" : `Speak the ${plural(todo.length, "line")} with no recording`}</button>
        <span className="dim">The price is shown first. Your own recording replaces a spoken line any time.</span></div>}
      {heard && <p className="dim cv-heard">Played a sample ({heard.split("/").pop()}).</p>}
      {err && <p className="error-text" role="alert">{err}</p>}
      {making && <VoiceMaker dir={dir} person={making} cast={cast} plan={plan} onClose={() => setMaking(null)} onDone={() => { setMaking(null); notifyVoice(); reload(); }} />}
    </section>);
}

type Tab = "library" | "design" | "clone";

/** Choose, design or clone a voice for one person. */
function VoiceMaker({ dir, person, cast, plan, onClose, onDone }: { dir: string; person: string; cast: NonNullable<ReturnType<typeof useCast>["cast"]>; plan: CastPlan | null; onClose: () => void; onDone: () => void }) {
  const [tab, setTab] = useState<Tab>("library");
  const [model, setModel] = useState(cast.models[0]?.id ?? "eleven_multilingual_v2");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");
  const [voices, setVoices] = useState<ElevenVoice[] | null>(null);
  const [desc, setDesc] = useState("");
  const [previews, setPreviews] = useState<CastPreview[]>([]);
  const [name, setName] = useState(`${person}'s voice`);
  const [files, setFiles] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [noise, setNoise] = useState(false);

  const go = async (f: () => Promise<void>) => { setErr(""); setBusy(true); try { await f(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); } };
  const search = () => go(async () => setVoices((await api.castVoice<{ voices: ElevenVoice[] }>("library", dir, { query })).voices));
  useEffect(() => { void search(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopImmediatePropagation(); onClose(); } };
    window.addEventListener("keydown", k, true);
    return () => window.removeEventListener("keydown", k, true);
  }, [onClose]);

  const use = (v: ElevenVoice) => go(async () => { await api.castVoice("set", dir, { person, voice: { voice_id: v.voice_id, voice_name: v.name, model } }); onDone(); });
  const hearOptions = () => go(async () => {
    if (!(await ask(`Hear a few voices for ${person}?\n\nElevenLabs uses a small number of your plan's characters to make the samples (it does not say how many beforehand). Nothing is kept as a voice until you choose one.`, { ok: "Hear options" }))) return;
    setPreviews((await api.castVoice<{ previews: CastPreview[] }>("design", dir, { description: desc })).previews);
  });
  const keep = (p: CastPreview) => go(async () => { await api.castVoice("design_save", dir, { person, generated_voice_id: p.id, name, description: desc, model }); onDone(); });
  const pickFiles = async () => { const r = await open({ multiple: true, filters: [{ name: "Recordings of the voice", extensions: AUDIO }] }); if (r) setFiles(Array.isArray(r) ? r : [r]); };
  const makeClone = () => go(async () => { await api.castVoice("clone", dir, { person, name, files, consent, remove_noise: noise, model }); onDone(); });

  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass cv-sheet" role="dialog" aria-label={`A voice for ${person}`} onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>A voice for {person}</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <div className="vr-who" role="tablist" aria-label="Where the voice comes from">
          {([["library", "From your library"], ["design", "Design one"], ["clone", "Clone my own"]] as [Tab, string][]).map(([t, l]) =>
            <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{l}</button>)}
          <span style={{ flex: 1 }} />
          <label className="cv-model">Model <select value={model} onChange={(e) => setModel(e.target.value)}>{cast.models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}</select></label>
        </div>

        {tab === "library" && <div className="cv-pane">
          <form className="cv-search" onSubmit={(e) => { e.preventDefault(); void search(); }}>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search your ElevenLabs voices (a name, an accent, a mood)" aria-label="Search voices" />
            <button className="btn sm" disabled={busy}><I.Search size={13} /> Search</button></form>
          <div className="cv-list">
            {voices?.length === 0 && <p className="dim">No voices found. Design one, or clone your own.</p>}
            {(voices ?? []).map((v) => (
              <div key={v.voice_id} className="cv-item"><div><b>{v.name}</b> <span className="dim">{v.category}</span>
                <div className="dim cv-tags">{Object.values(v.labels).slice(0, 4).join(" · ")}{v.description ? ` · ${v.description}` : ""}</div></div>
                {v.preview_url && <audio controls preload="none" src={v.preview_url} aria-label={`Hear ${v.name}`} />}
                <button className="btn sm primary" disabled={busy} onClick={() => void use(v)}>Use for {person}</button></div>))}
          </div>
        </div>}

        {tab === "design" && <div className="cv-pane">
          <p className="dim">Describe the voice: age, sound, accent, mood. ElevenLabs makes a few to listen to; you keep the one you like.</p>
          <textarea rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="A warm, tired woman in her sixties with a gentle northern accent…" aria-label="Describe the voice" />
          <div className="cv-ex">{EXAMPLES.map((x) => <button key={x} className="link" onClick={() => setDesc(x)}>{x.split(",")[0]}</button>)}</div>
          <div className="cv-actions"><button className="btn primary" disabled={busy || desc.trim().length < 20} onClick={() => void hearOptions()}>{busy ? "Working…" : "Hear a few options…"}</button>
            <span className="dim">{desc.trim().length < 20 ? "A sentence or two, at least 20 characters." : "Uses a little of your plan; you are asked first."}</span></div>
          {previews.length > 0 && <div className="cv-list">
            <label className="cv-name">Name it <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} /></label>
            {previews.map((p, i) => <div key={p.id} className="cv-item"><b>Option {i + 1}</b><audio controls src={api.mediaUrl(`${dir}/${p.file}`)} aria-label={`Option ${i + 1}`} />
              <button className="btn sm primary" disabled={busy} onClick={() => void keep(p)}>Keep this voice</button></div>)}
            <p className="dim">Keeping one saves it in your ElevenLabs library (it uses one of your plan's voice slots) and gives it to {person}.</p></div>}
        </div>}

        {tab === "clone" && <div className="cv-pane">
          <p className="dim">Make a voice from recordings of a real voice: yours, or someone who has agreed. A minute or two of clean, steady speech is plenty. {plan && !plan.can_clone ? <b>Your ElevenLabs plan does not include cloning.</b> : null}</p>
          <div className="cv-actions"><button className="btn sm" disabled={busy} onClick={() => void pickFiles()}><I.Upload size={13} /> Choose recordings…</button>
            <span className="dim">{files.length ? `${files.length} chosen: ${files.map((f) => f.split(/[\\/]/).pop()).join(", ")}` : "Up to 5 files, 30 MB each."}</span></div>
          <label className="cv-name">Name it <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} /></label>
          <label className="cv-check"><input type="checkbox" checked={noise} onChange={(e) => setNoise(e.target.checked)} /> Remove background noise (only if the recording is noisy)</label>
          <label className="cv-check"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> This is my own voice, or the speaker has agreed to it being cloned.</label>
          <div className="cv-actions"><button className="btn primary" disabled={busy || !files.length || !consent || (!!plan && !plan.can_clone)} onClick={() => void makeClone()}>{busy ? "Creating…" : "Create the voice"}</button>
            <span className="dim">Takes one of your plan's voice slots.</span></div>
        </div>}
        {err && <p className="error-text" role="alert">{err}</p>}
      </div>
    </div>);
}
