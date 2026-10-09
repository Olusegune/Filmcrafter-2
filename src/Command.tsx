import { useEffect, useRef, useState } from "react";
import { api, errorText, type EngineEvent, type Job, type ProposedAction } from "./api";
import * as I from "./icons";
import { ConfirmRender, PROVIDER_NAME } from "./Render";

const EXAMPLES = [
  "Regenerate this shot using Kling",
  "Keyframes for scene 2",
  "Make the second chorus much more energetic",
  "Less movement during Verse 1",
  "Make the selected shot more intimate",
  "Keep the performance but make the camera calmer in the bridge",
  "Warmer, golden light for the final chorus",
];

export type CommandResult = { id: string | null; summary: string; not_done: string; changed: string[] };

/** PRD §26: a temporary command surface, not a chat. Ctrl+K opens it; Esc closes it. */
export function DirectorCommand({ dir, selected, playhead, onApplied, onClose, onSettings, onJobs, onChanged }: {
  dir: string; selected: string | null; playhead: number;
  onApplied: (r: CommandResult) => void; onClose: () => void; onSettings: () => void;
  onJobs: (jobs: Job[]) => void; onChanged: () => void;
}) {
  const [proposal, setProposal] = useState<ProposedAction | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) onClose(); };
    window.addEventListener("keydown", k);
    const un = api.onEngine((e: EngineEvent) => { if (e.task === "command" && e.stage) setBusy(e.stage.charAt(0).toUpperCase() + e.stage.slice(1) + "…"); });
    return () => { window.removeEventListener("keydown", k); un.then((f) => f()); };
  }, [busy, onClose]);

  const run = async (text: string) => {
    if (!text.trim()) return;
    setError(""); setProposal(null); setBusy("Reading your note…");
    // Actions (render, keyframes, lip-sync, lock, use latest) are parsed locally and always confirmed first.
    try {
      const p = await api.parseAction(dir, text.trim(), selected, playhead);
      if (p.type === "error") { setError(p.message ?? "Couldn't do that."); setBusy(""); return; }
      if (p.type === "action") { setProposal(p); setBusy(""); return; }
    } catch (e) { setError(errorText(e)); setBusy(""); return; }
    if (!(await api.aiReady())) { onClose(); onSettings(); return; }
    try { onApplied(await api.directorCommand(dir, text.trim(), selected, playhead)); }
    catch (e) { setError(errorText(e)); setBusy(""); }
  };

  const execute = async () => {
    const p = proposal!;
    setConfirming(false); setBusy("Working…"); setError("");
    try {
      const shots = p.shots ?? [];
      if (p.action === "render") {
        if (p.render_kind === "lipsync") {
          const made: Job[] = [];
          for (const id of shots) made.push(...await api.queueRender(dir, [id], p.provider!, p.model!, {}, [], "lipsync", p.sources?.[id] ?? null));
          onJobs(made);
        } else {
          onJobs(await api.queueRender(dir, shots, p.provider!, p.model!, {}, [], p.render_kind === "image" ? "image" : "video"));
        }
      } else if (p.action === "lock" || p.action === "unlock") {
        for (const id of shots) await api.library(dir, "lock", { shot: id, on: p.action === "lock" });
      } else if (p.action === "approve_keyframes") {
        await api.library(dir, "approve_keyframes", { shots });
      } else if (p.action === "approve_latest") {
        await api.library(dir, "approve_latest", { shots });
      }
      onChanged();
      onClose();
    } catch (e) { setError(errorText(e)); setBusy(""); }
  };

  return (
    <div className="cmd-backdrop" onClick={() => !busy && !confirming && onClose()}>
      <div className="cmd glass" role="dialog" aria-label="Director Command" onClick={(e) => e.stopPropagation()}>
        <div className="cmd-row">
          <span className="cmd-label">Direct</span>
          <input ref={input} className="cmd-input" value={note} disabled={!!busy} placeholder="Give a note, e.g. “less dancing in Verse 1”"
                 onChange={(e) => setNote(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run(note)} aria-label="Director note" />
          <kbd>Enter</kbd>
        </div>
        {busy ? <div className="cmd-busy"><span className="spin" /> {busy}</div> : proposal ? (
          <div className="action-card">
            <div className="ac-sum">{proposal.summary}</div>
            <div className="ac-shots">{(proposal.shots ?? []).map((id) => <span key={id} className="chip num">{id}</span>)}</div>
            {proposal.warning && <div className="problems" role="alert" style={{ marginBottom: 8 }}>{proposal.warning}</div>}
            {proposal.skipped?.length ? <div className="dim">Skipped: {proposal.skipped.map((x) => `${x.id} (${x.reason})`).join(", ")}</div> : null}
            {proposal.action === "render" && <div style={{ margin: "6px 0" }}>
              <span className="dim num">{PROVIDER_NAME[proposal.provider!]} · {proposal.model}</span>{" "}
              {proposal.verified ? <span className="ver-ok">· tested with a real render</span> : <span className="ver-no">· not yet tested with a real render</span>}</div>}
            <div className="sheet-actions">
              <button className="btn ghost" onClick={() => setProposal(null)}>Back</button>
              <button className="btn primary" onClick={() => proposal.billable ? setConfirming(true) : execute()}>
                {proposal.action === "render" ? (proposal.billable ? "Check price…" : "Render") : proposal.action === "approve_latest" ? "Use newest versions" : proposal.action === "approve_keyframes" ? "Approve keyframes" :
                  proposal.action === "lock" ? "Lock" : "Unlock"}</button>
            </div>
          </div>
        ) : (
          <div className="cmd-hints">
            {selected && <div className="dim">Selected: {selected}. Notes can say “this shot”.</div>}
            {EXAMPLES.map((x) => <button key={x} className="cmd-ex" onClick={() => { setNote(x); run(x); }}>{x}</button>)}
          </div>
        )}
        {error && <div className="error-text" style={{ padding: "0 16px 12px" }}>{error}</div>}
      </div>
      {confirming && proposal && <ConfirmRender count={proposal.shots!.length} seconds={0} provider={proposal.provider!} model={proposal.label ?? proposal.model!}
                                                dir={dir} shots={proposal.shots} modelId={proposal.model} kind={proposal.render_kind}
                                                onCancel={() => setConfirming(false)} onConfirm={execute} />}
    </div>
  );
}

/** What changed, with Undo. Shown briefly after a command. */
export function CommandToast({ result, onUndo, onDismiss, onSelect }: {
  result: CommandResult; onUndo: () => void; onDismiss: () => void; onSelect: (id: string) => void;
}) {
  return (
    <div className="toast glass cmd-toast" role="status">
      <div className="t">Directed</div>
      <div className="s">{result.summary}</div>
      {result.changed.length > 0 && <div className="cmd-changed">{result.changed.map((id) =>
        <button key={id} className="chip num" onClick={() => onSelect(id)}>{id}</button>)}</div>}
      {result.not_done && <div className="dim" style={{ marginTop: 6 }}>Not changed: {result.not_done}</div>}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 10 }}>
        {result.id && result.changed.length > 0 && <button className="btn small" onClick={onUndo}><I.SkipBack size={12} /> Undo</button>}
        <button className="btn small ghost" onClick={onDismiss}>OK</button>
      </div>
    </div>
  );
}
