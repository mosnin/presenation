"use client";

import { useAuthActions } from "@convex-dev/auth/react";
import { useState } from "react";

export default function SignIn() {
  const { signIn } = useAuthActions();
  const [flow, setFlow] = useState<"signIn" | "signUp">("signIn");
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="panel" style={{ maxWidth: 380, margin: "4rem auto" }}>
      <h1>{flow === "signIn" ? "Sign in" : "Create account"}</h1>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          const formData = new FormData(e.currentTarget);
          formData.set("flow", flow);
          try {
            await signIn("password", formData);
          } catch {
            setError(
              flow === "signIn"
                ? "Could not sign in. Check your email and password."
                : "Could not create the account. Try a longer password."
            );
          }
        }}
      >
        <label htmlFor="email">Email</label>
        <input id="email" name="email" type="email" required />
        <label htmlFor="password">Password</label>
        <input id="password" name="password" type="password" required />
        {error && (
          <p className="hint" style={{ color: "var(--danger)" }}>
            {error}
          </p>
        )}
        <button type="submit">
          {flow === "signIn" ? "Sign in" : "Sign up"}
        </button>
      </form>
      <p className="hint">
        {flow === "signIn" ? "No account?" : "Already have an account?"}{" "}
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setFlow(flow === "signIn" ? "signUp" : "signIn");
          }}
        >
          {flow === "signIn" ? "Sign up" : "Sign in"}
        </a>
      </p>
    </div>
  );
}
