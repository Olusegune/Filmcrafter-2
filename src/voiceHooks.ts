import { useCallback, useEffect, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { api, type VoiceMatch, type VoiceShot, type VoiceStatus } from "./api";
import { audioFiles, usable } from "./voiceLogic";

/** Any screen that changes a recording tells every other screen showing voices, so a card, the timeline and the sheet stay in step. */
export const VOICE_EVENT = "fc-voice-changed";
export const notifyVoice = () => window.dispatchEvent(new Event(VOICE_EVENT));

const cache = new Map<string, VoiceStatus>();

/** The film's voices (one load shared by everything on screen). `dir` is the film's folder; null when the project is not a film. */
export function useVoiceStatus(dir: string | null): { st: VoiceStatus | null; byShot: Record<string, VoiceShot>; reload: () => void } {
  const [st, setSt] = useState<VoiceStatus | null>(dir ? cache.get(dir) ?? null : null);
  const reload = useCallback(() => {
    if (!dir) return;
    api.voice("status", dir).then((r) => { cache.set(dir, r); setSt(r); }).catch(() => {});
  }, [dir]);
  useEffect(() => { reload(); window.addEventListener(VOICE_EVENT, reload); return () => window.removeEventListener(VOICE_EVENT, reload); }, [reload]);
  const byShot: Record<string, VoiceShot> = {};
  for (const s of st?.shots ?? []) byShot[s.id] = s;
  return { st, byShot, reload };
}

/** What happened to files dropped on a shot: attached straight away, or a table to check (the sheet opens with these rows). */
export type DropResult = { attached: number; check: VoiceMatch[] | null; error?: string };

/** Match files to one shot and attach them when every one is clear; otherwise hand back the rows so the person can fix them. */
export async function attachToShot(dir: string, shot: string, files: string[]): Promise<DropResult> {
  const only = audioFiles(files);
  if (!only.length) return { attached: 0, check: null, error: "Drop audio files: WAV, MP3, M4A, FLAC, AAC or OGG." };
  const { rows } = await api.voice<{ rows: VoiceMatch[] }>("match", dir, { files: only, shot });
  if (rows.length && rows.every(usable)) {
    const r = await api.voice<{ attached: unknown[] }>("import", dir, { items: rows.map((x) => ({ file: x.file, shot: x.shot, speaker: x.speaker })) });
    notifyVoice();
    return { attached: r.attached.length, check: null };
  }
  return { attached: 0, check: rows };
}

/** Dropping audio onto a card or a timeline block (anything marked data-shot-id) attaches it to that shot. The block lights up while files are over it. */
export function useShotDrop(enabled: boolean, onDrop: (shot: string, files: string[]) => void): void {
  useEffect(() => {
    if (!enabled) return;
    let un: (() => void) | undefined;
    let live = true;
    let lit: Element | null = null;
    const at = (p: { x: number; y: number }) => document.elementFromPoint(p.x / (window.devicePixelRatio || 1), p.y / (window.devicePixelRatio || 1))?.closest("[data-shot-id]") ?? null;
    const light = (el: Element | null) => { if (lit && lit !== el) lit.classList.remove("voice-over"); lit = el; el?.classList.add("voice-over"); };
    getCurrentWebview().onDragDropEvent((e) => {
      const p = e.payload;
      if (p.type === "enter" || p.type === "over") light(at(p.position));
      else if (p.type === "leave") light(null);
      else if (p.type === "drop") {
        const el = at(p.position);
        light(null);
        const id = el?.getAttribute("data-shot-id");
        if (id && audioFiles(p.paths).length) onDrop(id, p.paths);
      }
    }).then((f) => { if (live) un = f; else f(); }).catch(() => {});
    return () => { live = false; light(null); un?.(); };
  }, [enabled, onDrop]);
}
