import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { ApiDown, Loading, Panel, StageBadge, StatTile } from "@/components/ui";
import { api, getMe } from "@/lib/api";
import { label, pct, usd } from "@/lib/format";
import { STAGE_LABEL, type DashboardData } from "@/lib/types";

export const metadata: Metadata = { title: "Dashboard" };

const RECENT_DAYS = 30;
const UPDATE_WINDOW_DAYS = 90;

const daysAgo = (iso: string) =>
  (Date.now() - new Date(iso).getTime()) / 86_400_000;

type Item = DashboardData["activity"][number];

function ActivityText({ item }: { item: Item }) {
  const drug = <Link href={`/assets/${item.asset_id}`}>{item.asset}</Link>;
  switch (item.kind) {
    case "stage":
      return item.stage === "approved" ? (
        <>
          {drug} was <span className="life">approved</span>
        </>
      ) : (
        <>
          {drug} entered <strong>{STAGE_LABEL[item.stage!]}</strong>
        </>
      );
    case "followed":
      return <>You started following {drug}</>;
    case "offer_sent":
      return (
        <>
          You sent an offer on {drug}
          {item.listing_id && (
            <>
              {" · "}
              <Link href={`/listings/${item.listing_id}`} className="muted">
                {item.detail}
              </Link>
            </>
          )}
        </>
      );
    case "listing_created":
      return <>You listed {drug} for funding</>;
    case "interest_received":
      return (
        <>
          <strong>{item.detail}</strong> is interested in {drug}
        </>
      );
  }
}

const KIND_TAG: Record<Item["kind"], string> = {
  stage: "MOVE",
  followed: "FOLLOW",
  offer_sent: "OFFER",
  listing_created: "LISTING",
  interest_received: "INTEREST",
};

async function DashboardContent() {
  const [result, me] = await Promise.all([
    api<DashboardData>("/me/dashboard"),
    getMe(),
  ]);
  if (!result.ok) {
    if (result.status === 401) redirect("/exit");
    return <ApiDown />;
  }
  const d = result.data;
  const canSeePos = me?.features.includes("asset_pos");
  const isSponsor =
    d.listings.length > 0 || me?.features.includes("create_listings");
  const updates = d.activity.filter(
    (a) => a.kind === "stage" && daysAgo(a.on) <= UPDATE_WINDOW_DAYS,
  );

  return (
    <>
      <h1>Dashboard</h1>
      <p className="sub">
        Drugs you follow, offers you&apos;ve made
        {isSponsor ? " and your listings" : ""}.
      </p>

      <div className="tiles">
        <StatTile label="Following" value={d.following.length} />
        <StatTile
          label={`Updates, last ${UPDATE_WINDOW_DAYS} days`}
          value={updates.length}
        />
        <StatTile label="Offers sent" value={d.offers.length} />
        {isSponsor && (
          <StatTile
            label="Interest received"
            value={d.interest_received.length}
          />
        )}
      </div>

      <div className="grid">
        <div>
          <Panel
            title="Following"
            right={<Link href="/screener">Find drugs →</Link>}
          >
            {d.following.length === 0 ? (
              <p className="muted">
                You&apos;re not following anything yet. Open any drug from the{" "}
                <Link href="/screener">screener</Link> and press WATCH.
              </p>
            ) : (
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Drug</th>
                      <th>Stage</th>
                      <th>Since</th>
                      <th className="num">Next stage</th>
                      <th className="num">To approval</th>
                      <th>Sponsor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.following.map((f) => (
                      <tr key={f.asset.id}>
                        <td>
                          <Link href={`/assets/${f.asset.id}`}>
                            {f.asset.name}
                          </Link>
                        </td>
                        <td>
                          <StageBadge stage={f.asset.stage} />
                        </td>
                        <td>
                          {f.latest ? (
                            <>
                              <span className="muted">{f.latest.on}</span>
                              {daysAgo(f.latest.on) <= RECENT_DAYS && (
                                <span className="new-tag">NEW</span>
                              )}
                            </>
                          ) : (
                            <span className="muted">—</span>
                          )}
                          {f.asset.status === "discontinued" && (
                            <span className="down"> · discontinued</span>
                          )}
                        </td>
                        <td className="num">
                          {canSeePos ? pct(f.next_stage_probability) : "—"}
                        </td>
                        <td className="num life">
                          {canSeePos ? pct(f.likelihood_of_approval) : "—"}
                        </td>
                        <td className="muted">
                          {f.asset.organization?.name ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!canSeePos && d.following.length > 0 && (
              <p className="disclaimer">
                Probabilities come with <Link href="/pricing">Pro</Link>.
              </p>
            )}
          </Panel>

          <Panel
            title="Offers sent"
            right={<Link href="/listings">Funding listings →</Link>}
          >
            {d.offers.length === 0 ? (
              <p className="muted">
                No offers yet. Browse{" "}
                <Link href="/listings">funding listings</Link> and use Contact
                owner.
              </p>
            ) : (
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Drug</th>
                      <th>Listing</th>
                      <th className="num">Your indication</th>
                      <th className="num">Seeking</th>
                      <th>Sent</th>
                      <th>Listing status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.offers.map((o) => (
                      <tr key={o.listing_id}>
                        <td>
                          <Link href={`/assets/${o.asset_id}`}>{o.asset}</Link>
                        </td>
                        <td className="wrap">
                          <Link href={`/listings/${o.listing_id}`}>
                            {o.headline}
                          </Link>
                        </td>
                        <td className="num life">
                          {usd(o.indicative_amount_usd)}
                        </td>
                        <td className="num">{usd(o.amount_sought_usd)}</td>
                        <td className="muted">{o.sent_on}</td>
                        <td>{label(o.listing_status)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          {isSponsor && (
            <Panel title="Your listings">
              {d.listings.length === 0 ? (
                <p className="muted">You haven&apos;t listed a drug yet.</p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Drug</th>
                      <th>Listing</th>
                      <th>Status</th>
                      <th className="num">Interested investors</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.listings.map((l) => (
                      <tr key={l.listing_id}>
                        <td>
                          <Link href={`/assets/${l.asset_id}`}>{l.asset}</Link>
                        </td>
                        <td className="wrap">
                          <Link href={`/listings/${l.listing_id}`}>
                            {l.headline}
                          </Link>
                        </td>
                        <td>{label(l.status)}</td>
                        <td className="num">{l.interest_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {d.interest_received.length > 0 && (
                <ul className="interest-list">
                  {d.interest_received.map((r, i) => (
                    <li key={`${r.listing_id}-${i}`}>
                      <strong>{r.investor}</strong> on {r.asset}
                      {r.indicative_amount_usd && (
                        <span className="life">
                          {" "}
                          · {usd(r.indicative_amount_usd)}
                        </span>
                      )}
                      <span className="muted"> · {r.on}</span>
                      {r.message && <p className="muted">“{r.message}”</p>}
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}
        </div>

        <div>
          <Panel title="Activity">
            {d.activity.length === 0 ? (
              <p className="muted">Your activity will show up here.</p>
            ) : (
              <ol className="activity">
                {d.activity.map((a, i) => (
                  <li
                    key={`${a.kind}-${a.asset_id}-${a.on}-${i}`}
                    className={`act act-${a.kind}`}
                  >
                    <span className="act-tag">{KIND_TAG[a.kind]}</span>
                    <span className="act-text">
                      <ActivityText item={a} />
                      {a.kind === "stage" && daysAgo(a.on) <= RECENT_DAYS && (
                        <span className="new-tag">NEW</span>
                      )}
                    </span>
                    <span className="act-date">{a.on}</span>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<Loading />}>
      <DashboardContent />
    </Suspense>
  );
}
