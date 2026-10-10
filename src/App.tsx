import { useCallback, useEffect, useState } from "react";
import { open as openDialog, save as saveDialog } from "@tauri-apps/plugin-dialog";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { api, errorText, type LoadedProject } from "./api";
import { Home } from "./Home";
import { Wizard } from "./Wizard";
import { Analysis } from "./Analysis";
import { Studio } from "./Studio";
import { Settings } from "./Settings";
import { HelpSheet } from "./Help";
import { ShowView, showDirOf } from "./ShowView";
import { BackupsSheet } from "./Backups";
import { ProducerImport, isProducerPackage } from "./ProducerImport";
import { EngineSetup } from "./EngineSetup";
import { Produce } from "./Produce";
import { FilmView } from "./FilmView";
import { NewFilm } from "./NewFilm";
import type { StoryKind } from "./api";
import "./styles.css";
import "./motion.css";

const PRODUCE_KEY = (dir: string) => `pf-produce:${dir}`;
const wantsProduce = (dir: string) => { try { return localStorage.getItem(PRODUCE_KEY(dir)) === "1"; } catch { return false; } };
const setProduce = (dir: string, on: boolean) => { try { if (on) localStorage.setItem(PRODUCE_KEY(dir), "1"); else localStorage.removeItem(PRODUCE_KEY(dir)); } catch { /* a convenience only */ } };

type View =
  | { name: "home" }
  | { name: "analysis"; dir: string; title: string }
  | { name: "wizard"; dir: string | null; file?: string | null; produce?: boolean }
  | { name: "produce"; project: LoadedProject }
  | { name: "studio"; project: LoadedProject }
  | { name: "show"; dir: string }
  | { name: "film"; dir: string };

export default function App() {
  const [view, setView] = useState<View>({ name: "home" });
  const [creating, setCreating] = useState<{ file?: string; kind?: StoryKind } | null>(null);       // the New film sheet, from Home or the File menu
  const [settings, setSettings] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [help, setHelp] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [importPath, setImportPath] = useState<string | null>(null);
  const [engine, setEngine] = useState<{ ready: boolean; gpu: boolean } | null>(null);
  useEffect(() => { api.engineStatus().then(setEngine).catch(() => setEngine({ ready: true, gpu: false })); }, []);
  const say = useCallback((t: string) => { setToast(t); setTimeout(() => setToast(""), 1800); }, []);

  // First paint is done: swap the splash window for this one.
  useEffect(() => { api.appReady().catch(() => {}); }, []);

  const openProject = useCallback(async (dir: string) => {
    setError("");
    if (isProducerPackage(dir)) { setImportPath(dir); setView({ name: "home" }); return; }   // Producer package: review, then a project
    try {
      if (await api.isFilm(dir)) { setView({ name: "film", dir: dir.replace(/[\/][^\/]+\.filmcrafter$/i, "") }); return; }
      if (await api.isShow(dir)) { setView({ name: "show", dir: dir.replace(/[\\/]show\.json$/i, "") }); return; }
      if (dir.toLowerCase().endsWith(".pulse")) {   // one-file project: unpack it into the projects folder first
        setToast("Unpacking the project…");
        dir = await api.openPulse(dir);
        setToast("");
      }
      const p = await api.loadProject(dir);
      // Setup not finished: resume the wizard where it was left (never forced on finished projects).
      if (p.project.onboarding && p.project.onboarding.stage !== "done") { setView({ name: "wizard", dir: p.dir }); return; }
      // A project that was never analysed (or was interrupted) resumes at the listening step.
      if (!p.song_map || p.project.state === "new" || p.project.state === "analyzing") setView({ name: "analysis", dir, title: p.project.title });
      else if (wantsProduce(p.dir)) setView({ name: "produce", project: p });   // chosen in the wizard (or from the Studio): plan the production first
      else setView({ name: "studio", project: p });
    } catch (e) { setError(errorText(e)); }
  }, []);

  // A project double-clicked in Explorer: at launch, or while the app is already open.
  useEffect(() => {
    api.launchPath().then((p) => { if (p) openProject(p); }).catch(() => {});
    const un = api.onOpenPath((p) => openProject(p));
    return () => { un.then((f) => f()); };
  }, [openProject]);

  // An item of a show goes back to its show; anything else goes Home.
  const backFrom = useCallback(async (dir: string) => {
    const show = showDirOf(dir);
    setView(show && (await api.isShow(show).catch(() => false)) ? { name: "show", dir: show } : { name: "home" });
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
      {view.name === "analysis" && <Analysis dir={view.dir} title={view.title}
                                             onDone={() => openProject(view.dir)} onBack={() => backFrom(view.dir)} />}
      {view.name === "film" && <FilmView key={view.dir} dir={view.dir} onHome={() => setView({ name: "home" })} onSettings={() => setSettings(true)} />}
      {view.name === "show" && <ShowView key={view.dir} dir={view.dir} onOpenItem={openProject} onHome={() => setView({ name: "home" })} />}
      {view.name === "studio" && <Studio project={view.project} onHome={() => backFrom(view.project.dir)}
                                         onSettings={() => setSettings(true)} onReload={() => openProject(view.project.dir)}
                                         onProduce={() => { setProduce(view.project.dir, true); setView({ name: "produce", project: view.project }); }} />}
      {view.name === "produce" && <Produce key={view.project.dir} project={view.project} onHome={() => { setProduce(view.project.dir, false); backFrom(view.project.dir); }}
                                           onSettings={() => setSettings(true)}
                                           onStudio={(makePictures) => {
                                             const dir = view.project.dir;
                                             setProduce(dir, false);
                                             try { if (makePictures) localStorage.setItem(`pf-open-refgen:${dir}`, "1"); } catch { /* optional */ }
                                             openProject(dir);
                                           }} />}
      {view.name === "wizard" && <Wizard key={view.dir ?? "new"} initialDir={view.dir} initialFile={view.file} produce={view.produce}
                                         onExit={() => setView({ name: "home" })}
                                         onProduce={(dir) => { setProduce(dir, true); openProject(dir); }}
                                         onFinish={(dir, director) => {
                                           try {
                                             localStorage.setItem(`pf-open-director:${dir}`, director ? "1" : "0");
                                             if (!director) localStorage.setItem(`pf-autopilot:${dir}`, "1");   // "Direct my video" = autopilot
                                           } catch { /* optional */ }
                                           openProject(dir);
                                         }} />}
      {settings && <Settings onClose={() => setSettings(false)} onHelp={() => { setSettings(false); setHelp(true); }} />}
      {help && <HelpSheet onClose={() => setHelp(false)} />}
      {importPath && <ProducerImport initial={importPath} onClose={() => setImportPath(null)} onOpen={(d) => { setImportPath(null); openProject(d); }} />}
      {restoring && current && <BackupsSheet dir={current.dir} onClose={() => setRestoring(false)}
                                             onRestored={() => { setRestoring(false); openProject(current.dir); say("Restored. The state before is kept as a backup."); }} />}
      {error && <div className="toast glass" role="alert"><div className="t" style={{ color: "var(--error)" }}>Could not open</div>
        <div className="s">{error}</div><div style={{ textAlign: "right", marginTop: 10 }}><button className="btn" onClick={() => setError("")}>OK</button></div></div>}
    </>
  );
}
