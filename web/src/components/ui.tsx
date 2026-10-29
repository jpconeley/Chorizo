import Link from "next/link";

import { FEATURE_LABEL, label, pct } from "@/lib/format";
import { STAGE_LABEL, STAGES, type Stage } from "@/lib/types";
import type { UpgradeRequired } from "@/lib/api";

export function Panel({
  title,
  right,
  children,
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <h2>
        <span>{title}</span>
        {right}
      </h2>
      <div className="body">{children}</div>
    </section>
  );
}

export function StageBadge({ stage }: { stage: Stage }) {
  return <span className={`stage stage-${stage}`}>{STAGE_LABEL[stage]}</span>;
}

export function Bar({ value }: { value: number }) {
  return (
    <div className="bar" title={pct(value)}>
      <span style={{ width: `${Math.min(100, value * 100)}%` }} />
    </div>
  );
}

export function StageTimeline({ current }: { current: Stage }) {
  const index = STAGES.indexOf(current);
  return (
    <div className="timeline">
      {STAGES.map((stage, i) => (
        <div key={stage} className={`stage-${stage} ${i < index ? "done" : i === index ? "current" : ""}`}>
          {STAGE_LABEL[stage]}
        </div>
      ))}
    </div>
  );
}

export function Locked({ upgrade }: { upgrade?: UpgradeRequired }) {
  const plan = upgrade?.plan ?? "pro";
  const feature = upgrade ? (FEATURE_LABEL[upgrade.feature] ?? label(upgrade.feature)) : "This data";
  return (
    <div className="locked">
      <strong>{feature}</strong>
      Available on the {label(plan)} plan.{" "}
      <Link href="/pricing">
        See plans →
      </Link>
    </div>
  );
}

export function Loading() {
  return <p className="muted">LOADING…</p>;
}

export function ApiDown() {
  return (
    <div className="notice error">
      Cannot reach the Chorizo API. Start it with <code>make api</code>.
    </div>
  );
}

/** Hexagon molecule mark: a benzene-style ring with a bonded node, in teal-to-green. */
export function Logo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <defs>
        <linearGradient id="logo-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#19d3c5" />
          <stop offset="1" stopColor="#3ee08f" />
        </linearGradient>
      </defs>
      <polygon
        points="12,2 20.66,7 20.66,17 12,22 3.34,17 3.34,7"
        fill="none"
        stroke="url(#logo-grad)"
        strokeWidth="2"
      />
      <circle cx="12" cy="12" r="3.2" fill="#3ee08f" />
      <line x1="12" y1="12" x2="20.66" y2="7" stroke="#19d3c5" strokeWidth="1.5" />
      <circle cx="20.66" cy="7" r="1.8" fill="#9b8cff" />
    </svg>
  );
}
