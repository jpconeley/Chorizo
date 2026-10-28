import "server-only";

import { cookies } from "next/headers";

export const API_URL = process.env.CHORIZO_API_URL ?? "http://localhost:8000";
export const TOKEN_COOKIE = "chorizo_token";

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; upgrade?: UpgradeRequired; message: string };

export type UpgradeRequired = { code: "upgrade_required"; feature: string; plan: string | null };

/** Server-side fetch against the Chorizo API, sending the session token if present. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_URL}/v1${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    return { ok: false, status: 503, message: "API unreachable" };
  }
  if (response.ok) {
    const text = await response.text();
    return { ok: true, data: (text ? JSON.parse(text) : null) as T };
  }
  const body = await response.json().catch(() => ({}));
  const detail = body?.detail;
  if (detail?.code === "upgrade_required") {
    return { ok: false, status: response.status, upgrade: detail, message: "Upgrade required" };
  }
  return {
    ok: false,
    status: response.status,
    message: typeof detail === "string" ? detail : response.statusText,
  };
}

export type Me = { id: number; email: string; full_name: string | null; plans: string[]; features: string[] };

export async function getMe(): Promise<Me | null> {
  const result = await api<Me>("/me");
  return result.ok ? result.data : null;
}
