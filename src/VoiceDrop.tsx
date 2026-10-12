import { useCallback, useEffect, useState, type ReactNode } from "react";
import { errorText, type VoiceMatch } from "./api";
import { attachToShot, useShotDrop } from "./voiceHooks";
import { VoiceoverSheet } from "./VoiceoverSheet";

/**
 * Drop recordings on a shot's card or timeline block to give that shot its voice. When every file is clear it is attached on the spot and a short note says so;
 * otherwise the Voiceover sheet opens on the match table for that shot, so nothing is attached that you have not seen. Returns what to draw (a note, the sheet).
 */
export function useVoiceDrop(dir: string | null, enabled = true): ReactNode {
  const [check, setCheck] = useState<{ shot: string; rows: VoiceMatch[] } | null>(null);
  const [note, setNote] = useState("");
  useEffect(() => { if (!note) return; const t = setTimeout(() => setNote(""), 3500); return () => clearTimeout(t); }, [note]);
  const onDrop = useCallback(async (shot: string, files: string[]) => {
    if (!dir) return;
    try {
      const r = await attachToShot(dir, shot, files);
      if (r.error) setNote(r.error);
      else if (r.check) setCheck({ shot, rows: r.check });
      else setNote(`Voice attached to ${shot}.`);
    } catch (e) { setNote(errorText(e)); }
  }, [dir]);
  useShotDrop(!!dir && enabled && !check, onDrop);
  return (
    <>
      {note && <div className="vo-toast" role="status">{note}</div>}
      {check && dir && <VoiceoverSheet dir={dir} only={check.shot} initialRows={check.rows} onClose={() => setCheck(null)} />}
    </>
  );
}
