import { useEffect, useMemo, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type ShowItem, type ShowStatus, type VoiceEntry } from "./api";
import * as I from "./icons";
import { ask } from "./ask";

type Line = { id?: string; character: string; text: string; emotion: string | null; pause: number; recording?: string; recording_name?: string };
type Dlg = { setting: string; lines: Line[]; timings?: { character: string; text: string; start: number; end: number; recording?: string | null }[]; stale?: boolean; native?: boolean };
type VoiceInfo = { voices: ShowStatus["voices"]; presets: { id: string; label: string }[]; emotions: string[]; model: string; eleven_models: { id: string; label: string }[]; eleven_key: boolean };
type ElevenVoice = { voice_id: string; name: string; category: string; description: string; labels: Record<string, string> };
type Est = { lines: number; characters: number; usd: number | null; basis: string };

const blank = (character = ""): Line => ({ character, text: "", emotion: null, pause: 0.45 });

/** A spoken scene's dialogue: who says what, how, and the pause after. Voicing it makes the scene's track. */
export function DialogueEditor({ item, characters, voices, onVoices, onClose, onOpen }: {
  item: ShowItem; characters: string[]; voices: ShowStatus["voices"];
  onVoices: () => void; onClose: () => void; onOpen: (path: string) => void;
}) {
  const [d, setD] = useState<Dlg | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [progress, setProgress] = useState("");
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    api.voices<Dlg>("dialogue", item.path).then((x) => setD({ ...x, lines: x.lines.length ? x.lines : [blank(characters[0])] })).catch((e) => setErr(errorText(e)));
  }, [item.path]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const un = api.onEngine((e) => { if (e.task === "voices" && e.stage) setProgress(String(e.stage)); });
    return () => { un.then((f) => f()); };
  }, []);

  const names = useMemo(() => Array.from(new Set([...characters, ...(d?.lines.map((l) => l.character).filter(Boolean) ?? [])])), [characters, d]);
  const unvoiced = d?.native ? [] : names.filter((n) => d?.lines.some((l) => l.character === n && l.text.trim() && !l.recording) && !voices[n]);   // a recorded line needs no voice
  const allRecorded = !!d && d.lines.length > 0 && d.lines.every((l) => l.recording);
  const edit = (i: number, patch: Partial<Line>) => { setDirty(true); setD((x) => x && { ...x, lines: x.lines.map((l, k) => (k === i ? { ...l, ...patch } : l)) }); };
  const moveLine = (i: number, delta: number) => setD((x) => {
    if (!x) return x;
    const j = i + delta;
    if (j < 0 || j >= x.lines.length) return x;
    const lines = [...x.lines];
    [lines[i], lines[j]] = [lines[j], lines[i]];
    setDirty(true);
    return { ...x, lines };
  });
  const save = async () => {
    if (!d) return null;
    const r = await api.voices<Dlg>("set_dialogue", item.path, { setting: d.setting, native: !!d.native, lines: d.lines.filter((l) => l.text.trim() || l.character.trim()) });
    setD({ ...r, lines: r.lines.length ? r.lines : [blank(characters[0])] });
    setDirty(false);
    return r;
  };
  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label); setErr("");
    try { await fn(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); setProgress(""); }
  };
  const recordLine = (i: number) => run("rec", async () => {
    if (!d) return;
    const f = await open({ filters: [{ name: "Your recording of this line", extensions: ["wav", "mp3", "m4a", "flac", "aac", "ogg"] }] });
    if (typeof f !== "string") return;
    const saved = await save();                                   // the line needs an id before a recording can be attached
    const nth = d.lines.slice(0, i).filter((l) => l.text.trim() || l.character.trim()).length;
    const id = saved?.lines[nth]?.id;
    if (!id) throw new Error("Write the line's words and character first.");
    const x = await api.voices<Dlg>("set_recording", item.path, { line: id, file: f });
    setD({ ...x, lines: x.lines.length ? x.lines : [blank()] });
  });
  const clearRecording = (l: Line) => run("rec", async () => {
    if (!l.id) return;
    const x = await api.voices<Dlg>("clear_recording", item.path, { line: l.id });
    setD({ ...x, lines: x.lines.length ? x.lines : [blank()] });
  });
  const hearRecording = (l: Line) => { if (l.recording) new Audio(api.mediaUrl(`${item.path}/${l.recording}`)).play().catch(() => {}); };
  const voiceScene = () => run("voice", async () => {
    await save();
    const e = await api.voices<Est>("estimate", item.path);
    if (e.lines > 0) {
      const cost = e.usd != null ? `≈ $${e.usd.toFixed(3)}` : "price not known in advance (MiniMax on fal)";
      if (!await ask(`Voice ${e.lines} line${e.lines === 1 ? "" : "s"} (${e.characters.toLocaleString()} characters) with MiniMax Speech.\n\nCost: ${cost}.\nLines already voiced with the same words and voice are reused for free. Start?`)) return;
    }
    await api.voices("generate", item.path);
    const x = await api.voices<Dlg>("dialogue", item.path);
    setD({ ...x, lines: x.lines.length ? x.lines : [blank()] });
  });

  if (!d) return null;
  const native = !!d.native;
  const hasRecording = d.lines.some((l) => l.recording);
  const voiced = !!d.timings?.length && !d.stale && !dirty;
  const audio = api.mediaUrl(`${item.path}/song.wav`) + `?v=${d.timings?.length ?? 0}-${d.lines.length}`;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass dlg-sheet" role="dialog" aria-label={`Dialogue for ${item.title}`} onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>{item.title}: dialogue</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={async () => { if (dirty) await save().catch(() => {}); onClose(); }} aria-label="Close"><I.Close size={18} /></button></div>
        <label className="field"><span>Where and when</span>
          <textarea className="text-input" rows={2} value={d.setting} placeholder="e.g. A rooftop at dusk, after the market closes"
                    onChange={(e) => { setDirty(true); setD({ ...d, setting: e.target.value }); }} /></label>
        <datalist id="dlg-characters">{names.map((n) => <option key={n} value={n} />)}</datalist>
        <label className="ov-check" title={hasRecording ? "Your own recordings can't be mixed with a scene the video model speaks" : "The video model says the lines itself, with matching lips and its own sound. No voice is generated or paid for here."}>
          <input type="checkbox" checked={native} disabled={hasRecording || !!busy} onChange={(e) => { setDirty(true); setD({ ...d, native: e.target.checked }); }} />
          {" "}Let the video model speak this scene (no generated voice)</label>
        {native && <p className="fr-note">Each shot is rendered with sound on and told what to say, so the scene needs a video model that makes sound (for example Veo 3.1 or Kling 2.6). Timing is estimated from the words until the shots exist, then the export uses each shot's own sound. Voices vary between shots, and renders with sound can cost more.</p>}
        <ol className="dlg-lines">
          {d.lines.map((l, i) => (
            <li key={l.id ?? `n${i}`} className="dlg-line">
              <input className="text-input dlg-who" list="dlg-characters" value={l.character} placeholder="Character" aria-label={`Line ${i + 1} character`}
                     onChange={(e) => edit(i, { character: e.target.value })} />
              <textarea className="text-input dlg-text" rows={1} value={l.text} placeholder="What they say" aria-label={`Line ${i + 1} words`}
                        onChange={(e) => edit(i, { text: e.target.value })} />
              <select value={l.emotion ?? ""} aria-label={`Line ${i + 1} emotion`} onChange={(e) => edit(i, { emotion: e.target.value || null })}>
                <option value="">Voice default</option>
                {["neutral", "happy", "sad", "angry", "fearful", "surprised", "disgusted"].map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <label className="dlg-pause" title="Silence after this line"><input type="number" min={0} max={5} step={0.1} value={l.pause}
                     aria-label={`Pause after line ${i + 1}`} onChange={(e) => edit(i, { pause: Number(e.target.value) })} /><span className="dim">s</span></label>
              <div className="dlg-line-actions">
                <button className="icon-btn" aria-label="Move line up" disabled={i === 0} onClick={() => moveLine(i, -1)}>↑</button>
                <button className="icon-btn" aria-label="Move line down" disabled={i === d.lines.length - 1} onClick={() => moveLine(i, 1)}>↓</button>
                <button className="icon-btn" aria-label="Remove line" onClick={() => { setDirty(true); setD({ ...d, lines: d.lines.filter((_, k) => k !== i) }); }}><I.Close size={13} /></button>
              </div>
              {!native && <div className="dlg-rec">
                {l.recording
                  ? <><span className="chip">Your recording</span>
                      <button className="link" onClick={() => hearRecording(l)} title="Play it">▶ {l.recording_name || "recording"}</button>
                      <button className="link" disabled={!!busy} onClick={() => recordLine(i)}>Change…</button>
                      <button className="link" disabled={!!busy} onClick={() => clearRecording(l)} title="Go back to a generated voice for this line">Use a generated voice</button></>
                  : <button className="link" disabled={!!busy || !(l.text.trim() && l.character.trim())} onClick={() => recordLine(i)}
                            title="Use your own recording of this line (an actor's take) instead of a generated voice. Free.">Use my own recording…</button>}
              </div>}
            </li>))}
        </ol>
        <button className="btn ghost sm" onClick={() => { setDirty(true); setD({ ...d, lines: [...d.lines, blank(d.lines[d.lines.length - 2]?.character ?? names[0] ?? "")] }); }}>+ Line</button>

        {unvoiced.length > 0 && <p className="fr-note warn">No voice yet for {unvoiced.join(", ")}. <button className="link" onClick={onVoices}>Cast voices</button></p>}
        {voiced && native && <p className="dim">{d.timings!.length} line{d.timings!.length === 1 ? "" : "s"} ready, timed from the words.</p>}
        {voiced && !native && <div className="dlg-audio"><audio controls src={audio} /><span className="dim">{d.timings!.length} line{d.timings!.length === 1 ? "" : "s"}{d.timings!.some((t) => t.recording) ? `, ${d.timings!.filter((t) => t.recording).length} from your recordings` : " voiced"}</span></div>}
        {d.stale && d.timings?.length ? <p className="fr-note warn">{native ? "The lines or the way they are spoken changed: prepare the scene again." : "The lines changed since the scene was voiced: voice it again (unchanged lines are reused for free)."}</p> : null}
        {(progress || err) && <p className={err ? "error-text" : "dim"} role={err ? "alert" : "status"}>{err || progress}</p>}
        <div className="sheet-actions">
          <button className="btn ghost" disabled={!!busy || !dirty} onClick={() => run("save", save)}>{busy === "save" ? "Saving…" : "Save"}</button>
          <button className="btn" disabled={!!busy || unvoiced.length > 0} onClick={voiceScene}>{native ? (busy === "voice" ? "Preparing…" : voiced ? "Prepare again" : "Prepare the scene") : busy === "voice" ? (allRecorded ? "Putting it together…" : "Voicing…") : allRecorded ? (voiced ? "Put it together again" : "Put the scene together") : voiced ? "Voice again" : "Voice the scene"}</button>
          <button className="btn primary" disabled={!!busy || !voiced} title={voiced ? "Analyse the scene, then direct and render it like a song" : "Voice the scene first"}
                  onClick={() => onOpen(item.path)}>Open in the Studio</button>
        </div>
      </div>
    </div>
  );
}

/** Cast a voice for every character once; every spoken scene in the show uses it. */
export function VoicesSheet({ show, characters, onClose }: { show: string; characters: string[]; onClose: () => void }) {
  const [info, setInfo] = useState<VoiceInfo | null>(null);
  const [extra, setExtra] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [playing, setPlaying] = useState<Record<string, string>>({});
  const [pick, setPick] = useState<null | { who: string; query: string; results: ElevenVoice[]; next: string | null; busy: boolean }>(null);
  const search = async (who: string, query: string, page?: string | null) => {
    setPick((p) => ({ who, query, results: page ? p?.results ?? [] : [], next: null, busy: true }));
    setErr("");
    try {
      const r = await api.voices<{ voices: ElevenVoice[]; next: string | null }>("eleven_voices", show, { query, page });
      setPick((p) => ({ who, query, results: [...(page ? p?.results ?? [] : []), ...r.voices], next: r.next, busy: false }));
    } catch (e) { setErr(errorText(e)); setPick((p) => (p ? { ...p, busy: false } : p)); }
  };
  useEffect(() => { api.voices<VoiceInfo>("voices", show).then(setInfo).catch((e) => setErr(errorText(e))); }, [show]);
  const names = useMemo(() => Array.from(new Set([...characters, ...Object.keys(info?.voices ?? {})])), [characters, info]);
  const setVoice = async (who: string, patch: Record<string, unknown>) => {
    const cur: VoiceEntry = info?.voices[who] ?? { voice_id: info?.presets[0].id ?? "", speed: 1, pitch: 0, emotion: null };
    if (patch.provider === undefined && cur.provider === "elevenlabs") patch = { provider: "elevenlabs", ...patch };
    setErr("");
    try { setInfo(await api.voices<VoiceInfo>("set_voice", show, { ...cur, ...patch, character: who })); } catch (e) { setErr(errorText(e)); }
  };
  const hear = async (who: string) => {
    const el = info?.voices[who]?.provider === "elevenlabs";
    if (!await ask(`Play a short sample of ${who}'s voice? ${el ? "It uses a few credits from your ElevenLabs plan" : "It costs a fraction of a cent on fal (MiniMax)"}; the same sample is free afterwards.`)) return;
    setBusy(who); setErr("");
    try { const r = await api.voices<{ path: string }>("preview", show, { character: who }); setPlaying((p) => ({ ...p, [who]: api.mediaUrl(r.path) })); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  if (!info) return null;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass" role="dialog" aria-label="Voices" onClick={(e) => e.stopPropagation()} style={{ width: "min(720px, calc(100vw - 48px))" }}>
        <div className="vs-head"><h2>Voices</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">One voice per character, used in every spoken scene of the show: a MiniMax preset voice (on fal) or any voice from your ElevenLabs library.
          Songs keep the singers' recordings, and any line can use your own recording instead.</p>
        <ul className="voice-list">
          {names.map((who) => {
            const v = info.voices[who];
            return (
              <li key={who} className="voice-row">
                <b>{who}</b>
                <select value={v?.provider === "elevenlabs" ? "elevenlabs" : "minimax"} aria-label={`Voice source for ${who}`}
                        onChange={(e) => e.target.value === "elevenlabs" ? search(who, "") : v?.provider === "elevenlabs" && setVoice(who, { provider: "minimax", voice_id: info.presets[0].id })}>
                  <option value="minimax">MiniMax (fal)</option>
                  <option value="elevenlabs">ElevenLabs</option>
                </select>
                {v?.provider !== "elevenlabs" ? (
                  <select value={v?.voice_id ?? ""} aria-label={`Voice for ${who}`} onChange={(e) => setVoice(who, { voice_id: e.target.value })}>
                    {!v && <option value="">Choose a voice…</option>}
                    {info.presets.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                  </select>
                ) : <button className="btn ghost sm" onClick={() => search(who, "")} title="Search your ElevenLabs voice library">{v.voice_name || "Choose a voice"}…</button>}
                {v && v.provider !== "elevenlabs" && <>
                  <label className="dim">Speed <input type="number" min={0.5} max={2} step={0.05} value={v.speed} aria-label={`Speed for ${who}`}
                                                      onChange={(e) => setVoice(who, { speed: Number(e.target.value) })} /></label>
                  <label className="dim">Pitch <input type="number" min={-12} max={12} step={1} value={v.pitch ?? 0} aria-label={`Pitch for ${who}`}
                                                      onChange={(e) => setVoice(who, { pitch: Number(e.target.value) })} /></label>
                </>}
                {v?.provider === "elevenlabs" && <>
                  <select value={v.model} aria-label={`ElevenLabs model for ${who}`} onChange={(e) => setVoice(who, { model: e.target.value })}>
                    {info.eleven_models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}</select>
                  <label className="dim" title="Lower = more varied, higher = steadier">Steady <input type="number" min={0} max={1} step={0.05} value={v.stability} onChange={(e) => setVoice(who, { stability: Number(e.target.value) })} /></label>
                  <label className="dim" title="How closely it keeps to the original voice">Match <input type="number" min={0} max={1} step={0.05} value={v.similarity} onChange={(e) => setVoice(who, { similarity: Number(e.target.value) })} /></label>
                  <label className="dim" title="Exaggeration of the speaking style">Style <input type="number" min={0} max={1} step={0.05} value={v.style} onChange={(e) => setVoice(who, { style: Number(e.target.value) })} /></label>
                  <label className="dim">Speed <input type="number" min={0.7} max={1.2} step={0.05} value={v.speed} onChange={(e) => setVoice(who, { speed: Number(e.target.value) })} /></label>
                </>}
                {v && <button className="btn ghost sm" disabled={!!busy} onClick={() => hear(who)}>{busy === who ? "…" : "Hear"}</button>}
                {playing[who] && <audio src={playing[who]} autoPlay controls />}
                {pick?.who === who && (
                  <div className="eleven-pick">
                    {!info.eleven_key ? <p className="dim">Add your ElevenLabs key in Settings first.</p> : <>
                      <form onSubmit={(e) => { e.preventDefault(); search(who, pick.query); }} className="voice-add">
                        <input className="text-input" autoFocus value={pick.query} placeholder="Search your voices (calm, British, narrator…)" aria-label="Search ElevenLabs voices"
                               onChange={(e) => setPick({ ...pick, query: e.target.value })} />
                        <button className="btn sm" type="submit" disabled={pick.busy}>{pick.busy ? "…" : "Search"}</button>
                        <button className="btn ghost sm" type="button" onClick={() => setPick(null)}>Close</button>
                      </form>
                      <ul className="eleven-results">
                        {pick.results.map((r) => (
                          <li key={r.voice_id}><b>{r.name}</b> <span className="dim">{[r.category, ...Object.values(r.labels)].filter(Boolean).join(" · ")}</span>
                            {r.description && <div className="dim">{r.description}</div>}
                            <button className="btn sm" onClick={async () => {
                              await setVoice(who, { provider: "elevenlabs", voice_id: r.voice_id, voice_name: r.name, model: v?.model, stability: v?.stability, similarity: v?.similarity, style: v?.style, speed: v?.provider === "elevenlabs" ? v.speed : 1 });
                              setPick(null);
                            }}>Use</button></li>))}
                        {!pick.busy && pick.results.length === 0 && <li className="dim">No voices found.</li>}
                      </ul>
                      {pick.next && <button className="link" onClick={() => search(who, pick.query, pick.next)}>More…</button>}
                    </>}
                  </div>)}
              </li>);
          })}
        </ul>
        <form className="voice-add" onSubmit={(e) => { e.preventDefault(); if (extra.trim()) { setVoice(extra.trim(), {}); setExtra(""); } }}>
          <input className="text-input" value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="Another speaking character (e.g. Narrator)" aria-label="Add a character" />
          <button className="btn ghost sm" type="submit">Add</button>
        </form>
        {err && <p className="error-text" role="alert">{err}</p>}
      </div>
    </div>
  );
}
