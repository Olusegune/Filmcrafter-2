import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { api, AUTO_IMAGE_MODEL, errorText, type CatalogItem, type KeyStatus, type PictureCard } from "./api";
import { Cta, PanelHead } from "./Dock";
import { ModelPicker } from "./ModelPicker";
import { ask } from "./ask";
import * as I from "./icons";

const PROVIDERS = [["kie", "Kie.ai"], ["fal", "fal.ai"], ["google", "Google"], ["openai", "OpenAI"], ["comfyui", "ComfyUI · free"]] as const;
const GROUPS: { kind: PictureCard["kind"][]; title: string; icon: ReactNode; hint: string }[] = [
  { kind: ["character"], title: "People", icon: <I.User size={15} />, hint: "One sheet per person: four views and six expressions. Made first, because the props and dance sheets are matched to them." },
  { kind: ["set"], title: "Places", icon: <I.Mountain size={15} />, hint: "The room or location, empty, lit as in the story." },
  { kind: ["prop", "wardrobe"], title: "Props and outfits", icon: <I.Cube size={15} />, hint: "Each prop on a plain background, shown next to its owner's sheet so the size and style match." },
  { kind: ["choreo"], title: "Dance sheets", icon: <I.Dance size={15} />, hint: "Eight numbered poses with motion arrows. They join the project's choreography as direction for the video model." },
];
const IMG_EXT = ["png", "jpg", "jpeg", "webp"];
const STATE_LABEL: Record<PictureCard["state"], string> = { missing: "No picture yet", making: "Making…", waiting: "Waiting for you", approved: "Approved", yours: "Your picture" };
const IDEAS = ["Older", "Warmer light", "Simpler outfit", "More expressive", "Cleaner background"];

type Est = { count: number; usd: number | null; kie_credits_est?: number; basis: string; title: string };
type Saved = { provider: string; model: string; draft: boolean; cap: string };
const key = (dir: string) => `pf-pictures:${dir}`;
const loadSaved = (dir: string): Saved => {
  try { const v = JSON.parse(localStorage.getItem(key(dir)) || "null"); if (v && typeof v.provider === "string") return { draft: true, cap: "5", ...v }; } catch { /* optional */ }
  return { provider: "kie", model: AUTO_IMAGE_MODEL.kie, draft: true, cap: "5" };
};
const price = (e: Est) => e.usd === 0 ? "free (it runs on your own ComfyUI)" : e.usd != null ? `about $${e.usd.toFixed(2)}${e.kie_credits_est ? ` (${e.kie_credits_est} Kie credits)` : ""}` : "a price this model does not publish";

/**
 * The Pictures step of Create from song: every picture of the production as a card you approve, change in plain words, or replace with your
 * own. Nothing is sent without a priced confirmation, a spend limit stops a batch that would cost more, and a picture only becomes the
 * reference when you approve it. People are made first so props and dance sheets are drawn next to the real person.
 */
export function Pictures({ dir, onDone, onError }: { dir: string; onDone: () => void; onError: (e: string) => void }) {
  const [cards, setCards] = useState<PictureCard[] | null>(null);
  const [working, setWorking] = useState(false);
  const [saved, setSaved] = useState<Saved>(() => loadSaved(dir));
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [keys, setKeys] = useState<KeyStatus | null>(null);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [changing, setChanging] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [est, setEst] = useState<Est | null>(null);
  const [busy, setBusy] = useState("");
  const seen = useRef(new Set<string>());
  const { provider, model, draft, cap } = saved;
  const set = (p: Partial<Saved>) => setSaved((s) => { const n = { ...s, ...p }; try { localStorage.setItem(key(dir), JSON.stringify(n)); } catch { /* optional */ } return n; });

  const load = useCallback(async () => {
    const r = await api.refgen<{ cards: PictureCard[]; working: boolean }>(dir, "cards");
    setCards(r.cards); setWorking(r.working);
    setPicked((p) => {
      const n = { ...p };
      for (const c of r.cards) if (!seen.current.has(c.id)) { seen.current.add(c.id); n[c.id] = c.state === "missing" && c.owner_ready; }
      return n;
    });
  }, [dir]);
  useEffect(() => { load().catch((e) => onError(errorText(e))); api.keyStatus().then(setKeys).catch(() => {}); }, [load]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { api.renderCatalog(provider, "image").then((c) => { setCatalog(c); if (provider === "comfyui" && c.length && !c.some((x) => x.model === model)) set({ model: c[0].model }); }).catch(() => setCatalog([])); }, [provider]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!working) return;
    const t = setInterval(() => { load().catch(() => {}); }, 3000);
    return () => clearInterval(t);
  }, [working, load]);

  const missing = useMemo(() => (cards ?? []).filter((c) => c.state === "missing"), [cards]);
  const ids = missing.filter((c) => picked[c.id] && c.owner_ready).map((c) => c.id);
  const waiting = (cards ?? []).filter((c) => c.state === "waiting");
  useEffect(() => {
    setEst(null);
    if (!ids.length || !model) return;
    let alive = true;
    api.refgen<Est>(dir, "estimate", { ids, provider, model }).then((e) => alive && setEst(e)).catch(() => {});
    return () => { alive = false; };
  }, [dir, provider, model, ids.join(",")]);   // eslint-disable-line react-hooks/exhaustive-deps

  const capUsd = cap.trim() === "" || isNaN(Number(cap)) ? null : Math.max(0, Number(cap));
  const over = !!est && est.usd != null && capUsd != null && est.usd > capUsd;
  const local = provider === "comfyui";
  const noKey = !local && !!keys && !keys[provider as keyof KeyStatus];
  const noFlow = local && catalog.length === 0;

  const queue = async (list: string[], extra: { redo?: string[]; notes?: Record<string, string> } = {}) => {
    const e = await api.refgen<Est>(dir, "estimate", { ids: list, provider, model, ...extra });
    if (capUsd != null && e.usd != null && e.usd > capUsd) { onError(`That would cost about $${e.usd.toFixed(2)}, over your limit of $${capUsd.toFixed(2)}. Raise the limit or choose fewer pictures. Nothing was sent.`); return false; }
    const ok = await ask(`Make ${list.length} picture${list.length === 1 ? "" : "s"} with ${e.title}${draft ? " (draft quality where the model has it)" : ""}?\n\nCost: ${price(e)}.${e.basis ? `\n${e.basis}.` : ""}`
      + `${capUsd != null ? `\nYour limit: $${capUsd.toFixed(2)}.` : ""}\n\nNothing is sent until you press Make. You approve each result afterwards.`, { ok: `Make ${list.length} for ${price(e)}` });
    if (!ok) return false;
    await api.refgen(dir, "queue", { ids: list, provider, model, confirmed: true, draft, cap_usd: capUsd, ...extra });
    return true;
  };
  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    try { await fn(); await load(); } catch (e) { onError(errorText(e)); } finally { setBusy(""); }
  };
  const makeBatch = () => run("Sending…", () => queue(ids));
  const makeAgain = (c: PictureCard) => run("Sending…", async () => {
    if (await queue([c.id], { redo: [c.id], notes: { [c.id]: note } })) { setChanging(null); setNote(""); }
  });
  const approve = (c: PictureCard) => run("Saving…", async () => {
    await api.refgen(dir, "use", { job: c.pending!.job });
    window.dispatchEvent(new Event("pf-library-changed"));
  });
  const approveAll = () => run("Saving…", async () => {
    for (const c of waiting) await api.refgen(dir, "use", { job: c.pending!.job });
    window.dispatchEvent(new Event("pf-library-changed"));
  });
  const discard = (c: PictureCard) => run("Saving…", () => api.refgen(dir, "discard", { job: c.pending!.job }));
  const mine = (c: PictureCard) => run("Saving…", async () => {
    const f = await open({ multiple: false, filters: [{ name: "Images", extensions: IMG_EXT }] });
    if (!f || Array.isArray(f)) return;
    const rel = (await api.importReference(dir, f)).ref.replace(/^project:/, "");
    await api.refgen(dir, "own", { id: c.id, file: rel });
    window.dispatchEvent(new Event("pf-library-changed"));
  });

  if (!cards) return <div className="dim" role="status">Loading the pictures…</div>;
  const total = cards.length;
  const done = cards.filter((c) => c.state === "approved" || c.state === "yours").length;
  const url = (p: string) => api.mediaUrl(`${dir}/${p}`);

  return (
    <section className="pr-sec pics">
      <PanelHead icon={<I.ImageIcon size={18} />} title="Make the pictures" tag={`${done} of ${total} ready`} tone={done === total ? "ok" : "free"}
                 hint="Each card is one picture. Choose which to make, see the price, then approve the results one by one, change them in plain words, or use your own." />
      <div className="pic-bar" role="group" aria-label="Picture settings">
        <div className="pic-bar-col">
          <span className="pr-label">Made with</span>
          <div className="seg" role="group" aria-label="Image provider">
            {PROVIDERS.map(([p, label]) => (
              <button key={p} className={provider === p ? "on" : ""} onClick={() => set({ provider: p, model: AUTO_IMAGE_MODEL[p] ?? "" })}>{label}{p !== "comfyui" && keys && !keys[p as keyof KeyStatus] && <span className="dim"> · no key</span>}</button>))}
          </div>
        </div>
        <div className="pic-bar-col grow"><span className="pr-label">Model</span><ModelPicker catalog={catalog} value={model} onChange={(m) => set({ model: m })} label="Image model" onRefresh={async () => setCatalog(await api.renderCatalog(provider, "image", true))} /></div>
        <div className="pic-bar-col">
          <span className="pr-label">Quality</span>
          <div className="seg" role="group" aria-label="Quality">
            <button className={draft ? "on" : ""} onClick={() => set({ draft: true })} title="Cheaper where the model offers it. Good enough to judge a design.">Draft</button>
            <button className={!draft ? "on" : ""} onClick={() => set({ draft: false })}>Full</button>
          </div>
        </div>
        <div className="pic-bar-col">
          <span className="pr-label">Spend limit</span>
          <label className="pic-cap"><span>$</span><input className="text-input" inputMode="decimal" value={cap} onChange={(e) => set({ cap: e.target.value })} aria-label="Spend limit in dollars" placeholder="none" /></label>
        </div>
      </div>
      {local && !noFlow && <div className="note"><I.Info size={14} /> <span>Pictures are made one after another on your own computer, for free. You can start them and leave FilmCrafter and ComfyUI running overnight; they will be waiting for your approval in the morning.</span></div>}
      {noFlow && <div className="note warn"><I.Alert size={14} /> <span>No ComfyUI image workflow was found. Add one in Settings → ComfyUI, or choose another provider above.</span></div>}
      {noKey && <div className="note warn"><I.Alert size={14} /> <span>Add your {PROVIDERS.find((p) => p[0] === provider)?.[1]} key in Settings to use it, or pick another provider above.</span></div>}

      {GROUPS.map((g) => {
        const list = cards.filter((c) => g.kind.includes(c.kind));
        if (!list.length) return null;
        return (
          <div key={g.title}>
            <h3 className="pr-h">{g.icon} {g.title} <span className="dim">{list.length}</span></h3>
            <p className="dim pic-hint">{g.hint}</p>
            <div className="pic-grid">
              {list.map((c) => {
                const shown = c.pending?.output ?? c.picture;
                const open_ = changing === c.id;
                return (
                  <article key={c.id} className={`pic ${c.state}`} aria-label={c.name}>
                    <div className="pic-art">
                      {shown ? <img src={url(shown)} alt={c.name} loading="lazy" /> : <div className="pic-empty">{c.state === "making" ? <span className="spin" /> : g.icon}</div>}
                      <span className={`pic-badge ${c.state}`}>{c.state === "making" && <span className="spin" />}{STATE_LABEL[c.state]}</span>
                    </div>
                    <div className="pic-body">
                      <div className="pic-name"><b>{c.name}</b>{c.owner && c.kind !== "character" && c.kind !== "choreo" && <span className="dim">{c.owner}'s</span>}</div>
                      {c.state === "missing" && (c.owner_ready
                        ? <label className="pic-check"><input type="checkbox" checked={!!picked[c.id]} onChange={(e) => setPicked({ ...picked, [c.id]: e.target.checked })} /> Make this one</label>
                        : <p className="dim pic-wait"><I.Info size={12} /> Made after {c.owner}'s sheet is approved, so it matches them.</p>)}
                      {c.state === "waiting" && !open_ && (
                        <div className="pic-actions">
                          <button className="btn primary small" onClick={() => approve(c)} disabled={!!busy}><I.Check size={13} /> Approve</button>
                          <button className="btn small" onClick={() => { setChanging(c.id); setNote(""); }} disabled={!!busy}>Change it…</button>
                          <button className="btn ghost small" onClick={() => discard(c)} disabled={!!busy}>Discard</button>
                        </div>)}
                      {c.state === "approved" && !open_ && (
                        <div className="pic-actions">
                          <button className="btn small" onClick={() => { setChanging(c.id); setNote(""); }} disabled={!!busy}><I.Refresh size={13} /> Change it…</button>
                        </div>)}
                      {open_ && (
                        <div className="pic-change">
                          <input className="text-input" autoFocus value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} aria-label={`What should change about ${c.name}`}
                                 placeholder="What should change? e.g. older, warmer"
                                 onKeyDown={(e) => { if (e.key === "Enter" && !busy) makeAgain(c); if (e.key === "Escape") setChanging(null); }} />
                          <div className="pr-ideas">{IDEAS.map((t) => <button key={t} className="pr-idea" onClick={() => setNote((n) => (n ? `${n}, ` : "") + t.toLowerCase())}>{t}</button>)}</div>
                          <div className="pic-actions"><button className="btn primary small" onClick={() => makeAgain(c)} disabled={!!busy || noKey}>Make it again…</button>
                            <button className="btn ghost small" onClick={() => setChanging(null)}>Cancel</button></div>
                          <p className="dim pic-wait">The current picture is shown to the model so the design holds. It is only replaced when you approve the new one.</p>
                        </div>)}
                      {c.error && <p className="error-text pic-err">{c.error}</p>}
                      {c.kind !== "choreo" && c.state !== "making" && !open_ && (
                        <button className="link pic-own" onClick={() => mine(c)} disabled={!!busy}><I.Upload size={12} /> {c.state === "yours" ? "Use a different picture" : "Use my own picture"}</button>)}
                      {c.prompt && c.state !== "yours" && <details className="pic-prompt"><summary>The written prompt</summary><p className="dim">{c.prompt}</p><p className="dim">{c.prompt_from}</p></details>}
                    </div>
                  </article>);
              })}
            </div>
          </div>);
      })}

      <div className="pic-dock" role="region" aria-label="Make the pictures">
        <div className="pic-dock-info">
          {ids.length > 0
            ? <><b>{ids.length} to make</b><span className="dim">{est ? `${price(est)} on ${est.title}` : "Working out the price…"}</span></>
            : waiting.length > 0 ? <><b>{waiting.length} waiting for your approval</b><span className="dim">Approve them to use them as the references.</span></>
              : working ? <><b>Making pictures…</b><span className="dim">They appear here as they finish.</span></>
                : missing.length > 0 ? <><b>Nothing chosen</b><span className="dim">Tick the pictures to make, or approve the people first.</span></>
                  : <><b>Every card has a picture</b><span className="dim">You can still change any made picture in plain words.</span></>}
          {over && <span className="pic-over"><I.Alert size={12} /> Over your ${capUsd!.toFixed(2)} limit: raise it or untick some.</span>}
        </div>
        {waiting.length > 1 && <button className="btn" onClick={approveAll} disabled={!!busy}><I.Check size={14} /> Approve all {waiting.length}</button>}
        {ids.length > 0 && <Cta icon={<I.ImageIcon size={16} />} busy={!!busy} disabled={!est || over || noKey || noFlow} onClick={makeBatch}
                                price={est?.usd != null ? `$${est.usd.toFixed(2)}` : undefined}>Make {ids.length} picture{ids.length === 1 ? "" : "s"}</Cta>}
        <button className={`btn ${ids.length || waiting.length ? "ghost" : "primary"}`} onClick={onDone} disabled={!!busy}>Open in the Studio <I.ArrowRight size={14} /></button>
      </div>
    </section>
  );
}
