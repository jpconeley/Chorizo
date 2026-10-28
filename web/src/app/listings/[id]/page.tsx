import { Suspense } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiDown, Loading, Panel, StageBadge } from "@/components/ui";
import { expressInterest } from "@/lib/actions";
import { api, getMe } from "@/lib/api";
import { label, usd } from "@/lib/format";
import type { ListingDetail } from "@/lib/types";

async function ListingPageContent(props: PageProps<"/listings/[id]">) {
  const [{ id }, params] = await Promise.all([props.params, props.searchParams]);
  const [result, me] = await Promise.all([api<ListingDetail>(`/listings/${id}`), getMe()]);
  if (!result.ok) return result.status === 404 ? notFound() : <ApiDown />;
  const l = result.data;
  const canContact = me?.features.includes("express_interest");

  return (
    <>
      <h1>
        {l.asset.name} <StageBadge stage={l.asset.stage} />
      </h1>
      <p className="sub">{l.headline}</p>
      {params.sent && <div className="notice">Your interest was sent to the owner.</div>}
      {typeof params.error === "string" && <div className="notice error">{params.error}</div>}

      <div className="grid">
        <div>
          <Panel title="Deal">
            <dl className="kv">
              <dt>Seeking</dt>
              <dd className="amber">{usd(l.amount_sought_usd)}</dd>
              <dt>Deal types</dt>
              <dd>{l.deal_types.map(label).join(", ") || "—"}</dd>
              <dt>Use of funds</dt>
              <dd>{l.use_of_funds ?? "—"}</dd>
              <dt>Owner</dt>
              <dd>
                {l.asset.organization?.name ?? "—"}
                {l.asset.organization?.verified && <span className="up"> ✓ verified</span>}
              </dd>
              <dt>Asset</dt>
              <dd>
                <Link href={`/assets/${l.asset.id}`}>
                  {l.asset.indication} · {label(l.asset.modality)} →
                </Link>
              </dd>
            </dl>
            {l.pitch && <p style={{ marginTop: 10 }}>{l.pitch}</p>}
            <p className="disclaimer">
              Owner-provided information, not verified by Chorizo. Not an offer to sell securities.
            </p>
          </Panel>
        </div>
        <div>
          <Panel title="Data room">
            <table>
              <tbody>
                {l.documents.map((d) => (
                  <tr key={d.id}>
                    <td>{d.locked ? <span className="muted">🔒 {d.title}</span> : <a href={d.url!}>{d.title}</a>}</td>
                    <td className="muted">{label(d.kind)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {l.documents.some((d) => d.locked) && (
              <p className="disclaimer">
                Locked documents need a <Link href="/pricing">Pro or Institutional plan</Link>.
              </p>
            )}
          </Panel>
          <Panel title="Contact owner">
            {canContact ? (
              <form action={expressInterest} className="stack">
                <input type="hidden" name="listing_id" value={l.id} />
                <textarea name="message" rows={4} placeholder="Introduce yourself and your interest" />
                <button>SEND INTEREST</button>
              </form>
            ) : (
              <p className="muted">
                <Link href="/pricing">Upgrade to Pro</Link> to contact owners.
              </p>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

export default function ListingPage(props: PageProps<"/listings/[id]">) {
  return (
    <Suspense fallback={<Loading />}>
      <ListingPageContent {...props} />
    </Suspense>
  );
}
