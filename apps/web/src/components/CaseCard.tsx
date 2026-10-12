import React, { useRef, useState } from "react";
import Link from "next/link";
import { CaseResponse } from "@/types/api";
import { StatusBadge } from "@/components/StatusBadge";
import { FileText, ArrowRight, Calendar, Tag, ShieldAlert, Cpu } from "lucide-react";

interface CaseCardProps {
  caseItem: CaseResponse;
}

export function CaseCard({ caseItem }: CaseCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [rotateX, setRotateX] = useState(0);
  const [rotateY, setRotateY] = useState(0);

  const formattedDate = new Date(caseItem.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    // Subtle tilt: max ~4 degrees
    const rX = -(y / (rect.height / 2)) * 3.5;
    const rY = (x / (rect.width / 2)) * 3.5;
    setRotateX(rX);
    setRotateY(rY);
  };

  const handleMouseLeave = () => {
    setRotateX(0);
    setRotateY(0);
  };

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{
        transform: `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(0)`,
        transition: rotateX === 0 ? "transform 0.4s cubic-bezier(0.16, 1, 0.3, 1)" : "none",
      }}
      className="glass-panel group relative flex flex-col justify-between p-6 rounded-2xl hover:border-cyan-500/40 hover:shadow-neon-cyan transition-all duration-300 overflow-hidden"
    >
      {/* Ambient subtle gradient glow on top-right */}
      <div className="absolute -top-12 -right-12 w-32 h-32 bg-cyan-500/10 rounded-full blur-2xl group-hover:bg-cyan-500/20 transition-all pointer-events-none" />

      {/* Card Content */}
      <div className="relative z-10">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(0,242,254,0.8)] shrink-0" />
            <h3 className="font-semibold text-white group-hover:text-cyan-300 transition-colors line-clamp-1 text-base tracking-tight">
              {caseItem.title}
            </h3>
          </div>
          <StatusBadge status={caseItem.status} size="sm" />
        </div>

        <p className="text-sm text-slate-300/80 line-clamp-2 mb-4 leading-relaxed font-normal">
          {caseItem.description || "No narrative description provided."}
        </p>

        {caseItem.tags && caseItem.tags.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 mb-5">
            {caseItem.tags.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 text-[11px] font-medium bg-cyan-950/40 text-cyan-300 border border-cyan-500/30 px-2 py-0.5 rounded-md backdrop-blur-xs tracking-wide"
              >
                <Tag className="w-2.5 h-2.5 text-cyan-400" />
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Card Footer with Meta & View Case Link */}
      <div className="relative z-10 pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 font-medium text-slate-300">
            <FileText className="w-3.5 h-3.5 text-cyan-400" />
            {caseItem.evidence_count} {caseItem.evidence_count === 1 ? "document" : "documents"}
          </span>
          <span className="flex items-center gap-1 font-mono text-[11px] text-slate-400">
            <Calendar className="w-3 h-3 text-slate-400" />
            {formattedDate}
          </span>
        </div>

        <Link
          href={`/cases/${caseItem.case_id}`}
          className="inline-flex items-center gap-1.5 font-semibold text-cyan-400 group-hover:text-cyan-300 hover:underline transition-all"
        >
          View Case
          <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
        </Link>
      </div>
    </div>
  );
}

