import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import CaseDetailsPage from "@/app/cases/[caseId]/page";
import { api } from "@/lib/api";
import { CaseResponse, EvidenceResponse, DossierResponse } from "@/types/api";

// Mock useParams from next/navigation
vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: "case_export_123" }),
}));

const mockCase: CaseResponse = {
  case_id: "case_export_123",
  user_id: "user_tester",
  title: "Maritime Freight Demurrage Dispute",
  description: "Disputed port demurrage fees under charter party agreement.",
  status: "READY",
  tags: ["maritime", "freight"],
  evidence_count: 2,
  metadata: {},
  created_at: "2026-03-01T10:00:00Z",
  updated_at: "2026-03-01T10:05:00Z",
};

const mockEvidenceList: EvidenceResponse[] = [
  {
    evidence_id: "evi_doc_1",
    case_id: "case_export_123",
    original_filename: "bill_of_lading.pdf",
    media_type: "application/pdf",
    file_size_bytes: 45000,
    sha256_hash: "1".repeat(64),
    status: "READY",
    processing_mode: "NEURAL_DEBERTA_CPU",
    processing_version: 1,
    active_processing_version: 1,
    created_at: "2026-03-01T10:01:00Z",
    updated_at: "2026-03-01T10:02:00Z",
  },
];

const mockDossier: DossierResponse = {
  report_version: "1.0.0",
  generated_at: "2026-03-02T12:00:00Z",
  manifest_hash: "test_manifest_hash_123",
  case: mockCase,
  executive_summary: "Test objective executive summary.",
  document_inventory: [
    {
      evidence_id: "evi_doc_1",
      original_filename: "bill_of_lading.pdf",
      media_type: "application/pdf",
      file_size_bytes: 45000,
      sha256_hash: "1".repeat(64),
      status: "READY",
      uploaded_at: "2026-03-01T10:01:00Z",
      active_processing_version: 1,
    },
  ],
  events_timeline: [],
  findings: [],
  human_reviews: [],
  evidence_gaps: [],
  methodology: {
    system_name: "ProofFlow Evidence Reasoning Engine",
    system_version: "1.0.0",
    report_standard: "ProofFlow v1",
    disclaimer: "Not a legal decision engine.",
    limitations: [],
  },
};

describe("Dispute Dossier Export Frontend Actions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "getCase").mockResolvedValue(mockCase);
    vi.spyOn(api, "listEvidence").mockResolvedValue({
      items: mockEvidenceList,
      pagination: { page: 1, limit: 100, total: 1, pages: 1 },
    });

    // Mock URL object creation and revocation
    global.URL.createObjectURL = vi.fn(() => "blob:mock-url");
    global.URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  it("renders export action buttons on case details page", async () => {
    render(<CaseDetailsPage />);

    await waitFor(() => {
      expect(screen.getByText("Maritime Freight Demurrage Dispute")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /Export PDF Dossier/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Export JSON/i })).toBeInTheDocument();
  });

  it("triggers PDF export and displays success confirmation message", async () => {
    const pdfSpy = vi.spyOn(api, "exportCasePdf").mockResolvedValue(
      new Blob(["%PDF-1.4 test data"], { type: "application/pdf" })
    );

    render(<CaseDetailsPage />);

    await waitFor(() => {
      expect(screen.getByText("Maritime Freight Demurrage Dispute")).toBeInTheDocument();
    });

    const exportPdfBtn = screen.getByRole("button", { name: /Export PDF Dossier/i });
    fireEvent.click(exportPdfBtn);

    await waitFor(() => {
      expect(pdfSpy).toHaveBeenCalledWith("case_export_123");
    });

    await waitFor(() => {
      expect(
        screen.getByText(/Dispute dossier PDF downloaded successfully\./i)
      ).toBeInTheDocument();
    });
  });

  it("triggers JSON export and displays success confirmation message", async () => {
    const jsonSpy = vi.spyOn(api, "exportCaseJson").mockResolvedValue(mockDossier);

    render(<CaseDetailsPage />);

    await waitFor(() => {
      expect(screen.getByText("Maritime Freight Demurrage Dispute")).toBeInTheDocument();
    });

    const exportJsonBtn = screen.getByRole("button", { name: /Export JSON/i });
    fireEvent.click(exportJsonBtn);

    await waitFor(() => {
      expect(jsonSpy).toHaveBeenCalledWith("case_export_123");
    });

    await waitFor(() => {
      expect(
        screen.getByText(/Dispute dossier JSON exported successfully\./i)
      ).toBeInTheDocument();
    });
  });

  it("displays error banner when PDF export fails", async () => {
    vi.spyOn(api, "exportCasePdf").mockRejectedValue(new Error("PDF generation service unavailable"));

    render(<CaseDetailsPage />);

    await waitFor(() => {
      expect(screen.getByText("Maritime Freight Demurrage Dispute")).toBeInTheDocument();
    });

    const exportPdfBtn = screen.getByRole("button", { name: /Export PDF Dossier/i });
    fireEvent.click(exportPdfBtn);

    await waitFor(() => {
      expect(screen.getByText("PDF generation service unavailable")).toBeInTheDocument();
    });
  });
});
