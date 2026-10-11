import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { EvidenceList } from "@/components/EvidenceList";
import { api, ApiError } from "@/lib/api";
import { EvidenceResponse } from "@/types/api";

vi.mock("@/lib/api", () => ({
  api: {
    listEvidence: vi.fn(),
    retryEvidence: vi.fn(),
    downloadEvidence: vi.fn(),
    previewEvidence: vi.fn(),
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
  {
    evidence_id: "evi_003",
    case_id: "case_123",
    original_filename: "damaged_goods.png",
    media_type: "image/png",
    file_size_bytes: 35000,
    sha256_hash: "99887766554433221100abcdef1234567890abcdef1234567890abcdef123456",
    status: "READY",
    processing_mode: "DETERMINISTIC_FALLBACK",
    processing_version: 1,
    active_processing_version: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

describe("EvidenceList", () => {
  const originalCreateObjectURL = window.URL.createObjectURL;
  const originalRevokeObjectURL = window.URL.revokeObjectURL;

  beforeEach(() => {
    vi.clearAllMocks();
    window.URL.createObjectURL = vi.fn(() => "blob:http://localhost/mock-preview-url");
    window.URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  afterEach(() => {
    window.URL.createObjectURL = originalCreateObjectURL;
    window.URL.revokeObjectURL = originalRevokeObjectURL;
    vi.restoreAllMocks();
  });

  it("renders evidence items with filename, status, and metrics", async () => {
    (api.listEvidence as any).mockResolvedValue({
      items: mockItems,
      pagination: { page: 1, limit: 100, total: 3, pages: 1 },
    });

    render(<EvidenceList caseId="case_123" />);

    await waitFor(() => {
      expect(screen.getByText("statement_march.pdf")).toBeInTheDocument();
      expect(screen.getByText("corrupt_invoice.pdf")).toBeInTheDocument();
      expect(screen.getByText("damaged_goods.png")).toBeInTheDocument();
      expect(screen.getByText("12 events extracted")).toBeInTheDocument();
      expect(screen.getAllByText("READY")).toHaveLength(2);
      expect(screen.getByText("FAILED")).toBeInTheDocument();
    });
  });

  it("renders Preview and Download buttons for all evidence items", async () => {
    (api.listEvidence as any).mockResolvedValue({
      items: mockItems,
      pagination: { page: 1, limit: 100, total: 3, pages: 1 },
    });

    render(<EvidenceList caseId="case_123" />);

    await waitFor(() => {
      const previewButtons = screen.getAllByRole("button", { name: /preview/i });
      expect(previewButtons).toHaveLength(3);

      const downloadButtons = screen.getAllByRole("button", { name: /download/i });
      expect(downloadButtons).toHaveLength(3);
    });
  });

  it("renders retry button only for failed/interrupted evidence and triggers api.retryEvidence", async () => {
    (api.listEvidence as any).mockResolvedValue({
      items: mockItems,
      pagination: { page: 1, limit: 100, total: 3, pages: 1 },
    });
    (api.retryEvidence as any).mockResolvedValue({
      ...mockItems[1],
      status: "QUEUED",
    });

    render(<EvidenceList caseId="case_123" />);

    await waitFor(() => {
      const retryButtons = screen.getAllByRole("button", { name: /retry extraction/i });
      expect(retryButtons).toHaveLength(1);
    });

    const retryButton = screen.getByRole("button", { name: /retry extraction/i });
    fireEvent.click(retryButton);

    await waitFor(() => {
      expect(api.retryEvidence).toHaveBeenCalledWith("case_123", "evi_002");
    });
  });

  it("opens preview modal and fetches PDF blob when Preview is clicked", async () => {
    (api.listEvidence as any).mockResolvedValue({
      items: mockItems,
      pagination: { page: 1, limit: 100, total: 3, pages: 1 },
    });
    const mockBlob = new Blob(["%PDF-1.4 dummy"], { type: "application/pdf" });
    (api.previewEvidence as any).mockResolvedValue(mockBlob);

    render(<EvidenceList caseId="case_123" />);

    await waitFor(() => {
      expect(screen.getByText("statement_march.pdf")).toBeInTheDocument();
    });

    const previewButtons = screen.getAllByRole("button", { name: /preview/i });
    fireEvent.click(previewButtons[0]);

    await waitFor(() => {
      expect(api.previewEvidence).toHaveBeenCalledWith("case_123", "evi_001");
      expect(window.URL.createObjectURL).toHaveBeenCalledWith(mockBlob);
      // Dialog modal is mounted
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      // Iframe for PDF preview is rendered
      const iframe = screen.getByTitle("Preview of statement_march.pdf");
      expect(iframe).toBeInTheDocument();
      expect(iframe).toHaveAttribute("src", "blob:http://localhost/mock-preview-url#toolbar=1");
    });
  });

  it("handles preview error gracefully when file is missing on ephemeral disk", async () => {
    (api.listEvidence as any).mockResolvedValue({
      items: mockItems,
      pagination: { page: 1, limit: 100, total: 3, pages: 1 },
    });
    (api.previewEvidence as any).mockRejectedValue(
      new ApiError("Evidence file is not available on disk. On Render Free hosting, local storage is ephemeral.", 404)
    );

    render(<EvidenceList caseId="case_123" />);

    await waitFor(() => {
      expect(screen.getByText("statement_march.pdf")).toBeInTheDocument();
    });

    const previewButtons = screen.getAllByRole("button", { name: /preview/i });
    fireEvent.click(previewButtons[0]);

    await waitFor(() => {
      expect(screen.getByText(/Unable to Preview Evidence/i)).toBeInTheDocument();
      expect(screen.getByText(/Render Free hosting, local storage is ephemeral/i)).toBeInTheDocument();
    });
  });

  it("closes modal and revokes object URL when close button is clicked", async () => {
    (api.listEvidence as any).mockResolvedValue({
      items: mockItems,
      pagination: { page: 1, limit: 100, total: 3, pages: 1 },
    });
    const mockBlob = new Blob(["%PDF-1.4 dummy"], { type: "application/pdf" });
    (api.previewEvidence as any).mockResolvedValue(mockBlob);

    render(<EvidenceList caseId="case_123" />);

    await waitFor(() => {
      expect(screen.getByText("statement_march.pdf")).toBeInTheDocument();
    });

    const previewButtons = screen.getAllByRole("button", { name: /preview/i });
    fireEvent.click(previewButtons[0]);

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    const closeButton = screen.getByRole("button", { name: /close preview/i });
    fireEvent.click(closeButton);

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(window.URL.revokeObjectURL).toHaveBeenCalledWith("blob:http://localhost/mock-preview-url");
    });
  });

  it("calls api.downloadEvidence and triggers file save when Download is clicked", async () => {
    (api.listEvidence as any).mockResolvedValue({
      items: mockItems,
      pagination: { page: 1, limit: 100, total: 3, pages: 1 },
    });
    const mockBlob = new Blob(["binary data"], { type: "application/pdf" });
    (api.downloadEvidence as any).mockResolvedValue(mockBlob);

    render(<EvidenceList caseId="case_123" />);

    await waitFor(() => {
      expect(screen.getByText("statement_march.pdf")).toBeInTheDocument();
    });

    const downloadButtons = screen.getAllByRole("button", { name: /download/i });
    fireEvent.click(downloadButtons[0]);

    await waitFor(() => {
      expect(api.downloadEvidence).toHaveBeenCalledWith("case_123", "evi_001", false);
      expect(window.URL.createObjectURL).toHaveBeenCalledWith(mockBlob);
      expect(window.URL.revokeObjectURL).toHaveBeenCalledWith("blob:http://localhost/mock-preview-url");
    });
  });
});
