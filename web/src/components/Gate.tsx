"use client";

import { useActionState } from "react";

import { Tesseract } from "@/components/Tesseract";
import { Logo } from "@/components/ui";
import { enterTerminal, type FormState } from "@/lib/actions";

export function Gate() {
  const [state, action, pending] = useActionState<FormState, FormData>(enterTerminal, {});
  const status = pending ? "AUTHENTICATING" : state.error ? state.error : "AWAITING CREDENTIALS";

  return (
    <main className="gate">
      <div className="gate-stage">
        <Tesseract />
        <form action={action} className="gate-form">
          <div className="gate-brand">
            <Logo size={22} />
            <span>CHORIZO</span>
          </div>
          <p className="gate-tag">SECURE TERMINAL ACCESS</p>
          <label>
            USER ID
            <input name="user" autoComplete="username" autoFocus spellCheck={false} />
          </label>
          <label>
            PASSWORD
            <input name="password" type="password" autoComplete="current-password" />
          </label>
          <button disabled={pending}>{pending ? "…" : "ENTER"}</button>
          <p className={`gate-status${state.error && !pending ? " error" : ""}`} role="status">
            &gt; {status}
            <span className="cursor" />
          </p>
        </form>
      </div>
    </main>
  );
}
