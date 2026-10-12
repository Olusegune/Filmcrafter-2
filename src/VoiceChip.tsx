import { useEffect, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type VoicePerson } from "./api";
import { FILTERS } from "./voiceLogic";
import { notifyVoice, useCast, useVoiceStatus } from "./voiceHooks";
import { speakLine } from "./CastVoices";
import { VoiceRecorder } from "./VoiceRecorder";
import * as I from "./icons";

let playing: HTMLAudioElement | null = null;           // one recording plays at a time

/**
 * Your own recorded voice for one shot, right where you work on it (a card, the shot panel): who speaks, a play button and the length once it is recorded,
 * or an Add voice button. `dir` is the film's folder. Shows nothing for a shot where nobody speaks and nothing is recorded.
 */
export function VoiceChip({ dir, shotId, compact }: { dir: string; shotId: string; compact?: boolean }) {
  const { byShot } = useVoiceStatus(dir);
  const { cast } = useCast(dir);
  const shot = byShot[shotId];
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [now, setNow] = useState<string | null>(null);
  const [rec, setRec] = useState<string | null>(null);
  const el = useRef<HTMLAudioElement | null>(null);
  useEffect(() => () => { if (el.current && playing === el.current) { el.current.pause(); playing = null; } }, []);
  if (!shot || !(shot.people ?? []).length) return null;

  const pick = async (who: string) => {
    setErr("");
    try {
      const r = await open({ multiple: false, filters: FILTERS });
      const f = Array.isArray(r) ? r[0] : r;
      if (!f) return;
      setBusy(true);
      await api.voice("import", dir, { items: [{ file: f, shot: shotId, speaker: who }] });
      notifyVoice();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const remove = async (who: string) => { setBusy(true); try { await api.voice("remove", dir, { shot: shotId, speaker: who }); notifyVoice(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); } };
  const play = (p: VoicePerson) => {
    if (!p.recording) return;
    if (el.current && now === p.key) { el.current.pause(); setNow(null); return; }
    playing?.pause();
    const a = new Audio(api.mediaUrl(`${dir}/${p.recording.file}`));
    a.onended = () => setNow(null);
    el.current = a; playing = a; setNow(p.key);
    void a.play().catch(() => setNow(null));
  };

  return (
    <div className={`vchip ${compact ? "compact" : ""}`}>
      {shot.people.map((p) => (
        <div key={p.key} data-voice-person={p.name} className={`vchip-row ${p.recording ? "has" : ""}`}>
          <I.Mic size={13} />
          <span className="vchip-name">{p.name}</span>
          {p.recording
            ? <>
                <button className="vchip-play" onClick={() => play(p)} aria-label={`${now === p.key ? "Stop" : "Play"} ${p.name}'s recording in ${shotId}, ${p.recording.seconds.toFixed(1)}s`} title={p.recording.name}>
                  {now === p.key ? <I.Pause size={12} /> : <I.Play size={12} />}<span className="num">{p.recording.seconds.toFixed(1)}s</span></button>
                <button className="link" disabled={busy} onClick={() => pick(p.name)}>Replace</button>
                <button className="link" disabled={busy} onClick={() => setRec(p.name)} title={`Record ${p.name}'s voice for this shot again`}>Re-record</button>
                {!compact && <button className="link" disabled={busy} onClick={() => remove(p.name)}>Remove</button>}
              </>
            : <>
                <button className="vchip-add" disabled={busy} onClick={() => pick(p.name)} title={`Choose ${p.name}'s recording for this shot (or drop the file on ${p.name}'s name)`}>Add voice…</button>
                <button className="vchip-rec" disabled={busy} onClick={() => setRec(p.name)} title={`Record ${p.name}'s voice now`}><I.Mic size={11} /> Record</button>
                {cast?.people[p.key] && p.lines.length > 0 && <button className="vchip-rec" disabled={busy} onClick={() => { setErr(""); setBusy(true); speakLine(dir, shotId, p.name).catch((e) => setErr(errorText(e))).finally(() => setBusy(false)); }} title={"Have the written line spoken in " + p.name + "'s ElevenLabs voice (the price is shown first)"}><I.Sparkle size={11} /> Speak it</button>}
              </>}
        </div>))}
      {err && <p className="error-text vchip-err" role="alert">{err}</p>}
      {rec && <VoiceRecorder dir={dir} shotId={shotId} speaker={rec} onClose={() => setRec(null)} />}
    </div>
  );
}
