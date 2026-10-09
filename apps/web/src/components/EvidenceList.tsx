"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
import { EvidenceResponse, EvidenceStatus } from "@/types/api";
import { api, ApiError } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import {
  FileText,
  RefreshCw,
  RotateCcw,
  CheckCircle2,
  AlertOctagon,
  Copy,
  Check,
  Cpu,
} from "lucide-react";

interface EvidenceListProps {
  caseId: string;
  refreshTrigger?: number;
}

const IN_FLIGHT_STATUSES: EvidenceStatus[] = [
  "QUEUED",
  "EXTRACTING",
  "STRUCTURING",
  "ANALYZING",
];

const ALLOWED_RETRY_STATUSES: EvidenceStatus[] = [
  "FAILED",
  "INTERRUPTED",
  "REVIEW_NEEDED",
];

export function EvidenceList({ caseId, refreshTrigger }: EvidenceListProps) {
  const [evidenceItems, setEvidenceItems] = useState<EvidenceResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  const isMountedRef = useRef(true);

  const fetchEvidence = useCallback(async (isPolling = false) => {
    if (!isPolling) setLoading(true);
    try {
      const res = await api.listEvidence(caseId, { limit: 100 });
      if (isMountedRef.current) {
        setEvidenceItems(res.items);
        setError(null);
      }
    } catch (err: unknown) {
      if (isMountedRef.current) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Failed to fetch evidence list");
        }
      }
    } finally {
      if (isMountedRef.current && !isPolling) {
        setLoading(false);
      }
    }
  }, [caseId]);

  // Initial fetch and trigger re-fetch
  useEffect(() => {
    isMountedRef.current = true;
    fetchEvidence(false);
    return () => {
      isMountedRef.current = false;
    };
  }, [fetchEvidence, refreshTrigger]);

  // Polling management: automatically active while in-flight items exist, stops on complete/unmount
  useEffect(() => {
    const hasInFlight = evidenceItems.some((item) =>
      IN_FLIGHT_STATUSES.includes(item.status)
    );

    if (!hasInFlight) return;

    const intervalId = setInterval(() => {
      fetchEvidence(true);
    }, 2500);

    return () => clearInterval(intervalId);
  }, [evidenceItems, fetchEvidence]);

  const handleRetry = async (evidenceId: string) => {
    setRetryingId(evidenceId);
    setError(null);
    try {
      await api.retryEvidence(caseId, evidenceId);
      await fetchEvidence(true);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to retry evidence processing");
      }
    } finally {
      setRetryingId(null);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard?.writeText(text);
    setCopiedHash(text);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-brand-600" />
          <h3 className="text-sm font-bold text-slate-900 tracking-tight">
            Case Evidence Assets ({evidenceItems.length})
          </h3>
        </div>

        <button
          onClick={() => fetchEvidence(false)}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-slate-600 hover:text-slate-900 bg-slate-50 border border-slate-200 rounded-md transition hover:bg-slate-100 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 px-3.5 py-2.5 rounded-lg text-xs flex items-center justify-between">
          <span className="font-medium">{error}</span>
          <button
            onClick={() => fetchEvidence(false)}
            className="text-rose-900 font-semibold underline text-xs ml-2"
          >
            Retry
          </button>
        </div>
      )}

      {loading && evidenceItems.length === 0 ? (
        <div className="space-y-3 py-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-16 bg-slate-50 border border-slate-100 rounded-lg animate-pulse"
            />
          ))}
        </div>
      ) : evidenceItems.length === 0 ? (
        <div className="text-center py-10 px-4">
          <FileText className="w-8 h-8 text-slate-300 mx-auto mb-2" />
          <p className="text-sm font-semibold text-slate-700">
            No evidence documents uploaded yet
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Drag and drop contracts, statements, or correspondence above to begin analysis.
          </p>
        </div>
      ) : (
        <div className="divide-y divide-slate-100">
          {evidenceItems.map((item) => {
            const canRetry = ALLOWED_RETRY_STATUSES.includes(item.status);
            const isRetrying = retryingId === item.evidence_id;

            return (
              <div
                key={item.evidence_id}
                className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/50 -mx-2 px-2 rounded-lg transition"
              >
                <div className="space-y-1 min-w-0 flex-1">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <span className="font-semibold text-xs text-slate-900 truncate">
                      {item.original_filename}
                    </span>
                    <StatusBadge status={item.status} size="sm" />
                    <StatusBadge status={item.processing_mode} size="sm" />
                  </div>

                  <div className="flex items-center gap-3 text-[11px] text-slate-500 font-mono flex-wrap">
                    <span>{formatFileSize(item.file_size_bytes)}</span>
                    <span>•</span>
                    <span className="truncate">{item.media_type}</span>
                    <span>•</span>
                    <button
                      onClick={() => copyToClipboard(item.sha256_hash)}
                      className="inline-flex items-center gap-1 hover:text-slate-800 transition"
                      title="Copy SHA-256 hash"
                    >
                      <span>SHA: {item.sha256_hash.substring(0, 10)}...</span>
                      {copiedHash === item.sha256_hash ? (
                        <Check className="w-3 h-3 text-emerald-600" />
                      ) : (
                        <Copy className="w-3 h-3 text-slate-400" />
                      )}
                    </button>
                    {item.active_processing_version && (
                      <>
                        <span>•</span>
                        <span className="text-brand-600 font-semibold font-sans">
                          v{item.active_processing_version}
                        </span>
                      </>
                    )}
                  </div>

                  {/* Extraction Summary */}
                  {item.extraction_summary && (
                    <div className="text-[11px] text-slate-600 flex items-center gap-3 pt-1">
                      {item.extraction_summary.events_extracted !== undefined && (
                        <span className="flex items-center gap-1 font-medium text-emerald-700">
                          <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                          {String(item.extraction_summary.events_extracted)} events extracted
                        </span>
                      )}
                      {item.extraction_summary.raw_text_length !== undefined && (
                        <span className="text-slate-400">
                          {String(item.extraction_summary.raw_text_length)} chars parsed
                        </span>
                      )}
                    </div>
                  )}

                  {/* Failure notice */}
                  {(item.status === "FAILED" || item.status === "INTERRUPTED") && (
                    <div className="text-[11px] text-rose-600 flex items-center gap-1 pt-1 font-medium">
                      <AlertOctagon className="w-3 h-3 text-rose-500" />
                      Processing halted. Ready for retry.
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 shrink-0 self-start sm:self-center">
                  {canRetry && (
                    <button
                      onClick={() => handleRetry(item.evidence_id)}
                      disabled={isRetrying}
                      className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-rose-700 bg-rose-50 border border-rose-200 rounded-md hover:bg-rose-100 transition disabled:opacity-50"
                      title="Reprocess failed or interrupted evidence"
                    >
                      <RotateCcw
                        className={`w-3.5 h-3.5 ${isRetrying ? "animate-spin" : ""}`}
                      />
                      {isRetrying ? "Retrying..." : "Retry Extraction"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
