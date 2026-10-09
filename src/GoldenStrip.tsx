import { useMemo } from "react";
import * as I from "./icons";

export type GoldenInput = {
  hasSong: boolean; shots: { id: string }[]; keyframes: Record<string, string>; videoReady: Set<string>; pending: number;
  people: { total: number; withPicture: number }; exported: boolean;
};
type Step = { id: string; label: string; icon: React.ReactNode; done: number; of: number; state: "done" | "current" | "todo"; note: string; free?: boolean };

/**
 * The Golden Path on one line: Song, Plan, References, Keyframes, Video, Export, with how far along each is and which one is next.
 * Every step is free until Keyframes; keyframes cost cents and video costs the most, so those are the two you approve before moving on.
 */
export function goldenSteps(g: GoldenInput): { steps: Step[]; next: Step | null } {
  const n = g.shots.length;
  const kf = g.shots.filter((s) => g.keyframes[s.id]).length;
  const vid = g.shots.filter((s) => g.videoReady.has(s.id)).length;
  const raw: Omit<Step, "state">[] = [
    { id: "song", label: "Song", icon: <I.Wave size={14} />, done: g.hasSong ? 1 : 0, of: 1, note: "The song is listened to and mapped.", free: true },
    { id: "plan", label: "Plan", icon: <I.Film size={14} />, done: n > 0 ? 1 : 0, of: 1, note: n ? `${n} shots planned.` : "Plan the shots (Create from song, or the Director).", free: true },
    { id: "refs", label: "References", icon: <I.User size={14} />, done: g.people.withPicture, of: Math.max(g.people.total, 1),
      note: g.people.total ? `${g.people.withPicture} of ${g.people.total} people have a picture, which keeps faces the same.` : "Add pictures of your people (optional).", free: true },
    { id: "keyframes", label: "Keyframes", icon: <I.ImageIcon size={14} />, done: kf, of: Math.max(n, 1),
      note: g.pending ? `${g.pending} new keyframe${g.pending === 1 ? "" : "s"} waiting for your approval.` : `${kf} of ${n} shots have an approved keyframe. A few cents each.` },
    { id: "video", label: "Video", icon: <I.Clapper size={14} />, done: vid, of: Math.max(n, 1), note: `${vid} of ${n} shots have video. This is the main cost: render after the keyframe is right.` },
    { id: "export", label: "Export", icon: <I.Export size={14} />, done: g.exported ? 1 : 0, of: 1, note: "Join the shots with your song, add captions, and export.", free: true },
  ];
  // the current step is the first one not finished; References and Plan are only "current" when nothing after them can start
  const firstOpen = raw.findIndex((s) => s.done < s.of && !(s.id === "refs"));
  const steps: Step[] = raw.map((s, i) => ({ ...s, state: s.done >= s.of ? "done" : i === firstOpen ? "current" : "todo" }));
  return { steps, next: steps[firstOpen] ?? null };
}

export function GoldenStrip({ input, spent, budget, onGo, onTour, test }: { input: GoldenInput; spent: number | null; budget: number | null; onGo: (step: string) => void; onTour?: () => void; test?: { id: string; why: string[] } | null }) {
  const { steps, next } = useMemo(() => goldenSteps(input), [input]);
  return (
    <>
    <nav className="golden" aria-label="Where you are in the production">
      <ol>
        {steps.map((s, i) => (
          <li key={s.id} data-s={s.id} className={s.state}>
            <button onClick={() => onGo(s.id)} title={s.note} aria-current={s.state === "current" ? "step" : undefined}>
              <span className="g-ic">{s.state === "done" ? <I.Check size={13} /> : s.icon}</span>
              <span className="g-t"><b>{s.label}</b>{s.of > 1 && <small className="num">{s.done}/{s.of}</small>}</span>
              {!s.free && <span className="g-paid" title="This step costs money. You see the price first.">$</span>}
            </button>
            {i < steps.length - 1 && <i className="g-bar" aria-hidden><i style={{ width: `${s.state === "done" ? 100 : s.state === "current" ? Math.round((s.done / s.of) * 100) : 0}%` }} /></i>}
          </li>))}
      </ol>
      <div className="g-side">
        {onTour && <button className="g-help" onClick={onTour} title="Show the welcome tour" aria-label="Show the welcome tour">?</button>}
        {next && <span className="g-next"><I.Rocket size={13} /> Next: <b>{next.label.toLowerCase()}</b></span>}
        {spent !== null && <span className="g-spent num" title="Spent on this project so far">{`$${spent.toFixed(2)}`}{budget ? ` / $${budget.toFixed(0)}` : ""}</span>}
      </div>
    </nav>
    {test && next?.id === "video" && next.done === 0 && (
      <div className="g-test" role="note">
        <I.Clapper size={13} /> <span>Before you render everything, <b>test one shot</b>: <b>{test.id}</b>{test.why.length ? ` has ${test.why.join(", ")}` : ""}. If it looks right, render the rest.</span>
        <button className="btn small" onClick={() => onGo(`test:${test.id}`)}>Open {test.id}</button>
      </div>)}
    </>
  );
}
