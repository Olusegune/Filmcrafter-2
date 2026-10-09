import { LivingWave } from "./LivingWave";
import { useEffect, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type ProjectSummary } from "./api";
import { Gear, Mark, Sparkle } from "./icons";
import * as I from "./icons";
import { Cta } from "./Dock";
import { ProducerImport, isProducerPackage } from "./ProducerImport";
import { ask } from "./ask";
import { UpdatePill } from "./Updates";

const AUDIO = ["mp3", "wav", "m4a", "flac", "aac", "ogg", "mp4", "mov", "m4v"];

export function Home({ onSong, onNew, onProduce, onOpen, onShow, onChooseProject, onSettings, onHelp }: {
  onSong: (path: string) => void; onNew: () => void; onProduce: () => void; onOpen: (dir: string) => void; onShow: (dir: string) => void;
  onChooseProject: () => void; onSettings: () => void; onHelp: () => void;
}) {
  const [newShow, setNewShow] = useState<string | null>(null);
  const [showErr, setShowErr] = useState("");
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [over, setOver] = useState(false);
  const [hint, setHint] = useState("");
  const [importing, setImporting] = useState(false);

  const [hiddenN, setHiddenN] = useState(0);
  const reloadList = () => { api.listProjects().then(setProjects).catch(() => setProjects([])); api.hiddenCount().then(setHiddenN).catch(() => {}); };
  useEffect(reloadList, []);
  const recent = async (action: "remove" | "clear" | "restore", dir: string | null = null) => { await api.recents(action, dir).catch(() => {}); reloadList(); };

  useEffect(() => {
    const un = getCurrentWebview().onDragDropEvent((e) => {
      const p = e.payload;
      if (p.type === "enter" || p.type === "over") setOver(true);
      else if (p.type === "leave") setOver(false);
      else if (p.type === "drop") {
        setOver(false);
        const proj = p.paths.find((f) => /\.(filmcrafter|pulse)$/i.test(f) || isProducerPackage(f));
        const song = p.paths.find((f) => AUDIO.includes(f.split(".").pop()!.toLowerCase()));
        if (proj) onOpen(proj);
        else if (song) onSong(song);
        else setHint("FilmCrafter accepts songs (MP3, WAV, M4A, FLAC), a video with a soundtrack, a project, or a Producer package.");
      }
    });
    return () => { un.then((f) => f()); };
  }, [onSong, onOpen]);

  const choose = async () => {
    const f = await open({ multiple: false, filters: [{ name: "Music", extensions: AUDIO }] });
    if (typeof f === "string") onSong(f);
  };

  return (
    <div className="home">
      <div className="home-top">
        <div className="wordmark"><Mark size={24} /> FilmCrafter</div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <UpdatePill />
          <button className="btn ghost" onClick={onHelp} title="The user guide (F1)">Documentation</button>
          <button className="icon-btn" onClick={onSettings} title="Settings" aria-label="Settings"><Gear /></button>
        </div>
      </div>

      <div className="home-hero">
        <h1>DIRECT MUSIC<br />INTO MOTION</h1>
        <div className={`dropcard ${over ? "over" : ""}`}>
          <LivingWave active={over} />
          <div className="big">Drop a song here</div>
          <div className="home-cta-row">
            <Cta icon={<Sparkle size={18} />} onClick={onProduce} title="The Producer plans the cast, outfits, props, places, movement and every shot from your song">Create from song</Cta>
            <button className="btn primary" onClick={onNew}>New Project</button>
          </div>
          <div className="home-cta-sub"><b>Create from song</b>: AI plans everything and you approve each step. <b>New Project</b>: you bring the pieces.</div>
          <button className="link" onClick={choose}>or choose a song file directly</button>
          <div className="hint">{hint || "MP3, WAV, M4A, FLAC · or a video's soundtrack"}</div>
        </div>
        <div className="home-secondary">
          <button className="btn ghost chip-btn" data-c="blue" onClick={onChooseProject}><I.Folder size={15} /> Open Project</button>
          <button className="btn ghost chip-btn" data-c="violet" onClick={() => setImporting(true)} title="A package from FilmCrafter Producer (ZIP, folder or manifest)"><I.Cube size={15} /> Import production package</button>
          <button className="btn ghost chip-btn" data-c="teal" onClick={() => setNewShow("")} title="A musical or multi-song production: numbers and spoken scenes with one cast"><I.Mask size={15} /> New show</button>
        </div>
        {newShow !== null && <div className="overlay" onClick={() => setNewShow(null)}>
          <form className="sheet glass" onClick={(e) => e.stopPropagation()} style={{ width: "min(520px, calc(100vw - 48px))" }}
                onSubmit={async (e) => { e.preventDefault(); setShowErr("");
                  try { const r = await api.show<{ dir: string }>("create", null, { title: newShow.trim() || "My Show" }); setNewShow(null); onShow(r.dir); }
                  catch (x) { setShowErr(errorText(x)); } }}>
            <h2>New show</h2>
            <p className="sub">A musical, a visual album or a stage show: songs and spoken scenes in acts, with one cast and one look, exported as one film.</p>
            <label className="field"><span>Title</span><input className="text-input" autoFocus value={newShow} onChange={(e) => setNewShow(e.target.value)} placeholder="My Musical" /></label>
            {showErr && <p className="error-text">{showErr}</p>}
            <div className="sheet-actions"><button type="button" className="btn ghost" onClick={() => setNewShow(null)}>Cancel</button>
              <button className="btn primary" type="submit">Create show</button></div>
          </form>
        </div>}
        {importing && <ProducerImport onClose={() => setImporting(false)} onOpen={(d) => { setImporting(false); onOpen(d); }} />}
      </div>

      {(projects.length > 0 || hiddenN > 0) && (
        <div className="recent">
          <div className="recent-head"><h2>Recent</h2>
            {projects.length > 0 && <button className="link" onClick={async () => { if (await ask("Clear the Recent list? Your projects stay on disk; open them any time with Open Project.")) recent("clear"); }}>Clear list</button>}
            {hiddenN > 0 && <button className="link" onClick={() => recent("restore")}>Show {hiddenN} hidden</button>}
          </div>
          <div className="recent-row">
            {projects.map((p) => (
              <div key={p.dir} className="project-card-wrap">
              <button className="recent-x" title="Remove from Recent (the project stays on disk)" aria-label={`Remove ${p.title} from Recent`}
                      onClick={() => recent("remove", p.dir)}>×</button>
              <button className="project-card" onClick={() => onOpen(p.dir)}>
                <div className="t">{p.title}</div>
                <div className="m">{p.onboarding && p.onboarding.stage !== "done" ? <span className="setup-badge">Setup · {SETUP[p.onboarding.stage] ?? "in progress"}</span>
                  : stateLabel(p.state)} · {new Date(p.modified * 1000).toLocaleDateString()}</div>
                <div className="mini-wave">{Array.from({ length: 36 }, (_, i) =>
                  <i key={i} style={{ height: `${25 + 70 * Math.abs(Math.sin(i * 1.7 + p.title.length))}%` }} />)}</div>
              </button></div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export const stateLabel = (s: string) =>
  ({ new: "New", analyzing: "Listening…", analyzed: "Ready to direct", directed: "Directed" } as Record<string, string>)[s] ?? s;

const SETUP: Record<string, string> = { music: "Music", lyrics: "Lyrics", script: "Script", assets: "References", choreography: "Choreography", review: "Review" };
