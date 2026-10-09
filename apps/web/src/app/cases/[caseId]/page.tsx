"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  CaseResponse,
  EvidenceResponse,
  EvidenceUploadResponse,
  EventResponse,
} from "@/types/api";
import { api, ApiError } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { EvidenceUploader } from "@/components/EvidenceUploader";
import { EvidenceList } from "@/components/EvidenceList";
import { EventTimeline } from "@/components/EventTimeline";
import { CrossEvidenceComparison } from "@/components/CrossEvidenceComparison";
import {
  ArrowLeft,
  FileText,
  Clock,
  AlertCircle,
  Calendar,
  Tag,
  GitCompare,
} from "lucide-react";

export default function CaseDetailsPage() {
  const params = useParams();
  const caseId = params?.caseId as string;

  const [caseItem, setCaseItem] = useState<CaseResponse | null>(null);
  const [evidenceList, setEvidenceList] = useState<EvidenceResponse[]>([]);
  const [events, setEvents] = useState<EventResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Tab State
  const [activeTab, setActiveTab] = useState<"EVIDENCE" | "TIMELINE" | "CROSS_EXAM">("EVIDENCE");

  const fetchCaseAndEvidence = useCallback(async () => {
    if (!caseId) return;
    try {
      const [caseRes, evidenceRes] = await Promise.all([
        api.getCase(caseId),
        api.listEvidence(caseId, { limit: 100 }),
      ]);
      setCaseItem(caseRes);
      setEvidenceList(evidenceRes.items);
      setError(null);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to load case data");
      }
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    setLoading(true);
    fetchCaseAndEvidence();
  }, [fetchCaseAndEvidence, refreshTrigger]);

  const handleUploadSuccess = (upload: EvidenceUploadResponse) => {
    // Notify EvidenceList and EventTimeline to refresh
    setRefreshTrigger((prev) => prev + 1);
  };

  const handleEventsLoaded = useCallback((loadedEvents: EventResponse[]) => {
    setEvents(loadedEvents);
  }, []);

  const formattedDate = caseItem
    ? new Date(caseItem.created_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "";

  return (
    <div className="space-y-6">
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-900 transition"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        Back to Incident Cases
      </Link>

      {loading && !caseItem ? (
        <div className="bg-white rounded-xl border border-slate-200 p-8 animate-pulse space-y-4">
          <div className="h-6 bg-slate-200 rounded w-1/3"></div>
          <div className="h-4 bg-slate-100 rounded w-2/3"></div>
        </div>
      ) : error ? (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 p-6 rounded-xl flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-sm">Error Loading Case</h3>
            <p className="text-sm text-rose-700 mt-1">{error}</p>
          </div>
        </div>
      ) : caseItem ? (
        <div className="space-y-6">
          {/* Case Header Card */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-6 shadow-sm space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-3 flex-wrap">
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                    {caseItem.title}
                  </h1>
                  <StatusBadge status={caseItem.status} />
                </div>
                <div className="flex items-center gap-3 text-xs text-slate-400 mt-1.5 font-mono">
                  <span>ID: {caseItem.case_id}</span>
                  <span>•</span>
                  <span className="flex items-center gap-1 font-sans">
                    <Calendar className="w-3.5 h-3.5 text-slate-400" />
                    {formattedDate}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs font-medium text-slate-700 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-brand-600" />
                  <span>{caseItem.evidence_count} Ingested Documents</span>
                </div>
              </div>
            </div>

            {caseItem.description && (
              <p className="text-sm text-slate-600 leading-relaxed border-t border-slate-100 pt-3">
                {caseItem.description}
              </p>
            )}

            {caseItem.tags && caseItem.tags.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                {caseItem.tags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 text-[11px] font-medium bg-slate-100 text-slate-600 px-2 py-0.5 rounded"
                  >
                    <Tag className="w-2.5 h-2.5 text-slate-400" />
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Workspace Tabs Navigation */}
          <div className="flex items-center gap-2 border-b border-slate-200 pb-px">
            <button
              onClick={() => setActiveTab("EVIDENCE")}
              className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition -mb-px ${
                activeTab === "EVIDENCE"
                  ? "border-brand-600 text-brand-600 bg-white rounded-t-lg"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>Evidence Ingestion</span>
              <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-600 font-mono">
                {evidenceList.length}
              </span>
            </button>

            <button
              onClick={() => setActiveTab("TIMELINE")}
              className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition -mb-px ${
                activeTab === "TIMELINE"
                  ? "border-brand-600 text-brand-600 bg-white rounded-t-lg"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <Clock className="w-4 h-4" />
              <span>Event Timeline</span>
              <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-600 font-mono">
                {events.length}
              </span>
            </button>

            <button
              onClick={() => setActiveTab("CROSS_EXAM")}
              className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition -mb-px ${
                activeTab === "CROSS_EXAM"
                  ? "border-brand-600 text-brand-600 bg-white rounded-t-lg"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <GitCompare className="w-4 h-4" />
              <span>Cross-Examination</span>
            </button>
          </div>

          {/* Active Tab Content */}
          {activeTab === "EVIDENCE" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-1">
                <EvidenceUploader
                  caseId={caseItem.case_id}
                  onUploadSuccess={handleUploadSuccess}
                />
              </div>

              <div className="lg:col-span-2">
                <EvidenceList
                  caseId={caseItem.case_id}
                  refreshTrigger={refreshTrigger}
                />
              </div>
            </div>
          )}

          {activeTab === "TIMELINE" && (
            <EventTimeline
              caseId={caseItem.case_id}
              evidenceList={evidenceList}
              onEventsLoaded={handleEventsLoaded}
              refreshTrigger={refreshTrigger}
            />
          )}

          {activeTab === "CROSS_EXAM" && (
            <CrossEvidenceComparison
              caseId={caseItem.case_id}
              events={events}
              evidenceList={evidenceList}
            />
          )}
        </div>
      ) : null}
    </div>
  );
}
