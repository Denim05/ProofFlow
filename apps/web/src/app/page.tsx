"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import { CaseResponse, CaseStatus } from "@/types/api";
import { api, ApiError } from "@/lib/api";
import { CaseCard } from "@/components/CaseCard";
import {
  FolderPlus,
  RefreshCw,
  Search,
  Filter,
  AlertTriangle,
  FolderOpen,
  Plus,
  ShieldCheck,
  Activity,
  Layers,
  Sparkles,
  X,
} from "lucide-react";

export default function CasesDashboardPage() {
  const [cases, setCases] = useState<CaseResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Create Case modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createTitle, setCreateTitle] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createTags, setCreateTags] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const fetchCases = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const statusParam =
        selectedStatus !== "ALL" ? (selectedStatus as CaseStatus) : undefined;
      const res = await api.listCases({ limit: 50, status: statusParam });
      setCases(res.items);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to connect to ProofFlow backend. Make sure the API server is running on http://127.0.0.1:8000.");
      }
    } finally {
      setLoading(false);
    }
  }, [selectedStatus]);

  useEffect(() => {
    fetchCases();
  }, [fetchCases]);

  const handleCreateCase = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createTitle.trim()) return;

    setCreating(true);
    setCreateError(null);

    try {
      const tagsList = createTags
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t.length > 0);

      await api.createCase({
        title: createTitle.trim(),
        description: createDesc.trim() || undefined,
        tags: tagsList.length > 0 ? tagsList : undefined,
      });

      setShowCreateModal(false);
      setCreateTitle("");
      setCreateDesc("");
      setCreateTags("");
      fetchCases();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setCreateError(err.message);
      } else {
        setCreateError("Failed to create case");
      }
    } finally {
      setCreating(false);
    }
  };

  // Metrics computed purely from real cases data
  const metrics = useMemo(() => {
    const total = cases.length;
    const ready = cases.filter((c) => c.status === "READY").length;
    const processing = cases.filter((c) =>
      ["PROCESSING", "EXTRACTING", "STRUCTURING", "ANALYZING", "QUEUED"].includes(c.status)
    ).length;
    const reviewNeeded = cases.filter((c) => c.status === "REVIEW_NEEDED").length;

    return { total, ready, processing, reviewNeeded };
  }, [cases]);

  const filteredCases = cases.filter((c) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      c.title.toLowerCase().includes(q) ||
      c.description.toLowerCase().includes(q) ||
      c.tags.some((t) => t.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-cyan-950/60 border border-cyan-500/30 text-cyan-300 text-xs font-mono mb-2">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
            INTELLIGENCE OPS // CASES REPOSITORY
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white flex items-center gap-3">
            Incident Cases
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Reconstruct timelines, ingest documentary evidence, and cross-examine events.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchCases}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium text-slate-300 glass-panel rounded-xl hover:text-white hover:border-slate-700 transition shadow-xs disabled:opacity-50"
            title="Refresh cases"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-cyan-400" : ""}`} />
            Refresh
          </button>

          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-950 bg-gradient-to-r from-cyan-400 to-cyan-300 rounded-xl hover:shadow-neon-cyan hover:brightness-110 transition shadow-md"
          >
            <Plus className="w-4 h-4 stroke-[2.5]" />
            New Case
          </button>
        </div>
      </div>

      {/* Summary Metrics Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass-panel p-4 rounded-xl border border-slate-800/80 flex items-center justify-between">
          <div>
            <div className="text-xs font-mono uppercase tracking-wider text-slate-400">Total Cases</div>
            <div className="text-2xl font-bold text-white mt-1">{metrics.total}</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-cyan-950/60 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
            <Layers className="w-5 h-5" />
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-slate-800/80 flex items-center justify-between">
          <div>
            <div className="text-xs font-mono uppercase tracking-wider text-emerald-400">Ready / Validated</div>
            <div className="text-2xl font-bold text-white mt-1">{metrics.ready}</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-emerald-950/60 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <ShieldCheck className="w-5 h-5" />
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-slate-800/80 flex items-center justify-between">
          <div>
            <div className="text-xs font-mono uppercase tracking-wider text-cyan-400">Processing</div>
            <div className="text-2xl font-bold text-white mt-1">{metrics.processing}</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-cyan-950/60 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
            <Activity className="w-5 h-5 animate-pulse" />
          </div>
        </div>

        <div className="glass-panel p-4 rounded-xl border border-slate-800/80 flex items-center justify-between">
          <div>
            <div className="text-xs font-mono uppercase tracking-wider text-amber-400">Review Needed</div>
            <div className="text-2xl font-bold text-white mt-1">{metrics.reviewNeeded}</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-amber-950/60 border border-amber-500/30 flex items-center justify-center text-amber-400">
            <AlertTriangle className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="glass-panel p-4 rounded-2xl flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Search Input */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search cases by title, narrative, or tag..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm rounded-xl bg-slate-900/80 text-white placeholder-slate-500 border border-slate-700/80 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20 transition"
          />
        </div>

        {/* Status Filter Buttons */}
        <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
          <Filter className="w-3.5 h-3.5 text-slate-400 mr-1 hidden sm:inline" />
          {["ALL", "READY", "PROCESSING", "REVIEW_NEEDED", "ARCHIVED"].map(
            (statusKey) => (
              <button
                key={statusKey}
                onClick={() => setSelectedStatus(statusKey)}
                className={`px-3 py-1.5 rounded-lg border transition ${
                  selectedStatus === statusKey
                    ? "bg-cyan-500/20 text-cyan-300 border-cyan-400/60 shadow-neon-cyan"
                    : "bg-slate-900/60 text-slate-400 border-slate-800 hover:bg-slate-800 hover:text-white"
                }`}
              >
                {statusKey.replace(/_/g, " ")}
              </button>
            )
          )}
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-rose-950/40 border border-rose-500/50 text-rose-200 px-4 py-3.5 rounded-xl flex items-start gap-3 backdrop-blur-xs">
          <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-rose-200">Backend Connection Notice</h4>
            <p className="text-sm mt-0.5 text-rose-300/90">{error}</p>
          </div>
          <button
            onClick={fetchCases}
            className="text-xs font-semibold underline text-rose-300 hover:text-rose-100"
          >
            Retry
          </button>
        </div>
      )}

      {/* Cases Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {[1, 2, 3, 4, 5, 6].map((idx) => (
            <div
              key={idx}
              className="glass-panel rounded-2xl p-6 space-y-4 animate-pulse border border-slate-800/80"
            >
              <div className="h-5 bg-slate-800 rounded w-3/4"></div>
              <div className="h-4 bg-slate-800/60 rounded w-full"></div>
              <div className="h-4 bg-slate-800/60 rounded w-2/3"></div>
              <div className="pt-4 border-t border-slate-800 flex justify-between">
                <div className="h-3 bg-slate-800 rounded w-1/4"></div>
                <div className="h-3 bg-slate-800 rounded w-1/4"></div>
              </div>
            </div>
          ))}
        </div>
      ) : filteredCases.length === 0 ? (
        <div className="glass-panel rounded-2xl p-12 text-center max-w-lg mx-auto border border-slate-800">
          <div className="w-14 h-14 bg-cyan-950/60 border border-cyan-500/30 text-cyan-400 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-neon-cyan">
            <FolderOpen className="w-7 h-7" />
          </div>
          <h3 className="text-lg font-bold text-white">
            {cases.length === 0 ? "No incident cases yet" : "No matching cases"}
          </h3>
          <p className="mt-2 text-sm text-slate-400 leading-relaxed">
            {cases.length === 0
              ? "Create your first case to begin ingesting evidence and analyzing chronology."
              : "Try adjusting your search query or status filter."}
          </p>
          {cases.length === 0 && (
            <button
              onClick={() => setShowCreateModal(true)}
              className="mt-6 inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-slate-950 bg-gradient-to-r from-cyan-400 to-cyan-300 rounded-xl hover:shadow-neon-cyan hover:brightness-110 transition"
            >
              <FolderPlus className="w-4 h-4 stroke-[2.5]" />
              Create First Case
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredCases.map((c) => (
            <CaseCard key={c.case_id} caseItem={c} />
          ))}
        </div>
      )}

      {/* Create Case Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in duration-200">
          <div className="glass-panel-elevated rounded-2xl max-w-lg w-full p-6 border border-slate-700/80 shadow-2xl relative">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <Sparkles className="w-5 h-5 text-cyan-400" />
                <h3 className="text-lg font-bold text-white tracking-tight">Create New Incident Case</h3>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateCase} className="mt-5 space-y-4">
              {createError && (
                <div className="text-xs text-rose-300 bg-rose-950/50 border border-rose-500/40 p-3 rounded-xl flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                  {createError}
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5 font-mono">
                  Case Title *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Supply Chain Contract Breach — Vendor A"
                  value={createTitle}
                  onChange={(e) => setCreateTitle(e.target.value)}
                  className="w-full px-3.5 py-2.5 text-sm rounded-xl bg-slate-900/90 text-white placeholder-slate-500 border border-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5 font-mono">
                  Narrative Description
                </label>
                <textarea
                  rows={3}
                  placeholder="Provide background context on the incident or dispute..."
                  value={createDesc}
                  onChange={(e) => setCreateDesc(e.target.value)}
                  className="w-full px-3.5 py-2.5 text-sm rounded-xl bg-slate-900/90 text-white placeholder-slate-500 border border-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5 font-mono">
                  Tags (comma separated)
                </label>
                <input
                  type="text"
                  placeholder="contract, invoices, delay"
                  value={createTags}
                  onChange={(e) => setCreateTags(e.target.value)}
                  className="w-full px-3.5 py-2.5 text-sm rounded-xl bg-slate-900/90 text-white placeholder-slate-500 border border-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20 transition"
                />
              </div>

              <div className="pt-4 border-t border-slate-800 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/60 rounded-xl transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating || !createTitle.trim()}
                  className="px-5 py-2 text-sm font-semibold text-slate-950 bg-gradient-to-r from-cyan-400 to-cyan-300 hover:brightness-110 rounded-xl transition shadow-neon-cyan disabled:opacity-50"
                >
                  {creating ? "Creating..." : "Create Case"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
