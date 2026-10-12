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
    <header className="sticky top-0 z-40 w-full border-b border-white/10 bg-[#050b18]/80 backdrop-blur-xl shadow-[0_4px_24px_rgba(0,0,0,0.5)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-3 font-bold text-xl text-slate-100 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500/20 via-blue-500/10 to-violet-500/20 text-cyan-300 border border-cyan-500/30 flex items-center justify-center shadow-neon-cyan group-hover:border-cyan-400/60 group-hover:scale-105 transition-all">
              <Shield className="w-4 h-4 text-cyan-300" />
            </div>
            <span className="tracking-tight text-slate-100 flex items-center gap-2">
              <span>Proof<span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-400">Flow</span></span>
              <span className="hidden lg:inline-flex items-center text-[10px] font-mono uppercase tracking-widest text-cyan-400/90 bg-cyan-950/60 border border-cyan-500/20 px-2 py-0.5 rounded-full">
                AI Core v2.4
              </span>
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-slate-400">
            <Link
              href="/"
              className="py-1 text-cyan-300 border-b-2 border-cyan-400 font-semibold drop-shadow-[0_0_8px_rgba(6,182,212,0.4)] transition"
            >
              Cases
            </Link>
            <span className="text-slate-700">|</span>
            <span className="text-slate-500 cursor-not-allowed text-xs uppercase tracking-wider font-semibold font-mono">
              Track 5B Workspace
            </span>
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {/* Health indicator */}
          <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg bg-slate-900/90 border border-white/10 text-xs text-slate-300 font-mono shadow-glass">
            <Database className="w-3.5 h-3.5 text-slate-400" />
            <span className="font-sans font-medium text-slate-400">Atlas DB:</span>
            {dbHealthy === null ? (
              <span className="text-slate-400 flex items-center gap-1 font-sans">Checking...</span>
            ) : dbHealthy ? (
              <span className="text-emerald-400 font-semibold flex items-center gap-1.5 font-sans">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_#10B981] animate-pulse" />
                Connected
              </span>
            ) : (
              <span className="text-amber-400 font-semibold flex items-center gap-1.5 font-sans">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shadow-[0_0_8px_#F59E0B]" />
                Standby
              </span>
            )}
          </div>

          {/* Clerk Authentication Controls */}
          <SignedIn>
            <div className="flex items-center gap-3">
              {process.env.NODE_ENV !== "production" && (
                <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-0.5 rounded-md bg-amber-950/60 border border-amber-500/30 text-[11px] font-medium text-amber-300 font-mono">
                  <Activity className="w-3 h-3 text-amber-400" />
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
                  className="px-4 py-1.5 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-bold text-xs shadow-neon-cyan transition-all"
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
