import "./acting.css";

export type Timing = { verdict: string; detail: string; lag_ms?: number; correlation?: number } | "none";
export type SingSetting = "auto" | "on" | "off";
export type LipMode = "first_frame" | "audio_first" | "auto";

const TIMING_TONE: Record<string, string> = { in_time: "ok", late: "warn", early: "warn", loose: "warn", own_audio: "warn", no_audio: "", no_vocal: "" };

/** The result of the free sound check, in words. */
export function TimingLine({ timing }: { timing: Timing }) {
  if (timing === "none") return <p className="dim ls-timing" role="status">There is no take of this shot to check yet.</p>;
  return <p className={`ls-timing ${TIMING_TONE[timing.verdict] === "ok" ? "ls-ok" : TIMING_TONE[timing.verdict] === "warn" ? "ls-warn" : "dim"}`} role="status">
    <b>Sound check:</b> {timing.detail}{timing.verdict === "own_audio" || timing.verdict === "loose" ? " Switch to following the song's audio, then render again." : ""}
    {timing.verdict === "late" || timing.verdict === "early" ? " A small offset can be fixed when you export; a big one needs another take." : ""}</p>;
}

/** Does someone on screen sing this? The app guesses; this is where the person says. A narrator or a voice-over (a man remembering his childhood) is not sung by the child shown. */
export function SingChoice({ performer, value, onChange }: { performer: string | null; value: SingSetting; onChange: (v: SingSetting) => void }) {
  const who = performer ?? "Someone on screen";
  const opt = (v: SingSetting, label: string, title: string) => <button key={v} className="btn small ghost ls-opt" aria-pressed={value === v} title={title} onClick={() => onChange(v)}>{label}</button>;
  return (
    <div className="ls-sing" role="group" aria-label={`Does ${who} sing this on screen?`}>
      <span className="dim">Does {who} sing this on screen?</span>
      {opt("auto", "Let PULSEFRAME decide", "A lead in a medium shot or closer, or words in the shot that say someone sings or speaks")}
      {opt("on", "Yes, sync the mouth", "Always sync a mouth to the vocal in this shot")}
      {opt("off", "No: a narrator or voice-over", "Never sync a mouth in this shot: the vocal belongs to someone else, or to a memory")}
    </div>);
}

/** What the Video tab says about the mouth of a sung shot, and the one-click way to change how it is made. */
export function LipSyncNote({ performer, lyrics, lipSync, audioFirst, keyframeBlocksAudio, model, mode = "first_frame", timing = null, timingBusy = false, sing = "auto", vocalHeard = 0, onMode, onTiming, onSing }: {
  performer: string | null; lyrics: string[]; lipSync: boolean; audioFirst: boolean; keyframeBlocksAudio: boolean; model: string; mode?: LipMode;
  timing?: Timing | null; timingBusy?: boolean; sing?: SingSetting; vocalHeard?: number; onMode: (m: LipMode) => void; onTiming?: () => void; onSing?: (v: SingSetting) => void;
}) {
  const choice = onSing ? <SingChoice performer={performer} value={sing} onChange={onSing} /> : null;
  if (!performer) {
    // a vocal is heard but nobody on screen is treated as singing it: say so, and say how to change it
    return (
      <div className="note" role="note"><div className="ls-body">
        <p>{sing === "off" ? "You marked this shot as not sung on screen, so no mouth is synced." : `A vocal is heard under this shot (${vocalHeard.toFixed(1)} s), but nobody on screen is treated as singing it, so no mouth is synced.`} If it is a narrator, a voice-over or a memory, that is right.</p>
        {choice}
      </div></div>);
  }
  const check = onTiming && (
    <div className="ls-check">
      <button className="btn small ghost" disabled={timingBusy} onClick={onTiming} title="Compares the sound in the take with the song's vocal on this computer. No AI, nothing is sent anywhere.">{timingBusy ? "Checking…" : "Check this take's sound against the song (free)"}</button>
      {timing && <TimingLine timing={timing} />}
    </div>);
  if (lipSync) {
    return (
      <div className="note" role="note"><div className="ls-body">
        <p>Lip-sync: {performer} sings “{lyrics.join(" / ")}” and the model is given the song's vocal under this shot to follow.
          {audioFirst && <> Your keyframe is a <b>reference picture</b> here, not the first frame, so the opening of the take may differ from it.</>}</p>
        {audioFirst && mode === "audio_first" && <div className="ls-choice"><button className="link" onClick={() => onMode("first_frame")}>Use the keyframe as the first frame instead</button></div>}
        {audioFirst && mode === "auto" && <div className="ls-choice"><span className="dim">Chosen automatically: this shot shows a mouth. </span><button className="link" onClick={() => onMode("first_frame")}>Always use the keyframe as the first frame instead</button></div>}
        {check}
        {choice}
      </div></div>);
  }
  if (keyframeBlocksAudio) {
    const auto = mode === "auto";
    return (
      <div className="note warn" role="note"><div className="ls-body">
        <p>{performer} sings here. {model} can follow the song's audio, but not together with a first frame, and your keyframe is the first frame.
          {auto ? <> This shot is too wide for a mouth to be watched, so Auto keeps the keyframe and the mouth follows the <b>words in the prompt only</b>.</>
                : <> So the mouth follows the <b>words in the prompt only</b>: close, but not in time with the music.</>}</p>
        <div className="ls-choice">
          <span className="dim">{auto ? "Close-ups and medium shots with a vocal already follow the song's audio. "
                                      : "The keyframe becomes a reference picture and the song's vocal is sent, so the mouth follows the music; the opening may differ from the keyframe. "}
            This applies to every sung shot in the project, and you can switch back. Or keep the keyframe and run <i>Lip-sync this take…</i> afterwards (priced by the second).</span>
          <button className="btn small ls-gold" onClick={() => onMode("audio_first")}>Follow the song's audio instead</button>
          {!auto && <button className="link" onClick={() => onMode("auto")}>Or let PULSEFRAME choose shot by shot (close-ups follow the audio)</button>}
        </div>
        {check}
        {choice}
      </div></div>);
  }
  return <div className="note" role="note"><div className="ls-body"><p>{performer} sings here, but this model can't take reference audio, so the mouth follows the words in the prompt only.</p>{check}{choice}</div></div>;
}
