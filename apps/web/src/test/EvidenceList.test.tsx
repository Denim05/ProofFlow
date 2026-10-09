import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { EvidenceList } from "@/components/EvidenceList";
import { api } from "@/lib/api";
import { EvidenceResponse } from "@/types/api";

vi.mock("@/lib/api", () => ({
  api: {
    listEvidence: vi.fn(),
    retryEvidence: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    public status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

const mockItems: EvidenceResponse[] = [
  {
    evidence_id: "evi_001",
    case_id: "case_123",
    original_filename: "statement_march.pdf",
    media_type: "application/pdf",
    file_size_bytes: 50000,
    sha256_hash: "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    status: "READY",
    processing_mode: "NEURAL_DEBERTA_CPU",
    processing_version: 1,
    active_processing_version: 1,
    extraction_summary: { events_extracted: 12, raw_text_length: 3500 },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    evidence_id: "evi_002",
    case_id: "case_123",
    original_filename: "corrupt_invoice.pdf",
    media_type: "application/pdf",
    file_size_bytes: 12000,
    sha256_hash: "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    status: "FAILED",
    processing_mode: "DETERMINISTIC_FALLBACK",
    processing_version: 1,
    error_code: "PDF_EXTRACTION_ERROR",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

describe("EvidenceList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders evidence items with filename, status, and metrics", async () => {
    (api.listEvidence as any).mockResolvedValue({
      items: mockItems,
      pagination: { page: 1, limit: 100, total: 2, pages: 1 },
    });

    render(<EvidenceList caseId="case_123" />);

    await waitFor(() => {
      expect(screen.getByText("statement_march.pdf")).toBeInTheDocument();
      expect(screen.getByText("corrupt_invoice.pdf")).toBeInTheDocument();
      expect(screen.getByText("12 events extracted")).toBeInTheDocument();
      expect(screen.getByText("READY")).toBeInTheDocument();
      expect(screen.getByText("FAILED")).toBeInTheDocument();
    });
  });

  it("renders retry button only for failed/interrupted evidence and triggers api.retryEvidence", async () => {
    (api.listEvidence as any).mockResolvedValue({
      items: mockItems,
      pagination: { page: 1, limit: 100, total: 2, pages: 1 },
    });
    (api.retryEvidence as any).mockResolvedValue({
      ...mockItems[1],
      status: "QUEUED",
    });

    render(<EvidenceList caseId="case_123" />);

    await waitFor(() => {
      // Only 1 retry button for the failed item
      const retryButtons = screen.getAllByRole("button", { name: /retry extraction/i });
      expect(retryButtons).toHaveLength(1);
    });

    const retryButton = screen.getByRole("button", { name: /retry extraction/i });
    fireEvent.click(retryButton);

    await waitFor(() => {
      expect(api.retryEvidence).toHaveBeenCalledWith("case_123", "evi_002");
    });
  });
});
