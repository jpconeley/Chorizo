"use client";

import { useState } from "react";

import { STAGE_LABEL, type Stage } from "@/lib/types";

type Tip = { x: number; y: number; value: string; label: string } | null;

function Tooltip({ tip }: { tip: Tip }) {
  if (!tip) return null;
  return (
    <div className="chart-tip" style={{ left: tip.x, top: tip.y }} role="status">
      <strong>{tip.value}</strong>
      <span>{tip.label}</span>
    </div>
  );
}

function TableView({ head, rows }: { head: [string, string]; rows: [string, string][] }) {
  return (
    <details className="chart-table">
      <summary>Table</summary>
      <table>
        <thead>
          <tr>
            <th>{head[0]}</th>
            <th className="num">{head[1]}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([a, b]) => (
            <tr key={a}>
              <td>{a}</td>
              <td className="num">{b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

/** Active programs by current stage: one teal series, horizontal bars from a shared baseline. */
export function PipelineChart({ data }: { data: { stage: Stage; count: number }[] }) {
  const [tip, setTip] = useState<Tip>(null);
  const max = Math.max(1, ...data.map((d) => d.count));
  const show = (e: React.SyntheticEvent<HTMLElement>, d: { stage: Stage; count: number }) => {
    const row = e.currentTarget;
    const box = row.parentElement!.getBoundingClientRect();
    const bar = row.querySelector(".hbar-track")!.getBoundingClientRect();
    setTip({
      x: bar.left - box.left + (bar.width * d.count) / max,
      y: bar.top - box.top,
      value: d.count.toLocaleString(),
      label: `${STAGE_LABEL[d.stage]} · active programs`,
    });
  };
  return (
    <>
      <div className="hbars" onPointerLeave={() => setTip(null)}>
        {data.map((d) => (
          <div
            key={d.stage}
            className="hbar-row"
            tabIndex={0}
            aria-label={`${STAGE_LABEL[d.stage]}: ${d.count.toLocaleString()} active programs`}
            onPointerEnter={(e) => show(e, d)}
            onFocus={(e) => show(e, d)}
            onBlur={() => setTip(null)}
          >
            <span className="hbar-label">{STAGE_LABEL[d.stage]}</span>
            <span className="hbar-track">
              <span className="hbar" style={{ width: `${(100 * d.count) / max}%` }} />
            </span>
            <span className="hbar-value">{d.count.toLocaleString()}</span>
          </div>
        ))}
        <Tooltip tip={tip} />
      </div>
      <TableView
        head={["Stage", "Active programs"]}
        rows={data.map((d) => [STAGE_LABEL[d.stage], d.count.toLocaleString()])}
      />
    </>
  );
}

const W = 600;
const H = 170;
const PAD = { top: 18, right: 8, bottom: 22, left: 34 };

function niceMax(v: number): number {
  if (v <= 4) return 4;
  const step = Math.pow(10, Math.floor(Math.log10(v)));
  return Math.ceil(v / step) * step;
}

/** Approvals per year: one green series, columns with rounded caps and a hover readout. */
export function ApprovalsChart({ data }: { data: { year: number; count: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const top = niceMax(Math.max(...data.map((d) => d.count), 1));
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const slot = plotW / data.length;
  const colW = Math.min(24, slot - 2);
  const y = (v: number) => PAD.top + plotH - (plotH * v) / top;
  const peak = data.reduce((best, d, i) => (d.count > data[best].count ? i : best), 0);
  const labelled = new Set([peak, data.length - 1]);
  const ticks = [0, top / 2, top];

  const column = (d: { count: number }, i: number) => {
    const x = PAD.left + slot * i + (slot - colW) / 2;
    const h = Math.max(0, (plotH * d.count) / top);
    if (h === 0) return null;
    const r = Math.min(4, h, colW / 2);
    const base = PAD.top + plotH;
    // Rounded at the data end (top), square at the baseline.
    return `M${x},${base} V${base - h + r} Q${x},${base - h} ${x + r},${base - h} H${x + colW - r} Q${x + colW},${base - h} ${x + colW},${base - h + r} V${base} Z`;
  };

  return (
    <>
      <div className="vchart">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="FDA approvals per year">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} className="grid" />
              <text x={PAD.left - 6} y={y(t) + 3} className="axis" textAnchor="end">
                {t.toLocaleString()}
              </text>
            </g>
          ))}
          {data.map((d, i) => {
            const path = column(d, i);
            const cx = PAD.left + slot * i + slot / 2;
            return (
              <g key={d.year}>
                {path && <path d={path} className={`col${hover === i ? " hover" : ""}`} />}
                {labelled.has(i) && d.count > 0 && (
                  <text x={cx} y={y(d.count) - 5} className="cap" textAnchor="middle">
                    {d.count.toLocaleString()}
                  </text>
                )}
                {(i % 3 === 0 || i === data.length - 1) && (
                  <text x={cx} y={H - 6} className="axis" textAnchor="middle">
                    {d.year}
                  </text>
                )}
                <rect
                  x={PAD.left + slot * i}
                  y={PAD.top}
                  width={slot}
                  height={plotH}
                  className="hit"
                  tabIndex={0}
                  aria-label={`${d.year}: ${d.count} approvals`}
                  onPointerEnter={() => setHover(i)}
                  onPointerLeave={() => setHover(null)}
                  onFocus={() => setHover(i)}
                  onBlur={() => setHover(null)}
                />
              </g>
            );
          })}
        </svg>
        {hover !== null && (
          <div
            className="chart-tip"
            style={{
              left: `${((PAD.left + slot * hover + slot / 2) / W) * 100}%`,
              top: `${(y(data[hover].count) / H) * 100}%`,
            }}
            role="status"
          >
            <strong>{data[hover].count.toLocaleString()}</strong>
            <span>approvals in {data[hover].year}</span>
          </div>
        )}
      </div>
      <TableView head={["Year", "Approvals"]} rows={data.map((d) => [String(d.year), d.count.toLocaleString()])} />
    </>
  );
}
