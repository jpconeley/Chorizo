import Link from "next/link";

import { CountUp } from "@/components/live";

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

/** A headline figure that counts up when it appears. */
export function StatTile({ label: name, value, note }: { label: string; value: number; note?: string }) {
  return (
    <div className="tile">
      <span className="tile-label">{name}</span>
      <span className="tile-value">
        <CountUp value={value} />
      </span>
      {note && <span className="tile-note">{note}</span>}
    </div>
  );
}

export function Loading() {
  return <p className="muted">LOADING…</p>;
}

export function ApiDown() {
  return (
    <div className="notice error">
      Cannot reach the LASO API. Start it with <code>make api</code>.
    </div>
  );
}

/** Prometheus' fire carried in a hexagon (science): a faceted flame with a violet core. */
export function Logo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <defs>
        <linearGradient id="logo-hex" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#19d3c5" />
          <stop offset="1" stopColor="#3ee08f" />
        </linearGradient>
        <linearGradient id="logo-fire" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#19d3c5" />
          <stop offset="1" stopColor="#3ee08f" />
        </linearGradient>
      </defs>
      <polygon
        points="12,1.5 21.1,6.75 21.1,17.25 12,22.5 2.9,17.25 2.9,6.75"
        fill="none"
        stroke="url(#logo-hex)"
        strokeWidth="1.6"
      />
      <path
        d="M12.6 3.8 L14.6 8.4 L14.1 10.9 L16.1 9.3 L17.3 13.4 Q17.3 17.9 12 19.7 Q6.7 17.9 6.7 13.6 L8.3 10.3 L9.7 12.3 L10.1 7.9 Z"
        fill="url(#logo-fire)"
      />
      <path d="M12 11.2 L13.9 14.7 Q13.9 17.1 12 17.8 Q10.1 17.1 10.1 14.7 Z" fill="#9b8cff" />
    </svg>
  );
}
