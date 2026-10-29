import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Loading, Panel, StageBadge } from "@/components/ui";
import { openBillingPortal } from "@/lib/actions";
import { api, getMe } from "@/lib/api";
import { FEATURE_LABEL, label } from "@/lib/format";
import type { AssetSummary } from "@/lib/types";

export const metadata: Metadata = { title: "Account" };

async function AccountContent(props: PageProps<"/account">) {
  const params = await props.searchParams;
  const me = await getMe();
  if (!me) redirect("/login");
  const watchlist = me.features.includes("watchlists") ? await api<AssetSummary[]>("/watchlist") : null;

  return (
    <>
      <h1>Account</h1>
      <p className="sub">{me.email}</p>
      {params.checkout === "success" && (
        <div className="notice">Thanks for subscribing. Your plan activates as soon as payment confirms.</div>
      )}
      {typeof params.error === "string" && <div className="notice error">{params.error}</div>}
      <div className="grid">
        <div>
          <Panel title="Watchlist">
            {watchlist?.ok ? (
              watchlist.data.length ? (
                <table>
                  <tbody>
                    {watchlist.data.map((a) => (
                      <tr key={a.id}>
                        <td>
                          <Link href={`/assets/${a.id}`}>{a.name}</Link>
                        </td>
                        <td>
                          <StageBadge stage={a.stage} />
                        </td>
                        <td>{a.indication}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted">Nothing watched yet. Use WATCH on any asset page.</p>
              )
            ) : (
              <p className="muted">
                Watchlists come with <Link href="/pricing">Pro</Link>.
              </p>
            )}
          </Panel>
        </div>
        <div>
          <Panel title="Subscription">
            <p>
              Plan:{" "}
              <span className="accent">{me.plans.length ? me.plans.map(label).join(" + ") : "Free"}</span>
            </p>
            <ul style={{ listStyle: "none", margin: "10px 0" }} className="muted">
              {me.features.map((f) => (
                <li key={f}>› {FEATURE_LABEL[f] ?? label(f)}</li>
              ))}
            </ul>
            <div style={{ display: "flex", gap: 8 }}>
              <Link href="/pricing" className="button">
                CHANGE PLAN
              </Link>
              <form action={openBillingPortal}>
                <button className="ghost">MANAGE BILLING</button>
              </form>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}

export default function Account(props: PageProps<"/account">) {
  return (
    <Suspense fallback={<Loading />}>
      <AccountContent {...props} />
    </Suspense>
  );
}
