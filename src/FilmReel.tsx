import type { CSSProperties } from "react";

/**
 * The Home screen's living film strip: two rows of frames rolling past in opposite directions behind the drop card, and a slow sweep of light.
 * Drag a screenplay over the card and the strips speed up and glow. Still, with reduced motion.
 */
export function FilmReel({ active }: { active: boolean }) {
  const set = (seed: number, key: number) => (
    <div className="reel-set" key={key}>
      {Array.from({ length: 22 }, (_, i) => <i key={i} style={{ "--h": (i * 37 + seed) % 360 } as CSSProperties} />)}
    </div>);
  return (
    <div className={`reel ${active ? "fast" : ""}`} aria-hidden="true">
      <div className="reel-row top"><div className="reel-track">{[0, 1].map((k) => set(10, k))}</div></div>
      <div className="reel-row bottom"><div className="reel-track">{[0, 1].map((k) => set(200, k))}</div></div>
      <div className="reel-sweep" />
    </div>
  );
}
