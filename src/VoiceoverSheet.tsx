import { useEffect } from "react";
import { VoiceoverPanel } from "./VoiceoverPanel";
import type { VoiceMatch } from "./api";
import * as I from "./icons";

/** Your own recorded voices, as a sheet that can be opened from anywhere in a film (the Studio's bar, the Export screen), so it is found in Simple mode too. `dir` is the film's folder. */
export function VoiceoverSheet({ dir, onClose, onChanged, initialRows, only }: { dir: string; onClose: () => void; onChanged?: () => void; initialRows?: VoiceMatch[] | null; only?: string }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass vo-sheet" role="dialog" aria-label="Voiceover" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Voiceover</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <div className="vo-sheet-body"><VoiceoverPanel dir={dir} only={only} onChanged={onChanged} initialRows={initialRows} /></div>
      </div>
    </div>
  );
}
