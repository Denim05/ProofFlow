import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { EventTimeline, formatEventDate } from "@/components/EventTimeline";
import { api } from "@/lib/api";
import { EventResponse, EvidenceResponse } from "@/types/api";

vi.mock("@/lib/api", () => ({
  api: {
    listCaseEvents: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    public status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

const mockEvidenceList: EvidenceResponse[] = [
  {
    evidence_id: "evi_doc_1",
    case_id: "case_test",
    original_filename: "purchase_contract.pdf",
    media_type: "application/pdf",
    file_size_bytes: 54000,
    sha256_hash: "1".repeat(64),
    status: "READY",
    processing_mode: "NEURAL_DEBERTA_CPU",
    processing_version: 1,
    active_processing_version: 1,
    created_at: "2026-03-01T10:00:00Z",
    updated_at: "2026-03-01T10:01:00Z",
  },
  {
    evidence_id: "evi_doc_2",
    case_id: "case_test",
    original_filename: "wire_receipt.pdf",
    media_type: "application/pdf",
    file_size_bytes: 32000,
    sha256_hash: "2".repeat(64),
    status: "READY",
    processing_mode: "NEURAL_DEBERTA_CPU",
    processing_version: 1,
    active_processing_version: 1,
    created_at: "2026-03-02T10:00:00Z",
    updated_at: "2026-03-02T10:01:00Z",
  },
];

const mockEvents: EventResponse[] = [
  {
    event_id: "evt_001",
    case_id: "case_test",
    evidence_id: "evi_doc_1",
    processing_version: 1,
    is_active: true,
    event_type: "ORDER_PLACED",
    decision_state: "VALIDATED",
    review_reasons: [],
    trigger_raw_text: "Acme Corp placed order PO-101 on November 10, 2023 for USD 50,000.",
    char_start: 12,
    char_end: 78,
    page_number: 1,
    actor: "Acme Corp",
    amount_currency: "USD",
    amount_value: "50000.00",
    order_reference: "PO-101",
    polarity: "POSITIVE",
    modality: "ASSERTED",
    tense: "PAST",
    model_confidence: 0.96,
    model_metadata: { event_date: "2023-11-10" },
    created_at: "2026-03-01T10:00:30Z",
  },
  {
    event_id: "evt_002",
    case_id: "case_test",
    evidence_id: "evi_doc_2",
    processing_version: 1,
    is_active: true,
    event_type: "PAYMENT_CONFIRMED",
    decision_state: "REVIEW_NEEDED",
    review_reasons: ["LOW_CONFIDENCE_THRESHOLD"],
    trigger_raw_text: "Payment of USD 45,000 for PO-101 was acknowledged on November 15, 2023.",
    char_start: 5,
    char_end: 75,
    page_number: 2,
    actor: "Global Logistics",
    amount_currency: "USD",
    amount_value: "45000.00",
    order_reference: "PO-101",
    polarity: "POSITIVE",
    modality: "ASSERTED",
    tense: "PAST",
    model_confidence: 0.72,
    model_metadata: { event_date: "2023-11-15" },
    created_at: "2026-03-02T10:00:30Z",
  },
  {
    event_id: "evt_003",
    case_id: "case_test",
    evidence_id: "evi_doc_1",
    processing_version: 1,
    is_active: true,
    event_type: "DISPUTE_RAISED",
    decision_state: "VALIDATED",
    review_reasons: [],
    trigger_raw_text: "Dispute opened regarding missing delivery confirmation.",
    char_start: 120,
    char_end: 175,
    page_number: null, // missing page provenance
    actor: null, // missing actor
    polarity: "POSITIVE",
    modality: "ASSERTED",
    tense: "PAST",
    model_confidence: 0.88,
    model_metadata: {}, // missing event date
    created_at: "2026-03-03T10:00:30Z",
  },
];

describe("EventTimeline", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches and renders events in chronological order with grounded dates", async () => {
    (api.listCaseEvents as any).mockResolvedValue({
      items: mockEvents,
      pagination: { page: 1, limit: 100, total: 3, pages: 1 },
    });

    render(
      <EventTimeline
        caseId="case_test"
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText("ORDER PLACED").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("PAYMENT CONFIRMED").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("DISPUTE RAISED").length).toBeGreaterThanOrEqual(1);
    });

    // Check grounded trigger text
    expect(
      screen.getByText(/Acme Corp placed order PO-101 on November 10, 2023/i)
    ).toBeInTheDocument();

    // Check confidence labels
    expect(screen.getByText("96%")).toBeInTheDocument();
    expect(screen.getByText("72%")).toBeInTheDocument();
    expect(screen.getByText("88%")).toBeInTheDocument();
  });

  it("handles missing event date and displays fallback notice", async () => {
    (api.listCaseEvents as any).mockResolvedValue({
      items: [mockEvents[2]],
      pagination: { page: 1, limit: 100, total: 1, pages: 1 },
    });

    render(
      <EventTimeline
        caseId="case_test"
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Date not stated in text")).toBeInTheDocument();
    });
  });

  it("displays empty state when no events exist", async () => {
    (api.listCaseEvents as any).mockResolvedValue({
      items: [],
      pagination: { page: 1, limit: 100, total: 0, pages: 0 },
    });

    render(
      <EventTimeline
        caseId="case_test"
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      expect(
        screen.getByText(/No Grounded Events Extracted Yet/i)
      ).toBeInTheDocument();
    });
  });

  it("filters events by source evidence document", async () => {
    (api.listCaseEvents as any).mockResolvedValue({
      items: [mockEvents[0]],
      pagination: { page: 1, limit: 100, total: 1, pages: 1 },
    });

    render(
      <EventTimeline
        caseId="case_test"
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      expect(api.listCaseEvents).toHaveBeenCalledWith("case_test", { limit: 100 });
    });

    // Change evidence filter
    const select = screen.getByLabelText(/Source Evidence/i);
    fireEvent.change(select, { target: { value: "evi_doc_1" } });

    await waitFor(() => {
      expect(api.listCaseEvents).toHaveBeenCalledWith("case_test", {
        evidence_id: "evi_doc_1",
        limit: 100,
      });
    });
  });

  it("handles API failure and provides retry action", async () => {
    (api.listCaseEvents as any).mockRejectedValue(new Error("Network timeout"));

    render(
      <EventTimeline
        caseId="case_test"
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      expect(
        screen.getByText(/Failed to fetch events from ProofFlow backend/i)
      ).toBeInTheDocument();
    });

    const retryBtn = screen.getByRole("button", { name: /retry/i });
    expect(retryBtn).toBeInTheDocument();
  });

  it("renders grounded event date from temporal_information and preserves separate ingestion date", async () => {
    const temporalEvents: EventResponse[] = [
      {
        event_id: "evt_order_1",
        case_id: "case_test",
        evidence_id: "evi_doc_1",
        processing_version: 1,
        is_active: true,
        event_type: "ORDER_PLACED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Order PF-1001 was placed on 5 October 2026",
        char_start: 0,
        char_end: 42,
        temporal_information: "2026-10-05",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: "2026-10-09T12:00:00Z",
      },
    ];

    (api.listCaseEvents as any).mockResolvedValue({
      items: temporalEvents,
      pagination: { page: 1, limit: 100, total: 1, pages: 1 },
    });

    render(
      <EventTimeline
        caseId="case_test"
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Oct 5, 2026/)).toBeInTheDocument();
      expect(screen.getByText(/Ingested:/)).toBeInTheDocument();
    });
  });

  it("prioritizes grounded temporal_information over ingestion timestamp for chronological sorting", async () => {
    // Event 2 was ingested earlier (created_at Oct 1) but occurred later (temporal Oct 7)
    // Event 1 was ingested later (created_at Oct 9) but occurred earlier (temporal Oct 5)
    const outOfOrderEvents: EventResponse[] = [
      {
        event_id: "evt_delivered",
        case_id: "case_test",
        evidence_id: "evi_doc_2",
        processing_version: 1,
        is_active: true,
        event_type: "ITEM_DELIVERED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Delivered on 7 October 2026",
        char_start: 0,
        char_end: 27,
        temporal_information: "2026-10-07",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: "2026-10-01T10:00:00Z", // Ingested earlier
      },
      {
        event_id: "evt_ordered",
        case_id: "case_test",
        evidence_id: "evi_doc_1",
        processing_version: 1,
        is_active: true,
        event_type: "ORDER_PLACED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Ordered on 5 October 2026",
        char_start: 0,
        char_end: 25,
        temporal_information: "2026-10-05",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: "2026-10-09T10:00:00Z", // Ingested later
      },
    ];

    (api.listCaseEvents as any).mockResolvedValue({
      items: outOfOrderEvents,
      pagination: { page: 1, limit: 100, total: 2, pages: 1 },
    });

    render(
      <EventTimeline
        caseId="case_test"
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      const renderedHeadings = screen.getAllByTestId("event-type-heading");
      expect(renderedHeadings[0]).toHaveTextContent("ORDER PLACED");
      expect(renderedHeadings[1]).toHaveTextContent("ITEM DELIVERED");
    });
  });

  it("formats ISO date-only strings safely without timezone shifts", () => {
    expect(formatEventDate("2026-10-05")).toMatch(/Oct 5, 2026/);
    expect(formatEventDate("2026-10-07")).toMatch(/Oct 7, 2026/);
    expect(formatEventDate(null)).toBe("Date not stated in text");
    expect(formatEventDate("")).toBe("Date not stated in text");
  });
});
