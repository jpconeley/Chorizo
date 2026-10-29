"use client";

import { useEffect, useRef } from "react";

// The 16 corners of a 4D hypercube, each coordinate ±1.
const VERTICES = Array.from({ length: 16 }, (_, i) =>
  [0, 1, 2, 3].map((bit) => ((i >> bit) & 1 ? 1 : -1)),
);
// Two corners share an edge when they differ in exactly one coordinate: 32 edges.
const EDGES: [number, number][] = [];
for (let a = 0; a < 16; a++) {
  for (let b = a + 1; b < 16; b++) {
    const diff = a ^ b;
    if ((diff & (diff - 1)) === 0) EDGES.push([a, b]);
  }
}

type Vec4 = number[];

/** Rotate in the plane of axes i and j. */
function rotate(v: Vec4, i: number, j: number, angle: number): Vec4 {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const out = [...v];
  out[i] = v[i] * c - v[j] * s;
  out[j] = v[i] * s + v[j] * c;
  return out;
}

const TEAL = [25, 211, 197];
const GREEN = [62, 224, 143];
const mix = (t: number) => TEAL.map((c, k) => Math.round(c + (GREEN[k] - c) * t)).join(",");

// A fixed tilted view in 3D keeps the cube-within-a-cube structure readable.
const TILT_Y = 0.62;
const TILT_X = 0.42;

/**
 * A rotating tesseract. The hypercube turns in the XW and ZW planes (the classic double
 * rotation that turns it "inside out"), is projected from 4D to 3D so the far side in W
 * becomes the inner cube, then viewed in 3D from a fixed tilted angle.
 */
export function Tesseract() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // The canvas fills the screen; the shape is sized from the shorter side, so on narrow
    // screens it runs off the edges and still frames the entry fields.
    let width = 0;
    let height = 0;
    let size = 0;
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      size = Math.min(800, Math.max(560, 0.92 * Math.min(width, height)));
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    let frame = 0;
    const draw = (time: number) => {
      const t = still ? 2400 : time;
      const a = t * 0.00028;
      const points = VERTICES.map((v) => {
        let p = rotate(v, 0, 3, a);
        p = rotate(p, 2, 3, a * 0.62);
        p = rotate(p, 1, 3, a * 0.21);
        const w = 1 / (3.2 - p[3]); // 4D -> 3D perspective: far side in W shrinks inward
        let q = [p[0] * w, p[1] * w, p[2] * w, 0];
        q = rotate(q, 0, 2, TILT_Y + a * 0.15);
        q = rotate(q, 1, 2, TILT_X);
        const d = 1 / (3 - q[2]); // 3D -> 2D perspective
        const scale = size * 2.1;
        return { x: width / 2 + q[0] * d * scale, y: height / 2 + q[1] * d * scale, w: p[3] };
      });

      ctx.clearRect(0, 0, width, height);
      ctx.lineWidth = 1.4;
      for (const [i, j] of EDGES) {
        const p = points[i];
        const q = points[j];
        const depth = Math.min(1, Math.max(0, ((p.w + q.w) / 2 + 1.5) / 3)); // 0 = far in W
        ctx.strokeStyle = `rgba(${mix(depth)},${0.25 + depth * 0.6})`;
        ctx.shadowColor = `rgba(${mix(depth)},0.8)`;
        ctx.shadowBlur = 6 + depth * 10;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(q.x, q.y);
        ctx.stroke();
      }
      ctx.shadowColor = "rgba(155,140,255,0.9)";
      ctx.shadowBlur = 10;
      ctx.fillStyle = "#9b8cff";
      for (const p of points) {
        const r = 1.4 + Math.min(1, Math.max(0, (p.w + 1.5) / 3)) * 1.8;
        ctx.fillRect(p.x - r, p.y - r, r * 2, r * 2);
      }
      if (!still) frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={ref} className="tesseract" aria-hidden="true" />;
}
