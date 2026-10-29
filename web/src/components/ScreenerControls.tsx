"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { label } from "@/lib/format";
import { AREAS, MODALITIES, STAGE_LABEL, STAGES } from "@/lib/types";

type Filters = { q: string; stage: string; therapeutic_area: string; modality: string };

const serialize = (f: Filters) => new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
const parse = (query: string): Filters => {
  const p = new URLSearchParams(query);
  return {
    q: p.get("q") ?? "",
    stage: p.get("stage") ?? "",
    therapeutic_area: p.get("therapeutic_area") ?? "",
    modality: p.get("modality") ?? "",
  };
};

/**
 * Screener filters that apply as you type or pick, no GO needed. While new results load,
 * the current table stays in place, dimmed, instead of flashing empty.
 */
export function ScreenerControls({ initial, children }: { initial: Filters; children: React.ReactNode }) {
  const router = useRouter();
  const [filters, setFilters] = useState(initial);
  const [pending, startTransition] = useTransition();
  const pushed = useRef(serialize(initial));

  // Navigation from elsewhere (the command bar) changes the URL under us: follow it, but
  // ignore the echo of our own updates so fast typing isn't overwritten.
  const incoming = serialize(initial);
  useEffect(() => {
    if (incoming !== pushed.current) {
      pushed.current = incoming;
      setFilters(parse(incoming));
    }
  }, [incoming]);

  useEffect(() => {
    const next = serialize(filters);
    if (next === pushed.current) return;
    const timer = setTimeout(() => {
      pushed.current = next;
      startTransition(() => router.replace(`/screener?${next}`, { scroll: false }));
    }, 250);
    return () => clearTimeout(timer);
  }, [filters, router]);

  const set = (key: keyof Filters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <>
      <form className="filters" action="/screener" onSubmit={(e) => e.preventDefault()}>
        <input
          className="command"
          name="q"
          placeholder="Filter by name, target, indication, sponsor…"
          value={filters.q}
          onChange={set("q")}
        />
        <select name="stage" value={filters.stage} onChange={set("stage")}>
          <option value="">All stages</option>
          {STAGES.map((s) => (
            <option key={s} value={s}>
              {STAGE_LABEL[s]}
            </option>
          ))}
        </select>
        <select name="therapeutic_area" value={filters.therapeutic_area} onChange={set("therapeutic_area")}>
          <option value="">All areas</option>
          {AREAS.map((a) => (
            <option key={a} value={a}>
              {label(a)}
            </option>
          ))}
        </select>
        <select name="modality" value={filters.modality} onChange={set("modality")}>
          <option value="">All modalities</option>
          {MODALITIES.map((m) => (
            <option key={m} value={m}>
              {label(m)}
            </option>
          ))}
        </select>
        <span className={`live-dot${pending ? " busy" : ""}`} aria-live="polite">
          {pending ? "UPDATING" : "LIVE"}
        </span>
      </form>
      <div className={pending ? "refreshing" : undefined}>{children}</div>
    </>
  );
}
