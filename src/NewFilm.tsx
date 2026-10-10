import { useEffect, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type StoryKind, type StoryPreview } from "./api";
import * as I from "./icons";
import { guessKind, previewLine, STORY_EXT, STORY_KINDS, titleFromFile } from "./storyView";

/**
 * A new film starts with its story, not with a song. Say how the story begins, bring it (paste it, or choose a file), and it is kept exactly as given.
 * FilmCrafter then reads it for scenes, characters and places, and may suggest things; it never rewrites the story.
 */
export function NewFilm({ file, kind: startKind, onClose, onCreated }: { file?: string | null; kind?: StoryKind; onClose: () => void; onCreated: (dir: string) => void }) {
  const [kind, setKind] = useState<StoryKind | null>(startKind ?? null);
  const [stage, setStage] = useState<"pick" | "write">(startKind || file ? "write" : "pick");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [source, setSource] = useState<string | null>(null);          // the file the story came from, kept as the original
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<StoryPreview | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [truncated, setTruncated] = useState(false);
  const titled = useRef(false);                                        // the person typed a title: don't replace it with the file name

  const readFile = async (path: string) => {
    setBusy("read"); setErr("");
    try {
      const r = await api.film<{ name: string; text: string; truncated: boolean }>("read_file", null, { file: path });
      setStage("write"); setText(r.text); setSource(path); setFileName(r.name); setTruncated(r.truncated);
      setKind((k) => (k && startKind) ? k : guessKind(r.name, r.text));
      if (!titled.current) setTitle(titleFromFile(r.name));
    } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  useEffect(() => { if (file) void readFile(file); }, [file]);        // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!kind || !text.trim()) { setPreview(null); return; }
    const t = setTimeout(() => { api.film<StoryPreview>("preview", null, { kind, text }).then(setPreview).catch(() => setPreview(null)); }, 300);
    return () => clearTimeout(t);
  }, [kind, text]);

  const choose = async () => {
    const f = await open({ multiple: false, filters: [{ name: "Story", extensions: STORY_EXT }] });
    if (typeof f === "string") await readFile(f);
  };
  const create = async () => {
    if (!kind) return;
    setBusy("create"); setErr("");
    try {
      const r = await api.film<{ dir: string }>("create", null, { title: title.trim() || "Untitled film", kind, text, file: source });
      onCreated(r.dir);
    } catch (e) { setErr(errorText(e)); setBusy(""); }
  };

  return (
    <div className="overlay" onClick={busy ? undefined : onClose}>
      <div className="sheet glass nf-sheet" role="dialog" aria-label="New film" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>New film</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>

        {stage === "pick" ? <>
          <p className="sub">How does your story begin? Pick the closest; you can change it. Whatever you bring is kept exactly as it is.</p>
          <div className="nf-kinds" role="radiogroup" aria-label="How your story begins">
            {STORY_KINDS.map((k) => (
              <button key={k.id} role="radio" aria-checked={kind === k.id} className={`nf-kind ${kind === k.id ? "on" : ""}`} onClick={() => { setKind(k.id); setStage("write"); }}>
                <b>{k.label}</b><span>{k.blurb}</span></button>))}
          </div>
          <div className="nf-or"><button className="link" onClick={choose}>or choose a story file</button></div>
          {err && <p className="error-text" role="alert">{err}</p>}
        </> : <>
          <label className="field"><span>Title</span>
            <input className="text-input" autoFocus value={title} placeholder="Untitled film" onChange={(e) => { titled.current = true; setTitle(e.target.value); }} /></label>
          <div className="nf-kind-row">
            <span className="dim">This is</span>
            <select className="text-input" value={kind ?? "idea"} onChange={(e) => setKind(e.target.value as StoryKind)} aria-label="What kind of story this is">
              {STORY_KINDS.map((k) => <option key={k.id} value={k.id}>{k.label.toLowerCase()}</option>)}</select>
            <button className="link" onClick={choose}>{fileName ? "choose a different file" : "or choose a file"}</button>
          </div>
          <label className="field"><span>{fileName ? `Your story (from ${fileName})` : "Your story"}</span>
            <textarea className="text-input nf-text" rows={12} value={text} onChange={(e) => { setText(e.target.value); setSource(null); setFileName(""); }}
                      placeholder={kind === "screenplay" ? "Paste the screenplay here" : "Write or paste the story here"} spellCheck={false} /></label>
          {truncated && <p className="dim">The file was longer than FilmCrafter reads at once; the first part is shown.</p>}
          <p className="nf-found" role="status">{previewLine(preview) || (busy === "read" ? "Reading…" : "")}</p>
          {err && <p className="error-text" role="alert">{err}</p>}
          <p className="dim nf-promise">Saved exactly as given. FilmCrafter will read it and may make suggestions; it never rewrites your story.</p>
          <div className="sheet-actions">
            <button className="btn ghost" onClick={() => { setText(""); setSource(null); setFileName(""); setPreview(null); setKind(startKind ?? null); setStage("pick"); }} disabled={!!busy}>Back</button>
            <button className="btn primary" onClick={create} disabled={!!busy || !text.trim()}>{busy === "create" ? "Creating…" : "Create film"}</button>
          </div>
        </>}
      </div>
    </div>
  );
}
