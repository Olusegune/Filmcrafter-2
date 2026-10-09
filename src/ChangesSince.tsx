import type { ChangesSince as Changes } from "./api";
import "./acting.css";

const LABEL: Record<string, string> = {
  model: "Model", keyframe: "Keyframe", first_frame: "First frame", audio: "Song", references: "Pictures", length: "Length",
  prompt_added: "Added to the prompt", prompt_removed: "Removed from the prompt", prompt_more: "",
};

/** What would be different if this shot were rendered again, in the words of what the model is told and shown. Pure display: the Video tab asks the engine (free). */
export function ChangesSince({ changes, busy }: { changes: Changes | null; busy?: boolean }) {
  if (!changes || !changes.has_take) return null;
  if (changes.same) {
    return <p className="cs cs-same" role="status"><b>Since the last take:</b> {busy ? "checking…" : changes.note}</p>;
  }
  const n = changes.changes.filter((c) => c.kind !== "prompt_more").length;
  return (
    <details className="cs cs-diff" open={n <= 4}>
      <summary><b>Since the last take:</b> {n} change{n === 1 ? "" : "s"} to what the model is told or shown{busy ? " (checking…)" : ""}</summary>
      <ul>
        {changes.changes.map((c, i) => (
          <li key={i} className={`cs-${c.kind}`}>
            {LABEL[c.kind] ? <span className="cs-tag">{LABEL[c.kind]}</span> : null}
            <span className="cs-text">{c.kind === "prompt_added" ? "+ " : c.kind === "prompt_removed" ? "− " : ""}{c.text}</span>
          </li>))}
      </ul>
    </details>
  );
}
