import { Component, type ErrorInfo, type ReactNode } from "react";

/** A screen that crashes never leaves a blank window: the project on disk is untouched (every change is saved as it happens,
 *  and backups exist), so offer to reload or go back Home, and show the details for a bug report. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error("PULSEFRAME crashed:", error, info.componentStack); }
  render() {
    const e = this.state.error;
    if (!e) return this.props.children;
    return (
      <div className="crash" role="alert">
        <h1>Something went wrong on this screen</h1>
        <p>Your project is safe: everything is saved on disk as you work, and PULSEFRAME keeps backups (File → Restore from Backup…).
          Reload to carry on where you were.</p>
        <div className="crash-actions">
          <button className="btn primary" onClick={() => location.reload()}>Reload PULSEFRAME</button>
          <button className="btn ghost" onClick={() => navigator.clipboard.writeText(`${e.name}: ${e.message}\n${e.stack ?? ""}`)}>Copy error details</button>
        </div>
        <details><summary>Details</summary><pre>{e.name}: {e.message}</pre></details>
      </div>
    );
  }
}
