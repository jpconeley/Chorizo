"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { api, API_URL, TOKEN_COOKIE } from "@/lib/api";

export type FormState = { error?: string };

/** Exchange credentials for an API token, or null if they're wrong or the API is down. */
async function apiLogin(email: string, password: string): Promise<string | null> {
  const response = await fetch(`${API_URL}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  }).catch(() => null);
  if (!response?.ok) return null;
  const body = await response.json().catch(() => ({}));
  return typeof body.access_token === "string" ? body.access_token : null;
}

/**
 * The entry gate. Real credentials log in as that user. While CHORIZO_OPEN_GATE=1 (local
 * development only), any other user ID and password enter as the shared demo account,
 * so the whole terminal can be explored. Never set it in production.
 */
export async function enterTerminal(_: FormState, formData: FormData): Promise<FormState> {
  const user = String(formData.get("user") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (!user || !password) return { error: "ENTER USER ID AND PASSWORD" };

  let token = await apiLogin(user, password);
  if (!token && process.env.CHORIZO_OPEN_GATE === "1") {
    token = await apiLogin(
      process.env.CHORIZO_OPEN_GATE_EMAIL ?? "institutional@chorizo-demo.example.com",
      process.env.CHORIZO_OPEN_GATE_PASSWORD ?? "chorizo-demo-pass",
    );
  }
  if (!token) return { error: "ACCESS DENIED" };

  (await cookies()).set(TOKEN_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24,
  });
  redirect("/dashboard");
}

export async function logout() {
  (await cookies()).delete(TOKEN_COOKIE);
  redirect("/");
}

export async function startCheckout(formData: FormData) {
  const result = await api<{ url: string }>("/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ plan: formData.get("plan"), seats: Number(formData.get("seats") ?? 1) }),
  });
  if (!result.ok) {
    if (result.status === 401) redirect("/");
    redirect(`/pricing?error=${encodeURIComponent(result.message)}`);
  }
  redirect(result.data.url);
}

export async function openBillingPortal() {
  const result = await api<{ url: string }>("/billing/portal", { method: "POST" });
  if (!result.ok) redirect(`/account?error=${encodeURIComponent(result.message)}`);
  redirect(result.data.url);
}

export async function toggleWatch(formData: FormData) {
  const assetId = formData.get("asset_id");
  const method = formData.get("watching") === "true" ? "DELETE" : "PUT";
  const result = await api(`/watchlist/${assetId}`, { method });
  if (!result.ok && result.upgrade) redirect("/pricing");
  redirect(`/assets/${assetId}`);
}

export async function expressInterest(formData: FormData) {
  const listingId = formData.get("listing_id");
  const result = await api(`/listings/${listingId}/interest`, {
    method: "POST",
    body: JSON.stringify({ message: formData.get("message") || null }),
  });
  if (!result.ok) {
    if (result.status === 401 || result.upgrade) redirect("/pricing");
    redirect(`/listings/${listingId}?error=${encodeURIComponent(result.message)}`);
  }
  redirect(`/listings/${listingId}?sent=1`);
}
