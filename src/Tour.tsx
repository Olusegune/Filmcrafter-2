import { useEffect, useState, type ReactNode } from "react";
import * as I from "./icons";

const KEY = "pf-tour-done";
export const tourSeen = (): boolean => { try { return localStorage.getItem(KEY) === "1"; } catch { return true; } };
const markSeen = () => { try { localStorage.setItem(KEY, "1"); } catch { /* optional */ } };

export const TOUR: { icon: ReactNode; title: string; text: string }[] = [
  { icon: <I.Rocket size={18} />, title: "This bar is your path", text: "Song, Plan, References, Keyframes, Video, Export. The highlighted step is the next one, and the numbers show how far along each is. Click a step to jump to it." },
  { icon: <I.Check size={18} />, title: "Free first", text: "Listening to the song, planning the shots and choosing references cost nothing. Nothing is ever charged without a price you confirm." },
  { icon: <I.ImageIcon size={18} />, title: "Keyframe, then video", text: "A keyframe is a still of the shot, a few cents. Approve it, then render the video from it: that is the main cost, so get the picture right first. Steps with a $ cost money." },
  { icon: <I.Camera size={18} />, title: "Fix things where you see them", text: "Select a shot to change its camera and lighting, tell the model what to fix in a keyframe, or read the exact prompt. Press F1 any time for the guide." },
];

/** A four-card welcome to the Golden Path, shown once on the first Studio visit and from the "?" on the strip. */
export function Tour({ onClose, right }: { onClose: () => void; right?: number }) {
  const [i, setI] = useState(0);
  const last = i === TOUR.length - 1;
  const done = () => { markSeen(); onClose(); };
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") done(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  });   // eslint-disable-line react-hooks/exhaustive-deps
  const t = TOUR[i];
  return (
    <div className={`tour ${right !== undefined ? "right" : ""}`} style={right !== undefined ? { right } : undefined} role="dialog" aria-label="Welcome tour">
      <div className="tour-ic">{t.icon}</div>
      <div className="tour-body"><b>{t.title}</b><p>{t.text}</p></div>
      <div className="tour-foot">
        <span className="tour-dots" aria-label={`Step ${i + 1} of ${TOUR.length}`}>{TOUR.map((_, k) => <i key={k} className={k === i ? "on" : ""} />)}</span>
        <span style={{ flex: 1 }} />
        <button className="link" onClick={done}>Skip</button>
        <button className="btn primary small" onClick={() => (last ? done() : setI(i + 1))}>{last ? "Got it" : "Next"}</button>
      </div>
    </div>
  );
}
