import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type Library, type LoadedProject } from "./api";
import { openScriptSheet } from "./ScriptSheet";
import { openChoreoSheet } from "./ChoreoSheet";
import * as I from "./icons";

export type References = { characters?: string; sets?: string; cast?: Record<string, string> };

type Item = { key: string; title: string; why: string; done: boolean; need: "required" | "recommended" | "optional"; detail?: string };

/** What PULSEFRAME can use, why it helps, and what's there. Shared by New Project and the Studio. */
export function materialItems(p: { song: boolean; lyrics: boolean; script: boolean; plan: boolean; refs: References; look: boolean }): Item[] {
  const cast = Object.keys(p.refs.cast ?? {});
  return [
    { key: "song", title: "Song", need: "required", done: p.song,
      why: "The master timeline. Every cut lands on its beats." },
    { key: "lyrics", title: "Lyrics with section tags", need: "recommended", done: p.lyrics,
      why: "Gives the real song structure ([Verse], [Chorus]…), times every line and drives lip-sync." },
    { key: "cast", title: "Character images", need: "recommended", done: cast.length > 0 || !!p.refs.characters,
      detail: cast.length ? cast.join(", ") : p.refs.characters ? "Combined character sheet" : undefined,
      why: "The biggest factor for the same faces, hair and outfits in every shot. Best: one image per character." },
    { key: "sets", title: "Locations & props", need: "optional", done: !!p.refs.sets,
      why: "Keeps places, props and colours consistent between shots." },
    { key: "story", title: "Script or story", need: "optional", done: p.script || p.plan,
      why: "Scenes and shots you've written are followed exactly. Without one, PULSEFRAME proposes three directions." },
    { key: "look", title: "Look", need: "optional", done: p.look,
      why: "One art or animation style for every shot. Auto matches your character images." },
  ];
}

export const TIPS = [
  "One character per image, face and full body, on a plain background.",
  "No text, labels, logos or collages in reference images: models copy them into the video.",
  "Name characters exactly as they're named in your script or lyrics.",
  "Tag lyrics with [Intro], [Verse 1], [Chorus], [Bridge]… on their own lines.",
];

export function MaterialsChecklist({ items, compact }: { items: Item[]; compact?: boolean }) {
  return (
    <ul className={`materials ${compact ? "compact" : ""}`}>
      {items.map((m) => (
        <li key={m.key} className={m.done ? "done" : ""}>
          <span className="mat-state">{m.done ? <I.Check size={14} /> : <I.Circle size={14} />}</span>
          <span className="mat-body">
            <span className="mat-title">{m.title} <span className={`mat-need ${m.need}`}>{m.need}</span></span>
            {m.detail && <span className="mat-detail">{m.detail}</span>}
            {!compact && <span className="mat-why">{m.why}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}


/** Studio: the checklist, read from the reference library (the single source of references). */
export function MaterialsPanel({ project, hasPlan, onChanged, onOpenLibrary }: {
  project: LoadedProject; hasPlan: boolean; onChanged: () => void; onOpenLibrary?: () => void;
}) {
  const [lib, setLib] = useState<Library | null>(null);
  const [thumbs, setThumbs] = useState<Record<string, string | null>>({});
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const load = () => api.library<Library>(project.dir, "library").then((l) => {
    setLib(l);
    api.thumbs(project.dir, l.items.map((i) => i.files[0]).filter(Boolean)).then(setThumbs).catch(() => {});
  }).catch(() => {});
  useEffect(() => {
    load();
    window.addEventListener("pf-library-changed", load);
    return () => window.removeEventListener("pf-library-changed", load);
  }, [project.dir]); // eslint-disable-line react-hooks/exhaustive-deps
  const chars = (lib?.items ?? []).filter((i) => i.kind === "character");
  const places = (lib?.items ?? []).filter((i) => i.kind === "set" || i.kind === "prop");
  const refs: References = {
    cast: Object.fromEntries(chars.filter((c) => !c.sheet).map((c) => [c.name, c.files[0]])),
    characters: chars.find((c) => c.sheet)?.files[0], sets: places[0]?.files[0],
  };
  const look = project.project.look;
  const items = materialItems({ song: !!project.song_path, lyrics: !!project.project.lyrics, script: !!project.project.script,
    plan: hasPlan, refs, look: typeof look === "object" ? look.style !== "auto" : !!look });
  const missing = items.filter((m) => !m.done && m.need !== "optional").length;

  const addCharacter = async () => {
    setError("");
    const f = await open({ filters: [{ name: "Image", extensions: ["png", "jpg", "jpeg", "webp"] }] });
    if (typeof f !== "string") return;
    try {
      const r = await api.importReference(project.dir, f);
      await api.library(project.dir, "upsert", { kind: "character", name: name.trim(), files: [r.ref.replace(/^project:/, "")] });
      setName(""); load(); onChanged();
    } catch (e) { setError(errorText(e)); }
  };
  const shown = (lib?.items ?? []).filter((i) => i.kind !== "audio" && i.files[0]);

  return (
    <div className="insp-section">
      <h4>Materials {missing ? <span className="mat-need recommended">{missing} to add</span> : null}</h4>
      <MaterialsChecklist items={items} compact />
      {shown.length > 0 && <div className="ref-grid">
        {shown.slice(0, 9).map((i) => (
          <div key={i.id} className="ref-tile" title={`${i.name} · ${i.kind}`}>
            {thumbs[i.files[0]] ? <img src={api.mediaUrl(`${project.dir}/${thumbs[i.files[0]]}`)} alt={i.name} /> : <span className="dim">…</span>}
            <span>{i.name}</span>
          </div>
        ))}
      </div>}
      {shown.length > 9 && <div className="dim" style={{ fontSize: 12 }}>+{shown.length - 9} more</div>}
      <div className="key-row" style={{ marginTop: 8 }}>
        <input className="text-input" placeholder="Character name" aria-label="Character name" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn small" onClick={addCharacter} disabled={!name.trim()}>Add image…</button>
      </div>
      <div className="wiz-row" style={{ marginTop: 6, gap: 6 }}>
        {onOpenLibrary && <button className="btn ghost small" onClick={onOpenLibrary}>Open the reference library…</button>}
        <button className="btn ghost small" onClick={openScriptSheet}>{project.project.script ? "Replace the script…" : "Add a script…"}</button>
        <button className="btn ghost small" onClick={openChoreoSheet}>Choreography…</button>
      </div>
      <details className="mat-tips"><summary>Tips for best results</summary><ul>{TIPS.map((t) => <li key={t}>{t}</li>)}</ul></details>
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}
