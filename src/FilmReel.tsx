import { useEffect, useRef } from "react";
import { at, beside, follow, makeTrack, seeded, turnToward, type Pt, type Track } from "./chase";

const GOLD = "232,180,92";

type Rig = { pos: Pt; angle: number; label: string; kind: "pan" | "chase"; home: Pt | null; side: number; ahead: number };

/**
 * The Home screen's chase: a gold car with two pursuers on a looping night road, and camera rigs that follow it: two on tripods that pan with it, one drone that flies alongside.
 * Drag a story over the card and everything speeds up and locks on. Still (one frame) with reduced motion; it stops when the window is hidden.
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
    let w = 0, h = 0, track: Track = makeTrack(10, 10);
    let blocks: { x: number; y: number; w: number; h: number }[] = [];
    let rigs: Rig[] = [];
    let dist = 0, speed = 46, last = 0, raf = 0, clock = 0;
    const trail: Pt[] = [];

    const layout = () => {
      const r = cv.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = Math.max(1, Math.round(r.width)); h = Math.max(1, Math.round(r.height));
      cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      track = makeTrack(w, h);
      const rnd = seeded(7);
      blocks = Array.from({ length: 34 }, () => ({ x: rnd() * w, y: rnd() * h, w: 18 + rnd() * 46, h: 14 + rnd() * 38 }));
      const lead = at(track, dist);
      rigs = [
        { pos: { x: w * 0.07, y: h * 0.5 }, angle: 0, label: "A", kind: "pan", home: { x: w * 0.07, y: h * 0.5 }, side: 0, ahead: 0 },
        { pos: { x: w * 0.93, y: h * 0.5 }, angle: Math.PI, label: "B", kind: "pan", home: { x: w * 0.93, y: h * 0.5 }, side: 0, ahead: 0 },
        { pos: beside(lead, 34, -20), angle: lead.angle, label: "C", kind: "chase", home: null, side: 34, ahead: -26 },
      ];
      trail.length = 0;
    };

    const car = (p: Pt & { angle: number }, body: string, glow: number) => {
      ctx.save();
      ctx.translate(p.x, p.y); ctx.rotate(p.angle); ctx.scale(1.45, 1.45);
      const cone = ctx.createLinearGradient(8, 0, 78, 0);                                    // headlights
      cone.addColorStop(0, `rgba(255,244,214,${0.5 * glow})`); cone.addColorStop(1, "rgba(255,244,214,0)");
      ctx.fillStyle = cone;
      ctx.beginPath(); ctx.moveTo(8, -3); ctx.lineTo(78, -20); ctx.lineTo(78, 20); ctx.lineTo(8, 3); ctx.closePath(); ctx.fill();
      ctx.fillStyle = body; ctx.strokeStyle = "rgba(244,247,250,0.28)"; ctx.lineWidth = 0.7;
      ctx.beginPath(); ctx.roundRect(-9, -4.2, 18, 8.4, 2.4); ctx.fill(); ctx.stroke();
      ctx.fillStyle = "rgba(10,12,16,0.7)"; ctx.fillRect(-2.5, -3, 6, 6);                      // roof and glass
      ctx.fillStyle = "rgba(255,92,72,0.95)"; ctx.fillRect(-9.2, -3.4, 1.6, 1.8); ctx.fillRect(-9.2, 1.6, 1.6, 1.8);   // tail lights
      ctx.restore();
    };

    const rig = (r: Rig, target: Pt, now: number) => {
      const fov = r.kind === "chase" ? 0.5 : 0.62;
      ctx.save();
      const g = ctx.createRadialGradient(r.pos.x, r.pos.y, 2, r.pos.x, r.pos.y, 150);               // the cone of view
      g.addColorStop(0, `rgba(${GOLD},0.26)`); g.addColorStop(1, `rgba(${GOLD},0)`);
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.moveTo(r.pos.x, r.pos.y);
      ctx.arc(r.pos.x, r.pos.y, 150, r.angle - fov / 2, r.angle + fov / 2); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = `rgba(${GOLD},${fast.current ? 0.55 : 0.28})`; ctx.setLineDash([2, 5]); ctx.lineWidth = 0.8;      // the line it holds to the car
      ctx.beginPath(); ctx.moveTo(r.pos.x, r.pos.y); ctx.lineTo(target.x, target.y); ctx.stroke(); ctx.setLineDash([]);
      ctx.translate(r.pos.x, r.pos.y); ctx.rotate(r.angle);
      ctx.fillStyle = "rgba(14,17,23,0.95)"; ctx.strokeStyle = `rgba(${GOLD},0.85)`; ctx.lineWidth = 1;
      if (r.kind === "chase") { ctx.beginPath(); ctx.arc(0, 0, 5.2, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }          // a drone: a round body
      else { ctx.beginPath(); ctx.roundRect(-5.5, -4, 11, 8, 1.4); ctx.fill(); ctx.stroke(); }                               // a tripod camera: a box
      ctx.fillStyle = `rgba(${GOLD},0.95)`; ctx.beginPath(); ctx.moveTo(5.5, -2.4); ctx.lineTo(10, -4.4); ctx.lineTo(10, 4.4); ctx.lineTo(5.5, 2.4); ctx.closePath(); ctx.fill();   // the lens
      ctx.restore();
      ctx.fillStyle = "rgba(244,247,250,0.8)"; ctx.font = "600 10px system-ui, sans-serif";
      ctx.fillText(`CAM ${r.label}`, r.pos.x + 9, r.pos.y - 8);
      if (Math.floor(now * 1.6) % 2 === 0 || fast.current) { ctx.fillStyle = "rgba(255,92,72,0.95)"; ctx.beginPath(); ctx.arc(r.pos.x + 41, r.pos.y - 11, 2.2, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "rgba(244,247,250,0.55)"; ctx.fillText("REC", r.pos.x + 46, r.pos.y - 8); }
    };

    const frame = (now: number) => {
      const t = now / 1000;
      const dt = Math.min(0.05, last ? t - last : 0.016);
      last = t; clock += dt;
      const boost = fast.current ? 2.4 : 1;
      speed += ((46 * boost) - speed) * Math.min(1, dt * 2.2);
      dist += speed * dt;
      ctx.clearRect(0, 0, w, h);
      ctx.save();
      ctx.strokeStyle = "rgba(244,247,250,0.07)"; ctx.lineWidth = 0.8;                           // the city, as faint outlines
      for (const b of blocks) ctx.strokeRect(b.x, b.y, b.w, b.h);
      ctx.lineJoin = "round"; ctx.lineCap = "round";
      const road = () => { ctx.beginPath(); track.pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y))); ctx.closePath(); };
      road(); ctx.strokeStyle = "rgba(244,247,250,0.14)"; ctx.lineWidth = 34; ctx.stroke();
      road(); ctx.strokeStyle = "rgba(12,15,20,0.97)"; ctx.lineWidth = 32; ctx.stroke();
      road(); ctx.strokeStyle = `rgba(${GOLD},0.32)`; ctx.lineWidth = 1.2; ctx.setLineDash([10, 12]); ctx.lineDashOffset = -dist * 0.6; ctx.stroke(); ctx.setLineDash([]);
      ctx.restore();

      const lead = at(track, dist);
      trail.push({ x: lead.x - Math.cos(lead.angle) * 9, y: lead.y - Math.sin(lead.angle) * 9 });
      if (trail.length > 70) trail.shift();
      for (let i = 1; i < trail.length; i++) {                                                     // a trail of tail light
        ctx.strokeStyle = `rgba(255,92,72,${(i / trail.length) * 0.55})`; ctx.lineWidth = 1.6 * (i / trail.length) + 0.3;
        ctx.beginPath(); ctx.moveTo(trail[i - 1].x, trail[i - 1].y); ctx.lineTo(trail[i].x, trail[i].y); ctx.stroke();
      }
      car(at(track, dist - 78), "rgba(150,160,175,0.9)", 0.8);
      car(at(track, dist - 142), "rgba(120,130,145,0.9)", 0.7);
      car(lead, `rgb(${GOLD})`, 1);

      for (const r of rigs) {
        const target = r.kind === "chase" ? beside(lead, r.side, r.ahead) : r.home!;
        if (r.kind === "chase") r.pos = follow(r.pos, target, Math.min(1, dt * 3.2));            // the drone follows with a little lag
        const aim = Math.atan2(lead.y - r.pos.y, lead.x - r.pos.x);
        r.angle = turnToward(r.angle, aim, Math.min(1, dt * (fast.current ? 7 : 3.4)));          // the tripods pan with the car
        rig(r, lead, clock);
      }
      if (!reduce) raf = requestAnimationFrame(frame);
    };

    layout();
    const ro = typeof ResizeObserver === "function" ? new ResizeObserver(() => { layout(); if (reduce) frame(performance.now()); }) : null;
    ro?.observe(cv);
    if (reduce) { dist = track.total * 0.18; frame(performance.now()); }
    else raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro?.disconnect(); };
  }, []);

  return (
    <div className={`reel ${active ? "fast" : ""}`} aria-hidden="true">
      <canvas ref={canvas} className="reel-canvas" />
      <div className="reel-vignette" />
      <div className="reel-scan" />
    </div>
  );
}
