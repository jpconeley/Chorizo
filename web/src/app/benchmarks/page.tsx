import { Suspense } from "react";
import type { Metadata } from "next";

import { ApiDown, Bar, Loading, Locked, Panel } from "@/components/ui";
import { api } from "@/lib/api";
import { label, pct } from "@/lib/format";
import { MODALITIES, STAGE_LABEL, type Benchmark } from "@/lib/types";

export const metadata: Metadata = { title: "Benchmarks" };

const AREAS = ["oncology", "immunology", "neurology", "cardiovascular", "metabolic", "infectious_disease", "rare_disease"];

async function BenchmarksContent(props: PageProps<"/benchmarks">) {
  const params = await props.searchParams;
  const query = new URLSearchParams();
  for (const key of ["therapeutic_area", "modality"]) {
    const value = params[key];
    if (typeof value === "string" && value) query.set(key, value);
  }
  const result = await api<Benchmark[]>(`/benchmarks?${query}`);
  if (!result.ok && !result.upgrade) return <ApiDown />;

  const bySource = new Map<string, Benchmark[]>();
  for (const b of result.ok ? result.data : []) {
    bySource.set(b.source, [...(bySource.get(b.source) ?? []), b]);
  }

  return (
    <>
      <h1>Stage benchmarks</h1>
      <p className="sub">
        How often drug programs advance from each stage, and their chance of eventual approval.
      </p>
      <form className="filters">
        <select name="therapeutic_area" defaultValue={query.get("therapeutic_area") ?? ""}>
          <option value="">All therapeutic areas</option>
          {AREAS.map((a) => (
            <option key={a} value={a}>
              {label(a)}
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

      {!result.ok && <Locked upgrade={result.upgrade} />}
      {result.ok && bySource.size === 0 && (
        <p className="muted">Not enough programs in this segment yet to publish rates.</p>
      )}
      {[...bySource.entries()].map(([source, rows]) => (
        <Panel key={source} title={source} right={<span className="muted">as of {rows[0].as_of}</span>}>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Stage</th>
                  <th className="num">Advance to next</th>
                  <th></th>
                  <th className="num">Likelihood of approval</th>
                  <th></th>
                  <th className="num">Programs (n)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((b) => (
                  <tr key={b.stage}>
                    <td>{STAGE_LABEL[b.stage]}</td>
                    <td className="num">{pct(b.transition_probability)}</td>
                    <td>
                      <Bar value={b.transition_probability} />
                    </td>
                    <td className="num">{pct(b.likelihood_of_approval)}</td>
                    <td>
                      <Bar value={b.likelihood_of_approval} />
                    </td>
                    <td className="num">{b.sample_size.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ))}
      <p className="disclaimer">
        Likelihood of approval multiplies the success rates of every remaining stage. Historical base
        rates only; individual programs vary.
      </p>
    </>
  );
}

export default function Benchmarks(props: PageProps<"/benchmarks">) {
  return (
    <Suspense fallback={<Loading />}>
      <BenchmarksContent {...props} />
    </Suspense>
  );
}
