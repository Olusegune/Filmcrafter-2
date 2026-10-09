import { useEffect, useRef } from "react";

/**
 * The picture above "Drop a song here": a song turning into a film frame. A waveform shaped like a song (a quiet verse, a build, a chorus, a dip, a last chorus) sits inside viewfinder corners;
 * a playhead sweeps across it, and every bar lights up gold as it passes. The bars breathe at 120 BPM. Dragging a song over the card wakes it up: taller, brighter, a faster sweep.
 * It is drawn, not an image, so it is crisp at any size. Under "reduce motion" it stands still on one beautiful frame; it stops drawing while the window is hidden.
 */

export const BARS = 56;
const BEAT_S = 0.5;                      // 120 BPM
const SWEEP_S = 9;                       // one pass of the playhead
const SWEEP_S_ACTIVE = 4.5;

const bump = (x: number, c: number, w: number) => Math.exp(-(((x - c) / w) ** 2));

/** The loudness of a made-up song along its length, 0..1: verse, build, chorus, dip, final chorus. */
export function envelope(x: number): number {
  return Math.min(1, 0.22 + 0.2 * bump(x, 0.16, 0.12) + 0.45 * bump(x, 0.44, 0.1) + 0.2 * bump(x, 0.62, 0.07) + 0.78 * bump(x, 0.82, 0.12) - 0.1 * bump(x, 0.58, 0.04));
}

/** The height of each bar (0..1) at time t seconds. Deterministic: the same time gives the same picture. `awake` is a drag over the card. */
export function waveBars(t: number, n = BARS, awake = false): number[] {
  const beat = Math.max(0, Math.cos((2 * Math.PI * t) / BEAT_S)) ** 6;           // a short pulse on every beat
  const lift = awake ? 1.3 : 1;
  return Array.from({ length: n }, (_, i) => {
    const e = envelope(i / (n - 1));
    const wobble = 0.5 + 0.5 * Math.sin(t * (1.15 + 0.11 * (i % 5)) + i * 0.93);
    const h = e * (0.3 + 0.7 * wobble) * (1 + 0.07 * beat) * lift;
    return Math.max(0.04, Math.min(1, h));
  });
}

/** Where the playhead is along the wave (0..1) at time t. */
export function playheadAt(t: number, awake = false): number {
  const period = awake ? SWEEP_S_ACTIVE : SWEEP_S;
  return (t % period) / period;
}

type Colours = { gold: string; signal: string; dim: string };

function draw(ctx: CanvasRenderingContext2D, w: number, h: number, t: number, awake: boolean, c: Colours) {
  ctx.clearRect(0, 0, w, h);
  const pad = 14, bw = (w - pad * 2) / BARS, mid = h / 2, maxH = h - pad * 2;
  const bars = waveBars(t, BARS, awake);
  const head = playheadAt(t, awake);
  const hx = pad + head * (w - pad * 2);
  bars.forEach((v, i) => {
    const x = pad + i * bw, bh = v * maxH, passed = x + bw / 2 <= hx;
    const near = Math.max(0, 1 - Math.abs(x + bw / 2 - hx) / 38);                 // a soft glow around the playhead
    ctx.globalAlpha = passed ? (awake ? 1 : 0.92) : 0.38 + 0.4 * near;
    ctx.fillStyle = passed ? c.gold : near > 0 ? c.signal : c.dim;
    const r = Math.min(bw * 0.3, 2);
    const rw = Math.max(1.5, bw * 0.56), rx = x + (bw - rw) / 2, ry = mid - bh / 2;
    ctx.beginPath();
    ctx.roundRect ? ctx.roundRect(rx, ry, rw, bh, r) : ctx.rect(rx, ry, rw, bh);
    ctx.fill();
  });
  ctx.globalAlpha = 1;
  // the playhead, as in the Studio: a thin line and a small triangle
  ctx.strokeStyle = c.signal; ctx.fillStyle = c.signal; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(hx, pad - 2); ctx.lineTo(hx, h - pad + 2); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(hx - 4, pad - 7); ctx.lineTo(hx + 4, pad - 7); ctx.lineTo(hx, pad - 1); ctx.closePath(); ctx.fill();
  // viewfinder corners: the song becoming a frame
  ctx.strokeStyle = c.gold; ctx.globalAlpha = awake ? 0.95 : 0.6; ctx.lineWidth = 1.6; ctx.lineCap = "round";
  const L = 12, o = 3;
  for (const [x, y, dx, dy] of [[o, o, 1, 1], [w - o, o, -1, 1], [o, h - o, 1, -1], [w - o, h - o, -1, -1]] as const) {
    ctx.beginPath(); ctx.moveTo(x, y + dy * L); ctx.lineTo(x, y); ctx.lineTo(x + dx * L, y); ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

export function LivingWave({ active = false, width = 360, height = 96 }: { active?: boolean; width?: number; height?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const awake = useRef(active);
  awake.current = active;
  useEffect(() => {
    const cv = ref.current;
    const ctx = cv?.getContext?.("2d");
    if (!cv || !ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    cv.width = width * dpr; cv.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const css = getComputedStyle(cv);
    const colours: Colours = { gold: css.getPropertyValue("--gold").trim() || "#e8b45c", signal: css.getPropertyValue("--signal").trim() || "#64b7ff", dim: css.getPropertyValue("--smoke").trim() || "#8a94a3" };
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (still) { draw(ctx, width, height, 3.4, false, colours); return; }
    let raf = 0, last = performance.now(), t = 3.4, wake = 0;
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      if (document.hidden) { last = now; return; }                                    // nothing to draw for a window nobody can see
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      wake += ((awake.current ? 1 : 0) - wake) * Math.min(1, dt * 6);                  // ease into and out of the awake look
      t += dt * (1 + 0.8 * wake);
      draw(ctx, width, height, t, wake > 0.5, colours);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [width, height]);
  return <canvas ref={ref} className="living-wave" style={{ width, height }} role="img" aria-label="A song turning into a film frame: a waveform with a playhead sweeping across it" />;
}
