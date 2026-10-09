import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatusBadge } from "@/components/StatusBadge";

describe("StatusBadge", () => {
  it("renders READY status with emerald styling", () => {
    render(<StatusBadge status="READY" />);
    const badge = screen.getByText("READY");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("bg-emerald-50");
  });

  it("renders PROCESSING status with pulse animation", () => {
    render(<StatusBadge status="PROCESSING" />);
    const badge = screen.getByText("PROCESSING");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("animate-pulse");
  });

  it("renders REVIEW_NEEDED with formatted space", () => {
    render(<StatusBadge status="REVIEW_NEEDED" />);
    const badge = screen.getByText("REVIEW NEEDED");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("bg-amber-50");
  });

  it("renders ML processing modes appropriately", () => {
    render(<StatusBadge status="DETERMINISTIC_FALLBACK" />);
    const badge = screen.getByText("DETERMINISTIC FALLBACK");
    expect(badge).toBeInTheDocument();
  });
});
