import { useEffect, useRef, useState } from "react";
import { peaksOf } from "./voiceLogic";

const BARS = 96;
const cache = new Map<string, number[]>();

/** Decodes a recording once and keeps its outline; null when the file can't be read here (the audio player still works). */
async function outline(src: string): Promise<number[] | null> {
  const hit = cache.get(src);
  if (hit) return hit;
  const Ctx = typeof window !== "undefined" ? (window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext) : undefined;
  if (!Ctx) return null;
  const ctx = new Ctx();
  try {
    const buf = await ctx.decodeAudioData(await (await fetch(src)).arrayBuffer());
    const a = buf.getChannelData(0), b = buf.numberOfChannels > 1 ? buf.getChannelData(1) : null;
    const mono = b ? a.map((v, i) => (Math.abs(v) > Math.abs(b[i]) ? v : b[i])) : a;
    const p = peaksOf(mono, BARS);
    cache.set(src, p);
    return p;
  } catch { return null; }
  finally { void ctx.close().catch(() => {}); }
}

/** The shape of a recording as thin bars, drawn when the row scrolls into view. Decorative: the audio player beside it is the control. */
export function Waveform({ src }: { src: string }) {
  const box = useRef<HTMLDivElement | null>(null);
  const [peaks, setPeaks] = useState<number[] | null>(cache.get(src) ?? null);
  useEffect(() => {
    const el = box.current;
    if (!el || peaks) return;
    let dead = false;
    const go = () => { void outline(src).then((p) => { if (!dead && p) setPeaks(p); }); };
    if (typeof IntersectionObserver !== "function") { go(); return () => { dead = true; }; }
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { io.disconnect(); go(); } });
    io.observe(el);
    return () => { dead = true; io.disconnect(); };
  }, [src, peaks]);
  return (
    <div className={`vo-wave ${peaks ? "has" : ""}`} ref={box} aria-hidden="true">
      {peaks && <svg viewBox={`0 0 ${BARS * 3} 32`} preserveAspectRatio="none" focusable="false">
        {peaks.map((v, i) => { const h = Math.max(1.5, v * 30); return <rect key={i} x={i * 3} y={16 - h / 2} width={2} height={h} rx={1} />; })}
      </svg>}
    </div>
  );
}
