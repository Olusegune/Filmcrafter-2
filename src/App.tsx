import { useCallback, useEffect, useState } from "react";
import { open as openDialog, save as saveDialog } from "@tauri-apps/plugin-dialog";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { api, errorText, type LoadedProject } from "./api";
import "./studio-shared.css";                // the Studio's focus mode and shared rules (loaded first, as when it came with the old wizard)
import { Home } from "./Home";
import { Studio } from "./Studio";
import { Settings } from "./Settings";
import { HelpSheet } from "./Help";
import { BackupsSheet } from "./Backups";
import { EngineSetup } from "./EngineSetup";
import { FilmView } from "./FilmView";
import { filmDirOfDoc, filmDirOfRender, isProducerPackage } from "./filmPaths";
import { NewFilm } from "./NewFilm";
import type { StoryKind } from "./api";
import "./styles.css";
import "./motion.css";

type View =
  | { name: "home" }
  | { name: "studio"; project: LoadedProject }
  | { name: "film"; dir: string; stage?: string };

/** FilmCrafter makes films. A music video that was never finished, a show, or a Producer package belongs in PULSEFRAME, which still has the song-first screens. */
const LEGACY = "This is a PULSEFRAME music-video project that FilmCrafter does not set up or continue from the start. Open it in PULSEFRAME to finish it. Finished projects open in the Studio here.";

export default function App() {
  const [view, setView] = useState<View>({ name: "home" });
  const [creating, setCreating] = useState<{ file?: string; kind?: StoryKind } | null>(null);       // the New film sheet, from Home or the File menu
  const [settings, setSettings] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [help, setHelp] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [engine, setEngine] = useState<{ ready: boolean; gpu: boolean } | null>(null);
  useEffect(() => { api.engineStatus().then(setEngine).catch(() => setEngine({ ready: true, gpu: false })); }, []);
  const say = useCallback((t: string) => { setToast(t); setTimeout(() => setToast(""), 1800); }, []);

  // First paint is done: swap the splash window for this one.
  useEffect(() => { api.appReady().catch(() => {}); }, []);

  const openProject = useCallback(async (dir: string) => {
    setError("");
    if (isProducerPackage(dir)) { setError(LEGACY); return; }
    try {
      if (await api.isFilm(dir)) { setView({ name: "film", dir: filmDirOfDoc(dir) }); return; }
      if (await api.isShow(dir)) { setError(LEGACY); return; }
      if (dir.toLowerCase().endsWith(".pulse")) {   // one-file project: unpack it into the projects folder first
        setToast("Unpacking the project…");
        dir = await api.openPulse(dir);
        setToast("");
      }
      const p = await api.loadProject(dir);
      // A music project whose setup or listening was never finished is not continued here; a finished one opens in the Studio.
      if ((p.project.onboarding && p.project.onboarding.stage !== "done") || !p.song_map || p.project.state === "new" || p.project.state === "analyzing") { setError(LEGACY); return; }
      setView({ name: "studio", project: p });
    } catch (e) { setError(errorText(e)); }
  }, []);

  // A project double-clicked in Explorer: at launch, or while the app is already open.
  useEffect(() => {
    api.launchPath().then((p) => { if (p) openProject(p); }).catch(() => {});
    const un = api.onOpenPath((p) => openProject(p));
    return () => { un.then((f) => f()); };
  }, [openProject]);

  // A studio opened from a film goes back to the film; anything else goes Home.
  const backFrom = useCallback(async (dir: string, stage?: string) => {
    const film = filmDirOfRender(dir);                                      // the studio was opened on a film's render project: back goes to the film
    if (film !== dir && await api.isFilm(film).catch(() => false)) { setView({ name: "film", dir: film, stage }); return; }
    setView({ name: "home" });
  }, []);

  const chooseProject = useCallback(async () => {
    const f = await openDialog({ filters: [{ name: "FilmCrafter Project", extensions: ["filmcrafter", "pulse"] }] });
    if (typeof f === "string") openProject(f);
  }, [openProject]);

  // Standard File menu (native menu bar + shortcuts).
  const current = view.name === "studio" ? view.project : null;
  useEffect(() => {
    const un = api.onMenu(async (id) => {
      try {
        switch (id) {
          case "new": setCreating({}); break;
          case "open": await chooseProject(); break;
          case "settings": setSettings(true); break;
          case "help": setHelp(true); break;
          case "save":
            if (current) { await api.saveProject(current.dir); await api.backups(current.dir, "backup", "saved").catch(() => {}); say("Saved"); }
            else say("Open a project to save it.");
            break;
          case "save_as": {
            if (!current) { say("Open a project first."); break; }
            const dest = await saveDialog({ defaultPath: `${current.project.title} copy.filmcrafter`,
                                            filters: [{ name: "FilmCrafter Project", extensions: ["filmcrafter"] }] });
            if (dest) { const dir = await api.saveProjectAs(current.dir, dest); await openProject(dir); say("Saved a copy"); }
            break;
          }
          case "save_pulse": {
            if (!current) { say("Open a project first."); break; }
            const dest = await saveDialog({ defaultPath: `${current.project.title}.pulse`, filters: [{ name: "FilmCrafter project in one file", extensions: ["pulse"] }] });
            if (dest) {
              setToast("Packing the project into one file…");
              const r = await api.packProject(current.dir, dest);
              say(`Saved ${r.files} files as one .pulse (${(r.bytes / 1e6).toFixed(0)} MB)`);
              await revealItemInDir(r.path).catch(() => {});
            }
            break;
          }
          case "backups": if (current) setRestoring(true); else say("Open a project first."); break;
          case "reveal": if (current) await revealItemInDir(current.doc ?? current.dir); break;
          case "close": setView({ name: "home" }); break;
          default: window.dispatchEvent(new CustomEvent("pf-menu", { detail: id })); // studio-level items
        }
      } catch (e) { setError(errorText(e)); }
    });
    return () => { un.then((f) => f()); };
  }, [current, chooseProject, openProject, say]);

  return (
    <>
      {engine && !engine.ready && <EngineSetup gpu={engine.gpu} onReady={() => setEngine({ ...engine, ready: true })} />}
      {(!engine || engine.ready) && view.name === "home" && <Home onNewFilm={(o) => setCreating(o ?? {})} onOpen={openProject} onChooseProject={chooseProject}
                                                                     onSettings={() => setSettings(true)} onHelp={() => setHelp(true)} />}
      {creating && <NewFilm file={creating.file} kind={creating.kind} onClose={() => setCreating(null)} onCreated={(d) => { setCreating(null); openProject(d); }} />}
      {toast && <div className="toast glass mini" role="status">{toast}</div>}
      {view.name === "film" && <FilmView key={`${view.dir}|${view.stage ?? ""}`} dir={view.dir} initialStage={view.stage} onHome={() => setView({ name: "home" })} onSettings={() => setSettings(true)} onStudio={(rd) => openProject(rd)} />}
      {view.name === "studio" && <Studio project={view.project} onHome={() => backFrom(view.project.dir)} onFilm={(st) => backFrom(view.project.dir, st)}
                                         onSettings={() => setSettings(true)} onReload={() => openProject(view.project.dir)} />}
      {settings && <Settings onClose={() => setSettings(false)} onHelp={() => { setSettings(false); setHelp(true); }} />}
      {help && <HelpSheet onClose={() => setHelp(false)} />}
      {restoring && current && <BackupsSheet dir={current.dir} onClose={() => setRestoring(false)}
                                             onRestored={() => { setRestoring(false); openProject(current.dir); say("Restored. The state before is kept as a backup."); }} />}
      {error && <div className="toast glass" role="alert"><div className="t" style={{ color: "var(--error)" }}>Could not open</div>
        <div className="s">{error}</div><div style={{ textAlign: "right", marginTop: 10 }}><button className="btn" onClick={() => setError("")}>OK</button></div></div>}
    </>
  );
}
