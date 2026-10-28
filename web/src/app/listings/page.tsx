import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";

import { ApiDown, Loading, Panel, StageBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { label, usd } from "@/lib/format";
import type { Listing } from "@/lib/types";

export const metadata: Metadata = { title: "Funding listings" };

async function ListingsContent() {
  const result = await api<Listing[]>("/listings");
  if (!result.ok) return <ApiDown />;

  return (
    <>
      <h1>Funding listings</h1>
      <p className="sub">Therapies whose owners are looking for investors or partners.</p>
      <Panel title="Open listings" right={<span className="muted">{result.data.length}</span>}>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Asset</th>
                <th>Stage</th>
                <th>Headline</th>
                <th className="num">Seeking</th>
                <th>Deal types</th>
                <th>Owner</th>
              </tr>
            </thead>
            <tbody>
              {result.data.map((l) => (
                <tr key={l.id}>
                  <td>
                    <Link href={`/listings/${l.id}`}>{l.asset.name}</Link>
                  </td>
                  <td>
                    <StageBadge stage={l.asset.stage} />
                  </td>
                  <td className="wrap">{l.headline}</td>
                  <td className="num amber">{usd(l.amount_sought_usd)}</td>
                  <td>{l.deal_types.map(label).join(", ")}</td>
                  <td className="muted">{l.asset.organization?.name ?? "—"}</td>
                </tr>
              ))}
              {result.data.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    No open listings.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

export default function Listings() {
  return (
    <Suspense fallback={<Loading />}>
      <ListingsContent />
    </Suspense>
  );
}
