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
import { filmDirOfDoc, filmDirOfRender, isProducerPackage, isRenderDir } from "./filmPaths";
import { NewFilm } from "./NewFilm";
import type { StoryKind } from "./api";
import type { StudioSheet } from "./guideSteps";
import "./styles.css";
import "./motion.css";

type View =
  | { name: "home" }
  | { name: "studio"; project: LoadedProject }
  | { name: "film"; dir: string; stage?: string };

/** FilmCrafter makes films. A music video (or anything else that is not a film) belongs in PULSEFRAME. */
const LEGACY = "This is not a FilmCrafter film. Music-video projects belong in PULSEFRAME: open it there.";

export default function App() {
  const [view, setView] = useState<View>({ name: "home" });
  const [creating, setCreating] = useState<{ file?: string; kind?: StoryKind; preset?: string } | null>(null);       // the New film sheet, from Home or the File menu
  const [settings, setSettings] = useState(false);
  const [studioSheet, setStudioSheet] = useState<StudioSheet | null>(null);          // a Studio sheet the guide asked to have open on arrival
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [help, setHelp] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [engine, setEngine] = useState<{ ready: boolean; gpu: boolean } | null>(null);
  useEffect(() => { api.engineStatus().then(setEngine).catch(() => setEngine({ ready: true, gpu: false })); }, []);
  const say = useCallback((t: string) => { setToast(t); setTimeout(() => setToast(""), 1800); }, []);

  // First paint is done: swap the splash window for this one.
  useEffect(() => { api.appReady().catch(() => {}); }, []);

  const openProject = useCallback(async (dir: string): Promise<void> => {
    setError("");
    if (isProducerPackage(dir)) { setError(LEGACY); return; }
    try {
      if (/\.(filmpack|pulse)$/i.test(dir)) {   // a film in one file (.filmpack, or .pulse from an earlier version): unpack it into the projects folder first, then open what came out
        setToast("Unpacking the project…");
        dir = await api.openPulse(dir);
        setToast("");
      }
      if (await api.isFilm(dir)) { setView({ name: "film", dir: filmDirOfDoc(dir) }); return; }
      const p = await api.loadProject(dir);
      if ((p.project as { film?: boolean }).film) { setView({ name: "studio", project: p }); return; }     // a film's render project saved on its own (File, Save as One File) opens in the Studio
      setError(LEGACY);                              // FilmCrafter opens films; a music-video project belongs in PULSEFRAME
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
    const f = await openDialog({ filters: [{ name: "FilmCrafter film", extensions: ["filmcrafter", "filmpack", "pulse"] }] });
    if (typeof f === "string") openProject(f);
  }, [openProject]);

  // Standard File menu (native menu bar + shortcuts). It works from the film screens as well as from the Studio.
  const current = view.name === "studio" ? view.project : null;
  const filmDir = view.name === "film" ? view.dir : current && isRenderDir(current.dir) ? filmDirOfRender(current.dir) : null;       // the film the person is working on, wherever they are in it
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
            else if (filmDir) say("Your film is saved as you work.");
            else say("Open a film to save it.");
            break;
          case "save_pulse": {
            if (!filmDir) { say("Open a film first."); break; }
            const name = filmDir.split(/[\/]/).filter(Boolean).pop() ?? "Film";
            const dest = await saveDialog({ defaultPath: `${name}.filmpack`, filters: [{ name: "FilmCrafter film in one file", extensions: ["filmpack"] }] });
            if (dest) {
              setToast("Packing the film into one file…");
              const r = await api.packFilm(filmDir, dest);
              setToast("");
              say(`Saved ${r.files} files as one film file (${(r.bytes / 1e6).toFixed(0)} MB)`);
              await revealItemInDir(r.path).catch(() => {});
            }
            break;
          }
          case "backups": if (current || filmDir) setRestoring(true); else say("Open a film first."); break;
          case "reveal": if (current) await revealItemInDir(current.doc ?? current.dir); else if (filmDir) await revealItemInDir(filmDir); break;
          case "close": setView({ name: "home" }); break;
          default: window.dispatchEvent(new CustomEvent("pf-menu", { detail: id })); // screen-level items: Export, Simple and Director mode, the inspector, the Director's command
        }
      } catch (e) { setToast(""); setError(errorText(e)); }
    });
    return () => { un.then((f) => f()); };
  }, [current, filmDir, chooseProject, openProject, say]);

  return (
    <>
      {engine && !engine.ready && <EngineSetup gpu={engine.gpu} onReady={() => setEngine({ ...engine, ready: true })} />}
      {(!engine || engine.ready) && view.name === "home" && <Home onNewFilm={(o) => setCreating(o ?? {})} onOpen={openProject} onChooseProject={chooseProject}
                                                                     onSettings={() => setSettings(true)} onHelp={() => setHelp(true)} />}
      {creating && <NewFilm file={creating.file} kind={creating.kind} preset={creating.preset} onClose={() => setCreating(null)} onCreated={(d) => { setCreating(null); openProject(d); }} />}
      {toast && <div className="toast glass mini" role="status">{toast}</div>}
      {view.name === "film" && <FilmView key={`${view.dir}|${view.stage ?? ""}`} dir={view.dir} initialStage={view.stage} onHome={() => setView({ name: "home" })} onSettings={() => setSettings(true)} onStudio={(rd, sheet) => { setStudioSheet(sheet ?? null); void openProject(rd); }} />}
      {view.name === "studio" && <Studio project={view.project} startSheet={studioSheet} onStartSheetShown={() => setStudioSheet(null)} onHome={() => backFrom(view.project.dir)} onFilm={(st) => backFrom(view.project.dir, st)}
                                         onSettings={() => setSettings(true)} onReload={() => openProject(view.project.dir)} />}
      {settings && <Settings onClose={() => setSettings(false)} onHelp={() => { setSettings(false); setHelp(true); }} />}
      {help && <HelpSheet onClose={() => setHelp(false)} />}
      {restoring && (current || filmDir) && <BackupsSheet dir={current?.dir ?? null} filmDir={filmDir} onClose={() => setRestoring(false)}
                                             onRestored={() => { setRestoring(false); if (current) openProject(current.dir); else if (filmDir) window.location.reload(); say("Restored. The state before is kept as a backup."); }} />}
      {error && <div className="toast glass" role="alert"><div className="t" style={{ color: "var(--error)" }}>Could not open</div>
        <div className="s">{error}</div><div style={{ textAlign: "right", marginTop: 10 }}><button className="btn" onClick={() => setError("")}>OK</button></div></div>}
    </>
  );
}
