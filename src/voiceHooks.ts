import { useCallback, useEffect, useState } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { api, type CastStatus, type VoiceMatch, type VoiceShot, type VoiceStatus } from "./api";
import { audioFiles, personAt, usable } from "./voiceLogic";

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
export type DropResult = { attached: number; check: VoiceMatch[] | null; error?: string; added?: { shot: string; speaker: string }[]; who?: string };

/** Match files to one shot and attach them when every one is clear; otherwise hand back the rows so the person can fix them. */
export async function attachToShot(dir: string, shot: string, files: string[]): Promise<DropResult> {
  const only = audioFiles(files);
  if (!only.length) return { attached: 0, check: null, error: "Drop audio files: WAV, MP3, M4A, FLAC, AAC or OGG." };
  const { rows } = await api.voice<{ rows: VoiceMatch[] }>("match", dir, { files: only, shot });
  if (rows.length && rows.every(usable)) {
    const r = await api.voice<{ attached: unknown[] }>("import", dir, { items: rows.map((x) => ({ file: x.file, shot: x.shot, speaker: x.speaker })) });
    notifyVoice();
    return { attached: r.attached.length, check: null, added: rows.filter((x) => x.status === "ok").map((x) => ({ shot: x.shot!, speaker: x.speaker! })) };
  }
  return { attached: 0, check: rows };
}

/** A file dropped on one person's chip: it is theirs, so it is attached to them at once, with no table. */
export async function attachToPerson(dir: string, shot: string, who: string, files: string[]): Promise<DropResult> {
  const only = audioFiles(files);
  if (!only.length) return { attached: 0, check: null, error: "Drop an audio file: WAV, MP3, M4A, FLAC, AAC or OGG." };
  const had = (await api.voice("status", dir)).shots.find((x) => x.id === shot)?.people.find((p) => p.name === who)?.recording;
  const r = await api.voice<{ attached: unknown[]; failed: { file: string; why: string }[] }>("import", dir, { items: [{ file: only[0], shot, speaker: who }] });
  notifyVoice();
  if (!r.attached.length) return { attached: 0, check: null, error: r.failed[0]?.why ?? "That file could not be attached." };
  return { attached: 1, check: null, who, added: had ? [] : [{ shot, speaker: who }] };
}

/** Take back a drop that added new recordings (the files go to the film's voice/_removed folder, nothing is deleted). A drop that replaced one is not undone here: the old one is kept in _removed. */
export async function undoAdded(dir: string, added: { shot: string; speaker: string }[]): Promise<void> {
  for (const a of added) await api.voice("remove", dir, { shot: a.shot, speaker: a.speaker });
  notifyVoice();
}

/** Dropping audio onto a card or a timeline block (anything marked data-shot-id) attaches it to that shot. The block lights up while files are over it. */
export function useShotDrop(enabled: boolean, onDrop: (shot: string, files: string[], who?: string) => void): void {
  useEffect(() => {
    if (!enabled) return;
    let un: (() => void) | undefined;
    let live = true;
    let lit: Element | null = null;
    let litChip: Element | null = null;
    const at = (p: { x: number; y: number }) => document.elementFromPoint(p.x / (window.devicePixelRatio || 1), p.y / (window.devicePixelRatio || 1))?.closest("[data-shot-id]") ?? null;
    const light = (el: Element | null) => { if (lit && lit !== el) lit.classList.remove("voice-over"); lit = el; el?.classList.add("voice-over"); if (!el) pick(null, null); };
    /** The chip of a person (inside the card under the pointer) that the pointer is on: dropping there gives the file to that person. */
    const chipAt = (card: Element | null, p: { x: number; y: number }): Element | null => {
      if (!card) return null;
      const dpr = window.devicePixelRatio || 1, at = { x: p.x / dpr, y: p.y / dpr };
      const chips = [...(card.matches("[data-voice-person]") ? [card] : []), ...card.querySelectorAll("[data-voice-person]")];       // a clip on the timeline is itself one person's slot
      const who = personAt(chips.map((c) => { const r = c.getBoundingClientRect(); return { who: c.getAttribute("data-voice-person") ?? "", left: r.left, top: r.top, right: r.right, bottom: r.bottom }; }), at);
      return who ? chips.find((c) => c.getAttribute("data-voice-person") === who) ?? null : null;
    };
    const pick = (_card: Element | null, chip: Element | null) => { if (litChip && litChip !== chip) litChip.classList.remove("voice-target"); litChip = chip; chip?.classList.add("voice-target"); };
    getCurrentWebview().onDragDropEvent((e) => {
      const p = e.payload;
      if (p.type === "enter" || p.type === "over") { const card = at(p.position); light(card); pick(card, chipAt(card, p.position)); }
      else if (p.type === "leave") light(null);
      else if (p.type === "drop") {
        const el = at(p.position);
        const who = chipAt(el, p.position)?.getAttribute("data-voice-person") ?? undefined;
        light(null);
        const id = el?.getAttribute("data-shot-id");
        if (id && audioFiles(p.paths).length) onDrop(id, p.paths, who);
      }
    }).then((f) => { if (live) un = f; else f(); }).catch(() => {});
    return () => { live = false; light(null); pick(null, null); un?.(); };
  }, [enabled, onDrop]);
}

const castCache = new Map<string, CastStatus>();
const castBusy = new Map<string, Promise<CastStatus>>();

/** The voices given to the film's people with ElevenLabs (one shared load, no call to ElevenLabs itself: that is only the Voiceover screen's plan line). Reloads when voices change anywhere. */
export function useCast(dir: string | null): { cast: CastStatus | null; reload: () => void } {
  const [cast, setCast] = useState<CastStatus | null>(dir ? castCache.get(dir) ?? null : null);
  const reload = useCallback(() => {
    if (!dir) return;
    const p = castBusy.get(dir) ?? api.castVoice("status", dir).finally(() => castBusy.delete(dir));
    castBusy.set(dir, p);
    p.then((r) => { castCache.set(dir, r); setCast(r); }).catch(() => {});
  }, [dir]);
  useEffect(() => { reload(); window.addEventListener(VOICE_EVENT, reload); return () => window.removeEventListener(VOICE_EVENT, reload); }, [reload]);
  return { cast, reload };
}
