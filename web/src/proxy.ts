import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const TOKEN_COOKIE = "chorizo_token"; // see lib/api.ts

/**
 * The terminal sits behind the entry gate at "/": without a session cookie every page
 * sends you to the gate, and with one the gate sends you on to the screener. This is
 * only an optimistic check; the API still verifies the token on every request.
 */
export function proxy(request: NextRequest) {
  const signedIn = request.cookies.has(TOKEN_COOKIE);
  const atGate = request.nextUrl.pathname === "/";
  if (atGate && signedIn) return NextResponse.redirect(new URL("/screener", request.url));
  if (!atGate && !signedIn) return NextResponse.redirect(new URL("/", request.url));
  return NextResponse.next();
}

export const config = {
  // Everything except Next.js internals and static files.
  matcher: ["/((?!_next/|favicon.ico|.*\\.[a-z0-9]+$).*)"],
};
