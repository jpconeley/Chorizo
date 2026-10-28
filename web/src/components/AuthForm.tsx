"use client";

import { useActionState } from "react";

import type { FormState } from "@/lib/actions";

export function AuthForm({
  action,
  submitLabel,
}: {
  action: (state: FormState, formData: FormData) => Promise<FormState>;
  submitLabel: string;
}) {
  const [state, formAction, pending] = useActionState(action, {});
  return (
    <form action={formAction}>
      <input name="email" type="email" placeholder="Email" required autoComplete="email" />
      <input name="password" type="password" placeholder="Password" required minLength={10} />
      {state.error && <p className="error">{state.error}</p>}
      <button disabled={pending}>{pending ? "…" : submitLabel}</button>
    </form>
  );
}
