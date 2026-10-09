import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { CaseCard } from "@/components/CaseCard";
import { CaseResponse } from "@/types/api";

const mockCase: CaseResponse = {
  case_id: "case_abc123",
  user_id: "dev_user_default",
  title: "Breach of SLA — Service X",
  description: "Investigation into missed contract milestones.",
  status: "READY",
  tags: ["sla", "vendor", "dispute"],
  evidence_count: 3,
  metadata: {},
  created_at: "2026-03-15T10:00:00Z",
  updated_at: "2026-03-15T12:00:00Z",
};

describe("CaseCard", () => {
  it("renders case title, description, and status", () => {
    render(<CaseCard caseItem={mockCase} />);
    expect(screen.getByText("Breach of SLA — Service X")).toBeInTheDocument();
    expect(
      screen.getByText("Investigation into missed contract milestones.")
    ).toBeInTheDocument();
    expect(screen.getByText("READY")).toBeInTheDocument();
  });

  it("renders tags correctly", () => {
    render(<CaseCard caseItem={mockCase} />);
    expect(screen.getByText("sla")).toBeInTheDocument();
    expect(screen.getByText("vendor")).toBeInTheDocument();
    expect(screen.getByText("dispute")).toBeInTheDocument();
  });

  it("renders evidence document count and navigation link", () => {
    render(<CaseCard caseItem={mockCase} />);
    expect(screen.getByText("3 documents")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /view case/i });
    expect(link).toHaveAttribute("href", "/cases/case_abc123");
  });
});
