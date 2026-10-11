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
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-5xl h-[88vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-slate-50/70">
          <div className="flex items-center gap-3 min-w-0 mr-3">
            <div className="p-2 bg-brand-50 text-brand-600 rounded-lg shrink-0">
              {isImage ? <ImageIcon className="w-5 h-5" /> : <FileText className="w-5 h-5" />}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2
                  id="preview-modal-title"
                  className="text-sm sm:text-base font-bold text-slate-900 truncate"
                  title={evidence.original_filename}
                >
                  {evidence.original_filename}
                </h2>
                <StatusBadge status={evidence.status} size="sm" />
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5 font-mono">
                <span>{formatFileSize(evidence.file_size_bytes)}</span>
                <span>•</span>
                <span className="truncate">{evidence.media_type}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {blobUrl && (
              <a
                href={blobUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition shadow-sm"
                title="Open in new tab"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>New Tab</span>
              </a>
            )}

            <button
              onClick={handleDownloadClick}
              disabled={isDownloading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-brand-700 bg-brand-50 border border-brand-200 rounded-lg hover:bg-brand-100 transition shadow-sm disabled:opacity-50"
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
              className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="flex-1 relative flex flex-col bg-slate-100/60 overflow-hidden">
          {loading && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-white/80 backdrop-blur-xs text-center p-6">
              <Loader2 className="w-9 h-9 animate-spin text-brand-600 mb-3" />
              <p className="text-sm font-semibold text-slate-800">
                Loading secure evidence preview...
              </p>
              <p className="text-xs text-slate-400 mt-1 max-w-sm">
                Authenticating session token and streaming encrypted file from storage.
              </p>
            </div>
          )}

          {error && !loading && (
            <div className="flex-1 flex items-center justify-center p-6">
              <div className="max-w-md w-full bg-white rounded-xl border border-rose-200 p-6 text-center shadow-sm space-y-4">
                <div className="w-12 h-12 bg-rose-50 text-rose-600 rounded-full flex items-center justify-center mx-auto">
                  <AlertCircle className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    Unable to Preview Evidence
                  </h3>
                  <p className="text-xs text-slate-600 mt-2 leading-relaxed">
                    {error}
                  </p>
                </div>
                <div className="flex items-center justify-center gap-3 pt-2">
                  <button
                    onClick={loadPreview}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    Try Again
                  </button>
                  <button
                    onClick={handleDownloadClick}
                    disabled={isDownloading}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg transition"
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
                <div className="flex-1 flex items-center justify-center p-4 sm:p-6 bg-slate-900/5 overflow-auto">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={blobUrl}
                    alt={evidence.original_filename}
                    className="max-h-[72vh] max-w-full object-contain rounded-lg shadow-md border border-slate-200/60 bg-white"
                  />
                </div>
              )}

              {!isPdf && !isImage && (
                <div className="flex-1 flex items-center justify-center p-6 text-center">
                  <div className="max-w-md bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-3">
                    <FileText className="w-10 h-10 text-slate-400 mx-auto" />
                    <h3 className="text-sm font-bold text-slate-900">
                      In-browser preview is not supported for this file type
                    </h3>
                    <p className="text-xs text-slate-500">
                      File format: <span className="font-mono">{evidence.media_type}</span>.
                      Please download the file to inspect its contents.
                    </p>
                    <div className="pt-2">
                      <button
                        onClick={handleDownloadClick}
                        className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg transition shadow-sm"
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
