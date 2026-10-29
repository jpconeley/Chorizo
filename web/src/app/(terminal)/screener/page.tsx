import { Suspense } from "react";
import Link from "next/link";

import { ApprovalsChart, PipelineChart } from "@/components/charts";
import { CountUp } from "@/components/live";
import { ScreenerControls } from "@/components/ScreenerControls";
import { ApiDown, Bar, Loading, Panel, StageBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { label, pct } from "@/lib/format";
import {
  STAGE_LABEL,
  STAGES,
  type AssetPage,
  type Benchmark,
  type MarketStats,
} from "@/lib/types";

const PAGE_SIZE = 50;

/** One row per stage: our computed rate when we have one, else the published reference. */
function preferredRates(rows: Benchmark[]): Benchmark[] {
  const byStage = new Map<string, Benchmark>();
  for (const b of rows) {
    const current = byStage.get(b.stage);
    if (
      !current ||
      (current.source.startsWith("BIO") && !b.source.startsWith("BIO"))
    )
      byStage.set(b.stage, b);
  }
  // Our Phase 3 rate runs through approval (filings aren't on ClinicalTrials.gov), so the
  // separate filing step only applies to the published figures.
  if (!byStage.get("phase3")?.source.startsWith("BIO"))
    byStage.delete("regulatory");
  return STAGES.flatMap((s) => byStage.get(s) ?? []);
}

const throughApproval = (b: Benchmark) =>
  b.stage === "phase3" && !b.source.startsWith("BIO");

function StatTile({
  label: name,
  value,
  note,
}: {
  label: string;
  value: number;
  note?: string;
}) {
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

async function ScreenerContent(props: PageProps<"/screener">) {
  const params = await props.searchParams;
  const query = new URLSearchParams();
  for (const key of ["q", "stage", "therapeutic_area", "modality"]) {
    const value = params[key];
    if (typeof value === "string" && value) query.set(key, value);
  }
  const offset = Math.max(0, Number(params.offset) || 0);
  const pageLink = (to: number) => {
    const next = new URLSearchParams(query);
    if (to > 0) next.set("offset", String(to));
    return `/screener?${next}`;
  };

  const [assets, benchmarks, stats] = await Promise.all([
    api<AssetPage>(`/assets?${query}&limit=${PAGE_SIZE}&offset=${offset}`),
    api<Benchmark[]>("/benchmarks"),
    api<MarketStats>("/market/stats"),
  ]);
  if (!assets.ok) return <ApiDown />;
  const initial = {
    q: query.get("q") ?? "",
    stage: query.get("stage") ?? "",
    therapeutic_area: query.get("therapeutic_area") ?? "",
    modality: query.get("modality") ?? "",
  };

  return (
    <>
      {stats.ok && (
        <div className="tiles">
          <StatTile label="Drug programs tracked" value={stats.data.programs} />
          <StatTile label="In active development" value={stats.data.active} />
          <StatTile label="Approved" value={stats.data.approved} />
          <StatTile
            label="Phase 3 starts, last 12 months"
            value={stats.data.phase3_starts_12m}
          />
          <StatTile
            label="Clinical trials"
            value={stats.data.trials}
            note="ClinicalTrials.gov"
          />
        </div>
      )}
      <div className="grid">
        <div>
          <Panel
            title="Asset screener"
            right={
              <span className="muted">
                {assets.data.total.toLocaleString()} assets
              </span>
            }
          >
            <ScreenerControls initial={initial}>
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Stage</th>
                      <th>Modality</th>
                      <th>Status</th>
                      <th>Indication</th>
                      <th>Area</th>
                      <th>Owner</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assets.data.items.map((a) => (
                      <tr key={a.id}>
                        <td>
                          <Link href={`/assets/${a.id}`}>{a.name}</Link>
                        </td>
                        <td>
                          <StageBadge stage={a.stage} />
                        </td>
                        <td>{label(a.modality)}</td>
                        <td
                          className={
                            a.status === "discontinued" ? "down" : "muted"
                          }
                        >
                          {label(a.status)}
                        </td>
                        <td>{a.indication}</td>
                        <td>{label(a.therapeutic_area)}</td>
                        <td className="muted">{a.organization?.name ?? "—"}</td>
                      </tr>
                    ))}
                    {assets.data.items.length === 0 && (
                      <tr>
                        <td colSpan={7} className="muted">
                          No assets match.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {assets.data.total > PAGE_SIZE && (
                <div className="pager">
                  {offset > 0 ? (
                    <Link href={pageLink(Math.max(0, offset - PAGE_SIZE))}>
                      ← Prev
                    </Link>
                  ) : (
                    <span />
                  )}
                  <span className="muted">
                    {(offset + 1).toLocaleString()}–
                    {Math.min(
                      offset + PAGE_SIZE,
                      assets.data.total,
                    ).toLocaleString()}{" "}
                    of {assets.data.total.toLocaleString()}
                  </span>
                  {offset + PAGE_SIZE < assets.data.total ? (
                    <Link href={pageLink(offset + PAGE_SIZE)}>Next →</Link>
                  ) : (
                    <span />
                  )}
                </div>
              )}
            </ScreenerControls>
          </Panel>
        </div>
        <div>
          <Panel title="Stage success rates">
            {benchmarks.ok && benchmarks.data.length > 0 ? (
              <table>
                <thead>
                  <tr>
                    <th>Stage</th>
                    <th className="num">Advance</th>
                    <th className="num">To approval</th>
                  </tr>
                </thead>
                <tbody>
                  {preferredRates(benchmarks.data).map((b) => (
                    <tr key={`${b.source}-${b.stage}`}>
                      <td
                        title={`${b.source}, n=${b.sample_size.toLocaleString()}`}
                      >
                        {STAGE_LABEL[b.stage]}
                        {throughApproval(b) && " → approval"}
                        {b.source.startsWith("BIO") && (
                          <span className="muted"> *</span>
                        )}
                      </td>
                      <td className="num">{pct(b.transition_probability)}</td>
                      <td className="num">
                        <Bar value={b.likelihood_of_approval} />
                        {pct(b.likelihood_of_approval)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">No benchmarks loaded.</p>
            )}
            <p className="disclaimer">
              All therapeutic areas, from ClinicalTrials.gov programs. *
              Published BIO 2006–2015 figure where we lack data.{" "}
              <Link href="/benchmarks">Full benchmarks →</Link>
            </p>
          </Panel>
          {stats.ok && (
            <>
              <Panel title="Pipeline · active programs by stage">
                <PipelineChart data={stats.data.pipeline} />
              </Panel>
              <Panel title="FDA approvals per year">
                <ApprovalsChart data={stats.data.approvals_by_year} />
              </Panel>
            </>
          )}
        </div>
      </div>
    </>
  );
}

export default function Screener(props: PageProps<"/screener">) {
  return (
    <Suspense fallback={<Loading />}>
      <ScreenerContent {...props} />
    </Suspense>
  );
}
