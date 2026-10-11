"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { SignedIn, SignedOut, UserButton, SignInButton } from "@clerk/nextjs";
import { Shield, Activity, Database, CheckCircle2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";

export function Navbar() {
  const [dbHealthy, setDbHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    let isMounted = true;
    api
      .getHealth()
      .then((res) => {
        if (isMounted) setDbHealthy(res.database === "connected");
      })
      .catch(() => {
        if (isMounted) setDbHealthy(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2.5 font-bold text-xl text-slate-900 group">
            <div className="w-8 h-8 rounded-lg bg-brand-600 text-cyan-400 border border-slate-800 flex items-center justify-center shadow-xs transition">
              <Shield className="w-4 h-4" />
            </div>
            <span className="tracking-tight text-slate-900">
              Proof<span className="text-cyan-600">Flow</span>
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-slate-600">
            <Link href="/" className="hover:text-slate-900 transition py-1 text-slate-900 border-b-2 border-cyan-600 font-semibold">
              Cases
            </Link>
            <span className="text-slate-300">|</span>
            <span className="text-slate-400 cursor-not-allowed text-xs uppercase tracking-wider font-semibold font-mono">
              Track 5B Workspace
            </span>
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {/* Health indicator */}
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-slate-50 border border-slate-200 text-xs text-slate-600 font-mono">
            <Database className="w-3.5 h-3.5 text-slate-400" />
            <span className="font-sans font-medium text-slate-500">Atlas DB:</span>
            {dbHealthy === null ? (
              <span className="text-slate-400 flex items-center gap-1 font-sans">Checking...</span>
            ) : dbHealthy ? (
              <span className="text-emerald-700 font-medium flex items-center gap-1 font-sans">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Connected
              </span>
            ) : (
              <span className="text-amber-700 font-medium flex items-center gap-1 font-sans">
                <AlertCircle className="w-3.5 h-3.5 text-amber-500" /> Standby
              </span>
            )}
          </div>

          {/* Clerk Authentication Controls */}
          <SignedIn>
            <div className="flex items-center gap-3">
              {process.env.NODE_ENV !== "production" && (
                <div className="hidden sm:flex items-center gap-1.5 px-2 py-0.5 rounded bg-amber-50 border border-amber-200 text-[11px] font-medium text-amber-800">
                  <Activity className="w-3 h-3 text-amber-600" />
                  <span>Dev Mode</span>
                </div>
              )}
              <UserButton afterSignOutUrl="/sign-in" />
            </div>
          </SignedIn>
          <SignedOut>
            <div className="flex items-center gap-2">
              <SignInButton mode="modal">
                <button
                  type="button"
                  className="px-3.5 py-1.5 rounded-lg bg-brand-600 hover:bg-slate-800 text-white text-xs font-semibold shadow-xs transition"
                >
                  Sign In
                </button>
              </SignInButton>
            </div>
          </SignedOut>
        </div>
      </div>
    </header>
  );
}
