import { ASPECTS, aspectCss } from "./frame";

const SHORT: Record<string, string> = { "2.39:1": "Scope", "21:9": "Ultra-wide", "16:9": "Widescreen", "4:3": "Classic", "1:1": "Square", "4:5": "Portrait", "9:16": "Vertical" };

/** The frame shapes to choose from, each drawn to scale (a wide strip for 21:9, a tall one for 9:16), with what it is for. */
export function FrameShapes({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <div className="fs-shapes" role="radiogroup" aria-label="Frame shape">
      {ASPECTS.map(([v, label]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} disabled={disabled} className={`fs-shape ${value === v ? "on" : ""}`} onClick={() => onChange(v)} title={label}>
          <span className="fs-box" style={{ aspectRatio: aspectCss(v) }} aria-hidden="true" />
          <b>{v}</b><i>{SHORT[v] ?? label.split(" · ")[0]}</i>
        </button>))}
    </div>
  );
}
