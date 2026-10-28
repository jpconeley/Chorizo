"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { api, API_URL, TOKEN_COOKIE } from "@/lib/api";

export type FormState = { error?: string };

async function authenticate(path: string, formData: FormData): Promise<FormState> {
  const response = await fetch(`${API_URL}/v1/auth/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: formData.get("email"), password: formData.get("password") }),
  }).catch(() => null);
  if (!response) return { error: "Cannot reach the API." };
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail;
    return { error: typeof detail === "string" ? detail : "Check your email and password (10+ characters)." };
  }
  (await cookies()).set(TOKEN_COOKIE, body.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24,
  });
  redirect("/account");
}

export async function login(_: FormState, formData: FormData) {
  return authenticate("login", formData);
}

export async function register(_: FormState, formData: FormData) {
  return authenticate("register", formData);
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
    if (result.status === 401) redirect("/login?next=/pricing");
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
