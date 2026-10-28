import type { Metadata } from "next";

import { AuthForm } from "@/components/AuthForm";
import { Panel } from "@/components/ui";
import { login, register } from "@/lib/actions";

export const metadata: Metadata = { title: "Log in" };

export default function Login() {
  return (
    <div className="auth">
      <Panel title="Log in">
        <AuthForm action={login} submitLabel="LOG IN" />
      </Panel>
      <Panel title="Create account">
        <AuthForm action={register} submitLabel="CREATE FREE ACCOUNT" />
      </Panel>
    </div>
  );
}
