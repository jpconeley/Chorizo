import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";

import { Logo } from "@/components/ui";
import { getMe } from "@/lib/api";
import { logout } from "@/lib/actions";
import "./globals.css";

const mono = IBM_Plex_Mono({ variable: "--font-mono", subsets: ["latin"], weight: ["400", "600", "700"] });
const sans = IBM_Plex_Sans({ variable: "--font-sans", subsets: ["latin"], weight: ["400", "600"] });

export const metadata: Metadata = {
  title: { default: "Chorizo", template: "%s · Chorizo" },
  description: "Biotech asset marketplace and drug-development analytics.",
};

const NAV = [
  ["SCRN", "/", "Screener"],
  ["BENCH", "/benchmarks", "Stage benchmarks"],
  ["DEAL", "/listings", "Funding listings"],
  ["PLANS", "/pricing", "Plans"],
] as const;

async function UserMenu() {
  const me = await getMe();
  if (!me) return <Link href="/login">LOGIN</Link>;
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

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${mono.variable} ${sans.variable}`}>
      <body>
        <header className="topbar">
          <Link href="/" className="brand">
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
      </body>
    </html>
  );
}
