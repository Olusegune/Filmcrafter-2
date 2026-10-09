import { useCallback, useEffect, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, errorText, type TitleCardSpec, type TitleCardState } from "./api";
import { FontPicker } from "./FontPicker";
import * as I from "./icons";

type Back = "none" | "colour" | "picture";
const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/**
 * The intro title card: a title and subtitle that move in over the opening of the film, on black, a colour, a picture of yours, or a
 * motion backdrop made like any other shot (described here, rendered in the Studio). The card itself is drawn when you export, so it costs nothing.
 */
export function IntroCardSheet({ dir, onClose, onChanged }: { dir: string; onClose: () => void; onChanged: () => void }) {
  const [st, setSt] = useState<TitleCardState | null>(null);
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [anim, setAnim] = useState("fade");
  const [color, setColor] = useState("#ffffff");
  const [size, setSize] = useState(0.09);
  const [font, setFont] = useState("");
  const [back, setBack] = useState<Back>("none");
  const [c1, setC1] = useState("#101820");
  const [c2, setC2] = useState("#101820");
  const [picture, setPicture] = useState("");        // a file chosen now
  const [kept, setKept] = useState("");               // the picture already in the project
  const [motion, setMotion] = useState("");
  const [motionPic, setMotionPic] = useState("");
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const seq = useRef(0);

  const spec = useCallback((): TitleCardSpec => ({
    title, subtitle, anim, color, size, font: font || null,
    background: back === "colour" ? { type: "colour", color: c1, color2: c2 }
      : back === "picture" ? (picture ? { type: "picture", picture } : { type: "picture", file: kept })
        : { type: "none" },
  }), [title, subtitle, anim, color, size, font, back, c1, c2, picture, kept]);

  const apply = (r: TitleCardState) => {
    setSt(r);
    const c = r.card;
    setTitle(c?.title ?? r.title ?? "");
    if (c) {
      setSubtitle(c.subtitle ?? ""); setAnim(c.anim ?? "fade"); setColor(c.color ?? "#ffffff"); setSize(c.size ?? 0.09); setFont(c.font ?? "");
      const b = c.background;
      setBack(b?.type ?? "none");
      if (b?.type === "colour") { setC1(b.color ?? "#101820"); setC2(b.color2 ?? b.color ?? "#101820"); }
      if (b?.type === "picture") setKept(b.file ?? "");
    }
  };
  useEffect(() => { api.titleCard(dir, "state").then(apply).catch((e) => setErr(errorText(e))); }, [dir]);

  // a live preview of the settled card, redrawn a moment after each change
  useEffect(() => {
    if (!st?.span && !st?.gap) return;
    if (!title.trim()) { setPreview(""); return; }
    const mine = ++seq.current;
    const t = setTimeout(() => {
      api.titleCard<{ path: string }>(dir, "preview", spec()).then((r) => { if (mine === seq.current) { setPreview(`${dir}/${r.path}`); setErr(""); } })
        .catch((e) => { if (mine === seq.current) setErr(errorText(e)); });
    }, 350);
    return () => clearTimeout(t);
  }, [dir, st, spec, title]);

  const choose = async (set: (p: string) => void) => {
    const f = await open({ filters: [{ name: "Picture", extensions: ["png", "jpg", "jpeg", "webp"] }] });
    if (typeof f === "string") set(f);
  };
  const run = async (what: string, fn: () => Promise<void>) => {
    setBusy(what); setErr(""); setNote("");
    try { await fn(); onChanged(); } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };
  const make = () => run("make", async () => {
    apply(await api.titleCard(dir, "make", spec()));
    window.dispatchEvent(new Event("pf-overlays-changed"));
    setNote("The card is in. Export draws it; edit its parts under Export > On-screen text.");
  });
  const remove = () => run("remove", async () => {
    apply(await api.titleCard(dir, "remove"));
    window.dispatchEvent(new Event("pf-overlays-changed"));
    setNote("The card is removed.");
  });
  const addShot = () => run("shot", async () => {
    const r = await api.titleCard<{ shot: string }>(dir, "intro_shot", { prompt: motion, picture: motionPic || undefined });
    setSt(await api.titleCard(dir, "state"));
    setNote(`Added shot ${r.shot} before the first shot. Make its keyframe and video in the Studio like any other shot; the title card draws over it.`);
  });

  const span = st?.span ?? st?.gap ?? null;
  const hasRoom = !!span;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet glass intro-card" role="dialog" aria-label="Intro title card" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Intro title card</h2><div style={{ flex: 1 }} />
          <button className="icon-btn" onClick={onClose} aria-label="Close"><I.Close size={18} /></button></div>
        {!st && !err && <p className="dim">Loading…</p>}
        {st && !hasRoom && <p className="sub">There is no room before the first shot (a card needs at least a second and a half). Let the first shot start later, or add a shot there first.</p>}
        {st && hasRoom && <>
          <p className="sub">A title that moves in over {clock(span![0])} to {clock(span![1])}. It is drawn when you export, so it costs nothing.</p>
          <div className="ic-grid">
            <div className="ic-form">
              <label className="field"><span>Title</span>
                <input className="text-input" value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} /></label>
              <label className="field"><span>Subtitle (optional)</span>
                <input className="text-input" value={subtitle} maxLength={120} placeholder="A family musical" onChange={(e) => setSubtitle(e.target.value)} /></label>
              <label className="field"><span>Movement</span>
                <select className="text-input" value={anim} onChange={(e) => setAnim(e.target.value)}>
                  {st.animations.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
              <div className="ic-row">
                <label className="field"><span>Colour</span><input type="color" value={color} onChange={(e) => setColor(e.target.value)} /></label>
                <label className="field ic-grow"><span>Size</span>
                  <input type="range" min={0.04} max={0.16} step={0.005} value={size} onChange={(e) => setSize(Number(e.target.value))} /></label>
              </div>
              <FontPicker dir={dir} value={font} onChange={setFont} />
              <fieldset className="ic-back"><legend>Behind the title</legend>
                {([["none", "Black"], ["colour", "Colour"], ["picture", "My picture"]] as [Back, string][]).map(([k, n]) =>
                  <label key={k} className="ic-opt"><input type="radio" name="icback" checked={back === k} onChange={() => setBack(k)} /> {n}</label>)}
                {back === "colour" && <div className="ic-row"><label className="field"><span>Top</span><input type="color" value={c1} onChange={(e) => setC1(e.target.value)} /></label>
                  <label className="field"><span>Bottom</span><input type="color" value={c2} onChange={(e) => setC2(e.target.value)} /></label></div>}
                {back === "picture" && <div className="ic-row">
                  <button className="btn sm" onClick={() => choose(setPicture)}>{picture || kept ? "Change picture…" : "Choose a picture…"}</button>
                  <span className="dim">{(picture || kept).split(/[\\/]/).pop() || "none chosen"} · it pushes in slowly</span></div>}
              </fieldset>
            </div>
            <div className="ic-side">
              <div className="ic-preview">{preview ? <img src={api.mediaUrl(preview) + `?t=${seq.current}`} alt="Preview of the card once it has settled" /> : <span className="dim">Write a title to see it.</span>}</div>
              <p className="dim">The preview shows the card once it has settled; the movement plays on export.</p>
            </div>
          </div>

          <details className="ic-motion" open={!!motion}>
            <summary><b>Motion backdrop</b> <span className="dim">(optional, made like a shot)</span></summary>
            <p className="dim">Describe what should move behind the title (for example “golden light drifts across burgundy velvet, slow push-in”). This adds an ordinary
              shot before the first one; you render its keyframe and video in the Studio, and that costs like any other shot. A picture of yours can be its starting frame.</p>
            <label className="field"><textarea className="text-input" rows={2} maxLength={600} value={motion} onChange={(e) => setMotion(e.target.value)} placeholder="What moves behind the title" /></label>
            <div className="ic-row">
              <button className="btn sm ghost" onClick={() => choose(setMotionPic)}>{motionPic ? "Change reference…" : "Reference picture…"}</button>
              {motionPic && <span className="dim">{motionPic.split(/[\\/]/).pop()} <button className="link" onClick={() => setMotionPic("")}>clear</button></span>}
              <div style={{ flex: 1 }} />
              <button className="btn sm" disabled={!motion.trim() || !!busy || !st.gap} onClick={addShot}>{busy === "shot" ? "Adding…" : "Add the intro shot"}</button>
            </div>
            {!st.gap && <p className="dim">An intro shot is already there (or there is no room for one).</p>}
          </details>

          {err && <p className="error-text" role="alert">{err}</p>}
          {note && <p className="dim" role="status">{note}</p>}
          <div className="ic-actions">
            {st.card && <button className="btn ghost" disabled={!!busy} onClick={remove}>Remove the card</button>}
            <div style={{ flex: 1 }} />
            <button className="btn ghost" onClick={onClose}>Close</button>
            <button className="btn primary" disabled={!title.trim() || !!busy} onClick={make}>{busy === "make" ? "Saving…" : st.card ? "Update the card" : "Create the card"}</button>
          </div>
        </>}
        {!hasRoom && err && <p className="error-text" role="alert">{err}</p>}
      </div>
    </div>
  );
}
