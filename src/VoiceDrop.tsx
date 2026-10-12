import { useCallback, useEffect, useState, type ReactNode } from "react";
import { errorText, type VoiceMatch } from "./api";
import { attachToPerson, attachToShot, undoAdded, useShotDrop, type DropResult } from "./voiceHooks";
import { VoiceoverSheet } from "./VoiceoverSheet";

type Note = { text: string; added?: DropResult["added"] };

/**
 * Drop recordings on a shot's card or timeline block to give that shot its voice; drop one on a person's name in a card to give it to that person. When it is clear the file is attached
 * on the spot and a short note says so, with Undo; otherwise the Voiceover sheet opens on the match table for that shot, so nothing is attached that you have not seen. Returns what to draw
 * (the note, the sheet).
 */
export function useVoiceDrop(dir: string | null, enabled = true): ReactNode {
  const [check, setCheck] = useState<{ shot: string; rows: VoiceMatch[] } | null>(null);
  const [note, setNote] = useState<Note | null>(null);
  useEffect(() => { if (!note) return; const t = setTimeout(() => setNote(null), note.added?.length ? 7000 : 3500); return () => clearTimeout(t); }, [note]);
  const onDrop = useCallback(async (shot: string, files: string[], who?: string) => {
    if (!dir) return;
    try {
      const r = who ? await attachToPerson(dir, shot, who, files) : await attachToShot(dir, shot, files);
      if (r.error) setNote({ text: r.error });
      else if (r.check) setCheck({ shot, rows: r.check });
      else setNote({ text: who ? `${who}'s voice is attached to ${shot}.` : `Voice attached to ${shot}.`, added: r.added });
    } catch (e) { setNote({ text: errorText(e) }); }
  }, [dir]);
  useShotDrop(!!dir && enabled && !check, onDrop);
  const undo = async () => {
    const added = note?.added;
    setNote(null);
    if (dir && added?.length) { try { await undoAdded(dir, added); setNote({ text: "Taken back. The file is kept in the film's voice/_removed folder." }); } catch (e) { setNote({ text: errorText(e) }); } }
  };
  return (
    <>
      {note && <div className="vo-toast" role="status">{note.text}{note.added?.length ? <button className="link vo-undo" onClick={undo}>Undo</button> : null}</div>}
      {check && dir && <VoiceoverSheet dir={dir} only={check.shot} initialRows={check.rows} onClose={() => setCheck(null)} />}
    </>
  );
}
