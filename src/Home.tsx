import { useEffect, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { open } from "@tauri-apps/plugin-dialog";
import { api, type ProjectSummary } from "./api";
import { Gear, Mark, Sparkle } from "./icons";
import * as I from "./icons";
import { Cta } from "./Dock";
import { ask } from "./ask";
import { UpdatePill } from "./Updates";
import { isStoryFile, STORY_EXT } from "./storyView";

/**
 * Home: a film begins with a story. Drop a screenplay, or start from an idea. Projects made in earlier versions (music videos, shows) still open from Recent.
 */
export function Home({ onNewFilm, onOpen, onChooseProject, onSettings, onHelp }: {
  onNewFilm: (opts?: { file?: string; kind?: "idea" }) => void; onOpen: (dir: string) => void; onChooseProject: () => void; onSettings: () => void; onHelp: () => void;
}) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [over, setOver] = useState(false);
  const [hint, setHint] = useState("");
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
        const proj = p.paths.find((f) => /\.(filmcrafter|pulse)$/i.test(f));
        const story = p.paths.find(isStoryFile);
        if (proj) onOpen(proj);
        else if (story) onNewFilm({ file: story });
        else setHint("Drop a screenplay (Fountain, text, Markdown, PDF or Word), or a FilmCrafter project.");
      }
    });
    return () => { un.then((f) => f()); };
  }, [onNewFilm, onOpen]);

  const choose = async () => {
    const f = await open({ multiple: false, filters: [{ name: "Story", extensions: STORY_EXT }] });
    if (typeof f === "string") onNewFilm({ file: f });
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
        <h1>CRAFT STORIES<br />INTO CINEMA</h1>
        <div className={`dropcard story ${over ? "over" : ""}`}>
          <div className="filmstrip" aria-hidden="true">{Array.from({ length: 14 }, (_, i) => <i key={i} />)}</div>
          <div className="big">Drop a screenplay here</div>
          <div className="home-cta-row">
            <Cta icon={<Sparkle size={18} />} onClick={() => onNewFilm()} title="Start a film from a screenplay, a logline, a synopsis, a treatment or a scene outline">New film</Cta>
            <button className="btn" onClick={() => onNewFilm({ kind: "idea" })}>Start from an idea</button>
          </div>
          <button className="link" onClick={choose}>or choose a story file</button>
          <div className="hint">{hint || "Fountain, text, Markdown, PDF or Word · your story is kept exactly as it is"}</div>
        </div>
        <div className="home-secondary">
          <button className="btn ghost chip-btn" data-c="blue" onClick={onChooseProject}><I.Folder size={15} /> Open project</button>
        </div>
      </div>

      {(projects.length > 0 || hiddenN > 0) && (
        <div className="recent">
          <div className="recent-head"><h2>Recent</h2>
            {projects.length > 0 && <button className="link" onClick={async () => { if (await ask("Clear the Recent list? Your projects stay on disk; open them any time with Open project.")) recent("clear"); }}>Clear list</button>}
            {hiddenN > 0 && <button className="link" onClick={() => recent("restore")}>Show {hiddenN} hidden</button>}
          </div>
          <div className="recent-row">
            {projects.map((p) => (
              <div key={p.dir} className="project-card-wrap">
                <button className="recent-x" title="Remove from Recent (the project stays on disk)" aria-label={`Remove ${p.title} from Recent`}
                        onClick={() => recent("remove", p.dir)}>×</button>
                <button className={`project-card ${p.kind === "film" ? "is-film" : ""}`} onClick={() => onOpen(p.dir)}>
                  <div className="t">{p.title}</div>
                  <div className="m">{p.kind === "film" || p.kind === "show" ? p.state : p.onboarding && p.onboarding.stage !== "done" ? <span className="setup-badge">Setup · {SETUP[p.onboarding.stage] ?? "in progress"}</span>
                    : stateLabel(p.state)} · {new Date(p.modified * 1000).toLocaleDateString()}</div>
                  {p.kind === "film"
                    ? <div className="mini-strip" aria-hidden="true">{Array.from({ length: 9 }, (_, i) => <i key={i} />)}</div>
                    : <div className="mini-wave">{Array.from({ length: 36 }, (_, i) =>
                      <i key={i} style={{ height: `${25 + 70 * Math.abs(Math.sin(i * 1.7 + p.title.length))}%` }} />)}</div>}
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
