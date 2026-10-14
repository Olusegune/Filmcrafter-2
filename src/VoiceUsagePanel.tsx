import { useCallback, useEffect, useState } from "react";
import { api, errorText, type VoiceUsage } from "./api";
import { notifyVoice, VOICE_EVENT } from "./voiceHooks";
import { attemptWords, STATUS_WORDS, usageWords } from "./voiceUsage";

/**
 * A quiet line about what voice generation has used in this film, with the operations whose outcome is unknown (so the person can check ElevenLabs' own usage page and say whether they were
 * charged), an optional credit limit, and the recent record. Shows nothing until something was done.
 */
export function VoiceUsagePanel({ dir }: { dir: string }) {
  const [u, setU] = useState<VoiceUsage | null>(null);
  const [err, setErr] = useState("");
  const [limit, setLimit] = useState("");
  const load = useCallback(() => { api.castVoice<VoiceUsage>("ledger", dir).then((r) => { if (r && r.by_unit) setU(r); }).catch(() => {}); }, [dir]);
  useEffect(() => { load(); window.addEventListener(VOICE_EVENT, load); return () => window.removeEventListener(VOICE_EVENT, load); }, [load]);
  const act = async (f: () => Promise<unknown>) => { setErr(""); try { await f(); notifyVoice(); load(); } catch (e) { setErr(errorText(e)); } };
  if (!u || (u.count === 0 && !Object.keys(u.limits ?? {}).length)) return null;
  const line = usageWords(u.by_unit);
  const cap = u.limits?.elevenlabs_credits;
  return (
    <div className="vu" aria-label="Voice usage">
      {line && <p className="vu-line">{line}.</p>}
      {u.unresolved.length > 0 && <div className="vu-unsure" role="alert">
        <b>Not sure whether {u.unresolved.length === 1 ? "this was" : "these were"} charged</b>
        <span className="dim"> FilmCrafter has not sent {u.unresolved.length === 1 ? "it" : "them"} again. Look at your ElevenLabs usage history, then say which it was.</span>
        {u.unresolved.map((e) => (
          <div key={e.id} className="vu-row"><span>{attemptWords(e)}</span>
            <button className="link" onClick={() => void act(() => api.castVoice("ledger_resolve", dir, { id: e.id, outcome: "not_charged" }))}>It was not charged</button>
            <button className="link" onClick={() => void act(() => api.castVoice("ledger_resolve", dir, { id: e.id, outcome: "charged" }))}>It was charged</button></div>))}
      </div>}
      <details className="vu-more"><summary>Usage details and limit</summary>
        <div className="vu-limit"><label>Stop before this film uses more than <input type="number" min={1} inputMode="numeric" value={limit} placeholder={cap ? String(cap) : "no limit"} onChange={(e) => setLimit(e.target.value)} aria-label="Credit limit" /> ElevenLabs credits</label>
          <button className="btn sm" disabled={!limit} onClick={() => void act(async () => { await api.castVoice("set_limit", dir, { unit: "elevenlabs_credits", value: Number(limit) }); setLimit(""); })}>Set</button>
          {cap ? <button className="link" onClick={() => void act(() => api.castVoice("set_limit", dir, { unit: "elevenlabs_credits", value: null }))}>Clear (now {cap.toLocaleString()})</button> : null}</div>
        <ul className="vu-list">{u.recent.slice(0, 10).map((e) => <li key={e.id}><span className={`vu-st ${e.status}`}>{STATUS_WORDS[e.status]}</span> {attemptWords(e)}{e.resolved ? ` (you said: ${e.resolved.outcome === "charged" ? "charged" : "not charged"})` : ""}</li>)}</ul>
        <p className="dim vu-note">Amounts marked estimated come from FilmCrafter's own count of characters; ElevenLabs does not always report what it charged. Your ElevenLabs usage page is the final word.</p>
      </details>
      {err && <p className="error-text" role="alert">{err}</p>}
    </div>);
}
