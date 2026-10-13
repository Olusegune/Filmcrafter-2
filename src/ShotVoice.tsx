import { useState } from "react";
import { LineEditor } from "./LineStudio";
import { useCast, useVoiceStatus } from "./voiceHooks";
import * as I from "./icons";

/** "2 of 3 voices" for a shot, in words (used by the Shot tab's pointer to the Video tab). */
export const voiceSummary = (people: { recording: unknown }[]): string => {
  const n = people.length, r = people.filter((p) => p.recording).length;
  return n === 0 ? "" : r === n ? (n === 1 ? "Voice recorded" : `All ${n} voices recorded`) : r === 0 ? (n === 1 ? "No voice yet" : `${n} voices to add`) : `${r} of ${n} voices recorded`;
};

/**
 * The voices in the selected shot, at the top of the Video tab (where the picture is made to speak). One card for each person who speaks: their ElevenLabs voice, whether their line is voiced,
 * and, opened up, the whole line editor: hear it, record it, add a file, have it spoken with feeling, compare takes. A shot where one person speaks opens straight onto them. Nothing here is
 * shown for a shot where nobody speaks.
 */
export function ShotVoice({ dir, shotId }: { dir: string; shotId: string }) {
  const { byShot } = useVoiceStatus(dir);
  const { cast } = useCast(dir);
  const shot = byShot[shotId];
  const people = shot?.people ?? [];
  const [open, setOpen] = useState<string | null>(null);
  if (!shot || people.length === 0) return null;
  const only = people.length === 1 ? people[0].name : null;
  const shown = open ?? only;

  return (
    <section className="sv" aria-label="Voices in this shot">
      <div className="sv-head"><h4><I.Mic size={13} /> Voices in this shot</h4><span className="dim">{voiceSummary(people)}</span></div>
      {people.map((p) => {
        const voice = cast?.people[p.key];
        const isOpen = shown === p.name;
        const rec = p.recording;
        return (
          <div key={p.key} className={`sv-card ${isOpen ? "open" : ""} ${rec ? "has" : "gap"}`} data-shot-id={shotId} data-voice-person={p.name}>
            <button className="sv-row" aria-expanded={isOpen} onClick={() => setOpen(isOpen && !only ? "" : p.name)}>
              <span className={`sv-dot ${rec ? "on" : ""}`} aria-hidden="true" />
              <span className="sv-who"><b>{p.name}</b>
                <span className="sv-sub">{rec ? `${rec.seconds.toFixed(1)}s · ${rec.source === "elevenlabs" ? "spoken" : "your voice"}` : "no voice yet"}</span></span>
              <span className="sv-voice">{voice ? voice.voice_name || "voice chosen" : cast?.key ? "choose a voice" : ""}</span>
              <I.Chevron size={14} />
            </button>
            {isOpen && <div className="sv-body"><LineEditor dir={dir} shotId={shotId} who={p.name} /></div>}
          </div>);
      })}
      <p className="dim sv-tip">Drop an audio file on a name to give it to that person. {cast?.key ? "" : "Add your ElevenLabs key in Settings to have lines spoken."}</p>
    </section>);
}

/** On the Shot tab: where the voices stand for this shot, and a way to the Video tab where they are made. Nothing for a shot where nobody speaks. */
export function VoicePointer({ dir, shotId }: { dir: string; shotId: string }) {
  const { byShot } = useVoiceStatus(dir);
  const people = byShot[shotId]?.people ?? [];
  if (!people.length) return null;
  return (
    <div className="insp-section sv-pointer"><h4>Voices</h4>
      <p className="prose">{voiceSummary(people)}. <button className="link" onClick={() => window.dispatchEvent(new CustomEvent("pf-open-tab", { detail: "video" }))}>Open them in the Video tab</button></p></div>);
}
