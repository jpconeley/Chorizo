import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { TOKEN_COOKIE } from "@/lib/api";

/** Clear a stale or expired session and go back to the entry gate. */
export function GET(request: NextRequest) {
  const response = NextResponse.redirect(new URL("/", request.url));
  response.cookies.delete(TOKEN_COOKIE);
  return response;
}
