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
          `Notice: An identical file (${response.original_filename}) already exists in this case. Retained existing record.`
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
    <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Upload className="w-4 h-4 text-brand-600" />
            Ingest Documentary Evidence
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
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
        className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition flex flex-col items-center justify-center ${
          isDragging
            ? "border-brand-500 bg-brand-50/50"
            : "border-slate-200 hover:border-slate-300 hover:bg-slate-50/50"
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

        <div className="w-10 h-10 rounded-full bg-brand-50 text-brand-600 flex items-center justify-center mb-2">
          <FileUp className="w-5 h-5" />
        </div>

        <p className="text-sm font-semibold text-slate-800">
          Click to upload <span className="font-normal text-slate-500">or drag and drop</span>
        </p>
        <p className="text-xs text-slate-400 mt-1">
          PDF, PNG, JPG, JPEG, or WEBP (up to 25 MB)
        </p>
      </div>

      {/* Selected File & Progress */}
      {selectedFile && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded bg-brand-100 text-brand-700 font-semibold text-xs flex items-center justify-center shrink-0">
              {selectedFile.name.split(".").pop()?.toUpperCase() || "DOC"}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-slate-800 truncate">
                {selectedFile.name}
              </p>
              <p className="text-[11px] text-slate-500">
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
                className="text-slate-400 hover:text-slate-600 p-1"
                title="Remove selection"
              >
                <X className="w-4 h-4" />
              </button>
            )}

            <button
              type="button"
              onClick={handleUpload}
              disabled={isUploading}
              className="px-3 py-1.5 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-md transition shadow-sm disabled:opacity-50"
            >
              {isUploading ? "Uploading..." : "Start Ingestion"}
            </button>
          </div>
        </div>
      )}

      {/* Upload Progress Bar */}
      {isUploading && uploadProgress !== null && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-slate-600 font-medium">
            <span>Uploading to ProofFlow...</span>
            <span>{uploadProgress}%</span>
          </div>
          <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-brand-600 transition-all duration-200 rounded-full"
              style={{ width: `${uploadProgress}%` }}
            ></div>
          </div>
        </div>
      )}

      {/* Duplicate Notice */}
      {duplicateNotice && (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 px-3.5 py-2.5 rounded-lg text-xs flex items-start gap-2">
          <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <p>{duplicateNotice}</p>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 px-3.5 py-2.5 rounded-lg text-xs flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
          <p className="flex-1 font-medium">{error}</p>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-rose-400 hover:text-rose-600"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
