import { useEffect, useRef, useState } from "react";
import { Sheet } from "./Sheet";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type StoryKind, type StoryPreview } from "./api";
import * as I from "./icons";
import { FrameShapes } from "./FrameShapes";
import { byId, layerChoices, lengthOptions, lengthWords, presetAspect, presetLength, SETUP_LAYERS, setupStack, stackedNames } from "./presetShelf";
import { guessKind, previewLine, STORY_EXT, STORY_KINDS, titleFromFile } from "./storyView";

/**
 * A new film starts with its story, not with a song. Say how the story begins, bring it (paste it, or choose a file), and it is kept exactly as given.
 * FilmCrafter then reads it for scenes, characters and places, and may suggest things; it never rewrites the story.
 */
export function NewFilm({ file, kind: startKind, preset: presetId, onClose, onCreated }: { file?: string | null; kind?: StoryKind; preset?: string | null; onClose: () => void; onCreated: (dir: string) => void }) {
  const preset = presetId ? byId(presetId) ?? null : null;               // a preset chosen on Home: it sets the film up once the film exists
  const [kind, setKind] = useState<StoryKind | null>(startKind ?? null);
  const [stage, setStage] = useState<"pick" | "write">(startKind || file ? "write" : "pick");
  const [title, setTitle] = useState("");
  const [aspect, setAspect] = useState((preset && presetAspect(preset)) || "16:9");                          // the shape of the frame: widescreen unless the film is vertical, cinema scope, square...
  const [text, setText] = useState("");
  const [source, setSource] = useState<string | null>(null);          // the file the story came from, kept as the original
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<StoryPreview | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [truncated, setTruncated] = useState(false);
  const [length, setLength] = useState<number | null>(null);                 // null: the length the preset aims for
  const [episodes, setEpisodes] = useState(10);
  const [layers, setLayers] = useState<Partial<Record<"visual" | "acting" | "editing" | "color", string>>>({});
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
      const r = await api.film<{ dir: string }>("create", null, { title: title.trim() || "Untitled film", kind, text, file: source, aspect_ratio: aspect });
      if (preset) await api.presets(r.dir, "set_pending", { stack: setupStack(preset, layers), setup: { ...(length ? { length } : {}), ...(preset.series ? { episodes } : {}) } }).catch(() => {});       // only remembers the choice (free, local); the film is not changed until you preview and apply it in Presets
      onCreated(r.dir);
    } catch (e) { setErr(errorText(e)); setBusy(""); }
  };

  return (
    <Sheet label="New film" className="nf-sheet" onDismiss={busy ? undefined : onClose}>
        <div className="vs-head"><h2>New film</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>

        {preset && <p className="nf-preset" role="status"><b>{preset.name}</b> is waiting for this film{stackedNames(preset).length ? `, with ${stackedNames(preset).join(", ")}` : ""}. Once the film has its shots, open Presets to see exactly what it would change before anything does. Nothing is made or charged.</p>}
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
          <div className="field nf-frame"><span>Frame shape <em className="dim">you can change it later</em></span><FrameShapes value={aspect} onChange={setAspect} disabled={!!busy} /></div>
          <div className="nf-kind-row">
            <span className="dim">This is</span>
            <select className="text-input" value={kind ?? "idea"} onChange={(e) => setKind(e.target.value as StoryKind)} aria-label="What kind of story this is">
              {STORY_KINDS.map((k) => <option key={k.id} value={k.id}>{k.label.toLowerCase()}</option>)}</select>
            <button className="link" onClick={choose}>{fileName ? "choose a different file" : "or choose a file"}</button>
          </div>
          {preset && <fieldset className="nf-setup"><legend>Set up from {preset.name}</legend>
            <div className="ly-two">
              <label className="field"><span>Length to aim for</span>
                <select className="text-input" value={length ?? ""} onChange={(e) => setLength(e.target.value ? Number(e.target.value) : null)}>
                  <option value="">As the preset{presetLength(preset) ? ` (about ${lengthWords(presetLength(preset)!)})` : ""}</option>
                  {lengthOptions(presetLength(preset)).map((s) => <option key={s} value={s}>{lengthWords(s)}</option>)}</select></label>
              {preset.series && <label className="field"><span>Episodes in the season</span>
                <input className="text-input" type="number" min={1} max={60} value={episodes} onChange={(e) => setEpisodes(Math.min(60, Math.max(1, Math.round(Number(e.target.value) || 1))))} /></label>}
            </div>
            <details className="nf-adv"><summary>Advanced: change what the preset brings</summary>
              <p className="dim">The preset already chooses these. Pick one only to use something else: it is added after the preset, so it wins.</p>
              {SETUP_LAYERS.map((l) => (
                <label key={l.key} className="field"><span>{l.label}</span>
                  <select className="text-input" value={layers[l.key] ?? ""} onChange={(e) => setLayers((x) => ({ ...x, [l.key]: e.target.value || undefined }))}>
                    <option value="">As the preset</option>
                    {layerChoices(l.type).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>))}
            </details>
          </fieldset>}
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
    </Sheet>
  );
}
