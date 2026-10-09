"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import { EventResponse, EvidenceResponse } from "@/types/api";
import { api, ApiError } from "@/lib/api";
import {
  Clock,
  Calendar,
  FileText,
  Filter,
  RefreshCw,
  Search,
  ExternalLink,
  DollarSign,
  User,
  Hash,
  AlertCircle,
  HelpCircle,
  CheckCircle2,
  ArrowUpDown,
} from "lucide-react";

interface EventTimelineProps {
  caseId: string;
  evidenceList: EvidenceResponse[];
  onEventsLoaded?: (events: EventResponse[]) => void;
  refreshTrigger?: number;
}

export function EventTimeline({
  caseId,
  evidenceList,
  onEventsLoaded,
  refreshTrigger,
}: EventTimelineProps) {
  const [events, setEvents] = useState<EventResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string>("ALL");
  const [selectedDecisionState, setSelectedDecisionState] = useState<string>("ALL");
  const [selectedEventType, setSelectedEventType] = useState<string>("ALL");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [searchQuery, setSearchQuery] = useState("");

  const evidenceMap = useMemo(() => {
    const map = new Map<string, EvidenceResponse>();
    evidenceList.forEach((e) => map.set(e.evidence_id, e));
    return map;
  }, [evidenceList]);

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: {
        evidence_id?: string;
        decision_state?: string;
        event_type?: string;
        limit?: number;
      } = {
        limit: 100,
      };

      if (selectedEvidenceId !== "ALL") {
        params.evidence_id = selectedEvidenceId;
      }
      if (selectedDecisionState !== "ALL") {
        params.decision_state = selectedDecisionState;
      }
      if (selectedEventType !== "ALL") {
        params.event_type = selectedEventType;
      }

      const res = await api.listCaseEvents(caseId, params);
      setEvents(res.items);
      if (onEventsLoaded) {
        onEventsLoaded(res.items);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to fetch events from ProofFlow backend");
      }
    } finally {
      setLoading(false);
    }
  }, [caseId, selectedEvidenceId, selectedDecisionState, selectedEventType, onEventsLoaded]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents, refreshTrigger]);

  // Extract distinct event types for filter dropdown
  const availableEventTypes = useMemo(() => {
    const types = new Set<string>();
    events.forEach((ev) => types.add(ev.event_type));
    return Array.from(types).sort();
  }, [events]);

  // Chronological sorting:
  // Extracts date from model_metadata if present, else parses from trigger_raw_text or falls back to created_at
  const sortedAndFilteredEvents = useMemo(() => {
    let filtered = events.filter((ev) => {
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return (
        ev.event_type.toLowerCase().includes(q) ||
        ev.trigger_raw_text.toLowerCase().includes(q) ||
        (ev.actor && ev.actor.toLowerCase().includes(q)) ||
        (ev.order_reference && ev.order_reference.toLowerCase().includes(q)) ||
        (ev.transaction_reference && ev.transaction_reference.toLowerCase().includes(q))
      );
    });

    return filtered.sort((a, b) => {
      // Resolve event date: check model_metadata.event_date / date, fallback to created_at
      const dateAStr =
        (a.model_metadata?.event_date as string) ||
        (a.model_metadata?.date as string) ||
        a.created_at;
      const dateBStr =
        (b.model_metadata?.event_date as string) ||
        (b.model_metadata?.date as string) ||
        b.created_at;

      const timeA = new Date(dateAStr).getTime();
      const timeB = new Date(dateBStr).getTime();

      return sortOrder === "asc" ? timeA - timeB : timeB - timeA;
    });
  }, [events, searchQuery, sortOrder]);

  const formatConfidence = (conf: number): string => {
    return `${Math.round(conf * 100)}%`;
  };

  const formatCurrency = (amount: string | number | null | undefined, currency: string | null | undefined): string => {
    if (amount === null || amount === undefined) return "";
    const num = Number(amount);
    if (isNaN(num)) return `${amount} ${currency || ""}`.trim();
    return `${currency || "$"}${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <div className="space-y-6">
      {/* Filters and Controls */}
      <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-sm space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-brand-600" />
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">
              Chronological Event Timeline ({events.length})
            </h3>
          </div>

          <div className="flex items-center gap-2 self-end sm:self-center">
            <button
              onClick={() => setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"))}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-slate-600 bg-slate-50 border border-slate-200 rounded-lg hover:bg-slate-100 transition"
              title="Toggle sort order"
            >
              <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
              <span>{sortOrder === "asc" ? "Oldest First" : "Newest First"}</span>
            </button>

            <button
              onClick={fetchEvents}
              disabled={loading}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-slate-600 bg-slate-50 border border-slate-200 rounded-lg hover:bg-slate-100 transition disabled:opacity-50"
              title="Refresh timeline"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* Filter Selection Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5 pt-2 border-t border-slate-100 text-xs">
          {/* Evidence Filter */}
          <div>
            <label
              htmlFor="source-evidence-filter"
              className="block text-[11px] font-semibold text-slate-500 mb-1"
            >
              Source Evidence
            </label>
            <select
              id="source-evidence-filter"
              value={selectedEvidenceId}
              onChange={(e) => setSelectedEvidenceId(e.target.value)}
              className="w-full px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="ALL">All Evidence Assets ({evidenceList.length})</option>
              {evidenceList.map((evi) => (
                <option key={evi.evidence_id} value={evi.evidence_id}>
                  {evi.original_filename} (v{evi.active_processing_version || 1})
                </option>
              ))}
            </select>
          </div>

          {/* Decision State Filter */}
          <div>
            <label
              htmlFor="validation-state-filter"
              className="block text-[11px] font-semibold text-slate-500 mb-1"
            >
              Validation State
            </label>
            <select
              id="validation-state-filter"
              value={selectedDecisionState}
              onChange={(e) => setSelectedDecisionState(e.target.value)}
              className="w-full px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="ALL">All Decision States</option>
              <option value="VALIDATED">Validated</option>
              <option value="REVIEW_NEEDED">Review Needed</option>
            </select>
          </div>

          {/* Event Type Filter */}
          <div>
            <label
              htmlFor="event-type-filter"
              className="block text-[11px] font-semibold text-slate-500 mb-1"
            >
              Event Type
            </label>
            <select
              id="event-type-filter"
              value={selectedEventType}
              onChange={(e) => setSelectedEventType(e.target.value)}
              className="w-full px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="ALL">All Event Types</option>
              {availableEventTypes.map((type) => (
                <option key={type} value={type}>
                  {type.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>

          {/* Search text */}
          <div>
            <label
              htmlFor="search-events-input"
              className="block text-[11px] font-semibold text-slate-500 mb-1"
            >
              Search Event Claims
            </label>
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                id="search-events-input"
                type="text"
                placeholder="Actor, order, snippet..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded-xl text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-500 shrink-0" />
            <span className="font-medium">{error}</span>
          </div>
          <button
            onClick={fetchEvents}
            className="text-rose-900 font-semibold underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading ? (
        <div className="space-y-4 py-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white rounded-xl border border-slate-200 p-5 space-y-3 animate-pulse"
            >
              <div className="h-4 bg-slate-200 rounded w-1/4"></div>
              <div className="h-3 bg-slate-100 rounded w-3/4"></div>
              <div className="h-3 bg-slate-100 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      ) : sortedAndFilteredEvents.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center shadow-sm">
          <Clock className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h4 className="text-sm font-bold text-slate-800">
            {events.length === 0 ? "No Grounded Events Extracted Yet" : "No Events Match Filters"}
          </h4>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto leading-relaxed">
            {events.length === 0
              ? "Upload and process evidence documents to extract chronological event milestones."
              : "Try adjusting your evidence selection, decision state, or search filter."}
          </p>
        </div>
      ) : (
        /* Timeline Nodes */
        <div className="relative pl-6 sm:pl-8 space-y-6 before:absolute before:left-2.5 sm:before:left-3 before:top-3 before:bottom-3 before:w-0.5 before:bg-slate-200">
          {sortedAndFilteredEvents.map((event, idx) => {
            const evidence = evidenceMap.get(event.evidence_id);
            const sourceFilename = evidence?.original_filename || event.evidence_id;

            // Distinguish contextual event date vs extraction timestamp
            const rawEventDate =
              (event.model_metadata?.event_date as string) ||
              (event.model_metadata?.date as string);
            const hasGroundedDate = Boolean(rawEventDate);

            const displayEventDate = hasGroundedDate
              ? new Date(rawEventDate).toLocaleDateString(undefined, {
                  year: "numeric",
                  month: "short",
                  day: "numeric",
                })
              : "Date not stated in text";

            const extractionDate = new Date(event.created_at).toLocaleDateString(undefined, {
              year: "numeric",
              month: "short",
              day: "numeric",
            });

            const isReviewNeeded = event.decision_state === "REVIEW_NEEDED";

            return (
              <div key={event.event_id} className="relative group">
                {/* Timeline node marker */}
                <div
                  className={`absolute -left-6 sm:-left-8 top-4 w-3.5 h-3.5 rounded-full border-2 bg-white ${
                    isReviewNeeded
                      ? "border-amber-500 group-hover:bg-amber-100"
                      : "border-brand-600 group-hover:bg-brand-100"
                  } transition`}
                />

                <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-sm space-y-3.5 hover:border-slate-300 transition">
                  {/* Header: Event Type, Date, Decision State */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-sm text-slate-900 tracking-tight">
                        {event.event_type.replace(/_/g, " ")}
                      </span>

                      <span
                        className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                          isReviewNeeded
                            ? "bg-amber-50 text-amber-700 border-amber-200"
                            : "bg-emerald-50 text-emerald-700 border-emerald-200"
                        }`}
                      >
                        {isReviewNeeded ? "Review Needed" : "Validated"}
                      </span>

                      <span className="text-[11px] font-mono text-slate-400">
                        {event.polarity} • {event.modality}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-xs text-slate-500 self-start sm:self-center">
                      <span
                        className={`flex items-center gap-1 font-medium ${
                          hasGroundedDate ? "text-slate-900" : "text-slate-400 italic"
                        }`}
                        title={
                          hasGroundedDate
                            ? "Grounded event date extracted from document"
                            : "No explicit date found in trigger context"
                        }
                      >
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        {displayEventDate}
                      </span>

                      <span className="text-slate-300">|</span>

                      <span className="text-[11px] text-slate-400" title="Ingestion timestamp">
                        Ingested: {extractionDate}
                      </span>
                    </div>
                  </div>

                  {/* Grounded Trigger Text Provenance */}
                  <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-3 space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] text-slate-400">
                      <span className="font-semibold text-slate-500 uppercase tracking-wider">
                        Source Trigger Quote
                      </span>
                      <span>
                        Chars: [{event.char_start}:{event.char_end}]
                      </span>
                    </div>
                    <blockquote className="text-xs text-slate-800 italic font-serif leading-relaxed">
                      &ldquo;{event.trigger_raw_text}&rdquo;
                    </blockquote>
                  </div>

                  {/* Grounded Arguments & Attributes */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-xs">
                    {event.actor && (
                      <div className="bg-slate-50/60 p-2 rounded border border-slate-100 flex items-center gap-1.5">
                        <User className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="truncate text-slate-700 font-medium">
                          {event.actor}
                        </span>
                      </div>
                    )}

                    {event.amount_value !== null && event.amount_value !== undefined && (
                      <div className="bg-slate-50/60 p-2 rounded border border-slate-100 flex items-center gap-1.5">
                        <DollarSign className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                        <span className="truncate text-emerald-800 font-semibold font-mono">
                          {formatCurrency(event.amount_value, event.amount_currency)}
                        </span>
                      </div>
                    )}

                    {event.order_reference && (
                      <div className="bg-slate-50/60 p-2 rounded border border-slate-100 flex items-center gap-1.5">
                        <Hash className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="truncate text-slate-700 font-mono font-medium">
                          {event.order_reference}
                        </span>
                      </div>
                    )}

                    {event.transaction_reference && (
                      <div className="bg-slate-50/60 p-2 rounded border border-slate-100 flex items-center gap-1.5">
                        <Hash className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="truncate text-slate-700 font-mono font-medium">
                          {event.transaction_reference}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Review reasons notice */}
                  {isReviewNeeded && event.review_reasons.length > 0 && (
                    <div className="text-[11px] text-amber-700 bg-amber-50/80 p-2 rounded border border-amber-200/80 flex items-center gap-1.5">
                      <HelpCircle className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                      <span>Flagged for review: {event.review_reasons.join(", ")}</span>
                    </div>
                  )}

                  {/* Provenance Footer: Source document & Model Confidence */}
                  <div className="pt-2 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[11px] text-slate-500">
                    <div className="flex items-center gap-2">
                      <FileText className="w-3.5 h-3.5 text-brand-600" />
                      <span className="font-semibold text-slate-700 truncate max-w-xs">
                        {sourceFilename}
                      </span>
                      {event.page_number && (
                        <span className="bg-slate-100 px-1.5 py-0.5 rounded text-[10px] font-medium text-slate-600">
                          Page {event.page_number}
                        </span>
                      )}
                      <span className="font-mono text-[10px] text-slate-400">
                        v{event.processing_version}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5" title="Neural classifier sequence confidence score (not truth probability)">
                      <span className="text-slate-400">Model Confidence:</span>
                      <span className="font-mono font-semibold text-slate-700">
                        {formatConfidence(event.model_confidence)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
