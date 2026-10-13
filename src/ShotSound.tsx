import { useCallback, useEffect, useState } from "react";
import { api, errorText, type ShotLevels, type ShotSound as Sound, type SoundLayer } from "./api";
import { filmDirOfRender, isRenderDir } from "./filmPaths";
import { useVoiceStatus } from "./voiceHooks";
import { ask } from "./ask";
import * as I from "./icons";
import "./sound.css";

/** What turning a shot's own sound on or off (Shift+M) does: the whole sound, or both parts once it is split. Returns a line to tell the person. */
export async function toggleShotSound(dir: string, shot: string): Promise<string> {
  const g = await api.shotSound(dir, "get", { shot });
  if (!g.take) return "This shot has no video take yet.";
  if (g.note) return g.note;
  if (!g.has_audio) return "This take has no audible sound.";
  const parts = g.layers.filter((l) => l.id !== "song");
  const turnOn = !parts.some((l) => l.on);
  for (const l of parts) await api.shotSound(dir, "set", { shot, layer: l.id, on: turnOn });
  return turnOn ? `${shot}: the take's own sound is on (the soundtrack is turned down under it)` : `${shot}: the take's own sound is off`;
}

const pct = (g: number | null) => Math.round((g ?? 1) * 100);

/**
 * The sound of one shot as layers: the soundtrack, and the sound the video model made inside the take (or, after Split, its voices and its effects and music).
 * Each can be switched off, turned down or deleted for this shot, and none of it renders anything again: it is mixed in when the film is exported.
 */
export function ShotSound({ dir, shotId, onChanged }: { dir: string; shotId: string; onChanged?: () => void }) {
  const [snd, setSnd] = useState<Sound | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [level, setLevel] = useState<Record<string, number>>({});          // a slider being dragged, before it is saved
  const [db, setDb] = useState<ShotLevels | null>(null);                    // how loud each layer is in the film under this shot
  const loadDb = useCallback(() => api.shotLevels(dir, shotId).then(setDb).catch(() => setDb(null)), [dir, shotId]);

  const load = useCallback(() => api.shotSound(dir, "get", { shot: shotId }).then((r) => { setSnd(r); setLevel({}); loadDb(); }).catch((e) => setErr(errorText(e))), [dir, shotId, loadDb]);
  useEffect(() => { setSnd(null); setDb(null); setErr(""); load(); }, [load]);
  useEffect(() => {
    window.addEventListener("pf-media-changed", load);
    return () => window.removeEventListener("pf-media-changed", load);
  }, [load]);

  const act = async (what: string, fn: () => Promise<Sound>) => {
    setBusy(what); setErr("");
    try { setSnd(await fn()); setLevel({}); loadDb(); onChanged?.(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const set = (l: SoundLayer, data: Record<string, unknown>) => act(l.id, () => api.shotSound(dir, "set", { shot: shotId, layer: l.id, ...data }));
  const remove = async (l: SoundLayer) => {
    if (!await ask(`Delete “${l.label}” from this shot?\n\nIt will not be in the exported film. The take itself is not changed, and you can bring the layer back with Restore.`, { ok: "Delete", danger: true })) return;
    await act(l.id, () => api.shotSound(dir, "delete", { shot: shotId, layer: l.id }));
  };
  const split = () => act("split", () => api.shotSound(dir, "split", { shot: shotId }));

  const { byShot } = useVoiceStatus(isRenderDir(dir) ? filmDirOfRender(dir) : null);
  const voices = (byShot[shotId]?.people ?? []).filter((p) => p.recording).map((p) => p.name);          // whose recordings are laid over this shot in the film
  if (!snd) return err ? <p className="error-text" role="alert">{err}</p> : null;
  return <SoundPanel voices={voices} shotId={shotId} snd={snd} busy={busy} err={err} level={level} setLevel={setLevel} db={db}
                     onSet={set} onRemove={remove} onRestore={(l) => act(l.id, () => api.shotSound(dir, "restore", { shot: shotId, layer: l.id }))}
                     onSplit={split} onReset={() => act("reset", () => api.shotSound(dir, "reset", { shot: shotId }))} />;
}

type PanelProps = { voices?: string[]; shotId: string; snd: Sound; busy: string; err: string; level: Record<string, number>; setLevel: (l: Record<string, number>) => void; db?: ShotLevels | null;
  onSet: (l: SoundLayer, data: Record<string, unknown>) => void; onRemove: (l: SoundLayer) => void; onRestore: (l: SoundLayer) => void; onSplit: () => void; onReset: () => void };

/** What is drawn: one row per layer, with its tick box, volume, and delete or restore. */
export function SoundPanel({ voices, shotId, snd, busy, err, level, setLevel, db, onSet, onRemove, onRestore, onSplit, onReset }: PanelProps) {
  const hasTake = !!snd.take;
  return (
    <section className="shot-sound" aria-label={`Sound of ${shotId}`}>
      <div className="ss-head"><I.Wave size={15} /> <b>Sound</b>
        <span className="dim">{hasTake && !snd.note ? "of the take in the video · free, nothing is rendered again" : ""}</span></div>
      {snd.note && <p className="dim">{snd.note}</p>}
      {voices && voices.length > 0 && <p className="ss-voice" role="note"><I.Mic size={13} /> Your recording{voices.length > 1 ? "s" : ""} of <b>{voices.join(" and ")}</b> {voices.length > 1 ? "are" : "is"} laid over this shot in the film.
        {snd.layers.some((l) => l.id !== "song" && l.on && !l.removed) && <> The video model's own sound is on too, and it can add a second voice: switch it off to hear only {voices.length > 1 ? "your recordings" : "yours"}.</>}</p>}
      {hasTake && !snd.note && <>
        {!snd.has_audio && <p className="dim">This take has no audible sound: the model made none, or its sound was switched off when it was rendered. To get the model's own sound,
          render this shot again with the model's sound option on. The soundtrack plays as usual.</p>}
        {db && db.mix_db !== null && <p className="ss-mix num" title="The mix of the soundtrack and the layers that are on, over this shot">
          In the film under this shot: {db.mix_db} dB{db.peak_db !== null ? ` (peak ${db.peak_db} dB)` : ""}{db.peak_db !== null && db.peak_db > -1 ? ". Close to the top: the export holds it just under so it does not distort." : ""}</p>}
        <ul className="ss-rows">
          {snd.layers.map((l) => {
            const song = l.id === "song";
            const disabled = !!busy || (!song && !snd.has_audio);
            const dragging = level[l.id] !== undefined;
            const shown = level[l.id] ?? (song ? pct(l.effective_gain ?? 1) : pct(l.gain));
            const commit = () => { if (dragging) onSet(l, { gain: level[l.id] / 100 }); };
            return (
              <li key={l.id} className={`ss-row ${l.removed ? "gone" : ""}`}>
                <label className="ss-name">
                  <input type="checkbox" checked={l.on} disabled={disabled || l.removed} onChange={(e) => onSet(l, { on: e.target.checked })} aria-label={`${l.label} on`} />
                  <span>{l.label}</span>
                  {db?.layers[l.id] != null && l.on && <span className="ss-db num" aria-label={`${db.layers[l.id]} decibels`}>{db.layers[l.id]} dB</span>}
                </label>
                {l.removed
                  ? <button className="btn small ghost" disabled={!!busy} onClick={() => onRestore(l)}>Restore</button>
                  : <>
                      <input type="range" min={0} max={150} step={5} value={shown} disabled={disabled || !l.on} aria-label={`${l.label} volume`}
                             aria-valuetext={`${shown} percent${song && l.auto && !dragging ? " (automatic)" : ""}`}
                             onChange={(e) => setLevel({ ...level, [l.id]: Number(e.target.value) })}
                             onPointerUp={commit} onKeyUp={commit} onBlur={commit} />
                      <span className="ss-val num">{shown}%{song && l.auto && !dragging && l.on ? " auto" : ""}</span>
                      {song && !l.auto
                        ? <button className="btn small ghost" disabled={!!busy} onClick={() => onSet(l, { gain: null })} title="Turn the soundtrack down automatically while this take's own sound plays">Auto</button>
                        : song ? <span className="ss-gap" />
                        : <button className="icon-btn" disabled={!!busy} onClick={() => onRemove(l)} aria-label={`Delete ${l.label}`} title="Delete this layer from the shot"><I.Close size={14} /></button>}
                    </>}
                {db?.layers[l.id] != null && l.on && <div className="ss-meter" aria-hidden="true"><i style={{ width: `${Math.max(2, Math.min(100, ((db.layers[l.id] as number) + 60) / 60 * 100))}%` }} /></div>}
              </li>);
          })}
        </ul>
        <div className="ss-actions">
          {snd.has_audio && !snd.split && <button className="btn small" disabled={!!busy} onClick={onSplit}
            title="Separate the voices from the sound effects and music on this computer (free, takes a few seconds), so you can keep one and drop the other">
            <I.Wave size={13} /> {busy === "split" ? "Separating…" : "Split voices from effects"}</button>}
          {snd.changed && <button className="btn small ghost" disabled={!!busy}
            onClick={onReset}>Back to how it was</button>}
        </div>
        {snd.split && <p className="dim ss-note">Split with a program made for songs, so a loud effect can leave a faint trace in the voices.</p>}
        {snd.native && <p className="dim ss-note">This is a spoken scene: the film's sound is each take's own sound, and the soundtrack is not played.</p>}
      </>}
      {err && <p className="error-text" role="alert">{err}</p>}
    </section>
  );
}
