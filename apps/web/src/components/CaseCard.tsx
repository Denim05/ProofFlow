import React from "react";
import Link from "next/link";
import { CaseResponse } from "@/types/api";
import { StatusBadge } from "@/components/StatusBadge";
import { FileText, ArrowRight, Calendar, Tag } from "lucide-react";

interface CaseCardProps {
  caseItem: CaseResponse;
}

export function CaseCard({ caseItem }: CaseCardProps) {
  const formattedDate = new Date(caseItem.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-sm hover:shadow-md hover:border-slate-300 transition group flex flex-col justify-between">
      <div>
        <div className="flex items-start justify-between gap-3 mb-3">
          <h3 className="font-semibold text-slate-900 group-hover:text-brand-600 transition line-clamp-1 text-base">
            {caseItem.title}
          </h3>
          <StatusBadge status={caseItem.status} size="sm" />
        </div>

        <p className="text-sm text-slate-600 line-clamp-2 mb-4 leading-relaxed">
          {caseItem.description || "No narrative description provided."}
        </p>

        {caseItem.tags && caseItem.tags.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 mb-4">
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

      <div className="pt-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1 font-medium text-slate-700">
            <FileText className="w-3.5 h-3.5 text-slate-400" />
            {caseItem.evidence_count} {caseItem.evidence_count === 1 ? "document" : "documents"}
          </span>
          <span className="flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5 text-slate-400" />
            {formattedDate}
          </span>
        </div>

        <Link
          href={`/cases/${caseItem.case_id}`}
          className="inline-flex items-center gap-1 font-semibold text-brand-600 group-hover:text-brand-700 hover:underline"
        >
          View Case
          <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
        </Link>
      </div>
    </div>
  );
}
