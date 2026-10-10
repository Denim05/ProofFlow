"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  EventResponse,
  EvidenceResponse,
  FindingResponse,
  ReviewDecision,
  FindingReviewResponse,
} from "@/types/api";
import { api } from "@/lib/api";
import {
  AlertTriangle,
  FileQuestion,
  HelpCircle,
  FileText,
  CheckCircle2,
  Info,
  RefreshCw,
  Loader2,
  UserCheck,
  History,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  XCircle,
  Check,
} from "lucide-react";

export interface CrossEvidenceComparisonProps {
  caseId?: string;
  initialFindings?: FindingResponse[];
  events?: EventResponse[];
  evidenceList?: EvidenceResponse[];
}

const AMBIGUOUS_REFERENCES = new Set([
  "N/A",
  "NA",
  "NONE",
  "NULL",
  "REF",
  "ID",
  "ORDER",
  "PO",
  "TXN",
  "UNKNOWN",
]);

function normalizeReference(ref: string | null | undefined): string | null {
  if (!ref) return null;
  const stripped = ref.trim().toUpperCase();
  const clean = stripped.replace(/[\s\-_]/g, "");
  if (clean.length < 3 || AMBIGUOUS_REFERENCES.has(stripped)) {
    return null;
  }
  return clean;
}

export function CrossEvidenceComparison({
  caseId,
  initialFindings,
  events = [],
  evidenceList = [],
}: CrossEvidenceComparisonProps) {
  const [backendFindings, setBackendFindings] = useState<FindingResponse[] | null>(
    initialFindings || null
  );
  const [loading, setLoading] = useState<boolean>(Boolean(caseId && !initialFindings));
  const [error, setError] = useState<string | null>(null);

  // Human Review Adjudication State
  const [adjudicatingFindingId, setAdjudicatingFindingId] = useState<string | null>(null);
  const [selectedDecision, setSelectedDecision] = useState<Record<string, ReviewDecision>>({});
  const [decisionReason, setDecisionReason] = useState<Record<string, string>>({});
  const [confirmingSave, setConfirmingSave] = useState<Record<string, boolean>>({});
  const [submittingReview, setSubmittingReview] = useState<Record<string, boolean>>({});
  const [reviewError, setReviewError] = useState<Record<string, string | null>>({});
  const [reviewSuccess, setReviewSuccess] = useState<Record<string, string | null>>({});
  const [viewingHistoryFindingId, setViewingHistoryFindingId] = useState<string | null>(null);
  const [findingHistories, setFindingHistories] = useState<Record<string, FindingReviewResponse[]>>({});
  const [loadingHistory, setLoadingHistory] = useState<Record<string, boolean>>({});

  const fetchFindings = useCallback(async () => {
    if (!caseId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.getCaseFindings(caseId);
      const items = Array.isArray(response) ? response : (response?.items || []);
      setBackendFindings(items);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load findings";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    if (caseId && !initialFindings) {
      fetchFindings();
    }
  }, [caseId, initialFindings, fetchFindings]);

  // Fallback client-side comparator when caseId is not provided (e.g. offline testing)
  const clientFallbackFindings = useMemo<FindingResponse[]>(() => {
    if (backendFindings !== null) return backendFindings;
    if (!events.length) return [];

    const evidenceNameMap = new Map<string, string>();
    evidenceList.forEach((e) => evidenceNameMap.set(e.evidence_id, e.original_filename));

    const findings: FindingResponse[] = [];
    const seenPairs = new Set<string>();

    const refGroups = new Map<string, { displayRef: string; items: EventResponse[] }>();

    events.forEach((ev) => {
      const normOrder = normalizeReference(ev.order_reference);
      const normTxn = normalizeReference(ev.transaction_reference);
      if (normOrder) {
        let group = refGroups.get(normOrder);
        if (!group) {
          group = { displayRef: (ev.order_reference || "").trim(), items: [] };
          refGroups.set(normOrder, group);
        }
        group.items.push(ev);
      }
      if (normTxn && normTxn !== normOrder) {
        let group = refGroups.get(normTxn);
        if (!group) {
          group = { displayRef: (ev.transaction_reference || "").trim(), items: [] };
          refGroups.set(normTxn, group);
        }
        group.items.push(ev);
      }
    });

    refGroups.forEach(({ displayRef, items: refEvents }, normRef) => {
      if (refEvents.length < 2) return;
      for (let i = 0; i < refEvents.length; i++) {
        for (let j = i + 1; j < refEvents.length; j++) {
          const evA = refEvents[i];
          const evB = refEvents[j];
          if (evA.evidence_id === evB.evidence_id) continue;

          const sourceA = evidenceNameMap.get(evA.evidence_id) || evA.evidence_id;
          const sourceB = evidenceNameMap.get(evB.evidence_id) || evB.evidence_id;
          const pageASuffix = evA.page_number ? ` (p. ${evA.page_number})` : "";
          const pageBSuffix = evB.page_number ? ` (p. ${evB.page_number})` : "";

          if (
            evA.amount_value !== null &&
            evA.amount_value !== undefined &&
            evB.amount_value !== null &&
            evB.amount_value !== undefined
          ) {
            const valA = Number(evA.amount_value);
            const valB = Number(evB.amount_value);
            if (!isNaN(valA) && !isNaN(valB)) {
              const currA = (evA.amount_currency || "").trim().toUpperCase();
              const currB = (evB.amount_currency || "").trim().toUpperCase();

              if (currA && currB && currA !== currB) {
                const pairKey = [evA.event_id, evB.event_id].sort().join("::") + "::CURRENCY";
                if (!seenPairs.has(pairKey)) {
                  seenPairs.add(pairKey);
                  findings.push({
                    finding_id: `fnd-curr-${displayRef}-${evA.event_id}-${evB.event_id}`,
                    case_id: evA.case_id,
                    finding_type: "POTENTIAL_INCONSISTENCY",
                    title: `Currency Denomination Mismatch on Reference ${displayRef}`,
                    summary: `Reference '${displayRef}' is denominated in ${currA} in ${sourceA} and in ${currB} in ${sourceB}. Direct numeric comparison requires exchange rate verification.`,
                    severity: "MEDIUM",
                    conflict_state: "POTENTIAL_CONFLICT",
                    citations: [
                      {
                        evidence_id: evA.evidence_id,
                        original_filename: sourceA,
                        page_number: evA.page_number,
                        char_start: evA.char_start,
                        char_end: evA.char_end,
                        trigger_raw_text: evA.trigger_raw_text,
                        event_id: evA.event_id,
                      },
                      {
                        evidence_id: evB.evidence_id,
                        original_filename: sourceB,
                        page_number: evB.page_number,
                        char_start: evB.char_start,
                        char_end: evB.char_end,
                        trigger_raw_text: evB.trigger_raw_text,
                        event_id: evB.event_id,
                      },
                    ],
                    field_diff: {
                      field: "Currency Denomination",
                      value_a: `${currA} ${valA.toLocaleString()}`,
                      source_a: `${sourceA}${pageASuffix}`,
                      value_b: `${currB} ${valB.toLocaleString()}`,
                      source_b: `${sourceB}${pageBSuffix}`,
                    },
                    model_confidence: 1.0,
                    model_name: "proofflow-reasoning-engine",
                    created_at: new Date().toISOString(),
                  });
                }
              } else if (Math.abs(valA - valB) > 0.01) {
                const pairKey = [evA.event_id, evB.event_id].sort().join("::") + "::AMOUNT";
                if (!seenPairs.has(pairKey)) {
                  seenPairs.add(pairKey);
                  const isUncertain =
                    evA.decision_state === "REVIEW_NEEDED" || evB.decision_state === "REVIEW_NEEDED";
                  findings.push({
                    finding_id: `fnd-amount-${normRef}-${evA.event_id}-${evB.event_id}`,
                    case_id: evA.case_id,
                    finding_type: "POTENTIAL_INCONSISTENCY",
                    title: isUncertain
                      ? `Uncertain Comparison: Amount Divergence on Reference ${displayRef}`
                      : `Potential Inconsistency: Amount Divergence on Reference ${displayRef}`,
                    summary: isUncertain
                      ? `Extracted amounts differ by ${currA || "$"}${Math.abs(valA - valB).toLocaleString()}, but extraction certainty requires manual review.`
                      : `Differing monetary amounts recorded across documents referencing '${displayRef}'. Differs by ${currA || "$"}${Math.abs(valA - valB).toLocaleString()}. Differing line items, tax inclusions, revisions, or partial milestones may account for this divergence.`,
                    severity: isUncertain ? "LOW" : "MEDIUM",
                    conflict_state: isUncertain ? "INSUFFICIENT_CONTEXT" : "POTENTIAL_CONFLICT",
                    citations: [
                      {
                        evidence_id: evA.evidence_id,
                        original_filename: sourceA,
                        page_number: evA.page_number,
                        char_start: evA.char_start,
                        char_end: evA.char_end,
                        trigger_raw_text: evA.trigger_raw_text,
                        event_id: evA.event_id,
                      },
                      {
                        evidence_id: evB.evidence_id,
                        original_filename: sourceB,
                        page_number: evB.page_number,
                        char_start: evB.char_start,
                        char_end: evB.char_end,
                        trigger_raw_text: evB.trigger_raw_text,
                        event_id: evB.event_id,
                      },
                    ],
                    field_diff: {
                      field: "Amount",
                      value_a: `${currA || "$"}${valA.toLocaleString()}`,
                      source_a: `${sourceA}${pageASuffix}`,
                      value_b: `${currB || "$"}${valB.toLocaleString()}`,
                      source_b: `${sourceB}${pageBSuffix}`,
                    },
                    model_confidence: isUncertain ? 0.5 : 1.0,
                    model_name: "proofflow-reasoning-engine",
                    created_at: new Date().toISOString(),
                  });
                }
              }
            }
          }
        }
      }
    });

    // 2. Missing Corroboration Analysis
    const outgoingEvents = events.filter(
      (e) => e.event_type === "PAYMENT_SENT" || e.event_type === "REFUND_REQUESTED"
    );
    outgoingEvents.forEach((paymentEv) => {
      const normRef =
        normalizeReference(paymentEv.order_reference) ||
        normalizeReference(paymentEv.transaction_reference);
      if (!normRef) return;

      const hasConfirmation = events.some((e) => {
        if (e.evidence_id === paymentEv.evidence_id) return false;
        const eRef =
          normalizeReference(e.order_reference) ||
          normalizeReference(e.transaction_reference);
        return (
          (e.event_type === "PAYMENT_MADE" ||
            e.event_type === "PAYMENT_CONFIRMED" ||
            e.event_type === "REFUND_COMPLETED" ||
            e.event_type === "REFUND_ISSUED" ||
            e.event_type === "REFUND_PROCESSED") &&
          eRef === normRef
        );
      });

      if (!hasConfirmation) {
        const pairKey = `MISSING_CORROB::${paymentEv.event_id}`;
        if (!seenPairs.has(pairKey)) {
          seenPairs.add(pairKey);
          const source =
            evidenceNameMap.get(paymentEv.evidence_id) || paymentEv.evidence_id;
          const displayRef =
            (paymentEv.order_reference ||
              paymentEv.transaction_reference ||
              "")!.trim();
          findings.push({
            finding_id: `fnd-missing-${paymentEv.event_id}`,
            case_id: paymentEv.case_id,
            finding_type: "MISSING_EVIDENCE_ADVISORY",
            title: `Unconfirmed Transaction Reference (${displayRef})`,
            summary: `An outgoing transaction is asserted in evidence, but no corresponding settlement or confirmation document is present in the case. This indicates an uncorroborated claim or documentation gap, not proof of a contradiction.`,
            severity: "MEDIUM",
            conflict_state: "POTENTIAL_CONFLICT",
            citations: [
              {
                evidence_id: paymentEv.evidence_id,
                original_filename: source,
                page_number: paymentEv.page_number,
                char_start: paymentEv.char_start,
                char_end: paymentEv.char_end,
                trigger_raw_text: paymentEv.trigger_raw_text,
                event_id: paymentEv.event_id,
              },
            ],
            model_confidence: 0.9,
            model_name: "proofflow-reasoning-engine",
            created_at: new Date().toISOString(),
          });
        }
      }
    });

    return findings;
  }, [backendFindings, events, evidenceList]);

  const activeFindings = backendFindings !== null ? backendFindings : clientFallbackFindings;

  // Review Adjudication Handlers
  const handleStartReview = (finding: FindingResponse) => {
    setAdjudicatingFindingId(finding.finding_id);
    setSelectedDecision((prev) => ({
      ...prev,
      [finding.finding_id]: finding.active_review?.decision || "CONFIRMED_INCONSISTENCY",
    }));
    setDecisionReason((prev) => ({
      ...prev,
      [finding.finding_id]: finding.active_review?.reason || "",
    }));
    setConfirmingSave((prev) => ({ ...prev, [finding.finding_id]: false }));
    setReviewError((prev) => ({ ...prev, [finding.finding_id]: null }));
    setReviewSuccess((prev) => ({ ...prev, [finding.finding_id]: null }));
  };

  const handleCancelReview = (findingId: string) => {
    setAdjudicatingFindingId(null);
    setConfirmingSave((prev) => ({ ...prev, [findingId]: false }));
    setReviewError((prev) => ({ ...prev, [findingId]: null }));
  };

  const handleRequestConfirm = (findingId: string) => {
    const decision = selectedDecision[findingId];
    const reason = (decisionReason[findingId] || "").trim();

    if (decision === "DISMISSED" && (!reason || reason.length < 3)) {
      setReviewError((prev) => ({
        ...prev,
        [findingId]: "A meaningful dismissal reason (at least 3 characters) is required.",
      }));
      return;
    }

    setReviewError((prev) => ({ ...prev, [findingId]: null }));
    setConfirmingSave((prev) => ({ ...prev, [findingId]: true }));
  };

  const handleSaveReview = async (findingId: string) => {
    if (!caseId) return;
    const decision = selectedDecision[findingId];
    if (!decision) return;
    const reason = (decisionReason[findingId] || "").trim();

    setSubmittingReview((prev) => ({ ...prev, [findingId]: true }));
    setReviewError((prev) => ({ ...prev, [findingId]: null }));

    try {
      const updatedReview = await api.recordFindingReview(caseId, findingId, {
        decision,
        reason: reason || undefined,
      });

      // Update finding with new active review state
      setBackendFindings((prev) => {
        if (!prev) return prev;
        return prev.map((f) =>
          f.finding_id === findingId ? { ...f, active_review: updatedReview } : f
        );
      });

      // Refresh history if history accordion is open
      if (viewingHistoryFindingId === findingId) {
        const historyRes = await api.getFindingReviews(caseId, findingId);
        setFindingHistories((prev) => ({ ...prev, [findingId]: historyRes.items }));
      }

      setReviewSuccess((prev) => ({
        ...prev,
        [findingId]: `Review decision '${decision.replace(/_/g, " ")}' saved to audit log.`,
      }));
      setConfirmingSave((prev) => ({ ...prev, [findingId]: false }));
      setAdjudicatingFindingId(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to save review decision";
      setReviewError((prev) => ({ ...prev, [findingId]: msg }));
    } finally {
      setSubmittingReview((prev) => ({ ...prev, [findingId]: false }));
    }
  };

  const handleToggleHistory = async (findingId: string) => {
    if (viewingHistoryFindingId === findingId) {
      setViewingHistoryFindingId(null);
      return;
    }
    setViewingHistoryFindingId(findingId);
    if (!caseId) return;

    setLoadingHistory((prev) => ({ ...prev, [findingId]: true }));
    try {
      const historyRes = await api.getFindingReviews(caseId, findingId);
      setFindingHistories((prev) => ({ ...prev, [findingId]: historyRes.items }));
    } catch {
      // Graceful fallback
    } finally {
      setLoadingHistory((prev) => ({ ...prev, [findingId]: false }));
    }
  };

  return (
    <div className="space-y-4">
      {/* Informational Guidance Notice */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex items-start justify-between gap-3 text-xs text-slate-600">
        <div className="flex items-start gap-3">
          <Info className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold text-slate-800">
              Cross-Examination & Human Adjudication Workspace
            </p>
            <p className="leading-relaxed">
              Authoritative, source-grounded findings computed on demand by the ProofFlow reasoning engine.
              Investigators can adjudicate individual findings as Confirmed Inconsistency, Resolved, or Dismissed.
              Human decisions are preserved in an immutable audit trail without modifying original ML extractions.
            </p>
          </div>
        </div>

        {caseId && (
          <button
            onClick={() => fetchFindings()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-50 shrink-0 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        )}
      </div>

      {loading ? (
        <div className="bg-white rounded-xl border border-slate-200/90 p-12 text-center shadow-sm">
          <Loader2 className="w-8 h-8 animate-spin text-brand-600 mx-auto mb-3" />
          <p className="text-sm font-semibold text-slate-800">
            Running Reasoning Engine...
          </p>
          <p className="text-xs text-slate-500 mt-1">
            Evaluating active evidence extractions for contradictions and sequence anomalies.
          </p>
        </div>
      ) : error ? (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-6 text-center space-y-3">
          <AlertTriangle className="w-6 h-6 text-rose-600 mx-auto" />
          <h4 className="text-sm font-bold text-rose-900">
            Failed to Compute Findings
          </h4>
          <p className="text-xs text-rose-700 max-w-md mx-auto">{error}</p>
          <button
            onClick={() => fetchFindings()}
            className="px-4 py-2 bg-rose-600 text-white text-xs font-semibold rounded-lg hover:bg-rose-700 transition"
          >
            Retry Analysis
          </button>
        </div>
      ) : activeFindings.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200/90 p-8 text-center shadow-sm">
          <div className="w-10 h-10 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto mb-3">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <h4 className="text-sm font-bold text-slate-900">
            No Contradictions or Inconsistencies Detected
          </h4>
          <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto leading-relaxed">
            All extracted facts, references, and amounts across active evidence documents are concordant.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {activeFindings.map((finding) => {
            let badgeColor = "bg-amber-50 text-amber-700 border-amber-200";
            let IconComponent = AlertTriangle;

            if (finding.conflict_state === "DIRECT_CONTRADICTION") {
              badgeColor = "bg-rose-50 text-rose-700 border-rose-200";
              IconComponent = AlertTriangle;
            } else if (
              finding.finding_type === "MISSING_EVIDENCE_ADVISORY" ||
              finding.finding_type === "MISSING_SUPPORTING_EVIDENCE"
            ) {
              badgeColor = "bg-sky-50 text-sky-700 border-sky-200";
              IconComponent = FileQuestion;
            } else if (finding.severity === "LOW") {
              badgeColor = "bg-indigo-50 text-indigo-700 border-indigo-200";
              IconComponent = HelpCircle;
            }

            const activeRev = finding.active_review;
            const isAdjudicating = adjudicatingFindingId === finding.finding_id;
            const isViewingHistory = viewingHistoryFindingId === finding.finding_id;
            const historyList = findingHistories[finding.finding_id] || [];
            const isSubmitting = submittingReview[finding.finding_id] || false;
            const isConfirming = confirmingSave[finding.finding_id] || false;
            const err = reviewError[finding.finding_id];
            const succ = reviewSuccess[finding.finding_id];

            return (
              <div
                key={finding.finding_id}
                className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-sm space-y-4 hover:border-slate-300 transition"
              >
                {/* Header: Finding Title + Conflict State + Severity */}
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="flex items-start gap-2.5">
                    <div
                      className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 border ${badgeColor} mt-0.5`}
                    >
                      <IconComponent className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-slate-900">
                        {finding.title}
                      </h4>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[11px] text-slate-400 font-mono">
                          {finding.conflict_state.replace(/_/g, " ")}
                        </span>
                        <span className="text-[11px] text-slate-300">•</span>
                        <span className="text-[11px] text-slate-400 font-mono">
                          ID: {finding.finding_id}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 self-start sm:self-center">
                    {/* Human Review Status Pill */}
                    {activeRev ? (
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${
                          activeRev.decision === "CONFIRMED_INCONSISTENCY"
                            ? "bg-amber-50 text-amber-800 border-amber-300"
                            : activeRev.decision === "RESOLVED"
                            ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                            : "bg-slate-100 text-slate-700 border-slate-300"
                        }`}
                      >
                        <UserCheck className="w-3 h-3 shrink-0" />
                        {activeRev.decision === "CONFIRMED_INCONSISTENCY"
                          ? "Confirmed Inconsistency"
                          : activeRev.decision === "RESOLVED"
                          ? "Resolved"
                          : "Dismissed"}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-50 text-slate-500 border border-slate-200">
                        Pending Review
                      </span>
                    )}

                    {/* ML Severity Badge */}
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                        finding.severity === "HIGH"
                          ? "bg-rose-50 text-rose-700 border-rose-200"
                          : finding.severity === "MEDIUM"
                          ? "bg-amber-50 text-amber-700 border-amber-200"
                          : "bg-slate-100 text-slate-600 border-slate-200"
                      }`}
                    >
                      {finding.severity} SEVERITY
                    </span>
                  </div>
                </div>

                {/* Finding Summary */}
                <p className="text-xs text-slate-600 leading-relaxed">
                  {finding.summary}
                </p>

                {/* Active Review Details Banner if reviewed */}
                {activeRev && (
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <span className="font-semibold text-slate-700 flex items-center gap-1">
                        <ShieldCheck className="w-3.5 h-3.5 text-slate-500" />
                        Human Review Adjudication (Revision v{activeRev.version})
                      </span>
                      <span>Reviewer: {activeRev.reviewer_id}</span>
                    </div>
                    {activeRev.reason && (
                      <p className="text-slate-700 italic border-l-2 border-slate-400 pl-2 text-[11px] leading-relaxed">
                        &ldquo;{activeRev.reason}&rdquo;
                      </p>
                    )}
                  </div>
                )}

                {/* Structured Difference View */}
                {finding.field_diff && (
                  <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                    <div className="space-y-1">
                      <div className="text-[11px] font-semibold text-slate-500 flex items-center gap-1">
                        <FileText className="w-3 h-3 text-slate-400" />
                        <span>Source A: {finding.field_diff.source_a}</span>
                      </div>
                      <div className="font-mono font-bold text-slate-900 bg-white p-2 rounded border border-slate-200">
                        {finding.field_diff.value_a}
                      </div>
                    </div>

                    <div className="space-y-1">
                      <div className="text-[11px] font-semibold text-slate-500 flex items-center gap-1">
                        <FileText className="w-3 h-3 text-slate-400" />
                        <span>Source B: {finding.field_diff.source_b}</span>
                      </div>
                      <div className="font-mono font-bold text-slate-900 bg-white p-2 rounded border border-slate-200">
                        {finding.field_diff.value_b}
                      </div>
                    </div>
                  </div>
                )}

                {/* Grounded Evidence Citations */}
                <div className="pt-2 border-t border-slate-100 space-y-1.5">
                  <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                    Grounded Evidence Citations
                  </span>
                  <div className="space-y-1.5">
                    {finding.citations.map((cite, idx) => {
                      const hasOffsets =
                        cite.char_start !== null &&
                        cite.char_start !== undefined &&
                        cite.char_end !== null &&
                        cite.char_end !== undefined &&
                        cite.char_start >= 0 &&
                        cite.char_end > 0;

                      return (
                        <div
                          key={cite.event_id || `${cite.evidence_id}-${idx}`}
                          className="text-xs bg-slate-50/70 p-2.5 rounded-lg border border-slate-100 space-y-1"
                        >
                          <div className="flex items-center justify-between text-[11px] text-slate-500">
                            <span className="font-semibold text-slate-700 flex items-center gap-1">
                              <FileText className="w-3 h-3 text-slate-400" />
                              {cite.original_filename}
                            </span>
                            <div className="flex items-center gap-2 text-slate-400">
                              <span>
                                {cite.page_number ? `Page ${cite.page_number}` : "Page not recorded"}
                              </span>
                              <span>•</span>
                              <span>
                                {hasOffsets
                                  ? `Chars [${cite.char_start}:${cite.char_end}]`
                                  : "Offsets not recorded"}
                              </span>
                            </div>
                          </div>

                          <blockquote className="text-slate-700 italic border-l-2 border-brand-400 pl-2 leading-relaxed">
                            &ldquo;{cite.trigger_raw_text}&rdquo;
                          </blockquote>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Reviewer Action Bar */}
                <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {caseId && (
                      <button
                        onClick={() =>
                          isAdjudicating ? handleCancelReview(finding.finding_id) : handleStartReview(finding)
                        }
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-900 text-white hover:bg-slate-800 transition"
                      >
                        <UserCheck className="w-3.5 h-3.5" />
                        {isAdjudicating
                          ? "Close Workspace"
                          : activeRev
                          ? "Update Adjudication"
                          : "Adjudicate Finding"}
                      </button>
                    )}

                    {caseId && (
                      <button
                        onClick={() => handleToggleHistory(finding.finding_id)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition"
                      >
                        <History className="w-3.5 h-3.5 text-slate-400" />
                        <span>Audit History</span>
                        {isViewingHistory ? (
                          <ChevronUp className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronDown className="w-3.5 h-3.5" />
                        )}
                      </button>
                    )}
                  </div>

                  {succ && (
                    <span className="text-xs text-emerald-600 font-semibold flex items-center gap-1">
                      <Check className="w-3.5 h-3.5" />
                      {succ}
                    </span>
                  )}
                </div>

                {/* Human Adjudication Workspace Form */}
                {isAdjudicating && (
                  <div className="bg-slate-50/80 border border-slate-200 rounded-xl p-4 space-y-4">
                    <div className="space-y-1">
                      <h5 className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                        <UserCheck className="w-4 h-4 text-brand-600" />
                        Human Review Adjudication
                      </h5>
                      <p className="text-[11px] text-slate-500 leading-relaxed">
                        Select a formal review decision. Decisions are recorded in the case audit trail and will not mutate underlying ML confidence scores.
                      </p>
                    </div>

                    {/* Decision Selection Grid */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedDecision((prev) => ({
                            ...prev,
                            [finding.finding_id]: "CONFIRMED_INCONSISTENCY",
                          }));
                          setConfirmingSave((prev) => ({ ...prev, [finding.finding_id]: false }));
                          setReviewError((prev) => ({ ...prev, [finding.finding_id]: null }));
                        }}
                        className={`p-3 rounded-lg border text-left space-y-1 transition ${
                          selectedDecision[finding.finding_id] === "CONFIRMED_INCONSISTENCY"
                            ? "bg-amber-50 border-amber-300 ring-1 ring-amber-300 text-amber-950"
                            : "bg-white border-slate-200 hover:border-slate-300 text-slate-800"
                        }`}
                      >
                        <div className="text-xs font-bold flex items-center justify-between">
                          <span>Confirmed Inconsistency</span>
                          {selectedDecision[finding.finding_id] === "CONFIRMED_INCONSISTENCY" && (
                            <Check className="w-3.5 h-3.5 text-amber-700" />
                          )}
                        </div>
                        <p className="text-[10px] text-slate-500 leading-normal">
                          Verified contradiction or sequence error represents a genuine dispute.
                        </p>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setSelectedDecision((prev) => ({
                            ...prev,
                            [finding.finding_id]: "RESOLVED",
                          }));
                          setConfirmingSave((prev) => ({ ...prev, [finding.finding_id]: false }));
                          setReviewError((prev) => ({ ...prev, [finding.finding_id]: null }));
                        }}
                        className={`p-3 rounded-lg border text-left space-y-1 transition ${
                          selectedDecision[finding.finding_id] === "RESOLVED"
                            ? "bg-emerald-50 border-emerald-300 ring-1 ring-emerald-300 text-emerald-950"
                            : "bg-white border-slate-200 hover:border-slate-300 text-slate-800"
                        }`}
                      >
                        <div className="text-xs font-bold flex items-center justify-between">
                          <span>Resolved</span>
                          {selectedDecision[finding.finding_id] === "RESOLVED" && (
                            <Check className="w-3.5 h-3.5 text-emerald-700" />
                          )}
                        </div>
                        <p className="text-[10px] text-slate-500 leading-normal">
                          Discrepancy reconciled, settled, or clarified by external evidence.
                        </p>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setSelectedDecision((prev) => ({
                            ...prev,
                            [finding.finding_id]: "DISMISSED",
                          }));
                          setConfirmingSave((prev) => ({ ...prev, [finding.finding_id]: false }));
                          setReviewError((prev) => ({ ...prev, [finding.finding_id]: null }));
                        }}
                        className={`p-3 rounded-lg border text-left space-y-1 transition ${
                          selectedDecision[finding.finding_id] === "DISMISSED"
                            ? "bg-slate-100 border-slate-400 ring-1 ring-slate-400 text-slate-900"
                            : "bg-white border-slate-200 hover:border-slate-300 text-slate-800"
                        }`}
                      >
                        <div className="text-xs font-bold flex items-center justify-between">
                          <span>Dismissed</span>
                          {selectedDecision[finding.finding_id] === "DISMISSED" && (
                            <Check className="w-3.5 h-3.5 text-slate-700" />
                          )}
                        </div>
                        <p className="text-[10px] text-slate-500 leading-normal">
                          Disregard finding (reason required: expected variance, policy exception, etc.).
                        </p>
                      </button>
                    </div>

                    {/* Reason Text Area */}
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-slate-700 flex items-center justify-between">
                        <span>
                          {selectedDecision[finding.finding_id] === "DISMISSED"
                            ? "Dismissal Reason (Required)"
                            : "Adjudication Notes (Optional)"}
                        </span>
                        {selectedDecision[finding.finding_id] === "DISMISSED" && (
                          <span className="text-[10px] text-rose-600 font-bold uppercase tracking-wider">
                            Mandatory
                          </span>
                        )}
                      </label>
                      <textarea
                        rows={2}
                        value={decisionReason[finding.finding_id] || ""}
                        onChange={(e) => {
                          setDecisionReason((prev) => ({
                            ...prev,
                            [finding.finding_id]: e.target.value,
                          }));
                          setReviewError((prev) => ({ ...prev, [finding.finding_id]: null }));
                        }}
                        placeholder={
                          selectedDecision[finding.finding_id] === "DISMISSED"
                            ? "Explain why this finding is dismissed (e.g. 'Partial settlement confirmed via banking portal')..."
                            : "Optional rationale or operational notes for the audit trail..."
                        }
                        className="w-full text-xs p-2.5 rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500 leading-relaxed text-slate-800 placeholder:text-slate-400"
                      />
                    </div>

                    {/* Error Banner */}
                    {err && (
                      <div className="bg-rose-50 border border-rose-200 rounded-lg p-2.5 flex items-start gap-2 text-xs text-rose-700">
                        <XCircle className="w-4 h-4 shrink-0 text-rose-600 mt-0.5" />
                        <span>{err}</span>
                      </div>
                    )}

                    {/* Confirmation Step & Actions */}
                    {isConfirming ? (
                      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2.5">
                        <div className="flex items-start gap-2 text-xs text-amber-900">
                          <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
                          <div className="space-y-0.5">
                            <span className="font-bold">Confirm Review Submission</span>
                            <p className="text-[11px] text-amber-800">
                              You are recording this finding as{" "}
                              <strong>
                                {selectedDecision[finding.finding_id]?.replace(/_/g, " ")}
                              </strong>
                              . This decision will be appended to the case audit log.
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 pt-1">
                          <button
                            type="button"
                            disabled={isSubmitting}
                            onClick={() => handleSaveReview(finding.finding_id)}
                            className="px-3 py-1.5 text-xs font-bold rounded-lg bg-amber-700 text-white hover:bg-amber-800 disabled:opacity-50 flex items-center gap-1.5 transition"
                          >
                            {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                            Confirm & Save Decision
                          </button>
                          <button
                            type="button"
                            disabled={isSubmitting}
                            onClick={() =>
                              setConfirmingSave((prev) => ({ ...prev, [finding.finding_id]: false }))
                            }
                            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition"
                          >
                            Back to Edit
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleRequestConfirm(finding.finding_id)}
                          className="px-3 py-1.5 text-xs font-bold rounded-lg bg-slate-900 text-white hover:bg-slate-800 transition"
                        >
                          Review & Confirm
                        </button>
                        <button
                          type="button"
                          onClick={() => handleCancelReview(finding.finding_id)}
                          className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 transition"
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Decision Audit History Accordion */}
                {isViewingHistory && (
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <h5 className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                        <History className="w-4 h-4 text-slate-500" />
                        Decision Audit History for Finding {finding.finding_id}
                      </h5>
                      <span className="text-[11px] text-slate-400 font-mono">
                        {historyList.length} revision{historyList.length === 1 ? "" : "s"}
                      </span>
                    </div>

                    {loadingHistory[finding.finding_id] ? (
                      <div className="py-4 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-400" />
                        Loading history...
                      </div>
                    ) : historyList.length === 0 ? (
                      <div className="text-xs text-slate-500 italic py-2">
                        No historical human decisions recorded for this finding yet.
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {historyList.map((rev) => (
                          <div
                            key={rev.review_id}
                            className={`p-2.5 rounded-lg border text-xs space-y-1 ${
                              rev.is_active
                                ? "bg-white border-slate-300 ring-1 ring-slate-200"
                                : "bg-slate-100/70 border-slate-200 opacity-75"
                            }`}
                          >
                            <div className="flex items-center justify-between text-[11px]">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-slate-800">
                                  Revision v{rev.version}
                                </span>
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                                    rev.decision === "CONFIRMED_INCONSISTENCY"
                                      ? "bg-amber-100 text-amber-800"
                                      : rev.decision === "RESOLVED"
                                      ? "bg-emerald-100 text-emerald-800"
                                      : "bg-slate-200 text-slate-700"
                                  }`}
                                >
                                  {rev.decision.replace(/_/g, " ")}
                                </span>
                                {rev.is_active ? (
                                  <span className="text-[10px] font-bold text-brand-600 uppercase">
                                    [Active]
                                  </span>
                                ) : (
                                  <span className="text-[10px] text-slate-400 uppercase">
                                    [Superseded]
                                  </span>
                                )}
                              </div>
                              <span className="text-slate-400">
                                {new Date(rev.created_at).toLocaleString()}
                              </span>
                            </div>

                            <div className="text-[11px] text-slate-500">
                              Reviewer: <span className="font-mono text-slate-700">{rev.reviewer_id}</span>
                            </div>

                            {rev.reason && (
                              <p className="text-slate-700 italic border-l-2 border-slate-300 pl-2 text-[11px]">
                                &ldquo;{rev.reason}&rdquo;
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
