import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { EvidenceUploader } from "@/components/EvidenceUploader";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    uploadEvidence: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    public status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

describe("EvidenceUploader", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders upload dropzone correctly", () => {
    render(<EvidenceUploader caseId="case_123" onUploadSuccess={() => {}} />);
    expect(screen.getByText(/Ingest Documentary Evidence/i)).toBeInTheDocument();
    expect(screen.getByText(/Click to upload/i)).toBeInTheDocument();
  });

  it("rejects unsupported file extensions client-side", () => {
    render(<EvidenceUploader caseId="case_123" onUploadSuccess={() => {}} />);

    const invalidFile = new File(["test content"], "document.txt", {
      type: "text/plain",
    });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [invalidFile] } });

    expect(
      screen.getByText(/Unsupported file format. Accepted formats:/i)
    ).toBeInTheDocument();
    expect(api.uploadEvidence).not.toHaveBeenCalled();
  });

  it("rejects files exceeding 25 MB limit client-side", () => {
    render(<EvidenceUploader caseId="case_123" onUploadSuccess={() => {}} />);

    const bigFile = new File(["x".repeat(100)], "large.pdf", {
      type: "application/pdf",
    });
    Object.defineProperty(bigFile, "size", { value: 26 * 1024 * 1024 });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [bigFile] } });

    expect(
      screen.getByText(/exceeds maximum allowed limit of 25 MB/i)
    ).toBeInTheDocument();
    expect(api.uploadEvidence).not.toHaveBeenCalled();
  });

  it("handles valid file selection and successful upload", async () => {
    const onUploadSuccess = vi.fn();
    const mockResponse = {
      evidence_id: "evi_456",
      case_id: "case_123",
      original_filename: "contract.pdf",
      media_type: "application/pdf",
      file_size_bytes: 1024,
      sha256_hash: "a".repeat(64),
      status: "QUEUED" as const,
      is_duplicate: false,
      created_at: new Date().toISOString(),
    };

    (api.uploadEvidence as any).mockResolvedValue(mockResponse);

    render(<EvidenceUploader caseId="case_123" onUploadSuccess={onUploadSuccess} />);

    const validFile = new File(["pdf binary content"], "contract.pdf", {
      type: "application/pdf",
    });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [validFile] } });

    expect(screen.getByText("contract.pdf")).toBeInTheDocument();
    const uploadBtn = screen.getByRole("button", { name: /start ingestion/i });
    fireEvent.click(uploadBtn);

    await waitFor(() => {
      expect(api.uploadEvidence).toHaveBeenCalledWith(
        "case_123",
        validFile,
        expect.any(Function)
      );
      expect(onUploadSuccess).toHaveBeenCalledWith(mockResponse);
    });
  });

  it("displays duplicate notice when backend returns is_duplicate: true", async () => {
    const mockDuplicate = {
      evidence_id: "evi_dup",
      case_id: "case_123",
      original_filename: "duplicate.pdf",
      media_type: "application/pdf",
      file_size_bytes: 2048,
      sha256_hash: "b".repeat(64),
      status: "READY" as const,
      is_duplicate: true,
      created_at: new Date().toISOString(),
    };

    (api.uploadEvidence as any).mockResolvedValue(mockDuplicate);

    render(<EvidenceUploader caseId="case_123" onUploadSuccess={() => {}} />);

    const validFile = new File(["pdf binary"], "duplicate.pdf", {
      type: "application/pdf",
    });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [validFile] } });

    fireEvent.click(screen.getByRole("button", { name: /start ingestion/i }));

    await waitFor(() => {
      expect(screen.getByText(/An identical file \(duplicate.pdf\) already exists/i)).toBeInTheDocument();
    });
  });
});
