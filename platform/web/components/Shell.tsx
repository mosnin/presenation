"use client";

import { useAuthActions } from "@convex-dev/auth/react";
import { Authenticated, Unauthenticated, AuthLoading } from "convex/react";
import Link from "next/link";
import { ReactNode } from "react";
import SignIn from "./SignIn";

export default function Shell({ children }: { children: ReactNode }) {
  const { signOut } = useAuthActions();
  return (
    <div className="container">
      <AuthLoading>
        <p className="hint">Loading…</p>
      </AuthLoading>
      <Unauthenticated>
        <SignIn />
      </Unauthenticated>
      <Authenticated>
        <nav className="topbar">
          <span className="brand">Presenton Platform</span>
          <Link href="/">Jobs</Link>
          <Link href="/keys">API keys</Link>
          <span className="spacer" />
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              void signOut();
            }}
          >
            Sign out
          </a>
        </nav>
        {children}
      </Authenticated>
    </div>
  );
}
