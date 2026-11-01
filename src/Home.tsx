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
import { lastFilm, relativeDay } from "./homeInfo";
import { FeaturedPresets, PresetDetailsSheet, PresetGallerySheet, WelcomeSheet } from "./HomePresets";
import { byId, cardMeta, RECENT_SHOWN, type HomePreset } from "./presetShelf";
import { markWelcomeSeen, shouldWelcome, welcomeSeen } from "./homePrefs";
import "./home.css";

/**
 * Home: three ways to begin (a story, a preset, or the film you were making), with the presets shown rather than hidden. A film still begins with its story: drop a screenplay anywhere on this screen,
 * or start from an idea. Choosing a preset only sets the new film up (look, acting, colour, editing, frame); nothing is made or charged. Projects made in earlier versions still open from Recent.
 */
export function Home({ onNewFilm, onOpen, onChooseProject, onSettings, onHelp }: {
  onNewFilm: (opts?: { file?: string; kind?: "idea"; preset?: string }) => void; onOpen: (dir: string) => void; onChooseProject: () => void; onSettings: () => void; onHelp: () => void;
}) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [over, setOver] = useState(false);
  const [hint, setHint] = useState("");
  const [hiddenN, setHiddenN] = useState(0);
  const [all, setAll] = useState(false);
  const [gallery, setGallery] = useState(false);
  const [pick, setPick] = useState<HomePreset | null>(null);
  const [welcome, setWelcome] = useState(false);
  const reloadList = () => { api.listProjects().then((p) => { setProjects(p); setLoaded(true); }).catch(() => { setProjects([]); setLoaded(true); }); api.hiddenCount().then(setHiddenN).catch(() => {}); };
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
  const start = (p: HomePreset) => { setPick(null); setGallery(false); onNewFilm({ preset: p.id }); };
  const last = lastFilm(projects);
  const films = projects.filter((p) => p.kind === "film");
  const shown = all ? films : films.slice(0, RECENT_SHOWN);
  useEffect(() => { if (shouldWelcome(films.length, loaded, welcomeSeen())) setWelcome(true); }, [loaded, films.length]);
  const answer = (go: () => void) => () => { markWelcomeSeen(); setWelcome(false); go(); };

  return (
    <div className="home hm">
      <div className="home-top">
        <div className="wordmark"><Mark size={24} /> FilmCrafter</div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <UpdatePill />
          <button className="btn ghost" onClick={onHelp} title="The user guide (F1)">Documentation</button>
          <button className="icon-btn" onClick={onSettings} title="Settings" aria-label="Settings"><Gear /></button>
        </div>
      </div>

      <main className="hm-main">
        <header className="hm-head">
          <p className="hm-eyebrow">Your creative studio</p>
          <h1>What will you create today?</h1>
          <p className="dim">From first idea to finished film. Choose how you would like to begin. <button type="button" className="link" onClick={() => setWelcome(true)}>Help me choose</button></p>
        </header>

        <section className="hm-starts" aria-label="Start a film">
          <div className={`hm-start ${over ? "over" : ""}`}>
            <I.Script size={20} aria-hidden="true" />
            <h2>Start from a story</h2>
            <p>Drop a screenplay anywhere on this screen, write an idea, or choose a file. Your story is kept exactly as it is.</p>
            <div className="hm-row">
              <Cta icon={<Sparkle size={18} />} onClick={() => onNewFilm()} title="Start a film from a screenplay, a logline, a synopsis, a treatment or a scene outline">New film</Cta>
              <button className="btn" onClick={() => onNewFilm({ kind: "idea" })}>Start from an idea</button>
              <button className="link" onClick={choose}>or choose a story file</button>
            </div>
            <p className="hint" role="status">{hint || "Fountain, text, Markdown, PDF or Word"}</p>
          </div>
          <div className="hm-start">
            <I.Wand size={20} aria-hidden="true" />
            <h2>Create from a preset</h2>
            <p>Micro-dramas, shorts, animation, documentaries and storybook looks, set up for you. Nothing is made or charged until you choose.</p>
            <div className="hm-row"><button className="btn" onClick={() => setGallery(true)}>Explore presets</button></div>
          </div>
        </section>

        <FeaturedPresets onPick={setPick} onAll={() => setGallery(true)} />

        <section className="hm-section" aria-labelledby="hm-recent-h">
          <div className="hm-shead">
            <h2 id="hm-recent-h">Continue creating</h2>
            <div className="hm-links">
              <button className="link" onClick={onChooseProject}><I.Folder size={14} /> Open project…</button>
              {films.length > 0 && <button className="link" onClick={async () => { if (await ask("Clear the Recent list? Your projects stay on disk; open them any time with Open project.")) recent("clear"); }}>Clear list</button>}
              {hiddenN > 0 && <button className="link" onClick={() => recent("restore")}>Show {hiddenN} hidden</button>}
            </div>
          </div>
          {!loaded ? <p className="dim" role="status">Loading your projects…</p>
            : films.length === 0 ? <p className="hm-empty">No films yet. Your films appear here, ready to continue, as soon as you start one.</p>
            : <>
              <ul className="hm-recent">
                {shown.map((p) => (
                  <li key={p.dir} className={`project-card-wrap hm-rcard ${last?.dir === p.dir ? "latest" : ""}`}>
                    <button className="recent-x" title="Remove from Recent (the project stays on disk)" aria-label={`Remove ${p.title} from Recent`} onClick={() => recent("remove", p.dir)}>×</button>
                    <button className="project-card is-film" onClick={() => onOpen(p.dir)} aria-label={`Continue ${p.title}`}>
                      <div className="mini-strip" aria-hidden="true">{Array.from({ length: 9 }, (_, i) => <i key={i} />)}</div>
                      <div className="t">{p.title}</div>
                      <div className="m">{cardMeta(p.state, p.aspect, relativeDay(p.modified))}</div>
                      <span className="hm-go">{last?.dir === p.dir ? "Continue where you left off" : "Continue"} →</span>
                    </button>
                  </li>))}
              </ul>
              {films.length > RECENT_SHOWN && <button className="link hm-more" onClick={() => setAll((v) => !v)}>{all ? "Show fewer" : `Show all ${films.length} films`}</button>}
            </>}
        </section>
      </main>

      {welcome && <WelcomeSheet onClose={answer(() => {})} onStory={answer(() => onNewFilm())} onPreset={answer(() => setGallery(true))} onAnimated={answer(() => setPick(byId("animated_short") ?? null))} onOpen={answer(onChooseProject)} />}
      {gallery && !pick && <PresetGallerySheet onPick={setPick} onClose={() => setGallery(false)} />}
      {pick && <PresetDetailsSheet p={pick} onStart={start} onClose={() => setPick(null)} />}
    </div>
  );
}
