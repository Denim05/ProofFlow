import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { EvidenceGraph3D } from "@/components/EvidenceGraph3D";
import { EvidenceResponse, EventResponse } from "@/types/api";

const mockEvidenceList: EvidenceResponse[] = [
  {
    evidence_id: "doc-1",
    case_id: "case-100",
    original_filename: "contracts.pdf",
    stored_filename: "stored-contracts.pdf",
    media_type: "application/pdf",
    file_size_bytes: 1048576,
    sha256_hash: "abcd1234abcd",
    status: "READY",
    extracted_text: "Agreement text...",
    created_at: "2026-10-12T00:00:00Z",
    updated_at: "2026-10-12T00:00:00Z",
  },
  {
    evidence_id: "doc-2",
    case_id: "case-100",
    original_filename: "invoice.pdf",
    stored_filename: "stored-invoice.pdf",
    media_type: "application/pdf",
    file_size_bytes: 524288,
    sha256_hash: "efgh5678efgh",
    status: "READY",
    extracted_text: "Invoice details...",
    created_at: "2026-10-12T00:00:00Z",
    updated_at: "2026-10-12T00:00:00Z",
  },
];

const mockEvents: EventResponse[] = [
  {
    event_id: "evt-1",
    case_id: "case-100",
    evidence_id: "doc-1",
    event_type: "CONTRACT_SIGNED",
    trigger_raw_text: "Contract officially executed",
    decision_state: "VALIDATED",
    temporal_information: "2026-05-01",
    created_at: "2026-10-12T00:00:00Z",
  },
  {
    event_id: "evt-2",
    case_id: "case-100",
    evidence_id: "doc-2",
    event_type: "PAYMENT_INITIATED",
    trigger_raw_text: "Disputed payment discrepancy",
    decision_state: "REVIEW_NEEDED",
    temporal_information: "2026-05-02",
    created_at: "2026-10-12T00:00:00Z",
  },
];

describe("EvidenceGraph3D Component", () => {
  let rAfSpy: any;
  let cAfSpy: any;

  beforeEach(() => {
    let frameId = 0;
    rAfSpy = vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      frameId += 1;
      return frameId;
    });
    cAfSpy = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});

    // Mock HTMLCanvasElement.getContext
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
      setTransform: vi.fn(),
      scale: vi.fn(),
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
      setLineDash: vi.fn(),
      createRadialGradient: vi.fn().mockReturnValue({
        addColorStop: vi.fn(),
      }),
      fillText: vi.fn(),
    }) as any;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders without error or maximum-update-depth exceeded", () => {
    const { container } = render(
      <EvidenceGraph3D
        caseTitle="Operation Vanguard"
        evidenceList={mockEvidenceList}
        events={mockEvents}
      />
    );

    expect(screen.getByText("3D EVIDENCE TOPOLOGY MATRIX")).toBeInTheDocument();
    expect(screen.getByText("ALL")).toBeInTheDocument();
    expect(screen.getByText("DOCS_ONLY")).toBeInTheDocument();
    expect(screen.getByText("CHRONO")).toBeInTheDocument();
    expect(container.querySelector("canvas")).toBeInTheDocument();
  });

  it("renders empty state guide when no evidence documents exist", () => {
    render(
      <EvidenceGraph3D
        caseTitle="Empty Case"
        evidenceList={[]}
        events={[]}
      />
    );

    expect(screen.getByText("Topology Awaiting Ingestion")).toBeInTheDocument();
    expect(
      screen.getByText(/Upload documentary evidence to generate automated 3D relational nodes/i)
    ).toBeInTheDocument();
  });

  it("handles zoom and reset controls correctly", () => {
    render(
      <EvidenceGraph3D
        caseTitle="Operation Vanguard"
        evidenceList={mockEvidenceList}
        events={mockEvents}
      />
    );

    const zoomInBtn = screen.getByRole("button", { name: "Zoom In" });
    const zoomOutBtn = screen.getByRole("button", { name: "Zoom Out" });
    const resetBtn = screen.getByRole("button", { name: "Reset View Orientation" });

    fireEvent.click(zoomInBtn);
    fireEvent.click(zoomOutBtn);
    fireEvent.click(resetBtn);

    expect(zoomInBtn).toBeInTheDocument();
    expect(zoomOutBtn).toBeInTheDocument();
    expect(resetBtn).toBeInTheDocument();
  });

  it("allows switching view modes without crashing", () => {
    render(
      <EvidenceGraph3D
        caseTitle="Operation Vanguard"
        evidenceList={mockEvidenceList}
        events={mockEvents}
      />
    );

    const docsOnlyBtn = screen.getByText("DOCS_ONLY");
    fireEvent.click(docsOnlyBtn);
    expect(docsOnlyBtn).toHaveClass("text-cyan-300");

    const chronoBtn = screen.getByText("CHRONO");
    fireEvent.click(chronoBtn);
    expect(chronoBtn).toHaveClass("text-cyan-300");
  });

  it("handles mouse interactions and cleans up on unmount", () => {
    const { container, unmount } = render(
      <EvidenceGraph3D
        caseTitle="Operation Vanguard"
        evidenceList={mockEvidenceList}
        events={mockEvents}
      />
    );

    const canvasContainer = container.querySelector(".cursor-grab");
    expect(canvasContainer).toBeInTheDocument();

    if (canvasContainer) {
      fireEvent.mouseDown(canvasContainer, { clientX: 100, clientY: 100, button: 0 });
      fireEvent.mouseMove(canvasContainer, { clientX: 120, clientY: 110 });
      fireEvent.mouseUp(canvasContainer);
      fireEvent.mouseLeave(canvasContainer);
      fireEvent.click(canvasContainer);
    }

    unmount();
    expect(cAfSpy).toHaveBeenCalled();
  });
});
