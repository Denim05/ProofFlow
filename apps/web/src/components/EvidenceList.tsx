"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
import { EvidenceResponse, EvidenceStatus } from "@/types/api";
import { api, ApiError } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { EvidencePreviewModal } from "@/components/EvidencePreviewModal";
import {
  FileText,
  RefreshCw,
  RotateCcw,
  CheckCircle2,
  AlertOctagon,
  Copy,
  Check,
  Cpu,
  Eye,
  Download,
  Loader2,
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
  const [previewEvidence, setPreviewEvidence] = useState<EvidenceResponse | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

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

  const handleOpenPreview = (item: EvidenceResponse) => {
    setPreviewEvidence(item);
    setIsPreviewOpen(true);
  };

  const handleClosePreview = () => {
    setIsPreviewOpen(false);
    setPreviewEvidence(null);
  };

  const handleDownload = async (item: EvidenceResponse) => {
    setDownloadingId(item.evidence_id);
    setError(null);
    try {
      const blob = await api.downloadEvidence(caseId, item.evidence_id, false);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = item.original_filename || `evidence_${item.evidence_id}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`Download failed: ${err.message}`);
      } else {
        setError("Failed to download evidence file.");
      }
    } finally {
      setDownloadingId(null);
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
    <div className="glass-panel rounded-2xl p-6 space-y-4 border border-slate-800 shadow-xl">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <FileText className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-bold text-white tracking-tight">
            Case Evidence Assets ({evidenceItems.length})
          </h3>
        </div>

        <button
          onClick={() => fetchEvidence(false)}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono text-slate-300 hover:text-white glass-panel rounded-xl hover:border-slate-700 transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-rose-950/40 border border-rose-500/40 text-rose-300 px-4 py-3 rounded-xl text-xs flex items-center justify-between backdrop-blur-xs">
          <span className="font-medium">{error}</span>
          <button
            onClick={() => fetchEvidence(false)}
            className="text-rose-300 font-semibold underline text-xs ml-2 hover:text-rose-100"
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
              className="h-16 bg-slate-900/60 border border-slate-800 rounded-xl animate-pulse"
            />
          ))}
        </div>
      ) : evidenceItems.length === 0 ? (
        <div className="text-center py-10 px-4">
          <FileText className="w-8 h-8 text-slate-500 mx-auto mb-2 opacity-60" />
          <p className="text-sm font-semibold text-slate-300">
            No evidence documents uploaded yet
          </p>
          <p className="text-xs text-slate-500 mt-1">
            Drag and drop contracts, statements, or correspondence above to begin analysis.
          </p>
        </div>
      ) : (
        <div className="divide-y divide-slate-800/80">
          {evidenceItems.map((item) => {
            const canRetry = ALLOWED_RETRY_STATUSES.includes(item.status);
            const isRetrying = retryingId === item.evidence_id;

            return (
              <div
                key={item.evidence_id}
                className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-900/40 -mx-2 px-3 rounded-xl transition"
              >
                <div className="space-y-1 min-w-0 flex-1">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <span className="font-semibold text-xs text-white truncate">
                      {item.original_filename}
                    </span>
                    <StatusBadge status={item.status} size="sm" />
                    <StatusBadge status={item.processing_mode} size="sm" />
                  </div>

                  <div className="flex items-center gap-3 text-[11px] text-slate-400 font-mono flex-wrap">
                    <span>{formatFileSize(item.file_size_bytes)}</span>
                    <span>•</span>
                    <span className="truncate">{item.media_type}</span>
                    <span>•</span>
                    <button
                      onClick={() => copyToClipboard(item.sha256_hash)}
                      className="inline-flex items-center gap-1 hover:text-cyan-300 transition"
                      title="Copy SHA-256 hash"
                    >
                      <span>SHA: {item.sha256_hash.substring(0, 10)}...</span>
                      {copiedHash === item.sha256_hash ? (
                        <Check className="w-3 h-3 text-emerald-400" />
                      ) : (
                        <Copy className="w-3 h-3 text-slate-500 hover:text-cyan-400" />
                      )}
                    </button>
                    {item.active_processing_version && (
                      <>
                        <span>•</span>
                        <span className="text-cyan-400 font-semibold font-mono">
                          v{item.active_processing_version}
                        </span>
                      </>
                    )}
                  </div>

                  {/* Extraction Summary */}
                  {item.extraction_summary && (
                    <div className="text-[11px] text-slate-300 flex items-center gap-3 pt-1">
                      {item.extraction_summary.events_extracted !== undefined && (
                        <span className="flex items-center gap-1 font-medium text-emerald-400">
                          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                          {String(item.extraction_summary.events_extracted)} events extracted
                        </span>
                      )}
                      {item.extraction_summary.raw_text_length !== undefined && (
                        <span className="text-slate-500 font-mono">
                          {String(item.extraction_summary.raw_text_length)} chars parsed
                        </span>
                      )}
                    </div>
                  )}

                  {/* Failure notice */}
                  {(item.status === "FAILED" || item.status === "INTERRUPTED") && (
                    <div className="text-[11px] text-rose-400 flex items-center gap-1 pt-1 font-medium">
                      <AlertOctagon className="w-3 h-3 text-rose-400" />
                      Processing halted. Ready for retry.
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 shrink-0 self-start sm:self-center">
                  <button
                    onClick={() => handleOpenPreview(item)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-300 glass-panel rounded-xl hover:text-white hover:border-cyan-500/40 transition shadow-2xs"
                    title="Preview evidence document"
                  >
                    <Eye className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Preview</span>
                  </button>

                  <button
                    onClick={() => handleDownload(item)}
                    disabled={downloadingId === item.evidence_id}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-300 glass-panel rounded-xl hover:text-white hover:border-cyan-500/40 transition shadow-2xs disabled:opacity-50"
                    title="Download evidence file"
                  >
                    {downloadingId === item.evidence_id ? (
                      <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
                    ) : (
                      <Download className="w-3.5 h-3.5 text-cyan-400" />
                    )}
                    <span>{downloadingId === item.evidence_id ? "Downloading..." : "Download"}</span>
                  </button>

                  {canRetry && (
                    <button
                      onClick={() => handleRetry(item.evidence_id)}
                      disabled={isRetrying}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-rose-300 bg-rose-950/40 border border-rose-500/40 rounded-xl hover:bg-rose-900/40 transition disabled:opacity-50 shadow-2xs"
                      title="Reprocess failed or interrupted evidence"
                    >
                      <RotateCcw
                        className={`w-3.5 h-3.5 text-rose-400 ${isRetrying ? "animate-spin" : ""}`}
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

      {/* Authenticated Evidence Preview Modal */}
      <EvidencePreviewModal
        isOpen={isPreviewOpen}
        onClose={handleClosePreview}
        caseId={caseId}
        evidence={previewEvidence}
        onDownload={handleDownload}
      />
    </div>
  );
}
