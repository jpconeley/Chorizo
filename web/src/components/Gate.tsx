"use client";

import { useActionState, useState } from "react";

import { Tesseract } from "@/components/Tesseract";
import { Logo } from "@/components/ui";
import { enterTerminal, type FormState } from "@/lib/actions";

export function Gate() {
  const [state, action, pending] = useActionState<FormState, FormData>(enterTerminal, {});
  // Controlled, so a failed attempt doesn't wipe what was typed (forms reset after an action).
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");

  return (
    <main className="gate">
      <div className="gate-stage">
        <Tesseract />
        <form action={action} className="gate-form">
          <div className="gate-brand">
            <Logo size={22} />
            <span>CHORIZO</span>
          </div>
          <label>
            USER ID
            <input
              name="user"
              autoComplete="username"
              autoFocus
              spellCheck={false}
              value={user}
              onChange={(e) => setUser(e.target.value)}
            />
          </label>
          <label>
            PASSWORD
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button disabled={pending}>{pending ? "…" : "ENTER"}</button>
          <p className="gate-error" role="alert">
            {!pending && state.error}
          </p>
        </form>
      </div>
    </main>
  );
}
