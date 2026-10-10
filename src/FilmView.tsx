import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorText, type FilmAdvice, type FilmScene, type FilmStatus, type StoryKind } from "./api";
import * as I from "./icons";
import { ask } from "./ask";
import { CastWorld } from "./CastWorld";
import { ShotLab } from "./ShotLab";
import { LADDER, ladderAt, minutes, openAdvice, sceneLine, STAGES, STORY_KINDS, storyState } from "./storyView";

/**
 * A film's story: the script as written, the scenes found in it, and what was noticed. The script is never edited here; a change is a new version,
 * and a version can be locked so the rest of the film is made from one fixed story.
 */
export function FilmView({ dir, onHome, onSettings }: { dir: string; onHome: () => void; onSettings: () => void }) {
  const [f, setF] = useState<FilmStatus | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [writing, setWriting] = useState(false);
  const [scene, setScene] = useState<number | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [stage, setStage] = useState<"story" | "cast" | "shots">("story");
  const reader = useRef<HTMLDivElement>(null);

  const load = useCallback((version?: number) =>
    api.film<FilmStatus>("status", dir, version ? { version } : {}).then(setF).catch((e) => setErr(errorText(e))), [dir]);
  useEffect(() => { void load(); }, [load]);

  const run = async (what: string, fn: () => Promise<FilmStatus>) => {
    setBusy(what); setErr("");
    try { setF(await fn()); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };

  const lines = useMemo(() => (f ? f.text.split("\n") : []), [f]);
  const headingAt = useMemo(() => new Map((f?.found.scenes ?? []).filter((s) => !s.implied).map((s) => [sceneLine(s), s])), [f]);
  const goTo = (s: FilmScene) => {
    setScene(s.number);
    reader.current?.querySelector(`[data-line="${sceneLine(s)}"]`)?.scrollIntoView({ block: "start", behavior: "smooth" });
  };

  if (!f) return <div className="film"><div className="film-load dim">{err || "Opening the film…"}</div></div>;
  const st = f.story;
  const isScreenplay = f.kind === "screenplay";
  const advice = openAdvice(f.advice);
  const setAside = f.advice.filter((a) => a.status !== "open");
  const shownAdvice = showAll ? advice : advice.slice(0, 3);
  const mark = (a: FilmAdvice, state: "noted" | "dismissed" | "open") => run("rec", () => api.film<FilmStatus>("rec_set", dir, { version: f.version, id: a.id, state }));

  const lock = async () => {
    if (!await ask(`Lock version ${f.version} as the story?\n\nThe rest of the film will be made from this exact version. It will never be changed: if the story changes later you write a new version and lock that one.`, { ok: "Lock the story" })) return;
    await run("lock", () => api.film<FilmStatus>("lock", dir, { version: f.version }));
  };

  return (
    <div className="film">
      <header className="film-top">
        <button className="btn ghost sm" onClick={onHome}>‹ Home</button>
        <h1 className="film-title" title={f.title}>{f.title}</h1>
        <ol className="film-stages" aria-label="The stages of making a film">
          {STAGES.map((s) => <li key={s.id} className={s.id === stage ? "on" : s.ready ? "ready" : ""} title={s.ready ? undefined : "Coming in a later update"} aria-current={s.id === stage ? "step" : undefined}>
            {s.ready ? <button onClick={() => setStage(s.id as "story" | "cast" | "shots")}>{s.label}</button> : s.label}</li>)}
        </ol>
        <button className="icon-btn" onClick={onSettings} title="Settings" aria-label="Settings"><I.Gear /></button>
      </header>

      {stage === "cast" ? <CastWorld key={dir} dir={dir} /> : stage === "shots" ? <ShotLab key={dir} dir={dir} /> : <div className="film-body">
        <nav className="film-scenes" aria-label="Scenes">
          <h2>Scenes <span className="dim">{f.found.scenes.filter((s) => !s.implied).length || ""}</span></h2>
          {f.found.scenes.length === 0 && <p className="dim">{isScreenplay ? "No scenes found yet." : "Scenes appear once the story is a screenplay or an outline."}</p>}
          <ol>
            {f.found.scenes.map((s) => (
              <li key={s.number}>
                <button className={scene === s.number ? "on" : ""} onClick={() => goTo(s)} disabled={s.implied && f.found.scenes.length === 1}>
                  <span className="n num">{s.number}</span>
                  <span className="h">{s.heading || "Scene"}</span>
                  {s.seconds > 0 && <span className="dim t">{Math.round(s.seconds)}s</span>}
                </button>
              </li>))}
          </ol>
        </nav>

        <main className="film-main">
          <div className="film-readhead">
            <label className="film-version"><span className="dim">Version</span>
              <select className="text-input" value={f.version} onChange={(e) => void load(Number(e.target.value))} aria-label="Which version of the story to read">
                {f.versions.map((v) => <option key={v.version} value={v.version}>{`${v.version}${v.locked ? " · locked" : ""} · ${v.note || "—"}`}</option>)}</select></label>
            {f.version !== st.current && <button className="link" onClick={() => run("cur", () => api.film<FilmStatus>("set_current", dir, { version: f.version }))}>Make this the current version</button>}
            <div style={{ flex: 1 }} />
            <span className="dim">{f.found.words.toLocaleString()} words{f.found.seconds > 0 ? ` · ${minutes(f.found.seconds)}` : ""}</span>
          </div>
          <div className={`film-script ${isScreenplay ? "sp" : "prose"}`} ref={reader} tabIndex={0} aria-label="The story, as written">
            {lines.map((l, i) => {
              const h = headingAt.get(i);
              return <div key={i} data-line={i} className={`ln ${h ? "heading" : ""} ${h && h.number === scene ? "cur" : ""}`}>{l || " "}</div>;
            })}
          </div>
        </main>

        <aside className="film-side" aria-label="The story">
          <section className={`film-state ${st.locked !== null ? "locked" : ""}`}>
            <h2>{st.locked !== null ? <><I.Check size={15} /> Story locked</> : "The story"}</h2>
            <p className="film-state-text">{storyState({ kind: f.kind, locked: st.locked, as_is: st.as_is, current: st.current })}</p>
            {isScreenplay ? <div className="film-actions">
              {st.as_is !== f.version && st.locked === null && <button className="btn" disabled={!!busy} onClick={() => run("asis", () => api.film<FilmStatus>("as_is", dir, { version: f.version }))}
                title="Set every suggestion aside. The script stays exactly as it is.">Use story as it is</button>}
              {!f.locked_here && <button className="btn primary" disabled={!!busy} onClick={lock}>Lock this version</button>}
            </div> : <Ladder kind={f.kind} onWrite={() => setWriting(true)} />}
          </section>

          {advice.length > 0 && <section className="film-advice">
            <h2>What I noticed <span className="dim">{advice.length}</span></h2>
            <p className="dim">Suggestions only. Nothing changes your story.</p>
            <ul>
              {shownAdvice.map((a) => (
                <li key={a.id}>
                  <span className="topic">{a.topic}</span>
                  <p>{a.text}</p>
                  <div className="row">
                    <button className="link" onClick={() => mark(a, "noted")}>I'll deal with it</button>
                    <button className="link" onClick={() => mark(a, "dismissed")}>Dismiss</button>
                    {a.scene && <button className="link" onClick={() => { const s = f.found.scenes.find((x) => x.number === a.scene); if (s) goTo(s); }}>Go to scene {a.scene}</button>}
                  </div>
                </li>))}
            </ul>
            {advice.length > 3 && <button className="link" onClick={() => setShowAll((v) => !v)}>{showAll ? "Show fewer" : `Show all ${advice.length}`}</button>}
          </section>}
          {setAside.length > 0 && <details className="film-aside"><summary>{setAside.length} set aside</summary>
            <ul>{setAside.map((a) => <li key={a.id}><span className="dim">{a.status === "noted" ? "To deal with" : "Dismissed"}:</span> {a.text} <button className="link" onClick={() => mark(a, "open")}>Bring back</button></li>)}</ul></details>}

          {(f.found.characters.length > 0 || f.found.locations.length > 0) && <section className="film-cast">
            {f.found.characters.length > 0 && <><h2>Characters <span className="dim">{f.found.characters.length}</span></h2>
              <div className="chips">{f.found.characters.map((c) => <span key={c.name} className="chip" title={`In ${c.scene_count} scene${c.scene_count === 1 ? "" : "s"}`}>{c.name}<i>{c.scene_count}</i></span>)}</div></>}
            {f.found.locations.length > 0 && <><h2>Places <span className="dim">{f.found.locations.length}</span></h2>
              <div className="chips">{f.found.locations.map((c) => <span key={c.name} className="chip" title={`In ${c.scenes.length} scene${c.scenes.length === 1 ? "" : "s"}`}>{c.name}<i>{c.scenes.length}</i></span>)}</div></>}
          </section>}

          <section className="film-versions">
            <h2>Versions <span className="dim">{f.versions.length}</span></h2>
            <ul>
              {[...f.versions].reverse().map((v) => (
                <li key={v.version} className={v.version === f.version ? "on" : ""}>
                  <button className="link" onClick={() => void load(v.version)}>Version {v.version}</button>
                  {v.locked && <span className="badge">locked</span>}{v.version === st.current && <span className="badge dim">current</span>}
                  <span className="dim">{v.note || v.origin} · {v.words.toLocaleString()} words</span>
                </li>))}
            </ul>
            <button className="btn ghost sm" onClick={() => setWriting(true)}>Write a new version…</button>
          </section>

          <section className="film-next"><h3>Next</h3>
            <p className="dim">Next: Cast &amp; World, then Shots (above). The storyboard and making the film arrive in later updates. Lock the story when it is final.</p></section>
          {err && <p className="error-text" role="alert">{err}</p>}
        </aside>
      </div>}
      {writing && <NewVersion from={f} onClose={() => setWriting(false)} onSaved={(s) => { setF(s); setWriting(false); setScene(null); }} dir={dir} />}
    </div>
  );
}

/** Where a story that is not a screenplay yet stands on the way to one. */
function Ladder({ kind, onWrite }: { kind: StoryKind; onWrite: () => void }) {
  const at = ladderAt(kind === "idea" ? "logline" : kind);
  return (
    <div className="film-ladder">
      <ol aria-label="From a spark to a screenplay">{LADDER.map((r, i) => <li key={r} className={i < at ? "done" : i === at ? "now" : ""} aria-current={i === at ? "step" : undefined}>{r}</li>)}</ol>
      <p className="dim">Write or paste the next step as a new version. When the screenplay is written, lock it.</p>
      <button className="btn" onClick={onWrite}>Add the next step…</button>
    </div>
  );
}

/** A change to the story is a new version; this is where it is written. */
function NewVersion({ dir, from, onClose, onSaved }: { dir: string; from: FilmStatus; onClose: () => void; onSaved: (s: FilmStatus) => void }) {
  const [text, setText] = useState(from.text);
  const [note, setNote] = useState("");
  const [kind, setKind] = useState<StoryKind>(from.kind);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const save = async () => {
    setBusy(true); setErr("");
    try { onSaved(await api.film<FilmStatus>("add_version", dir, { text, note: note.trim(), kind })); } catch (e) { setErr(errorText(e)); setBusy(false); }
  };
  return (
    <div className="overlay" onClick={busy ? undefined : onClose}>
      <div className="sheet glass nf-sheet" role="dialog" aria-label="New version" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>New version</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="sub">The version you started from stays exactly as it is. This becomes version {from.versions.length + 1}.</p>
        <div className="nf-kind-row"><span className="dim">This is</span>
          <select className="text-input" value={kind} onChange={(e) => setKind(e.target.value as StoryKind)} aria-label="What kind of story this is">
            {STORY_KINDS.map((k) => <option key={k.id} value={k.id}>{k.label.toLowerCase()}</option>)}</select></div>
        <label className="field"><span>What changed (optional)</span><input className="text-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Sharper ending" maxLength={300} /></label>
        <label className="field"><span>The story</span><textarea className="text-input nf-text" rows={14} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} /></label>
        {err && <p className="error-text" role="alert">{err}</p>}
        <div className="sheet-actions"><button className="btn ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn primary" onClick={save} disabled={busy || !text.trim() || text === from.text && kind === from.kind}>{busy ? "Saving…" : "Save as a new version"}</button></div>
      </div>
    </div>
  );
}
