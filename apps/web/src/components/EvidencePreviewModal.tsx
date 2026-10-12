"use client";

import React, { useEffect, useState, useCallback } from "react";
import { EvidenceResponse } from "@/types/api";
import { api, ApiError } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import {
  X,
  Download,
  Loader2,
  FileText,
  AlertCircle,
  RotateCcw,
  Image as ImageIcon,
  ExternalLink,
} from "lucide-react";

interface EvidencePreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  caseId: string;
  evidence: EvidenceResponse | null;
  onDownload?: (evidence: EvidenceResponse) => void;
}

export function EvidencePreviewModal({
  isOpen,
  onClose,
  caseId,
  evidence,
  onDownload,
}: EvidencePreviewModalProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);

  const cleanupBlob = useCallback(() => {
    if (blobUrl) {
      if (typeof window !== "undefined" && window.URL?.revokeObjectURL) {
        window.URL.revokeObjectURL(blobUrl);
      }
      setBlobUrl(null);
    }
  }, [blobUrl]);

  const loadPreview = useCallback(async () => {
    if (!evidence || !isOpen) return;

    setLoading(true);
    setError(null);

    try {
      const blob = await api.previewEvidence(caseId, evidence.evidence_id);
      if (typeof window !== "undefined" && window.URL?.createObjectURL) {
        const url = window.URL.createObjectURL(blob);
        setBlobUrl((prev) => {
          if (prev && window.URL?.revokeObjectURL) {
            window.URL.revokeObjectURL(prev);
          }
          return url;
        });
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to stream evidence preview from server.");
      }
    } finally {
      setLoading(false);
    }
  }, [caseId, evidence, isOpen]);

  // Load preview when modal opens or selected evidence changes
  useEffect(() => {
    if (isOpen && evidence) {
      loadPreview();
    } else {
      cleanupBlob();
      setError(null);
      setLoading(false);
    }

    return () => {
      cleanupBlob();
    };
  }, [isOpen, evidence?.evidence_id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Handle Escape key to close modal
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const handleDownloadClick = async () => {
    if (!evidence) return;
    if (onDownload) {
      onDownload(evidence);
      return;
    }

    setIsDownloading(true);
    try {
      const blob = await api.downloadEvidence(caseId, evidence.evidence_id, false);
      if (typeof window !== "undefined" && window.URL?.createObjectURL) {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = evidence.original_filename || `evidence_${evidence.evidence_id}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        if (window.URL?.revokeObjectURL) {
          window.URL.revokeObjectURL(url);
        }
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`Download failed: ${err.message}`);
      } else {
        setError("Failed to download file.");
      }
    } finally {
      setIsDownloading(false);
    }
  };

  if (!isOpen || !evidence) return null;

  const isPdf =
    evidence.media_type === "application/pdf" ||
    evidence.original_filename.toLowerCase().endsWith(".pdf");
  const isImage =
    evidence.media_type.startsWith("image/") ||
    /\.(png|jpe?g|webp)$/i.test(evidence.original_filename);

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="preview-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/80 backdrop-blur-md animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="glass-panel-elevated rounded-2xl shadow-2xl border border-slate-700/80 w-full max-w-5xl h-[88vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200 bg-slate-950/95"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/60">
          <div className="flex items-center gap-3 min-w-0 mr-3">
            <div className="p-2.5 bg-cyan-950/60 text-cyan-400 border border-cyan-500/30 rounded-xl shrink-0 shadow-neon-cyan">
              {isImage ? <ImageIcon className="w-5 h-5" /> : <FileText className="w-5 h-5" />}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2.5 flex-wrap">
                <h2
                  id="preview-modal-title"
                  className="text-sm sm:text-base font-bold text-white tracking-tight truncate"
                  title={evidence.original_filename}
                >
                  {evidence.original_filename}
                </h2>
                <StatusBadge status={evidence.status} size="sm" />
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-400 mt-0.5 font-mono">
                <span>{formatFileSize(evidence.file_size_bytes)}</span>
                <span>•</span>
                <span className="truncate">{evidence.media_type}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            {blobUrl && (
              <a
                href={blobUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono text-slate-300 hover:text-white glass-panel rounded-xl hover:border-slate-600 transition"
                title="Open in new tab"
              >
                <ExternalLink className="w-3.5 h-3.5 text-cyan-400" />
                <span>New Tab</span>
              </a>
            )}

            <button
              onClick={handleDownloadClick}
              disabled={isDownloading}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-slate-950 bg-gradient-to-r from-cyan-400 to-cyan-300 hover:brightness-110 rounded-xl transition shadow-neon-cyan disabled:opacity-50"
              title="Download original evidence file"
            >
              {isDownloading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              <span>Download</span>
            </button>

            <button
              onClick={onClose}
              aria-label="Close preview"
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-xl transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="flex-1 relative flex flex-col bg-slate-950/80 overflow-hidden">
          {loading && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-950/90 backdrop-blur-xs text-center p-6">
              <Loader2 className="w-9 h-9 animate-spin text-cyan-400 mb-3" />
              <p className="text-sm font-semibold text-white">
                Loading secure evidence preview...
              </p>
              <p className="text-xs text-slate-400 mt-1 max-w-sm font-mono">
                Authenticating session token and streaming encrypted file from storage.
              </p>
            </div>
          )}

          {error && !loading && (
            <div className="flex-1 flex items-center justify-center p-6">
              <div className="max-w-md w-full glass-panel-elevated rounded-2xl border border-rose-500/40 p-6 text-center shadow-xl space-y-4">
                <div className="w-12 h-12 bg-rose-950/60 text-rose-400 border border-rose-500/30 rounded-xl flex items-center justify-center mx-auto">
                  <AlertCircle className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">
                    Unable to Preview Evidence
                  </h3>
                  <p className="text-xs text-slate-300 mt-2 leading-relaxed">
                    {error}
                  </p>
                </div>
                <div className="flex items-center justify-center gap-3 pt-2">
                  <button
                    onClick={loadPreview}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-slate-200 glass-panel hover:text-white rounded-xl transition"
                  >
                    <RotateCcw className="w-3.5 h-3.5 text-cyan-400" />
                    Try Again
                  </button>
                  <button
                    onClick={handleDownloadClick}
                    disabled={isDownloading}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-slate-950 bg-gradient-to-r from-cyan-400 to-cyan-300 hover:brightness-110 rounded-xl transition shadow-neon-cyan"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Download File
                  </button>
                </div>
              </div>
            </div>
          )}

          {!loading && !error && blobUrl && (
            <>
              {isPdf && (
                <iframe
                  src={`${blobUrl}#toolbar=1`}
                  title={`Preview of ${evidence.original_filename}`}
                  className="w-full h-full border-0 bg-white"
                />
              )}

              {isImage && (
                <div className="flex-1 flex items-center justify-center p-4 sm:p-6 bg-slate-950/60 overflow-auto">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={blobUrl}
                    alt={evidence.original_filename}
                    className="max-h-[72vh] max-w-full object-contain rounded-xl shadow-2xl border border-slate-800 bg-slate-900"
                  />
                </div>
              )}

              {!isPdf && !isImage && (
                <div className="flex-1 flex items-center justify-center p-6 text-center">
                  <div className="max-w-md glass-panel rounded-2xl border border-slate-800 p-6 shadow-xl space-y-3">
                    <FileText className="w-10 h-10 text-slate-500 mx-auto" />
                    <h3 className="text-sm font-bold text-white">
                      In-browser preview is not supported for this file type
                    </h3>
                    <p className="text-xs text-slate-400">
                      File format: <span className="font-mono">{evidence.media_type}</span>.
                      Please download the file to inspect its contents.
                    </p>
                    <div className="pt-2">
                      <button
                        onClick={handleDownloadClick}
                        className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-slate-950 bg-gradient-to-r from-cyan-400 to-cyan-300 hover:brightness-110 rounded-xl transition shadow-neon-cyan"
                      >
                        <Download className="w-4 h-4" />
                        Download File
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
