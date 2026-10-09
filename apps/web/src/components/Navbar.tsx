"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
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
            <div className="w-9 h-9 rounded-lg bg-brand-600 text-white flex items-center justify-center shadow-sm group-hover:bg-brand-700 transition">
              <Shield className="w-5 h-5" />
            </div>
            <span className="tracking-tight">
              Proof<span className="text-brand-600">Flow</span>
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-slate-600">
            <Link href="/" className="hover:text-slate-900 transition py-1 text-brand-600 border-b-2 border-brand-600">
              Cases
            </Link>
            <span className="text-slate-300">|</span>
            <span className="text-slate-400 cursor-not-allowed text-xs uppercase tracking-wider font-semibold">
              Track 5B Workspace
            </span>
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {/* Health indicator */}
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-slate-50 border border-slate-200 text-xs text-slate-600">
            <Database className="w-3.5 h-3.5 text-slate-400" />
            <span>Atlas DB:</span>
            {dbHealthy === null ? (
              <span className="text-slate-400 flex items-center gap-1">Checking...</span>
            ) : dbHealthy ? (
              <span className="text-emerald-600 font-medium flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Connected
              </span>
            ) : (
              <span className="text-amber-600 font-medium flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5 text-amber-500" /> Standby
              </span>
            )}
          </div>

          {/* Dev user badge */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-indigo-50 border border-indigo-100 text-xs font-medium text-indigo-700">
            <Activity className="w-3.5 h-3.5 text-indigo-500" />
            <span>dev_user_default</span>
          </div>
        </div>
      </div>
    </header>
  );
}
