import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { api } from "@/lib/api";
import type { AssetPage, SearchHit } from "@/lib/types";

/** Command-bar suggestions. The browser can't reach the API directly, so this relays. */
export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  if (q.length < 2) return NextResponse.json([]);
  const result = await api<AssetPage>(`/assets?${new URLSearchParams({ q, limit: "8" })}`);
  if (!result.ok) return NextResponse.json([], { status: result.status });
  const hits: SearchHit[] = result.data.items.map((a) => ({
    id: a.id,
    name: a.name,
    stage: a.stage,
    indication: a.indication,
    sponsor: a.organization?.name ?? null,
  }));
  return NextResponse.json(hits);
}
