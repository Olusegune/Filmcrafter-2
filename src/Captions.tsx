import { useCallback, useEffect, useState } from "react";
import { api, errorText, type CaptionsState } from "./api";
import { FontPicker } from "./FontPicker";

const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/**
 * Lyric captions: the words of the song (or a spoken scene's lines) drawn on the exported film as they are sung, and written to an
 * .srt subtitles file next to it. The lines come from the analysed song; here you change how they look and, line by line, what they say.
 */
export function CaptionsPanel({ dir }: { dir: string }) {
  const [st, setSt] = useState<CaptionsState | null>(null);
  const [err, setErr] = useState("");
  const [preview, setPreview] = useState("");
  const [showLines, setShowLines] = useState(false);
  const [styling, setStyling] = useState<string | null>(null);

  const apply = (r: CaptionsState) => { setSt(r); window.dispatchEvent(new Event("pf-captions-changed")); };
  const load = useCallback(async () => { setSt(await api.captions(dir, "get")); }, [dir]);
  useEffect(() => { load().catch((e) => setErr(errorText(e))); }, [load]);

  const call = async (action: "set" | "edit" | "section", data: Record<string, unknown>) => {
    setErr("");
    try { apply(await api.captions<CaptionsState>(dir, action, data)); setPreview(""); } catch (e) { setErr(errorText(e)); }
  };
  const show = async (key?: string) => {
    setErr("");
    try { const r = await api.captions<{ path: string }>(dir, "preview", { key }); setPreview(r.path); } catch (e) { setErr(errorText(e)); }
  };
  if (!st) return null;
  const s = st.style;
  const edited = st.lines.filter((l) => l.edited).length;

  return (
    <details className="ov-panel">
      <summary><b>Lyric captions</b> <span className="dim">{st.enabled ? "on" : "off"}{st.available ? ` · ${st.lines.filter((l) => !l.hidden).length} lines` : ""}</span></summary>
      <p className="dim">The words of the song drawn on the film as they are sung, with a matching subtitles file. Change how they look here, and what any line says under
        <b> Edit lines</b>. A spoken scene's captions can show who is speaking.</p>
      {err && <p className="error-text" role="alert">{err}</p>}
      {!st.available ? <p className="dim">{st.reason}</p> : <>
        <label className="ov-check"><input type="checkbox" checked={st.enabled} onChange={(e) => call("set", { enabled: e.target.checked })} /> Draw lyric captions on the exported film</label>
        <label className="ov-check"><input type="checkbox" checked={s.srt} onChange={(e) => call("set", { srt: e.target.checked })} /> Also write a subtitles file (.srt) next to the film</label>
        <label className="ov-check"><input type="checkbox" checked={s.names} onChange={(e) => call("set", { names: e.target.checked })} /> Show who is speaking (spoken scenes)</label>
        <label className="ov-check"><input type="checkbox" checked={s.uppercase} onChange={(e) => call("set", { uppercase: e.target.checked })} /> CAPITALS</label>
        <div className="ov-grid">
          <label>Size {Math.round(s.size * 100)}%<input type="range" min={2} max={15} defaultValue={Math.round(s.size * 100)} onPointerUp={(e) => call("set", { size: Number(e.currentTarget.value) / 100 })} onKeyUp={(e) => call("set", { size: Number(e.currentTarget.value) / 100 })} /></label>
          <label>Down {Math.round(s.y * 100)}%<input type="range" min={5} max={95} defaultValue={Math.round(s.y * 100)} onPointerUp={(e) => call("set", { y: Number(e.currentTarget.value) / 100 })} onKeyUp={(e) => call("set", { y: Number(e.currentTarget.value) / 100 })} /></label>
          <label>Colour<input type="color" defaultValue={s.color} onBlur={(e) => call("set", { color: e.target.value })} /></label>
          <FontPicker dir={dir} value={s.font ?? ""} onChange={(id) => call("set", { font: id })} />
        </div>
        {st.section_names.length > 1 && <details className="ov-sub">
          <summary>Style by section {Object.keys(st.sections).length ? <span className="dim">({Object.keys(st.sections).length} changed)</span> : null}</summary>
          <p className="dim">Give every line in a section its own size, position or colour (for example bigger chorus lines). Lines can still override it one by one.</p>
          {st.section_names.map((sec) => {
            const own = st.sections[sec] ?? {};
            return (
              <div key={sec} className="ov-grid sec-style">
                <b>{sec}</b>
                <label>Size {Math.round((own.size ?? s.size) * 100)}%<input type="range" min={2} max={15} defaultValue={Math.round((own.size ?? s.size) * 100)}
                       onPointerUp={(e) => call("section", { section: sec, size: Number(e.currentTarget.value) / 100 })} onKeyUp={(e) => call("section", { section: sec, size: Number(e.currentTarget.value) / 100 })} /></label>
                <label>Down {Math.round((own.y ?? s.y) * 100)}%<input type="range" min={5} max={95} defaultValue={Math.round((own.y ?? s.y) * 100)}
                       onPointerUp={(e) => call("section", { section: sec, y: Number(e.currentTarget.value) / 100 })} onKeyUp={(e) => call("section", { section: sec, y: Number(e.currentTarget.value) / 100 })} /></label>
                <label>Colour<input type="color" defaultValue={own.color ?? s.color} onBlur={(e) => call("section", { section: sec, color: e.target.value })} /></label>
                <FontPicker dir={dir} value={own.font ?? ""} inherit="Like the film" allowAdd={false} onChange={(id) => call("section", { section: sec, font: id })} />
                {Object.keys(own).length > 0 && <button className="link" onClick={() => call("section", { section: sec, reset: true })}>reset</button>}
              </div>);
          })}
        </details>}
        <div className="ov-add">
          <button className="btn sm" onClick={() => show()}>Preview</button>
          <button className="btn sm ghost" onClick={() => setShowLines(!showLines)} aria-expanded={showLines}>{showLines ? "Hide lines" : `Edit lines (${st.lines.length}${edited ? `, ${edited} changed` : ""})`}</button>
        </div>
        {preview && <img className="ov-preview" src={api.mediaUrl(`${dir}/${preview}`) + `?t=${Date.now()}`} alt="Preview of a caption" />}
        {showLines && <ul className="ov-list cap-lines">
          {st.lines.map((l) => (
            <li key={l.key} className={`cap-line ${l.hidden ? "off" : ""}`}>
              <button className="link num" onClick={() => show(l.key)} title="Preview this line">{clock(l.start)}</button>
              <input key={l.text} className="text-input" defaultValue={l.text} aria-label={`Caption at ${clock(l.start)}`} maxLength={300}
                     onBlur={(e) => e.target.value.trim() && e.target.value !== l.text && call("edit", { key: l.key, text: e.target.value })} />
              <label title="Don't show this line"><input type="checkbox" checked={l.hidden} onChange={(e) => call("edit", { key: l.key, hidden: e.target.checked })} /> hide</label>
              {l.edited && <button className="link" title={`Put back: ${l.original}`} onClick={() => call("edit", { key: l.key, reset: true })}>reset</button>}
              <button className="link" aria-expanded={styling === l.key} title="This line's own size, position, colour and font" onClick={() => setStyling(styling === l.key ? null : l.key)}>
                {Object.keys(l.own).length ? "style •" : "style"}</button>
              {styling === l.key && <div className="ov-grid cap-style">
                <label>Size {Math.round(l.look.size * 100)}%<input type="range" min={2} max={15} defaultValue={Math.round(l.look.size * 100)}
                       onPointerUp={(e) => call("edit", { key: l.key, size: Number(e.currentTarget.value) / 100 })} onKeyUp={(e) => call("edit", { key: l.key, size: Number(e.currentTarget.value) / 100 })} /></label>
                <label>Down {Math.round(l.look.y * 100)}%<input type="range" min={5} max={95} defaultValue={Math.round(l.look.y * 100)}
                       onPointerUp={(e) => call("edit", { key: l.key, y: Number(e.currentTarget.value) / 100 })} onKeyUp={(e) => call("edit", { key: l.key, y: Number(e.currentTarget.value) / 100 })} /></label>
                <label>Colour<input type="color" defaultValue={l.look.color} onBlur={(e) => call("edit", { key: l.key, color: e.target.value })} /></label>
                <FontPicker dir={dir} value={l.own.font ?? ""} inherit="Like its section" allowAdd={false} onChange={(id) => call("edit", { key: l.key, font: id })} />
                {Object.keys(l.own).length > 0 && <button className="link" onClick={() => call("edit", { key: l.key, size: "", y: "", color: "", font: "" })}>like its section</button>}
              </div>}
            </li>
          ))}
        </ul>}
      </>}
    </details>
  );
}
