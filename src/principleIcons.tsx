import type { ReactNode } from "react";

/** One small picture for each of the twelve principles of animation, drawn in the app's own line style (24 px, 1.75 stroke, round ends), so the list can be taken in at a glance. */
const DRAW: Record<string, ReactNode> = {
  // a ball flattened where it lands, with the speed lines of its fall
  "squash-stretch": <><ellipse cx="12" cy="17" rx="6.5" ry="3.2" /><path d="M5 20.5h14" /><path d="M9 5v4M12 3.5v5M15 5v4" /></>,
  // a small pull-back arrow before the big one forward
  "anticipation": <><path d="M9 12H4m0 0 2.5-2.5M4 12l2.5 2.5" /><path d="M11 12h9m0 0-3.5-3.5M20 12l-3.5 3.5" /></>,
  // one figure in the light, the rest dimmed
  "staging": <><path d="M12 3 7 21h10L12 3Z" opacity="0.45" /><circle cx="12" cy="11" r="2.4" /><path d="M9.2 18.5c.6-2.4 1.6-3.6 2.8-3.6s2.2 1.2 2.8 3.6" /></>,
  // three key poses on a path
  "pose-to-pose": <><circle cx="5" cy="17" r="2" /><circle cx="12" cy="7" r="2" /><circle cx="19" cy="15" r="2" /><path d="M7 15.5 10.2 9M14 8l3.4 5.2" strokeDasharray="1.5 2.5" /></>,
  // a body stops and the cloth keeps going
  "follow-through": <><circle cx="6" cy="8" r="2.2" /><path d="M8.2 8.6C12 8 14 11 17 11.5s3-.5 4 .5M8 10.5c3.5.5 5 3.5 8.5 4.2 2 .4 3.2-.2 4.5-.7" /></>,
  // an ease curve: slow, fast, slow
  "slow-in-out": <><path d="M3 18h18" opacity="0.4" /><path d="M3 18c6 0 3.5-12 9-12s3 12 9 12" /><path d="M12 6V3" opacity="0.4" /></>,
  // an arc with the thing travelling along it
  "arcs": <><path d="M4 18C6 8 14 4 20 7" /><circle cx="15.5" cy="5.6" r="2" /></>,
  // the main action and a small extra one beside it
  "secondary-action": <><circle cx="9" cy="12" r="4.5" /><circle cx="19" cy="6.5" r="1.6" /><path d="M16.5 9.5c1.2.4 2 1.3 2.4 2.6" /></>,
  // a stopwatch
  "timing": <><circle cx="12" cy="13.5" r="7" /><path d="M12 13.5V9.5M9.5 3.5h5M12 3.5v3M17.5 6l1.2-1.2" /></>,
  // a burst, pushed past real life
  "exaggeration": <><path d="m12 2.5 2.2 5.2 5.6-.8-3.4 4.5 3.4 4.5-5.6-.8L12 21.5l-2.2-5.2-5.6.8 3.4-4.5-3.4-4.5 5.6.8L12 2.5Z" /></>,
  // a box with volume from every side
  "solid-drawing": <><path d="m12 3 8 4.2v9.6L12 21l-8-4.2V7.2L12 3Z" /><path d="M12 12.4 4 7.2M12 12.4l8-5.2M12 12.4V21" /></>,
  // a face worth looking at
  "appeal": <><circle cx="12" cy="12" r="8.5" /><path d="M8.5 14c1 1.7 2.1 2.5 3.5 2.5s2.5-.8 3.5-2.5" /><circle cx="9" cy="10" r="0.6" fill="currentColor" /><circle cx="15" cy="10" r="0.6" fill="currentColor" /></>,
};

export const hasPrincipleIcon = (id: string): boolean => id in DRAW;

export function PrincipleIcon({ id, size = 26 }: { id: string; size?: number }) {
  return (
    <svg className="pr-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {DRAW[id] ?? <circle cx="12" cy="12" r="6" />}
    </svg>
  );
}
