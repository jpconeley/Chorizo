import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { Logo } from "@/components/ui";
import { logout } from "@/lib/actions";
import { getMe } from "@/lib/api";

const NAV = [
  ["SCRN", "/screener", "Screener"],
  ["BENCH", "/benchmarks", "Stage benchmarks"],
  ["DEAL", "/listings", "Funding listings"],
  ["PLANS", "/pricing", "Plans"],
] as const;

async function UserMenu() {
  const me = await getMe();
  if (!me) redirect("/exit"); // session expired or no longer valid
  return (
    <>
      <Link href="/account">
        {me.email} · {me.plans.length ? me.plans.join("+").toUpperCase() : "FREE"}
      </Link>
      <form action={logout}>
        <button className="ghost">LOGOUT</button>
      </form>
    </>
  );
}

/** The terminal chrome: top bar, function keys and status bar around every signed-in page. */
export default function TerminalLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <header className="topbar">
        <Link href="/screener" className="brand">
          <Logo />
          CHORIZO
          <small>BIO TERMINAL</small>
        </Link>
        <nav className="fnkeys">
          {NAV.map(([key, href, title]) => (
            <Link key={key} href={href} title={title}>
              {key}
            </Link>
          ))}
        </nav>
        <span className="spacer" />
        <Suspense>
          <UserMenu />
        </Suspense>
      </header>
      <main>{children}</main>
      <footer className="statusbar">
        <span className="live">DATA: ClinicalTrials.gov · Drugs@FDA · BIO/Biomedtracker 2006–2015</span>
        <span>Not investment advice. Estimates are historical base rates, not predictions.</span>
      </footer>
    </>
  );
}
