import { Suspense } from "react";
import Link from "next/link";

import { ApiDown, Bar, Loading, Panel, StageBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { label, pct } from "@/lib/format";
import { MODALITIES, STAGE_LABEL, STAGES, type AssetPage, type Benchmark } from "@/lib/types";

async function ScreenerContent(props: PageProps<"/">) {
  const params = await props.searchParams;
  const query = new URLSearchParams();
  for (const key of ["q", "stage", "therapeutic_area", "modality"]) {
    const value = params[key];
    if (typeof value === "string" && value) query.set(key, value);
  }

  const [assets, benchmarks] = await Promise.all([
    api<AssetPage>(`/assets?${query}`),
    api<Benchmark[]>("/benchmarks"),
  ]);
  if (!assets.ok) return <ApiDown />;

  return (
    <div className="grid">
      <div>
        <Panel title="Asset screener" right={<span className="muted">{assets.data.total} assets</span>}>
          <form className="filters">
            <input
              className="command"
              name="q"
              placeholder="Search name, target, indication…"
              defaultValue={query.get("q") ?? ""}
            />
            <select name="stage" defaultValue={query.get("stage") ?? ""}>
              <option value="">All stages</option>
              {STAGES.map((s) => (
                <option key={s} value={s}>
                  {STAGE_LABEL[s]}
                </option>
              ))}
            </select>
            <select name="modality" defaultValue={query.get("modality") ?? ""}>
              <option value="">All modalities</option>
              {MODALITIES.map((m) => (
                <option key={m} value={m}>
                  {label(m)}
                </option>
              ))}
            </select>
            <button>GO</button>
          </form>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Stage</th>
                  <th>Modality</th>
                  <th>Target</th>
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
                    <td>{a.target ?? "—"}</td>
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
                {benchmarks.data.map((b) => (
                  <tr key={`${b.source}-${b.stage}`}>
                    <td>{STAGE_LABEL[b.stage]}</td>
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
            All therapeutic areas. <Link href="/benchmarks">Full benchmarks →</Link>
          </p>
        </Panel>
      </div>
    </div>
  );
}

export default function Screener(props: PageProps<"/">) {
  return (
    <Suspense fallback={<Loading />}>
      <ScreenerContent {...props} />
    </Suspense>
  );
}
