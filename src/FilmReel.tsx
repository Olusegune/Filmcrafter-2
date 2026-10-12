/**
 * The Home screen's one piece of motion: a clapperboard above the heading. The arm lifts, the board eases up a little, the arm claps shut and the board settles back to its own size,
 * then it rests. Drag a story over the card and it claps faster, with a warmer light. Still (arm closed) with reduced motion.
 */
export function FilmReel({ active }: { active: boolean }) {
  const stripes = (y: number, flip: boolean) => Array.from({ length: 7 }, (_, i) => {
    const x = 6 + i * 16 + (flip ? 8 : 0);
    return <polygon key={i} points={`${x},${y + 11} ${x + 8},${y + 11} ${x + 14},${y} ${x + 6},${y}`} className="clap-stripe" />;
  });
  return (
    <div className={`reel ${active ? "fast" : ""}`} aria-hidden="true">
      <svg className="clap" viewBox="0 0 120 92" focusable="false">
        <defs>
          <clipPath id="clap-low"><rect x="6" y="34" width="108" height="11" rx="1.5" /></clipPath>
          <clipPath id="clap-top"><rect x="6" y="22" width="108" height="11" rx="1.5" /></clipPath>
        </defs>
        <rect className="clap-body" x="6" y="46" width="108" height="40" rx="2" />
        <g className="clap-text">
          <rect x="14" y="55" width="22" height="2" /><rect x="14" y="62" width="40" height="2" />
          <rect x="14" y="73" width="22" height="2" /><rect x="64" y="55" width="22" height="2" />
          <rect x="64" y="62" width="36" height="2" /><rect x="64" y="73" width="22" height="2" />
        </g>
        <g clipPath="url(#clap-low)"><rect className="clap-stick" x="6" y="34" width="108" height="11" />{stripes(34, false)}</g>
        <rect className="clap-edge" x="6" y="34" width="108" height="11" rx="1.5" />
        <g className="clap-arm">
          <g clipPath="url(#clap-top)"><rect className="clap-stick" x="6" y="22" width="108" height="11" />{stripes(22, true)}</g>
          <rect className="clap-edge" x="6" y="22" width="108" height="11" rx="1.5" />
        </g>
        <circle className="clap-hinge" cx="9" cy="33.5" r="2" />
      </svg>
    </div>
  );
}
