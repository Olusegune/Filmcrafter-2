import { useCallback, useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type BibleView, type RefItem, type RefKind } from "./api";

const IMG = /\.(png|jpe?g|webp)$/i;
const PICTURES = [{ name: "Pictures", extensions: ["png", "jpg", "jpeg", "webp"] }];
const ANY = [{ name: "Images, video, audio", extensions: ["png", "jpg", "jpeg", "webp", "mp4", "mov", "webm", "m4v", "mp3", "wav", "m4a"] }];
const BIBLE_KIND: Record<string, "character" | "environment" | "prop"> = { character: "character", set: "environment", prop: "prop" };
const DETAIL_FIELD = { character: "physical", environment: "description", prop: "notes" } as const;

/** Whether a reference was made from Cast & World (so the Bible is its source and the edit belongs there: a copy kept here would be rebuilt from the Bible). */
export const bibleBacked = (it: RefItem, filmDir?: string) => !!filmDir && /^fc-(?!sm-|board-)/.test(it.id) && it.kind in BIBLE_KIND;

/**
 * Change a reference: its name and notes, and each of its files (replace one, remove one, add more). A reference that comes from Cast & World is changed in the Bible, so the change lasts;
 * any other is changed in the library. Nothing is deleted: a file that is taken off stays in the project folder.
 */
export function RefEditor({ dir, filmDir, item, kinds, onDone, onChanged }: { dir: string; filmDir?: string; item: RefItem; kinds: { id: RefKind; label: string }[]; onDone: () => void; onChanged: () => void }) {
  const fromBible = bibleBacked(item, filmDir);
  const bk = BIBLE_KIND[item.kind];
  const [name, setName] = useState(item.name);
  const [notes, setNotes] = useState(item.notes ?? "");
  const [kind, setKind] = useState<RefKind>(item.kind);
  const [files, setFiles] = useState<string[]>(item.files);                 // library mode
  const [entry, setEntry] = useState<BibleView["characters"][number] | null>(null);   // Bible mode
  const [mediaKinds, setMediaKinds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const loadEntry = useCallback(async () => {
    if (!fromBible || !filmDir) return;
    const b = await api.bible("get", filmDir);
    const list = (bk === "character" ? b.characters : bk === "environment" ? b.environments : b.props) as unknown as BibleView["characters"];
    const e = list.find((x) => x.id === item.id.slice(3)) ?? null;
    setEntry(e);
    setMediaKinds(b.media_kinds);
    if (e) { setName((n) => (n === item.name ? e.name : n)); setNotes((n) => (n === (item.notes ?? "") ? String((e as unknown as Record<string, unknown>)[DETAIL_FIELD[bk]] ?? "") : n)); }
  }, [fromBible, filmDir, bk, item]);
  useEffect(() => { loadEntry().catch((e) => setErr(errorText(e))); }, [loadEntry]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr("");
    try { await fn(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };
  const afterBible = async () => { if (filmDir) await api.make("sync", filmDir).catch(() => {}); await loadEntry(); onChanged(); };
  const bibleOp = (action: "replace_media" | "update_media" | "remove_media" | "add_media", data: Record<string, unknown>) =>
    run(async () => { await api.bible(action, filmDir!, { kind: bk, id: item.id.slice(3), ...data }); await afterBible(); });

  const replaceBible = async (path: string) => { const f = await open({ multiple: false, filters: PICTURES }); if (typeof f === "string") await bibleOp("replace_media", { path, file: f }); };
  const addBible = async () => {
    const f = await open({ multiple: true, filters: PICTURES });
    const list = typeof f === "string" ? [f] : Array.isArray(f) ? f : [];
    for (const file of list) await bibleOp("add_media", { file, label: "Reference", media_kind: (entry?.media.length ?? 0) || list.indexOf(file) ? "reference" : "master" });
  };
  const importOne = async (p: string) => (await api.importReference(dir, p)).ref.replace(/^project:/, "");
  const replaceLib = async (i: number) => {
    const f = await open({ multiple: false, filters: ANY });
    if (typeof f !== "string") return;
    await run(async () => { const rel = await importOne(f); setFiles((l) => l.map((x, k) => (k === i ? rel : x))); });
  };
  const addLib = async () => {
    const f = await open({ multiple: true, filters: ANY });
    const list = typeof f === "string" ? [f] : Array.isArray(f) ? f : [];
    await run(async () => { const got: string[] = []; for (const p of list) got.push(await importOne(p)); setFiles((l) => [...l, ...got]); });
  };
  const save = () => run(async () => {
    if (fromBible && filmDir && entry) {
      await api.bible("upsert", filmDir, { kind: bk, item: { id: entry.id, name, [DETAIL_FIELD[bk]]: notes } });
      await afterBible();
    } else {
      await api.library(dir, "upsert", { id: item.id, kind, name, files, notes });
      onChanged();
    }
    onDone();
  });

  const pictureRow = (src: string, label: string, buttons: React.ReactNode, extra?: React.ReactNode) => (
    <li className="re-file" key={src}>
      {IMG.test(src) ? <img className="re-thumb" src={api.mediaUrl(src)} alt="" /> : <span className="re-thumb re-nothumb" aria-hidden="true">{/\.(mp3|wav|m4a)$/i.test(src) ? "♪" : "▶"}</span>}
      <div className="re-meta"><span className="num">{label}</span>{extra}</div>
      <div className="re-btns">{buttons}</div>
    </li>);

  return (
    <div className="ref-editor" role="group" aria-label={`Edit ${item.name}`}>
      {fromBible && <p className="why">This one comes from <b>Cast &amp; World</b>, so your changes are made there and last. Pictures you replace or take off stay in the project folder.</p>}
      <label className="field"><span>Name</span><input className="text-input" value={name} onChange={(e) => setName(e.target.value)} disabled={busy} /></label>
      {!fromBible && <label className="field"><span>Kind</span><select className="text-input" value={kind} onChange={(e) => setKind(e.target.value as RefKind)} disabled={busy}>{kinds.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}</select></label>}
      <label className="field"><span>{fromBible ? (bk === "character" ? "What she, he or it looks like" : bk === "environment" ? "What the place is" : "Notes") : "Notes (sent with the reference)"}</span>
        <textarea className="text-input" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} disabled={busy} /></label>
      <h4>{fromBible ? "Pictures" : "Files"}</h4>
      <ul className="re-files">
        {fromBible && entry && entry.media.map((m) => pictureRow(`${filmDir}/${m.path}`, m.path.split("/").pop() ?? m.path, <>
          <button className="btn ghost sm" disabled={busy} onClick={() => void replaceBible(m.path)} title="Choose another picture to take its place">Replace…</button>
          <button className="btn ghost sm" disabled={busy} onClick={() => void bibleOp("remove_media", { path: m.path })} title="Take it off (the file stays in the project folder)">Remove</button></>,
          <select className="text-input re-kind" aria-label="What this picture shows" value={m.kind} disabled={busy} onChange={(e) => void bibleOp("update_media", { path: m.path, media_kind: e.target.value })}>
            {(mediaKinds.length ? mediaKinds : [m.kind]).map((k) => <option key={k} value={k}>{k === "master" ? "Master sheet" : k}</option>)}</select>))}
        {!fromBible && files.map((f, i) => pictureRow(`${dir}/${f}`, f.split("/").pop() ?? f, <>
          <button className="btn ghost sm" disabled={busy} onClick={() => void replaceLib(i)} title="Choose another file to take its place">Replace…</button>
          <button className="btn ghost sm" disabled={busy} onClick={() => setFiles((l) => l.filter((_, k) => k !== i))} title="Take it off (the file stays in the project folder)">Remove</button></>))}
      </ul>
      {((fromBible && entry && entry.media.length === 0) || (!fromBible && files.length === 0)) && <p className="dim">No pictures yet.</p>}
      <button className="btn ghost sm" disabled={busy} onClick={() => void (fromBible ? addBible() : addLib())}>+ Add pictures…</button>
      {err && <p className="error-text" role="alert">{err}</p>}
      <div className="sheet-actions"><button className="btn ghost" disabled={busy} onClick={onDone}>{fromBible ? "Close" : "Cancel"}</button>
        <button className="btn primary" disabled={busy || !name.trim()} onClick={() => void save()}>{busy ? "Working…" : fromBible ? "Save changes" : "Save"}</button></div>
    </div>
  );
}
