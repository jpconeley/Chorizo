import { Suspense } from "react";
import type { Metadata } from "next";

import { ApiDown, Loading, Panel } from "@/components/ui";
import { startCheckout } from "@/lib/actions";
import { api, getMe } from "@/lib/api";
import { FEATURE_LABEL, label } from "@/lib/format";
import type { PlanInfo } from "@/lib/types";

export const metadata: Metadata = { title: "Plans" };

async function PricingContent(props: PageProps<"/pricing">) {
  const params = await props.searchParams;
  const [plans, me] = await Promise.all([api<PlanInfo[]>("/plans"), getMe()]);
  if (!plans.ok) return <ApiDown />;

  return (
    <>
      <h1>Plans</h1>
      <p className="sub">Free to browse. Paid plans unlock the analytics, deal flow and data tools.</p>
      {typeof params.error === "string" && <div className="notice error">{params.error}</div>}
      <div className="plans">
        {plans.data.map((p) => {
          const current = p.plan === "free" ? !me?.plans.length : me?.plans.includes(p.plan);
          return (
            <Panel key={p.plan} title={p.name} right={current && <span className="up">CURRENT</span>}>
              <p className="muted">{p.audience}</p>
              <ul>
                {p.features.map((f) => (
                  <li key={f}>{FEATURE_LABEL[f] ?? label(f)}</li>
                ))}
              </ul>
              {p.plan !== "free" && !current && (
                <form action={startCheckout} style={{ display: "flex", gap: 6 }}>
                  <input type="hidden" name="plan" value={p.plan} />
                  {p.per_seat && (
                    <input name="seats" type="number" min={1} defaultValue={3} style={{ width: 70 }} aria-label="Seats" />
                  )}
                  <button>SUBSCRIBE{p.per_seat ? " (SEATS)" : ""}</button>
                </form>
              )}
            </Panel>
          );
        })}
      </div>
    </>
  );
}

export default function Pricing(props: PageProps<"/pricing">) {
  return (
    <Suspense fallback={<Loading />}>
      <PricingContent {...props} />
    </Suspense>
  );
}
