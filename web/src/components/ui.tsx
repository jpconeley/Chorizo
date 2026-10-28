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
  return <span className="stage">{STAGE_LABEL[stage]}</span>;
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
        <div key={stage} className={i < index ? "done" : i === index ? "current" : ""}>
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
      <Link href="/pricing" className="amber">
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
