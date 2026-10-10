import { useEffect, useRef } from "react";
import { aimAt, coneLength, framesFor, onOrbit, orbitFor, playhead, seeded, sees, timelineFor, type Pt, type Rect } from "./blueprint";

const GOLD = "232,180,92";
const ICE = "159,184,232";

type Frame = Rect & { label: string; scene: "coast" | "arch" | "city" | "platform"; flash: number };

/**
 * The Home screen's director's board: a blueprint grid, an orbit with two cameras riding it and sweeping their cones across the room, storyboard frames that flash as a camera takes them in,
 * and a timeline with a playhead along the bottom. Drag a story over the card and it quickens and glows. Still (one frame) with reduced motion; it stops when the window is hidden.
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
    let angle = [0.5, Math.PI + 0.5];

    const layout = () => {
      const r = cv.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = Math.max(1, Math.round(r.width)); h = Math.max(1, Math.round(r.height));
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      frames = framesFor(w, h).map((f) => ({ ...f, flash: 0 }));
      const rnd = seeded(11);
      marks = Array.from({ length: 16 }, () => ({ x: rnd() * w, y: rnd() * h, kind: Math.floor(rnd() * 3) }));
    };

    const scene = (f: Frame) => {
      ctx.save();
      ctx.beginPath(); ctx.rect(f.x, f.y, f.w, f.h); ctx.clip();
      const sky = ctx.createLinearGradient(0, f.y, 0, f.y + f.h);
      sky.addColorStop(0, "#0d1626"); sky.addColorStop(1, "#070a10");
      ctx.fillStyle = sky; ctx.fillRect(f.x, f.y, f.w, f.h);
      const X = (u: number) => f.x + u * f.w, Y = (v: number) => f.y + v * f.h;
      ctx.fillStyle = "#101b2d";
      if (f.scene === "coast") {
        ctx.beginPath(); ctx.moveTo(X(0), Y(0.7)); ctx.lineTo(X(0.18), Y(0.38)); ctx.lineTo(X(0.3), Y(0.55)); ctx.lineTo(X(0.5), Y(0.28)); ctx.lineTo(X(0.7), Y(0.6)); ctx.lineTo(X(0.86), Y(0.44)); ctx.lineTo(X(1), Y(0.7)); ctx.lineTo(X(1), Y(1)); ctx.lineTo(X(0), Y(1)); ctx.closePath(); ctx.fill();
        ctx.fillStyle = "#0a111d"; ctx.fillRect(X(0), Y(0.72), f.w, f.h * 0.28);
        ctx.strokeStyle = `rgba(${ICE},0.25)`; ctx.lineWidth = 0.6;
        for (let i = 0; i < 4; i++) { ctx.beginPath(); ctx.moveTo(X(0.1 + i * 0.1), Y(0.8 + i * 0.04)); ctx.lineTo(X(0.5 + i * 0.1), Y(0.8 + i * 0.04)); ctx.stroke(); }
      } else if (f.scene === "arch") {
        ctx.fillStyle = "#0c1422"; ctx.fillRect(X(0.2), Y(0.12), f.w * 0.6, f.h * 0.88);
        ctx.fillStyle = "#04060a"; ctx.beginPath(); ctx.moveTo(X(0.34), Y(1)); ctx.lineTo(X(0.34), Y(0.4)); ctx.quadraticCurveTo(X(0.5), Y(0.12), X(0.66), Y(0.4)); ctx.lineTo(X(0.66), Y(1)); ctx.closePath(); ctx.fill();
        ctx.fillStyle = `rgba(${GOLD},0.55)`; ctx.fillRect(X(0.485), Y(0.58), f.w * 0.03, f.h * 0.3); ctx.beginPath(); ctx.arc(X(0.5), Y(0.54), f.w * 0.022, 0, Math.PI * 2); ctx.fill();
      } else if (f.scene === "city") {
        const rnd = seeded(5);
        for (let i = 0; i < 12; i++) {
          const bw = 0.06 + rnd() * 0.05, bh = 0.25 + rnd() * 0.55, bx = i * 0.085;
          ctx.fillStyle = "#0e1829"; ctx.fillRect(X(bx), Y(1 - bh), f.w * bw, f.h * bh);
          ctx.fillStyle = `rgba(${GOLD},0.5)`;
          for (let k = 0; k < 3; k++) if (rnd() > 0.5) ctx.fillRect(X(bx + 0.015), Y(1 - bh + 0.08 + k * 0.12), 2, 2);
        }
      } else {
        ctx.fillStyle = "#0a111d"; ctx.fillRect(X(0), Y(0.66), f.w, f.h * 0.34);
        ctx.strokeStyle = `rgba(${ICE},0.28)`; ctx.lineWidth = 0.7;
        for (const u of [0.1, 0.4, 0.6, 0.9]) { ctx.beginPath(); ctx.moveTo(X(0.5), Y(0.66)); ctx.lineTo(X(u), Y(1)); ctx.stroke(); }
        ctx.fillStyle = "#04060a"; ctx.fillRect(X(0.52), Y(0.42), f.w * 0.035, f.h * 0.26); ctx.beginPath(); ctx.arc(X(0.5375), Y(0.39), f.w * 0.024, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
    };

    const frameBox = (f: Frame) => {
      scene(f);
      const a = 0.34 + f.flash * 0.6;
      ctx.strokeStyle = f.flash > 0.05 ? `rgba(${GOLD},${a})` : "rgba(244,247,250,0.26)"; ctx.lineWidth = 0.8;
      ctx.strokeRect(f.x, f.y, f.w, f.h);
      ctx.strokeStyle = "rgba(244,247,250,0.12)"; ctx.strokeRect(f.x - 7, f.y - 7, f.w + 14, f.h + 14);
      ctx.fillStyle = f.flash > 0.05 ? `rgba(${GOLD},0.95)` : "rgba(244,247,250,0.38)"; ctx.font = "500 9px system-ui, sans-serif";
      ctx.fillText(f.label, f.x + f.w - 38, f.y + f.h + 17);
      if (f.flash > 0.05) { ctx.fillStyle = `rgba(${GOLD},${f.flash * 0.1})`; ctx.fillRect(f.x, f.y, f.w, f.h); }
    };

    const camera = (p: Pt, aim: number, label: string, now: number) => {
      const fov = 0.5;
      const len = coneLength(w, h);
      const g = ctx.createRadialGradient(p.x, p.y, 2, p.x, p.y, len);
      g.addColorStop(0, `rgba(${GOLD},${0.36 + glow * 0.25})`); g.addColorStop(1, `rgba(${GOLD},0)`);
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.arc(p.x, p.y, len, aim - fov / 2, aim + fov / 2); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = `rgba(${GOLD},0.35)`; ctx.lineWidth = 0.7;
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + Math.cos(aim - fov / 2) * len, p.y + Math.sin(aim - fov / 2) * len); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + Math.cos(aim + fov / 2) * len, p.y + Math.sin(aim + fov / 2) * len); ctx.stroke();
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(aim);
      ctx.fillStyle = "rgba(10,13,19,0.96)"; ctx.strokeStyle = `rgba(${GOLD},0.95)`; ctx.lineWidth = 1.1;
      ctx.beginPath(); ctx.roundRect(-9, -5.5, 14, 11, 2); ctx.fill(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(5, -3.2); ctx.lineTo(12, -6.4); ctx.lineTo(12, 6.4); ctx.lineTo(5, 3.2); ctx.closePath(); ctx.fillStyle = `rgba(${GOLD},0.95)`; ctx.fill();
      ctx.restore();
      ctx.fillStyle = "rgba(244,247,250,0.72)"; ctx.font = "600 10px system-ui, sans-serif";
      ctx.fillText(label, p.x - 20, p.y - 17);
      if (Math.floor(now * 1.5) % 2 === 0 || fast.current) { ctx.fillStyle = "rgba(255,92,72,0.95)"; ctx.beginPath(); ctx.arc(p.x + 28, p.y - 20, 2, 0, Math.PI * 2); ctx.fill(); }
    };

    const frame = (nowMs: number) => {
      const t = nowMs / 1000;
      const dt = Math.min(0.05, last ? t - last : 0.016);
      last = t; clock += dt;
      glow += ((fast.current ? 1 : 0) - glow) * Math.min(1, dt * 3);
      const k = 1 + glow * 1.6;
      angle = [angle[0] + dt * 0.16 * k, angle[1] + dt * 0.16 * k];
      ctx.clearRect(0, 0, w, h);

      // the blueprint: dots, crosshairs and hairlines
      ctx.fillStyle = "rgba(159,184,232,0.075)";
      for (let x = 12; x < w; x += 28) for (let y = 12; y < h; y += 28) ctx.fillRect(x, y, 1, 1);
      ctx.strokeStyle = "rgba(159,184,232,0.1)"; ctx.lineWidth = 0.7;
      for (const m of marks) {
        if (m.kind === 0) { ctx.beginPath(); ctx.moveTo(m.x - 6, m.y); ctx.lineTo(m.x + 6, m.y); ctx.moveTo(m.x, m.y - 6); ctx.lineTo(m.x, m.y + 6); ctx.stroke(); }
        else if (m.kind === 1) ctx.strokeRect(m.x - 3, m.y - 3, 6, 6);
        else { ctx.beginPath(); ctx.arc(m.x, m.y, 2.5, 0, Math.PI * 2); ctx.stroke(); }
      }
      ctx.strokeStyle = "rgba(159,184,232,0.045)";
      ctx.beginPath(); ctx.moveTo(0, h * 0.34); ctx.lineTo(w, h * 0.34); ctx.moveTo(0, h * 0.74); ctx.lineTo(w, h * 0.74); ctx.moveTo(w * 0.12, 0); ctx.lineTo(w * 0.12, h); ctx.moveTo(w * 0.88, 0); ctx.lineTo(w * 0.88, h); ctx.stroke();

      // the orbit: a hairline and a dashed gold path
      const o = orbitFor(w, h);
      ctx.save(); ctx.translate(o.cx, o.cy); ctx.rotate(o.rot);
      ctx.strokeStyle = "rgba(159,184,232,0.16)"; ctx.lineWidth = 0.8; ctx.beginPath(); ctx.ellipse(0, 0, o.rx, o.ry, 0, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = `rgba(${GOLD},${0.3 + glow * 0.25})`; ctx.lineWidth = 1; ctx.setLineDash([7, 9]); ctx.lineDashOffset = -clock * 14 * k;
      ctx.beginPath(); ctx.ellipse(0, 0, o.rx * 1.035, o.ry * 1.05, 0, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
      ctx.restore();

      const target = { x: w / 2, y: h * 0.5 };
      const cams = [onOrbit(o, angle[0]), onOrbit(o, angle[1])];
      for (const c of cams) {
        const aim = aimAt(c, target);
        for (const f of frames) { const mid = { x: f.x + f.w / 2, y: f.y + f.h / 2 }; if (Math.hypot(mid.x - c.x, mid.y - c.y) <= coneLength(w, h) * 1.25 && sees(c, aim, 0.5, mid)) f.flash = Math.min(1, f.flash + dt * 3.2); }
      }
      for (const f of frames) { f.flash = Math.max(0, f.flash - dt * (fast.current ? 0.9 : 0.5)); frameBox(f); }
      cams.forEach((c, i) => camera(c, aimAt(c, target), i === 0 ? "CAM A" : "CAM B", clock));

      // the timeline: ticks, clips and the playhead
      const tl = timelineFor(w, h);
      ctx.strokeStyle = "rgba(159,184,232,0.22)"; ctx.lineWidth = 0.8; ctx.beginPath(); ctx.moveTo(tl.x0, tl.y); ctx.lineTo(tl.x1, tl.y); ctx.stroke();
      for (let x = tl.x0; x <= tl.x1; x += 14) { ctx.beginPath(); ctx.moveTo(x, tl.y - ((x - tl.x0) % 70 < 1 ? 6 : 3)); ctx.lineTo(x, tl.y); ctx.stroke(); }
      ctx.fillStyle = `rgba(${GOLD},0.2)`;
      for (const [a, b] of [[0.04, 0.18], [0.2, 0.42], [0.45, 0.6], [0.63, 0.95]]) ctx.fillRect(tl.x0 + (tl.x1 - tl.x0) * a, tl.y + 6, (tl.x1 - tl.x0) * (b - a) - 3, 5);
      ctx.fillStyle = `rgba(${GOLD},0.95)`; ctx.beginPath(); ctx.arc(tl.x0, tl.y, 3, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `rgba(${ICE},0.9)`; ctx.beginPath(); ctx.arc(tl.x1, tl.y, 3, 0, Math.PI * 2); ctx.fill();
      const px = playhead(tl, clock * k);
      ctx.strokeStyle = `rgba(${GOLD},0.9)`; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(px, tl.y - 12); ctx.lineTo(px, tl.y + 14); ctx.stroke();
      ctx.fillStyle = `rgba(${GOLD},0.95)`; ctx.beginPath(); ctx.moveTo(px - 4, tl.y - 16); ctx.lineTo(px + 4, tl.y - 16); ctx.lineTo(px, tl.y - 10); ctx.closePath(); ctx.fill();
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
