import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CrossEvidenceComparison } from "@/components/CrossEvidenceComparison";
import { EventResponse, EvidenceResponse, FindingResponse } from "@/types/api";
import { api } from "@/lib/api";

const mockEvidenceList: EvidenceResponse[] = [
  {
    evidence_id: "evi_doc_A",
    case_id: "case_test",
    original_filename: "sales_agreement.pdf",
    media_type: "application/pdf",
    file_size_bytes: 40000,
    sha256_hash: "1".repeat(64),
    status: "READY",
    processing_mode: "NEURAL_DEBERTA_CPU",
    processing_version: 1,
    active_processing_version: 1,
    created_at: "2026-03-01T10:00:00Z",
    updated_at: "2026-03-01T10:01:00Z",
  },
  {
    evidence_id: "evi_doc_B",
    case_id: "case_test",
    original_filename: "payment_receipt.pdf",
    media_type: "application/pdf",
    file_size_bytes: 25000,
    sha256_hash: "2".repeat(64),
    status: "READY",
    processing_mode: "NEURAL_DEBERTA_CPU",
    processing_version: 1,
    active_processing_version: 1,
    created_at: "2026-03-02T10:00:00Z",
    updated_at: "2026-03-02T10:01:00Z",
  },
];

describe("CrossEvidenceComparison Hardening Audit", () => {
  it("flags different currencies on same reference as Currency Mismatch, not raw amount contradiction", () => {
    const currencyMismatchEvents: EventResponse[] = [
      {
        event_id: "evt_curr_1",
        case_id: "case_test",
        evidence_id: "evi_doc_A",
        processing_version: 1,
        is_active: true,
        event_type: "ORDER_PLACED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Contract total is 50,000 USD for PO-778.",
        char_start: 10,
        char_end: 45,
        page_number: 1,
        order_reference: "PO-778",
        amount_currency: "USD",
        amount_value: "50000.00",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
      {
        event_id: "evt_curr_2",
        case_id: "case_test",
        evidence_id: "evi_doc_B",
        processing_version: 1,
        is_active: true,
        event_type: "PAYMENT_CONFIRMED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Settlement executed for 45,000 EUR against PO-778.",
        char_start: 15,
        char_end: 62,
        page_number: 1,
        order_reference: "PO-778",
        amount_currency: "EUR",
        amount_value: "45000.00",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.92,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
    ];

    render(
      <CrossEvidenceComparison
        events={currencyMismatchEvents}
        evidenceList={mockEvidenceList}
      />
    );

    // Verify it is flagged as Currency Denomination Mismatch (POTENTIAL_CONFLICT), not DIRECT_CONTRADICTION
    expect(
      screen.getByText(/Currency Denomination Mismatch on Reference PO-778/i)
    ).toBeInTheDocument();
    expect(screen.getByText("POTENTIAL CONFLICT")).toBeInTheDocument();
    expect(screen.getByText("MEDIUM SEVERITY")).toBeInTheDocument();
    expect(
      screen.getByText(/Direct numeric comparison requires exchange rate verification/i)
    ).toBeInTheDocument();
  });

  it("does not report amount discrepancies when amounts are missing (null/undefined)", () => {
    const missingAmountEvents: EventResponse[] = [
      {
        event_id: "evt_no_amt_1",
        case_id: "case_test",
        evidence_id: "evi_doc_A",
        processing_version: 1,
        is_active: true,
        event_type: "ORDER_PLACED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Order placed for PO-999 without listed price.",
        char_start: 0,
        char_end: 42,
        order_reference: "PO-999",
        amount_currency: null,
        amount_value: null,
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.90,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
      {
        event_id: "evt_no_amt_2",
        case_id: "case_test",
        evidence_id: "evi_doc_B",
        processing_version: 1,
        is_active: true,
        event_type: "ORDER_PLACED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Order confirmation received for PO-999.",
        char_start: 0,
        char_end: 38,
        order_reference: "PO-999",
        amount_currency: "USD",
        amount_value: "1000.00",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.91,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
    ];

    render(
      <CrossEvidenceComparison
        events={missingAmountEvents}
        evidenceList={mockEvidenceList}
      />
    );

    // No amount discrepancy finding
    expect(
      screen.queryByText(/Monetary Discrepancy/i)
    ).not.toBeInTheDocument();
  });

  it("does not match similar but non-identical order references", () => {
    const nonMatchingEvents: EventResponse[] = [
      {
        event_id: "evt_ref_1",
        case_id: "case_test",
        evidence_id: "evi_doc_A",
        processing_version: 1,
        is_active: true,
        event_type: "ORDER_PLACED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Order placed for PO-100.",
        char_start: 0,
        char_end: 24,
        order_reference: "PO-100",
        amount_currency: "USD",
        amount_value: "5000.00",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
      {
        event_id: "evt_ref_2",
        case_id: "case_test",
        evidence_id: "evi_doc_B",
        processing_version: 1,
        is_active: true,
        event_type: "ORDER_PLACED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Order placed for PO-101.",
        char_start: 0,
        char_end: 24,
        order_reference: "PO-101",
        amount_currency: "USD",
        amount_value: "8000.00",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
    ];

    render(
      <CrossEvidenceComparison
        events={nonMatchingEvents}
        evidenceList={mockEvidenceList}
      />
    );

    expect(
      screen.queryByText(/Monetary Discrepancy/i)
    ).not.toBeInTheDocument();
  });

  it("safely ignores ambiguous tokens like 'N/A' or 'ID'", () => {
    const ambiguousEvents: EventResponse[] = [
      {
        event_id: "evt_amb_1",
        case_id: "case_test",
        evidence_id: "evi_doc_A",
        processing_version: 1,
        is_active: true,
        event_type: "PAYMENT_SENT",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Wire sent.",
        char_start: 0,
        char_end: 10,
        order_reference: "N/A",
        amount_currency: "USD",
        amount_value: "100.00",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
      {
        event_id: "evt_amb_2",
        case_id: "case_test",
        evidence_id: "evi_doc_B",
        processing_version: 1,
        is_active: true,
        event_type: "PAYMENT_SENT",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Wire acknowledged.",
        char_start: 0,
        char_end: 18,
        order_reference: "N/A",
        amount_currency: "USD",
        amount_value: "200.00",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
    ];

    render(
      <CrossEvidenceComparison
        events={ambiguousEvents}
        evidenceList={mockEvidenceList}
      />
    );

    // Ignored by ambiguity guard
    expect(
      screen.queryByText(/Monetary Discrepancy/i)
    ).not.toBeInTheDocument();
  });

  it("does not compare two events originating from the exact SAME evidence document as a cross-document contradiction", () => {
    const sameDocEvents: EventResponse[] = [
      {
        event_id: "evt_same_1",
        case_id: "case_test",
        evidence_id: "evi_doc_A", // SAME
        processing_version: 1,
        is_active: true,
        event_type: "ORDER_PLACED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Initial quote 10,000.",
        char_start: 0,
        char_end: 20,
        order_reference: "PO-SAME",
        amount_currency: "USD",
        amount_value: "10000.00",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
      {
        event_id: "evt_same_2",
        case_id: "case_test",
        evidence_id: "evi_doc_A", // SAME
        processing_version: 1,
        is_active: true,
        event_type: "ORDER_PLACED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Final revision 12,000.",
        char_start: 100,
        char_end: 122,
        order_reference: "PO-SAME",
        amount_currency: "USD",
        amount_value: "12000.00",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
    ];

    render(
      <CrossEvidenceComparison
        events={sameDocEvents}
        evidenceList={mockEvidenceList}
      />
    );

    // Cross-evidence contradiction must enforce distinct documents
    expect(
      screen.queryByText(/Monetary Discrepancy/i)
    ).not.toBeInTheDocument();
  });

  it("gracefully displays missing page and character offsets without fabricating", () => {
    const missingProvenanceEvents: EventResponse[] = [
      {
        event_id: "evt_missing_prov",
        case_id: "case_test",
        evidence_id: "evi_doc_A",
        processing_version: 1,
        is_active: true,
        event_type: "PAYMENT_SENT",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Payment dispatched without page header.",
        char_start: 0,
        char_end: 0, // no offsets
        page_number: null, // no page
        order_reference: "PO-PROV",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.85,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
    ];

    render(
      <CrossEvidenceComparison
        events={missingProvenanceEvents}
        evidenceList={mockEvidenceList}
      />
    );

    expect(screen.getByText("Page not recorded")).toBeInTheDocument();
    expect(screen.getByText("Offsets not recorded")).toBeInTheDocument();
  });

  it("deduplicates findings so multiple traversals never generate duplicate cards", () => {
    const dupEventPair: EventResponse[] = [
      {
        event_id: "evt_dup_A",
        case_id: "case_test",
        evidence_id: "evi_doc_A",
        processing_version: 1,
        is_active: true,
        event_type: "ORDER_PLACED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Order PO-DUP for 100.",
        char_start: 1,
        char_end: 20,
        order_reference: "PO-DUP",
        amount_currency: "USD",
        amount_value: "100.00",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
      {
        event_id: "evt_dup_B",
        case_id: "case_test",
        evidence_id: "evi_doc_B",
        processing_version: 1,
        is_active: true,
        event_type: "ORDER_PLACED",
        decision_state: "VALIDATED",
        review_reasons: [],
        trigger_raw_text: "Order PO-DUP for 200.",
        char_start: 1,
        char_end: 20,
        order_reference: "PO-DUP",
        amount_currency: "USD",
        amount_value: "200.00",
        polarity: "POSITIVE",
        modality: "ASSERTED",
        tense: "PAST",
        model_confidence: 0.95,
        model_metadata: {},
        created_at: new Date().toISOString(),
      },
    ];

    render(
      <CrossEvidenceComparison
        events={dupEventPair}
        evidenceList={mockEvidenceList}
      />
    );

    const cards = screen.getAllByText(/Amount Divergence on Reference PO-DUP/i);
    expect(cards).toHaveLength(1);
  });

  it("renders backend findings directly when initialFindings prop is passed", () => {
    const backendFindings: FindingResponse[] = [
      {
        finding_id: "fnd_test_12345",
        case_id: "case_test",
        finding_type: "POTENTIAL_INCONSISTENCY",
        title: "Potential Inconsistency: Amount Divergence on Reference PO-BACKEND",
        summary: "Differing amounts recorded across documents referencing 'PO-BACKEND'. Differs by $3,000.00.",
        severity: "MEDIUM",
        conflict_state: "POTENTIAL_CONFLICT",
        citations: [
          {
            evidence_id: "evi_doc_A",
            original_filename: "sales_agreement.pdf",
            page_number: 2,
            char_start: 10,
            char_end: 45,
            trigger_raw_text: "Total agreed PO-BACKEND: $10,000.00",
            event_id: "evt_1",
          },
          {
            evidence_id: "evi_doc_B",
            original_filename: "payment_receipt.pdf",
            page_number: 1,
            char_start: 5,
            char_end: 40,
            trigger_raw_text: "Invoice total PO-BACKEND: $13,000.00",
            event_id: "evt_2",
          },
        ],
        field_diff: {
          field: "Amount",
          value_a: "$10,000.00",
          source_a: "sales_agreement.pdf (p. 2)",
          value_b: "$13,000.00",
          source_b: "payment_receipt.pdf (p. 1)",
        },
        model_confidence: 1.0,
        model_name: "proofflow-reasoning-engine",
        created_at: new Date().toISOString(),
      },
    ];

    render(
      <CrossEvidenceComparison
        initialFindings={backendFindings}
      />
    );

    expect(screen.getByText("Potential Inconsistency: Amount Divergence on Reference PO-BACKEND")).toBeInTheDocument();
    expect(screen.getByText("POTENTIAL CONFLICT")).toBeInTheDocument();
    expect(screen.getByText("MEDIUM SEVERITY")).toBeInTheDocument();
    expect(screen.getByText(/Differs by \$3,000.00/i)).toBeInTheDocument();
    expect(screen.getByText("Source A: sales_agreement.pdf (p. 2)")).toBeInTheDocument();
    expect(screen.getByText("$10,000.00")).toBeInTheDocument();
    expect(screen.getByText("sales_agreement.pdf")).toBeInTheDocument();
    expect(screen.getByText("payment_receipt.pdf")).toBeInTheDocument();
  });

  it("fetches backend findings on mount when caseId is provided", async () => {
    const mockFinding: FindingResponse = {
      finding_id: "fnd_api_999",
      case_id: "case_backend",
      finding_type: "MISSING_EVIDENCE_ADVISORY",
      title: "Unconfirmed Transaction Reference (TXN-999)",
      summary: "An outgoing transaction is asserted in evidence, but no corresponding settlement document is present.",
      severity: "MEDIUM",
      conflict_state: "POTENTIAL_CONFLICT",
      citations: [
        {
          evidence_id: "evi_doc_A",
          original_filename: "sales_agreement.pdf",
          page_number: 1,
          char_start: 0,
          char_end: 25,
          trigger_raw_text: "Dispatched wire for TXN-999",
          event_id: "evt_wire_1",
        },
      ],
      model_confidence: 0.90,
      model_name: "proofflow-reasoning-engine",
      created_at: new Date().toISOString(),
    };

    const getFindingsSpy = vi.spyOn(api, "getCaseFindings").mockResolvedValueOnce({
      items: [mockFinding],
      total: 1,
      case_id: "case_backend",
    });

    render(<CrossEvidenceComparison caseId="case_backend" />);

    expect(screen.getByText("Running Reasoning Engine...")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Unconfirmed Transaction Reference (TXN-999)")).toBeInTheDocument();
    });

    expect(getFindingsSpy).toHaveBeenCalledWith("case_backend");
    expect(screen.getByText("MEDIUM SEVERITY")).toBeInTheDocument();
    getFindingsSpy.mockRestore();
  });
});
