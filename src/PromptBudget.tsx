import { budgetNote, budgetOf, GROUPS, type PromptBlock } from "./promptShare";
import "./sound.css";

/** How much of the prompt each kind of text takes: a thin bar and a legend, so a shot whose acting is buried under rules can be seen at a glance. */
export function PromptBudget({ blocks }: { blocks: PromptBlock[] | null | undefined }) {
  if (!blocks?.length) return null;
  const b = budgetOf(blocks);
  if (!b.total) return null;
  const note = budgetNote(b);
  return (
    <details className="prompt-budget">
      <summary>Where the prompt's words go <span className="dim num">{b.total.toLocaleString()} characters</span></summary>
      <div className="pb-bar" role="img" aria-label={b.shares.map((s) => `${GROUPS.find((g) => g.id === s.id)?.label} ${s.pct}%`).join(", ")}>
        {b.shares.filter((s) => s.pct > 0).map((s) => <i key={s.id} className={`pb-${s.id}`} style={{ width: `${s.pct}%` }} />)}
      </div>
      <ul className="pb-legend">
        {b.shares.map((s) => <li key={s.id} title={GROUPS.find((g) => g.id === s.id)?.what}><i className={`pb-${s.id}`} /> {GROUPS.find((g) => g.id === s.id)?.label} <span className="dim num">{s.pct}%</span></li>)}
      </ul>
      {note && <p className="dim pb-note">{note}</p>}
    </details>
  );
}
