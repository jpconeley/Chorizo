import Link from "next/link";

import { api } from "@/lib/api";
import { STAGE_LABEL, type FeedEvent } from "@/lib/types";

const VERB: Record<string, string> = {
  phase1: "ENTERS PHASE 1",
  phase2: "ENTERS PHASE 2",
  phase3: "ENTERS PHASE 3",
  approved: "APPROVED",
};

/** Scrolling tape of the latest pipeline events, like a market ticker. */
export async function Ticker() {
  const feed = await api<FeedEvent[]>("/market/feed?limit=30");
  if (!feed.ok || feed.data.length === 0) return null;
  const items = feed.data.map((e, i) => (
    <Link key={`${e.asset_id}-${e.stage}-${i}`} href={`/assets/${e.asset_id}`} className="tick">
      <span className={`stage stage-${e.stage}`}>{STAGE_LABEL[e.stage]}</span>
      <strong>{e.asset}</strong>
      <span className={e.stage === "approved" ? "life" : "accent"}>{VERB[e.stage]}</span>
      <span className="muted">
        {e.on}
        {e.sponsor && ` · ${e.sponsor}`}
      </span>
    </Link>
  ));
  return (
    <div className="ticker" aria-label="Latest pipeline events">
      {/* Two copies back to back so the loop is seamless. */}
      <div className="ticker-track" style={{ animationDuration: `${feed.data.length * 5}s` }}>
        <div className="ticker-run">{items}</div>
        <div className="ticker-run" aria-hidden="true">
          {items}
        </div>
      </div>
    </div>
  );
}
