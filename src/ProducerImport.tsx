import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText } from "./api";
import * as I from "./icons";

type Inspect = { title: string; counts: Record<string, number>; files: number; missing: { asset: string; file: string }[];
  song_file: string | null; readiness: string | null; qa_report: string | null; without_images?: { name: string; kind: string }[]; lyrics_text?: string; shots_with_cues?: number };

const AUDIO = ["mp3", "wav", "m4a", "flac", "aac", "ogg", "mp4", "mov", "m4v"];
const LABEL: Record<string, string> = { characters: "characters", wardrobe: "wardrobe", props: "props", environments: "environments",
  references: "style references", choreography: "choreography", shots: "shots" };

/** A Producer package opened from Explorer, dropped on the window, or handed over by the Producer plugin. */
export const isProducerPackage = (p: string) => /\.(pfproducer|zip)$|[\\/]manifest\.json$/i.test(p);

/** Import a FilmCrafter Producer package → review → a normal project (listening, then the Studio). */
export function ProducerImport({ onClose, onOpen, initial }: { onClose: () => void; onOpen: (dir: string) => void; initial?: string }) {
  const [pkg, setPkg] = useState("");
  const [info, setInfo] = useState<Inspect | null>(null);
  const [song, setSong] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const read = async (path: string) => {
    setBusy("Reading the package…"); setErr(""); setInfo(null);
    try { const r = await api.producer<Inspect>("inspect", path); setPkg(path); setInfo(r); setSong(r.song_file ?? ""); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  useEffect(() => { if (initial) read(initial); }, [initial]);   // eslint-disable-line react-hooks/exhaustive-deps
  const pickFile = async () => {
    const f = await open({ filters: [{ name: "FilmCrafter Producer package", extensions: ["pfproducer", "zip", "json"] }] });
    if (typeof f === "string") read(f);
  };
  const pickFolder = async () => { const f = await open({ directory: true }); if (typeof f === "string") read(f); };
  const pickSong = async () => { const f = await open({ filters: [{ name: "Song", extensions: AUDIO }] }); if (typeof f === "string") setSong(f); };
  const go = async () => {
    if (!info || !song) return;
    setBusy("Creating the project…"); setErr("");
    try {
      const dir = await api.createProject(song, info.title, info.lyrics_text || null, null, null);
      setBusy("Importing characters, assets, choreography and shots…");
      await api.producer("apply", pkg, dir);
      onOpen(dir);   // the song is listened to next; the shots are placed on it right after
    } catch (e) { setErr(errorText(e)); setBusy(""); }
  };
  return (
    <div className="overlay" onClick={() => !busy && onClose()}>
      <div className="sheet glass pi-sheet" role="dialog" aria-label="Import a production package" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Import a production package</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close" disabled={!!busy}><I.Close size={18} /></button></div>
        <p className="sub">From FilmCrafter Producer (the ChatGPT plugin): a ZIP, a folder or a manifest. Characters, wardrobe, props and
          places go to the Reference library; continuity rules to the Production Bible; choreography and acting to their characters; and
          the shot plan is placed on your song. Everything stays editable, and nothing is rendered or billed.</p>
        {!info && <div className="wiz-row"><button className="btn primary" onClick={pickFile} disabled={!!busy}>Choose a ZIP or manifest…</button>
          <button className="btn ghost" onClick={pickFolder} disabled={!!busy}>Choose a folder…</button></div>}
        {info && <div className="pi-body">
          <div className="pi-title"><b>{info.title}</b>{info.readiness && <span className={`chip pi-ready ${info.readiness.startsWith("READY") ? (info.readiness === "READY" ? "ok" : "warn") : "no"}`}>{info.readiness}</span>}</div>
          <div className="pi-counts">{Object.entries(info.counts).filter(([, n]) => n > 0).map(([k, n]) => <span key={k}><b>{n}</b> {LABEL[k] ?? k}</span>)}
            {Object.values(info.counts).every((n) => !n) && <span className="dim">The package is empty.</span>}</div>
          {info.qa_report && <div className="dim">Producer's note: {info.qa_report}</div>}
          {info.lyrics_text
            ? <div className="dim">Lyrics: included ({info.lyrics_text.split(/\r?\n/).filter((l) => l.trim() && !/^\[.*\]$/.test(l.trim())).length} lines); the song is aligned to them so shots land on their cues.</div>
            : (info.shots_with_cues ?? 0) > 0 && <div className="pi-missing"><I.Alert size={13} /> {info.shots_with_cues} shots are placed by lyric cues, but this package has no
              plain-text lyrics file, so those shots will be spread by section instead. Add lyrics in the Studio after importing, then re-import to place them.</div>}
          {(info.without_images?.length ?? 0) > 0 && <div className="pi-missing"><I.Alert size={13} /> {info.without_images!.length} of the
            {" "}{(info.counts.characters ?? 0) + (info.counts.wardrobe ?? 0) + (info.counts.props ?? 0) + (info.counts.environments ?? 0)} characters, outfits, props and places have no picture in
            this package (written specs only): {info.without_images!.slice(0, 5).map((x) => x.name).join(", ")}{info.without_images!.length > 5 ? "…" : ""}. They
            reach the prompts as words, but a model has nothing to look at for them. Add an image to each in the Reference library, or have this package's
            producer include them.</div>}
          {info.missing.length > 0 && <div className="pi-missing"><I.Alert size={13} /> {info.missing.length} file{info.missing.length === 1 ? "" : "s"} named in the package
            {info.missing.length === 1 ? " isn't" : " aren't"} in it: {info.missing.slice(0, 4).map((m) => `${m.asset} (${m.file.split(/[\\/]/).pop()})`).join(", ")}
            {info.missing.length > 4 ? "…" : ""}. You can still import; they're listed in the Production Supervisor to add later.</div>}
          {!info.counts.shots && <div className="dim">No shot plan in this package: after importing, plan the shots in the Studio as usual
            (Direct My Video, a script, or cut on the beat).</div>}
          <div className="pi-song">
            <span className="wiz-label">Song</span>
            {song ? <span><b>{song.split(/[\\/]/).pop()}</b>{info.song_file === song ? <span className="dim"> · from the package</span> : null}</span>
              : <span className="dim">The package has no song file. Choose it:</span>}
            <button className="btn small ghost" onClick={pickSong} disabled={!!busy}>{song ? "Change" : "Choose the song…"}</button>
          </div>
          <div className="sheet-actions">
            <button className="btn ghost" onClick={() => { setInfo(null); setPkg(""); }} disabled={!!busy}>Another package</button>
            <button className="btn primary" onClick={go} disabled={!song || !!busy}>{busy || "Import"}</button>
          </div>
        </div>}
        {busy && !info && <div className="dim">{busy}</div>}
        {err && <div className="error-text">{err}</div>}
      </div>
    </div>
  );
}
