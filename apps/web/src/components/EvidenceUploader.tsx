"use client";

import React, { useState, useRef } from "react";
import { Upload, FileUp, CheckCircle, AlertCircle, Info, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { EvidenceUploadResponse } from "@/types/api";

const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB
const ALLOWED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".webp"];

interface EvidenceUploaderProps {
  caseId: string;
  onUploadSuccess: (upload: EvidenceUploadResponse) => void;
}

export function EvidenceUploader({ caseId, onUploadSuccess }: EvidenceUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duplicateNotice, setDuplicateNotice] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): string | null => {
    const name = file.name.toLowerCase();
    const matchesExtension = ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext));
    if (!matchesExtension) {
      return `Unsupported file format. Accepted formats: ${ALLOWED_EXTENSIONS.join(", ")}`;
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      return `File size (${sizeMb} MB) exceeds maximum allowed limit of 25 MB.`;
    }
    return null;
  };

  const handleFileSelect = (file: File) => {
    setError(null);
    setDuplicateNotice(null);

    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile || isUploading) return;

    setIsUploading(true);
    setUploadProgress(0);
    setError(null);
    setDuplicateNotice(null);

    try {
      const response = await api.uploadEvidence(
        caseId,
        selectedFile,
        (percentage) => {
          setUploadProgress(percentage);
        }
      );

      if (response.is_duplicate) {
        setDuplicateNotice(
          response.file_restored
            ? `Notice: Physical evidence file (${response.original_filename}) was restored for the existing record.`
            : `Notice: An identical file (${response.original_filename}) already exists in this case. Retained existing record.`
        );
      }

      onUploadSuccess(response);
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Network error occurred while uploading evidence.");
      }
    } finally {
      setIsUploading(false);
      setUploadProgress(null);
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-6 space-y-5 border border-slate-800 shadow-xl">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
            <Upload className="w-4 h-4 text-cyan-400" />
            Ingest Documentary Evidence
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Upload PDF contracts, emails, statements, or receipts (Max 25 MB).
          </p>
        </div>
      </div>

      {/* Drag & Drop Zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-7 text-center cursor-pointer transition-all flex flex-col items-center justify-center relative overflow-hidden ${
          isDragging
            ? "border-cyan-400 bg-cyan-950/30 shadow-neon-cyan"
            : "border-slate-800 bg-slate-900/40 hover:border-cyan-500/50 hover:bg-slate-900/70"
        } ${isUploading ? "opacity-60 cursor-not-allowed" : ""}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleFileSelect(e.target.files[0]);
            }
          }}
          disabled={isUploading}
        />

        <div className="w-12 h-12 rounded-xl bg-cyan-950/60 text-cyan-400 border border-cyan-500/30 flex items-center justify-center mb-3 shadow-neon-cyan">
          <FileUp className="w-6 h-6" />
        </div>

        <p className="text-sm font-semibold text-white">
          Click to upload <span className="font-normal text-slate-400">or drag and drop</span>
        </p>
        <p className="text-xs text-slate-500 mt-1 font-mono">
          PDF, PNG, JPG, JPEG, or WEBP (up to 25 MB)
        </p>
      </div>

      {/* Selected File & Progress */}
      {selectedFile && (
        <div className="glass-panel-elevated border border-slate-700/80 rounded-xl p-3.5 flex items-center justify-between gap-3 animate-in fade-in duration-200">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-cyan-950/70 text-cyan-300 border border-cyan-500/40 font-mono font-bold text-xs flex items-center justify-center shrink-0">
              {selectedFile.name.split(".").pop()?.toUpperCase() || "DOC"}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-white truncate">
                {selectedFile.name}
              </p>
              <p className="text-[11px] text-slate-400 font-mono">
                {(selectedFile.size / 1024).toFixed(0)} KB
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {!isUploading && (
              <button
                type="button"
                onClick={() => {
                  setSelectedFile(null);
                  if (fileInputRef.current) fileInputRef.current.value = "";
                }}
                className="text-slate-400 hover:text-white p-1 rounded-lg transition"
                title="Remove selection"
              >
                <X className="w-4 h-4" />
              </button>
            )}

            <button
              type="button"
              onClick={handleUpload}
              disabled={isUploading}
              className="px-3.5 py-1.5 text-xs font-semibold text-slate-950 bg-gradient-to-r from-cyan-400 to-cyan-300 hover:brightness-110 rounded-xl transition shadow-neon-cyan disabled:opacity-50"
            >
              {isUploading ? "Uploading..." : "Start Ingestion"}
            </button>
          </div>
        </div>
      )}

      {/* Upload Progress Bar */}
      {isUploading && uploadProgress !== null && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-cyan-300 font-mono font-medium">
            <span>Uploading to ProofFlow...</span>
            <span>{uploadProgress}%</span>
          </div>
          <div className="w-full h-2 bg-slate-900 rounded-full overflow-hidden border border-slate-800">
            <div
              className="h-full bg-gradient-to-r from-cyan-400 to-cyan-300 transition-all duration-200 rounded-full shadow-[0_0_8px_#00F2FE]"
              style={{ width: `${uploadProgress}%` }}
            ></div>
          </div>
        </div>
      )}

      {/* Duplicate Notice */}
      {duplicateNotice && (
        <div className="bg-amber-950/40 border border-amber-500/40 text-amber-200 px-4 py-3 rounded-xl text-xs flex items-start gap-2.5 backdrop-blur-xs">
          <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <p>{duplicateNotice}</p>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="bg-rose-950/40 border border-rose-500/40 text-rose-200 px-4 py-3 rounded-xl text-xs flex items-start gap-2.5 backdrop-blur-xs">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <p className="flex-1 font-medium">{error}</p>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-rose-400 hover:text-white"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
