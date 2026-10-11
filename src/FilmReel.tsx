import { useEffect, useRef } from "react";
import { aimAt, coneLength, framesFor, lookTarget, onOrbit, orbitFor, playhead, seeded, sees, timelineFor, turnToward, type BoardFrame, type Pt } from "./blueprint";

const GOLD = "232,180,92";
const ICE = "159,184,232";
const MONO = "ui-monospace, 'Cascadia Mono', Consolas, monospace";

type Frame = BoardFrame & { flash: number };

/**
 * The Home screen's director's board: a fine blueprint grid, an orbit with two cameras riding it and sweeping their cones across the room, four storyboard frames in four different shapes
 * (square, ultra-wide, vertical, widescreen) that light up as a camera takes them in, and a timeline with a playhead. Drag a story over the card and it quickens and glows.
 * Still (one frame) with reduced motion; it stops when the window is hidden.
 */
export function FilmReel({ active }: { active: boolean }) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const fast = useRef(active);
  fast.current = active;

  useEffect(() => {
    const cv = canvas.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const reduce = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, raf = 0, last = 0, clock = 0, glow = 0;
    let frames: Frame[] = [];
    let marks: { x: number; y: number; kind: number }[] = [];
    let angle = [0.55, Math.PI + 0.55];
    let aims: number[] | null = null;                                   // where each camera is looking now (it swings smoothly)

    const layout = () => {
      const r = cv.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = Math.max(1, Math.round(r.width)); h = Math.max(1, Math.round(r.height));
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      frames = framesFor(w, h).map((f) => ({ ...f, flash: 0 }));
      const rnd = seeded(11);
      marks = Array.from({ length: 9 }, () => ({ x: 20 + rnd() * (w - 40), y: 20 + rnd() * (h - 40), kind: Math.floor(rnd() * 3) }));
    };

    /** What a frame shows: a small dark scene, drawn to whatever shape the frame has. */
    const scene = (f: Frame) => {
      ctx.save();
      ctx.beginPath(); ctx.rect(f.x, f.y, f.w, f.h); ctx.clip();
      const sky = ctx.createLinearGradient(0, f.y, 0, f.y + f.h);
      sky.addColorStop(0, "#0c1424"); sky.addColorStop(1, "#070a10");
      ctx.fillStyle = sky; ctx.fillRect(f.x, f.y, f.w, f.h);
      const X = (u: number) => f.x + u * f.w, Y = (v: number) => f.y + v * f.h;
      ctx.fillStyle = "#0f192b";
      if (f.scene === "coast") {
        ctx.beginPath(); ctx.moveTo(X(0), Y(0.72)); ctx.lineTo(X(0.14), Y(0.4)); ctx.lineTo(X(0.26), Y(0.58)); ctx.lineTo(X(0.46), Y(0.22)); ctx.lineTo(X(0.66), Y(0.62)); ctx.lineTo(X(0.82), Y(0.36)); ctx.lineTo(X(1), Y(0.72)); ctx.lineTo(X(1), Y(1)); ctx.lineTo(X(0), Y(1)); ctx.closePath(); ctx.fill();
        ctx.fillStyle = "#091019"; ctx.fillRect(X(0), Y(0.74), f.w, f.h * 0.26);
        ctx.strokeStyle = `rgba(${ICE},0.22)`; ctx.lineWidth = 0.6;
        for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.moveTo(X(0.12 + i * 0.1), Y(0.82 + i * 0.05)); ctx.lineTo(X(0.52 + i * 0.1), Y(0.82 + i * 0.05)); ctx.stroke(); }
      } else if (f.scene === "arch") {
        ctx.fillStyle = "#0b1321"; ctx.fillRect(X(0.12), Y(0.08), f.w * 0.76, f.h * 0.92);
        ctx.fillStyle = "#04060a"; ctx.beginPath(); ctx.moveTo(X(0.26), Y(1)); ctx.lineTo(X(0.26), Y(0.34)); ctx.quadraticCurveTo(X(0.5), Y(0.02), X(0.74), Y(0.34)); ctx.lineTo(X(0.74), Y(1)); ctx.closePath(); ctx.fill();
        ctx.fillStyle = `rgba(${GOLD},0.6)`; ctx.fillRect(X(0.465), Y(0.62), f.w * 0.07, f.h * 0.26); ctx.beginPath(); ctx.arc(X(0.5), Y(0.57), f.w * 0.05, 0, Math.PI * 2); ctx.fill();
      } else if (f.scene === "city") {
        const rnd = seeded(5);
        for (let i = 0; i < 11; i++) {
          const bw = 0.07 + rnd() * 0.05, bh = 0.25 + rnd() * 0.55, bx = i * 0.092;
          ctx.fillStyle = "#0d1727"; ctx.fillRect(X(bx), Y(1 - bh), f.w * bw, f.h * bh);
          ctx.fillStyle = `rgba(${GOLD},0.5)`;
          for (let k = 0; k < 3; k++) if (rnd() > 0.5) ctx.fillRect(X(bx + 0.02), Y(1 - bh + 0.08 + k * 0.13), 1.6, 1.6);
        }
      } else {
        ctx.fillStyle = "#091019"; ctx.fillRect(X(0), Y(0.66), f.w, f.h * 0.34);
        ctx.strokeStyle = `rgba(${ICE},0.26)`; ctx.lineWidth = 0.6;
        for (const u of [0.1, 0.4, 0.6, 0.9]) { ctx.beginPath(); ctx.moveTo(X(0.5), Y(0.66)); ctx.lineTo(X(u), Y(1)); ctx.stroke(); }
        ctx.fillStyle = "#04060a"; ctx.fillRect(X(0.5), Y(0.4), f.w * 0.05, f.h * 0.26); ctx.beginPath(); ctx.arc(X(0.525), Y(0.37), f.w * 0.035, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
    };

    /** A frame: the scene, four corner ticks (not a box), and its name and shape beneath. It lights up gold when a camera has it in view. */
    const frameBox = (f: Frame) => {
      scene(f);
      const on = f.flash > 0.05;
      const k = 8, g = 4;
      ctx.strokeStyle = on ? `rgba(${GOLD},${0.55 + f.flash * 0.4})` : "rgba(244,247,250,0.34)"; ctx.lineWidth = 1;
      ctx.beginPath();
      for (const [cx, cy, sx, sy] of [[f.x - g, f.y - g, 1, 1], [f.x + f.w + g, f.y - g, -1, 1], [f.x - g, f.y + f.h + g, 1, -1], [f.x + f.w + g, f.y + f.h + g, -1, -1]] as const) {
        ctx.moveTo(cx + sx * k, cy); ctx.lineTo(cx, cy); ctx.lineTo(cx, cy + sy * k);
      }
      ctx.stroke();
      ctx.font = `500 8.5px ${MONO}`;
      ctx.fillStyle = on ? `rgba(${GOLD},0.95)` : "rgba(244,247,250,0.4)";
      ctx.fillText(f.label, f.x - g, f.y + f.h + 18);
      ctx.fillStyle = on ? `rgba(${GOLD},0.75)` : "rgba(159,184,232,0.55)";
      const rw = ctx.measureText(f.ratio).width;
      ctx.fillText(f.ratio, f.x + f.w + g - rw, f.y + f.h + 18);
      if (on) { ctx.fillStyle = `rgba(${GOLD},${f.flash * 0.09})`; ctx.fillRect(f.x, f.y, f.w, f.h); }
    };

    const camera = (p: Pt, aim: number, label: string, now: number) => {
      const fov = 0.4;
      const len = coneLength(w, h);
      const g = ctx.createRadialGradient(p.x, p.y, 2, p.x, p.y, len);
      g.addColorStop(0, `rgba(${GOLD},${0.3 + glow * 0.22})`); g.addColorStop(1, `rgba(${GOLD},0)`);
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.arc(p.x, p.y, len, aim - fov / 2, aim + fov / 2); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = `rgba(${GOLD},0.22)`; ctx.lineWidth = 0.6;
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + Math.cos(aim - fov / 2) * len, p.y + Math.sin(aim - fov / 2) * len); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + Math.cos(aim + fov / 2) * len, p.y + Math.sin(aim + fov / 2) * len); ctx.stroke();
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(aim);
      ctx.fillStyle = "rgba(9,12,18,0.97)"; ctx.strokeStyle = `rgba(${GOLD},0.9)`; ctx.lineWidth = 0.9;
      ctx.beginPath(); ctx.roundRect(-7, -4.5, 11, 9, 1.6); ctx.fill(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(4, -2.6); ctx.lineTo(9.5, -5); ctx.lineTo(9.5, 5); ctx.lineTo(4, 2.6); ctx.closePath(); ctx.fillStyle = `rgba(${GOLD},0.92)`; ctx.fill();
      ctx.restore();
      ctx.font = `600 8.5px ${MONO}`; ctx.fillStyle = "rgba(244,247,250,0.62)";
      ctx.fillText(label, p.x - 16, p.y - 13);
      if (Math.floor(now * 1.5) % 2 === 0 || fast.current) { ctx.fillStyle = "rgba(255,92,72,0.9)"; ctx.beginPath(); ctx.arc(p.x + 24, p.y - 15.5, 1.7, 0, Math.PI * 2); ctx.fill(); }
    };

    const frame = (nowMs: number) => {
      const t = nowMs / 1000;
      const dt = Math.min(0.05, last ? t - last : 0.016);
      last = t; clock += dt;
      glow += ((fast.current ? 1 : 0) - glow) * Math.min(1, dt * 3);
      const k = 1 + glow * 1.6;
      angle = [angle[0] + dt * 0.15 * k, angle[1] + dt * 0.15 * k];
      ctx.clearRect(0, 0, w, h);

      // the blueprint: a fine dot grid and a few marks
      ctx.fillStyle = "rgba(159,184,232,0.06)";
      for (let x = 14; x < w; x += 32) for (let y = 14; y < h; y += 32) ctx.fillRect(x, y, 1, 1);
      ctx.strokeStyle = "rgba(159,184,232,0.1)"; ctx.lineWidth = 0.6;
      for (const m of marks) {
        if (m.kind === 0) { ctx.beginPath(); ctx.moveTo(m.x - 4, m.y); ctx.lineTo(m.x + 4, m.y); ctx.moveTo(m.x, m.y - 4); ctx.lineTo(m.x, m.y + 4); ctx.stroke(); }
        else if (m.kind === 1) ctx.strokeRect(m.x - 2.5, m.y - 2.5, 5, 5);
        else { ctx.beginPath(); ctx.arc(m.x, m.y, 2, 0, Math.PI * 2); ctx.stroke(); }
      }

      // the orbit: a hairline and a dashed gold path
      const o = orbitFor(w, h);
      ctx.save(); ctx.translate(o.cx, o.cy); ctx.rotate(o.rot);
      ctx.strokeStyle = "rgba(159,184,232,0.14)"; ctx.lineWidth = 0.7; ctx.beginPath(); ctx.ellipse(0, 0, o.rx, o.ry, 0, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = `rgba(${GOLD},${0.26 + glow * 0.25})`; ctx.lineWidth = 0.9; ctx.setLineDash([5, 9]); ctx.lineDashOffset = -clock * 12 * k;
      ctx.beginPath(); ctx.ellipse(0, 0, o.rx * 1.04, o.ry * 1.055, 0, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
      ctx.restore();

      const middle = { x: w / 2, y: h * 0.5 };
      const cams = [onOrbit(o, angle[0]), onOrbit(o, angle[1])];
      const want = cams.map((c) => aimAt(c, lookTarget(c, frames, coneLength(w, h) * 1.5, middle)));
      aims = aims ? aims.map((a, i) => turnToward(a, want[i], dt * (fast.current ? 4 : 2.4))) : want;
      cams.forEach((c, i) => {
        for (const f of frames) { const mid = { x: f.x + f.w / 2, y: f.y + f.h / 2 }; if (Math.hypot(mid.x - c.x, mid.y - c.y) <= coneLength(w, h) * 1.3 && sees(c, aims![i], 0.4, mid)) f.flash = Math.min(1, f.flash + dt * 3.2); }
      });
      for (const f of frames) { f.flash = Math.max(0, f.flash - dt * (fast.current ? 0.9 : 0.5)); frameBox(f); }
      cams.forEach((c, i) => camera(c, aims![i], i === 0 ? "CAM A" : "CAM B", clock));

      // the timeline: fine ticks, clips and the playhead
      const tl = timelineFor(w, h);
      ctx.strokeStyle = "rgba(159,184,232,0.2)"; ctx.lineWidth = 0.7; ctx.beginPath(); ctx.moveTo(tl.x0, tl.y); ctx.lineTo(tl.x1, tl.y); ctx.stroke();
      for (let x = tl.x0; x <= tl.x1; x += 12) { ctx.beginPath(); ctx.moveTo(x, tl.y - ((x - tl.x0) % 60 < 1 ? 5 : 2.5)); ctx.lineTo(x, tl.y); ctx.stroke(); }
      ctx.fillStyle = `rgba(${GOLD},0.22)`;
      for (const [a, b] of [[0.03, 0.2], [0.22, 0.46], [0.49, 0.64], [0.67, 0.97]]) ctx.fillRect(tl.x0 + (tl.x1 - tl.x0) * a, tl.y + 5, (tl.x1 - tl.x0) * (b - a) - 3, 3);
      ctx.fillStyle = `rgba(${GOLD},0.9)`; ctx.beginPath(); ctx.arc(tl.x0, tl.y, 2.4, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `rgba(${ICE},0.85)`; ctx.beginPath(); ctx.arc(tl.x1, tl.y, 2.4, 0, Math.PI * 2); ctx.fill();
      const px = playhead(tl, clock * k);
      ctx.strokeStyle = `rgba(${GOLD},0.85)`; ctx.lineWidth = 0.9; ctx.beginPath(); ctx.moveTo(px, tl.y - 9); ctx.lineTo(px, tl.y + 11); ctx.stroke();
      ctx.fillStyle = `rgba(${GOLD},0.95)`; ctx.beginPath(); ctx.moveTo(px - 3.4, tl.y - 13); ctx.lineTo(px + 3.4, tl.y - 13); ctx.lineTo(px, tl.y - 8); ctx.closePath(); ctx.fill();
      if (!reduce) raf = requestAnimationFrame(frame);
    };

    layout();
    const ro = typeof ResizeObserver === "function" ? new ResizeObserver(() => { layout(); if (reduce) frame(performance.now()); }) : null;
    ro?.observe(cv);
    if (reduce) { clock = 5; frame(performance.now()); }
    else raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro?.disconnect(); };
  }, []);

  return (
    <div className={`reel ${active ? "fast" : ""}`} aria-hidden="true">
      <canvas ref={canvas} className="reel-canvas" />
      <div className="reel-vignette" />
    </div>
  );
}
