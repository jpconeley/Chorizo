"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const everySecond = (tick: () => void) => {
  const id = setInterval(tick, 1000);
  return () => clearInterval(id);
};

/** UTC clock for the status bar, ticking every second. Renders nothing on the server. */
export function Clock() {
  const seconds = useSyncExternalStore(everySecond, () => Math.floor(Date.now() / 1000), () => 0);
  if (!seconds) return null;
  const now = new Date(seconds * 1000);
  return <span className="clock">{now.toISOString().slice(0, 19).replace("T", " ")} UTC</span>;
}

/** A number that counts up from zero when it first appears. */
export function CountUp({ value, duration = 900 }: { value: number; duration?: number }) {
  const [shown, setShown] = useState(value);
  const started = useRef(false);
  useEffect(() => {
    if (started.current || reducedMotion()) return;
    started.current = true;
    let frame = 0;
    const start = performance.now();
    const step = (t: number) => {
      const p = Math.min(1, (t - start) / duration);
      setShown(Math.round(value * (1 - Math.pow(1 - p, 3))));
      if (p < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);
  return <>{shown.toLocaleString()}</>;
}
