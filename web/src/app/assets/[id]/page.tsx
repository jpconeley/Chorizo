import { Suspense } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiDown, Loading, Locked, Panel, StageBadge, StageTimeline } from "@/components/ui";
import { toggleWatch } from "@/lib/actions";
import { api, getMe } from "@/lib/api";
import { label, pct } from "@/lib/format";
import { STAGE_LABEL, type AssetDetail, type AssetSummary, type Pos, type Stage } from "@/lib/types";

async function AssetPageContent(props: PageProps<"/assets/[id]">) {
  const { id } = await props.params;
  const [asset, pos, me] = await Promise.all([
    api<AssetDetail>(`/assets/${id}`),
    api<Pos>(`/assets/${id}/pos`),
    getMe(),
  ]);
  if (!asset.ok) return asset.status === 404 ? notFound() : <ApiDown />;
  const a = asset.data;

  let watching = false;
  if (me?.features.includes("watchlists")) {
    const list = await api<AssetSummary[]>("/watchlist");
    watching = list.ok && list.data.some((w) => w.id === a.id);
  }

  return (
    <>
      <h1>
        {a.name} <StageBadge stage={a.stage} />
      </h1>
      <p className="sub">
        {a.indication} · {label(a.modality)}
        {a.target && ` · ${a.target}`} · {a.organization?.name ?? "Unknown owner"}
      </p>

      <Panel title="Development stage">
        <StageTimeline current={a.stage} />
      </Panel>

      <div className="grid">
        <div>
          <Panel title="Overview">
            <dl className="kv">
              <dt>Mechanism</dt>
              <dd>{a.mechanism ?? "—"}</dd>
              <dt>Therapeutic area</dt>
              <dd>{label(a.therapeutic_area)}</dd>
              <dt>Status</dt>
              <dd>{label(a.status)}</dd>
              <dt>Biomarker selection</dt>
              <dd>{a.uses_biomarker_selection ? "Yes" : "No"}</dd>
              <dt>Orphan designation</dt>
              <dd>{a.orphan_designation ? "Yes" : "No"}</dd>
              {a.synonyms.length > 0 && (
                <>
                  <dt>Also known as</dt>
                  <dd>{a.synonyms.join(", ")}</dd>
                </>
              )}
            </dl>
            {a.summary && <p style={{ marginTop: 10 }}>{a.summary}</p>}
          </Panel>

          <Panel title="Clinical trials" right={<span className="muted">{a.trials.length}</span>}>
            {a.trials.length === 0 ? (
              <p className="muted">No linked trials yet.</p>
            ) : (
              <div className="scroll">
                <table>
                  <thead>
                    <tr>
                      <th>NCT ID</th>
                      <th>Phase</th>
                      <th>Status</th>
                      <th className="num">Enrolment</th>
                      <th>Start</th>
                      <th>Title</th>
                    </tr>
                  </thead>
                  <tbody>
                    {a.trials.map((t) => (
                      <tr key={t.nct_id}>
                        <td>
                          <a href={`https://clinicaltrials.gov/study/${t.nct_id}`} target="_blank" rel="noreferrer">
                            {t.nct_id}
                          </a>
                        </td>
                        <td>{t.phase ? STAGE_LABEL[t.phase] : "—"}</td>
                        <td>{label(t.overall_status.toLowerCase())}</td>
                        <td className="num">{t.enrollment ?? "—"}</td>
                        <td>{t.start_date ?? "—"}</td>
                        <td className="wrap">{t.title}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel title="Stage history">
            <table>
              <tbody>
                {a.stage_history.map((e) => (
                  <tr key={`${e.stage}-${e.entered_on}`}>
                    <td>{e.entered_on}</td>
                    <td>{STAGE_LABEL[e.stage]}</td>
                    <td className="muted">{e.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </div>

        <div>
          <Panel title="Probability of success">
            {pos.ok ? (
              <>
                <div className="stats">
                  <div className="stat">
                    <span className="muted">Advance to next stage</span>
                    <span className="big">{pct(pos.data.next_stage_probability)}</span>
                  </div>
                  <div className="stat">
                    <span className="muted">Reach approval</span>
                    <span className="big">{pct(pos.data.likelihood_of_approval)}</span>
                  </div>
                </div>
                {pos.data.inputs && (
                  <table style={{ marginTop: 12 }}>
                    <thead>
                      <tr>
                        <th>Stage</th>
                        <th className="num">P</th>
                        <th className="num">n</th>
                        <th>Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(pos.data.inputs).map(([stage, input]) => (
                        <tr key={stage}>
                          <td>{STAGE_LABEL[stage as Stage]}</td>
                          <td className="num">{pct(input?.probability)}</td>
                          <td className="num">{input?.sample_size ?? "—"}</td>
                          <td className="muted">{input?.source ?? "no data"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <p className="disclaimer">
                  Model {pos.data.model_version}: historical base rates for comparable programs. Not
                  investment advice.
                </p>
              </>
            ) : pos.upgrade ? (
              <Locked upgrade={pos.upgrade} />
            ) : (
              <p className="muted">Not enough history to estimate this asset yet.</p>
            )}
          </Panel>

          <Panel title="Actions">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {a.open_listing_ids.map((listingId) => (
                <Link key={listingId} href={`/listings/${listingId}`} className="button">
                  VIEW FUNDING LISTING
                </Link>
              ))}
              <form action={toggleWatch}>
                <input type="hidden" name="asset_id" value={a.id} />
                <input type="hidden" name="watching" value={String(watching)} />
                <button className="ghost">{watching ? "UNWATCH" : "WATCH"}</button>
              </form>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}

export default function AssetPage(props: PageProps<"/assets/[id]">) {
  return (
    <Suspense fallback={<Loading />}>
      <AssetPageContent {...props} />
    </Suspense>
  );
}
