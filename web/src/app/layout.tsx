import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Chorizo", template: "%s · Chorizo" },
  description: "Biotech asset marketplace and drug-development analytics.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
