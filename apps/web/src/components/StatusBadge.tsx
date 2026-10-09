import React from "react";
import { CaseStatus, EvidenceStatus, MLProcessingMode } from "@/types/api";

interface StatusBadgeProps {
  status: CaseStatus | EvidenceStatus | MLProcessingMode | string;
  size?: "sm" | "md";
}

export function StatusBadge({ status, size = "md" }: StatusBadgeProps) {
  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs";

  let colorClasses = "bg-slate-100 text-slate-700 border-slate-200";

  switch (status) {
    case "READY":
    case "VALIDATED":
      colorClasses = "bg-emerald-50 text-emerald-700 border-emerald-200";
      break;
    case "PROCESSING":
    case "EXTRACTING":
    case "STRUCTURING":
    case "ANALYZING":
    case "QUEUED":
      colorClasses = "bg-sky-50 text-sky-700 border-sky-200 animate-pulse";
      break;
    case "REVIEW_NEEDED":
      colorClasses = "bg-amber-50 text-amber-700 border-amber-200";
      break;
    case "FAILED":
    case "INTERRUPTED":
    case "MODEL_UNAVAILABLE":
      colorClasses = "bg-rose-50 text-rose-700 border-rose-200";
      break;
    case "ARCHIVED":
      colorClasses = "bg-zinc-100 text-zinc-600 border-zinc-200";
      break;
    case "NEURAL_DEBERTA_GPU":
    case "NEURAL_DEBERTA_CPU":
      colorClasses = "bg-indigo-50 text-indigo-700 border-indigo-200";
      break;
    case "DETERMINISTIC_FALLBACK":
      colorClasses = "bg-amber-50 text-amber-800 border-amber-200";
      break;
  }

  const formattedLabel = status.replace(/_/g, " ");

  return (
    <span
      className={`inline-flex items-center font-medium rounded-full border ${sizeClasses} ${colorClasses}`}
    >
      {formattedLabel}
    </span>
  );
}
