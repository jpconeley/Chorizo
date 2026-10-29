import type { Metadata } from "next";

import { Gate } from "@/components/Gate";

export const metadata: Metadata = { title: "LASO · Secure access" };

export default function EntryPage() {
  return <Gate />;
}
