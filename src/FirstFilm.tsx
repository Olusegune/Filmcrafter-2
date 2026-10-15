import { useEffect, useMemo, useState } from "react";
import { api, type AudioLibrary, type CueList, type FilmProgress, type MakeStatus, type VoiceStatus } from "./api";
import * as I from "./icons";
import { buildSteps, doneCount, markGuideSeen, nextStep, requiredCount, type Step } from "./guideSteps";

type Pick = { provider?: string; model?: string; label?: string };

/**
 * "Your first film": the order a film is made in, worked out from what this film already has, with what each step costs said plainly. It only reads and points: nothing here makes, buys or
 * changes anything, and every paid step still shows its own price and waits for its own yes where it happens. A step's "Take me there" opens that part of the app.
 */
export function FirstFilm({ dir, progress, pro, onGo, onClose }: { dir: string; progress: FilmProgress | null; pro: boolean; onGo: (where: Step["go"]) => void; onClose: () => void }) {
  const [voices, setVoices] = useState<VoiceStatus | null>(null);
  const [sound, setSound] = useState<{ cues: number; assets: number } | null>(null);
  const [test, setTest] = useState<{ pictures?: string; video?: string }>({});
  useEffect(() => {
    api.voice("status", dir).then(setVoices).catch(() => setVoices(null));
    Promise.all([api.filmCues<CueList>("list", dir), api.filmAudio<AudioLibrary>("list", dir)]).then(([c, a]) => setSound({ cues: c.cues.length, assets: a.assets.length })).catch(() => setSound(null));
  }, [dir]);
  useEffect(() => {                                                   // what one test shot would cost: read from the same free estimate the Studio uses
    if (!progress?.make.shots) return;
    const rd = `${dir}/render`;
    let live = true;
    (async () => {
      const st = await api.make<MakeStatus>("status", dir).catch(() => null);
      const id = st?.shots[0]?.id;
      if (!id) return;
      const out: { pictures?: string; video?: string } = {};
      for (const [k, kind] of [["pictures", "image"], ["video", "video"]] as const) {
        const pick = await api.routing<Pick>(rd, "pick", { kind }).catch(() => null);
        if (!pick?.provider || !pick.model) continue;
        const est = await api.renderEstimate(rd, [id], pick.provider, pick.model, kind).catch(() => null);
        if (est?.usd != null) out[k] = `about $${est.usd.toFixed(2)} for one test shot with ${pick.label || pick.model}`;
      }
      if (live) setTest(out);
    })();
    return () => { live = false; };
  }, [dir, progress?.make.shots]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !document.querySelector(".ask, [role=alertdialog]")) { e.stopImmediatePropagation(); close(); } };
    window.addEventListener("keydown", k, true);
    return () => window.removeEventListener("keydown", k, true);
  });                                                                  // eslint-disable-line react-hooks/exhaustive-deps
  const close = () => { markGuideSeen(dir); onClose(); };
  const steps = useMemo(() => buildSteps({ progress, voices: voices ? { people: voices.people, recorded: voices.recorded } : null, sound, pro, exported: false }), [progress, voices, sound, pro]);
  const next = nextStep(steps);
  const done = doneCount(steps), total = requiredCount(steps);
  return (
    <div className="overlay" onClick={close}>
      <div className="sheet glass ff" role="dialog" aria-label="Your first film" onClick={(e) => e.stopPropagation()}>
        <div className="vs-head"><h2>Your first film</h2><div style={{ flex: 1 }} /><button className="icon-btn" onClick={close} aria-label="Close"><I.Close size={18} /></button></div>
        <p className="ff-lead">{next ? <>Next: <b>{next.title}</b>. </> : <>Every step is done. </>}{done} of {total} steps finished. Nothing on this page makes or buys anything: each step shows its own price and asks first, where it happens.</p>
        <div className="ff-bar" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} aria-label="Steps finished"><i style={{ width: `${Math.round((done / total) * 100)}%` }} /></div>
        <ol className="ff-steps">
          {steps.map((s, i) => {
            const price = s.id === "pictures" ? test.pictures : s.id === "video" ? test.video : undefined;
            return (
              <li key={s.id} className={`ff-step ${s.status}`} aria-current={s.status === "next" ? "step" : undefined}>
                <span className="ff-n" aria-hidden="true">{s.status === "done" ? <I.Check size={13} /> : i + 1}</span>
                <div className="ff-main">
                  <div className="ff-title"><b>{s.title}</b>
                    <span className={`ff-cost ${s.cost}`} title={s.costWords}>{s.cost === "free" ? "Free" : s.cost === "asks" ? "Asks first" : "Free or asks first"}</span>
                    {s.status === "done" && <span className="ff-state">Done</span>}{s.status === "next" && <span className="ff-state on">Next</span>}</div>
                  <p className="ff-what">{s.what}</p>
                  <p className="why">{s.costWords}.{price ? ` Right now: ${price}.` : ""}{s.detail ? ` ${s.detail}` : ""}</p>
                </div>
                <button className={`btn sm ${s.status === "next" ? "primary" : "sel"}`} onClick={() => { markGuideSeen(dir); onGo(s.go); onClose(); }}>{s.status === "done" ? "Open" : s.status === "next" ? "Take me there" : "Look"}</button>
              </li>);
          })}
        </ol>
        <p className="why ff-foot">Tip: test one shot first. If its picture, mouth and voice are right, the others will be too, and you have spent a fraction of the cost finding out.</p>
        <div className="cv-actions"><button className="btn" onClick={close}>Close</button><span className="why">Open it again any time from the <b>Guide</b> button at the top.</span></div>
      </div>
    </div>
  );
}
