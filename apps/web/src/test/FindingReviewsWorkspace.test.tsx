import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CrossEvidenceComparison } from "@/components/CrossEvidenceComparison";
import { FindingResponse, EvidenceResponse } from "@/types/api";
import { api } from "@/lib/api";

const mockEvidenceList: EvidenceResponse[] = [
  {
    evidence_id: "evi_doc_1",
    case_id: "case_review_test",
    original_filename: "contract.pdf",
    media_type: "application/pdf",
    file_size_bytes: 10000,
    sha256_hash: "a".repeat(64),
    status: "READY",
    processing_mode: "NEURAL_DEBERTA_CPU",
    processing_version: 1,
    active_processing_version: 1,
    created_at: "2026-03-01T10:00:00Z",
    updated_at: "2026-03-01T10:01:00Z",
  },
  {
    evidence_id: "evi_doc_2",
    case_id: "case_review_test",
    original_filename: "invoice.pdf",
    media_type: "application/pdf",
    file_size_bytes: 12000,
    sha256_hash: "b".repeat(64),
    status: "READY",
    processing_mode: "NEURAL_DEBERTA_CPU",
    processing_version: 1,
    active_processing_version: 1,
    created_at: "2026-03-02T10:00:00Z",
    updated_at: "2026-03-02T10:01:00Z",
  },
];

const mockFindingWithoutReview: FindingResponse = {
  finding_id: "fnd_test_101",
  case_id: "case_review_test",
  finding_type: "POTENTIAL_INCONSISTENCY",
  title: "Amount Divergence on PO-100",
  summary: "Differing monetary amounts recorded across documents referencing PO-100.",
  severity: "HIGH",
  conflict_state: "POTENTIAL_CONFLICT",
  citations: [
    {
      evidence_id: "evi_doc_1",
      original_filename: "contract.pdf",
      page_number: 1,
      char_start: 0,
      char_end: 20,
      trigger_raw_text: "$5000 due",
      event_id: "evt_1",
    },
    {
      evidence_id: "evi_doc_2",
      original_filename: "invoice.pdf",
      page_number: 1,
      char_start: 0,
      char_end: 20,
      trigger_raw_text: "$6000 billed",
      event_id: "evt_2",
    },
  ],
  field_diff: {
    field: "Amount",
    value_a: "$5,000",
    source_a: "contract.pdf",
    value_b: "$6,000",
    source_b: "invoice.pdf",
  },
  model_confidence: 0.95,
  model_name: "proofflow-reasoning-engine",
  created_at: "2026-03-03T10:00:00Z",
  active_review: null,
};

const mockFindingWithReview: FindingResponse = {
  ...mockFindingWithoutReview,
  finding_id: "fnd_test_102",
  active_review: {
    review_id: "rev_001",
    case_id: "case_review_test",
    finding_id: "fnd_test_102",
    reviewer_id: "auditor_smith",
    decision: "CONFIRMED_INCONSISTENCY",
    reason: "Vendor billed over contract price without change order.",
    version: 1,
    is_active: true,
    created_at: "2026-03-04T12:00:00Z",
    updated_at: "2026-03-04T12:00:00Z",
  },
};

describe("Dispute Decision Workspace & Human-in-the-Loop Review UI", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders pending review status pill and permits opening adjudication workspace", async () => {
    vi.spyOn(api, "getCaseFindings").mockResolvedValue({
      items: [mockFindingWithoutReview],
      total: 1,
      case_id: "case_review_test",
    });

    render(
      <CrossEvidenceComparison
        caseId="case_review_test"
        events={[]}
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Amount Divergence on PO-100")).toBeInTheDocument();
    });

    // Human Review status pill should show "Pending Review"
    expect(screen.getByText(/Pending Review/i)).toBeInTheDocument();

    // Click "Adjudicate Finding" action button
    const adjudicateBtn = screen.getByRole("button", { name: /Adjudicate Finding/i });
    fireEvent.click(adjudicateBtn);

    // Workspace should expand with human review adjudication options
    expect(screen.getByText("Human Review Adjudication")).toBeInTheDocument();
    expect(screen.getByText("Confirmed Inconsistency")).toBeInTheDocument();
    expect(screen.getByText("Resolved")).toBeInTheDocument();
    expect(screen.getByText("Dismissed")).toBeInTheDocument();
  });

  it("enforces dismissal reason requirement before allowing adjudication confirmation", async () => {
    vi.spyOn(api, "getCaseFindings").mockResolvedValue({
      items: [mockFindingWithoutReview],
      total: 1,
      case_id: "case_review_test",
    });

    render(
      <CrossEvidenceComparison
        caseId="case_review_test"
        events={[]}
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Amount Divergence on PO-100")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Adjudicate Finding/i }));

    // Select DISMISSED decision
    fireEvent.click(screen.getByText("Dismissed"));

    // Attempt to proceed without entering a reason
    const proceedBtn = screen.getByRole("button", { name: /Review & Confirm/i });
    fireEvent.click(proceedBtn);

    // Validation error should appear
    expect(
      screen.getByText(/A meaningful dismissal reason \(at least 3 characters\) is required\./i)
    ).toBeInTheDocument();
  });

  it("supports two-step confirmation and records adjudication decision successfully", async () => {
    vi.spyOn(api, "getCaseFindings").mockResolvedValue({
      items: [mockFindingWithoutReview],
      total: 1,
      case_id: "case_review_test",
    });
    const recordReviewSpy = vi.spyOn(api, "recordFindingReview").mockResolvedValue({
      review_id: "rev_new_99",
      case_id: "case_review_test",
      finding_id: "fnd_test_101",
      reviewer_id: "user_adjudicator",
      decision: "RESOLVED",
      reason: "Confirmed payment processed through banking portal.",
      version: 1,
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    render(
      <CrossEvidenceComparison
        caseId="case_review_test"
        events={[]}
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Amount Divergence on PO-100")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Adjudicate Finding/i }));

    // Select RESOLVED
    fireEvent.click(screen.getByText("Resolved"));

    // Add reason
    const reasonInput = screen.getByPlaceholderText(/Optional rationale or operational notes/i);
    fireEvent.change(reasonInput, {
      target: { value: "Confirmed payment processed through banking portal." },
    });

    // Step 1: Proceed to Confirmation
    fireEvent.click(screen.getByRole("button", { name: /Review & Confirm/i }));

    // Step 2: Confirmation banner is displayed
    expect(screen.getByText(/Confirm Review Submission/i)).toBeInTheDocument();
    expect(screen.getByText(/You are recording this finding as/i)).toBeInTheDocument();

    // Confirm Adjudication
    const confirmBtn = screen.getByRole("button", { name: /Confirm & Save Decision/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(recordReviewSpy).toHaveBeenCalledWith(
        "case_review_test",
        "fnd_test_101",
        expect.objectContaining({
          decision: "RESOLVED",
          reason: "Confirmed payment processed through banking portal.",
        })
      );
    });

    // Success feedback is displayed
    await waitFor(() => {
      expect(screen.getByText(/Review decision 'RESOLVED' saved to audit log\./i)).toBeInTheDocument();
    });
  });

  it("displays existing active review and allows viewing review audit history", async () => {
    vi.spyOn(api, "getCaseFindings").mockResolvedValue({
      items: [mockFindingWithReview],
      total: 1,
      case_id: "case_review_test",
    });
    const historySpy = vi.spyOn(api, "getFindingReviews").mockResolvedValue({
      items: [
        {
          review_id: "rev_002",
          case_id: "case_review_test",
          finding_id: "fnd_test_102",
          reviewer_id: "auditor_smith",
          decision: "CONFIRMED_INCONSISTENCY",
          reason: "Vendor billed over contract price without change order.",
          version: 2,
          is_active: true,
          created_at: "2026-03-04T12:00:00Z",
          updated_at: "2026-03-04T12:00:00Z",
        },
        {
          review_id: "rev_001",
          case_id: "case_review_test",
          finding_id: "fnd_test_102",
          reviewer_id: "auditor_smith",
          decision: "RESOLVED",
          reason: "Initial assessment under investigation.",
          version: 1,
          is_active: false,
          created_at: "2026-03-03T10:00:00Z",
          updated_at: "2026-03-03T10:00:00Z",
        },
      ],
      total: 2,
      finding_id: "fnd_test_102",
      case_id: "case_review_test",
    });

    render(
      <CrossEvidenceComparison
        caseId="case_review_test"
        events={[]}
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Amount Divergence on PO-100")).toBeInTheDocument();
    });

    // Pill shows "Confirmed Inconsistency"
    expect(screen.getByText("Confirmed Inconsistency")).toBeInTheDocument();

    // Active review note is displayed
    expect(
      screen.getByText(/Vendor billed over contract price without change order/i)
    ).toBeInTheDocument();

    // Click "Audit History" toggle button
    const historyToggleBtn = screen.getByRole("button", { name: /Audit History/i });
    fireEvent.click(historyToggleBtn);

    await waitFor(() => {
      expect(historySpy).toHaveBeenCalledWith("case_review_test", "fnd_test_102");
    });

    // Verify history records are rendered
    await waitFor(() => {
      expect(
        screen.getByText(/Decision Audit History for Finding fnd_test_102/i)
      ).toBeInTheDocument();
      expect(screen.getByText("Revision v2")).toBeInTheDocument();
      expect(screen.getByText("Revision v1")).toBeInTheDocument();
      expect(screen.getByText(/Initial assessment under investigation/i)).toBeInTheDocument();
    });
  });

  it("handles adjudication API errors gracefully with clear user feedback", async () => {
    vi.spyOn(api, "getCaseFindings").mockResolvedValue({
      items: [mockFindingWithoutReview],
      total: 1,
      case_id: "case_review_test",
    });
    vi.spyOn(api, "recordFindingReview").mockRejectedValue(new Error("Network connection dropped"));

    render(
      <CrossEvidenceComparison
        caseId="case_review_test"
        events={[]}
        evidenceList={mockEvidenceList}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Amount Divergence on PO-100")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Adjudicate Finding/i }));
    fireEvent.click(screen.getByRole("button", { name: /Review & Confirm/i }));
    fireEvent.click(screen.getByRole("button", { name: /Confirm & Save Decision/i }));

    await waitFor(() => {
      expect(screen.getByText("Network connection dropped")).toBeInTheDocument();
    });
  });
});
