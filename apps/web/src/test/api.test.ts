import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { api, ApiError } from "@/lib/api";

describe("ProofFlow API Client", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("attaches dev identity header in non-production", async () => {
    const mockResponse = {
      success: true,
      data: {
        status: "healthy",
        database: "connected",
        service: "ProofFlow API",
        version: "0.1.0",
        timestamp: new Date().toISOString(),
      },
    };

    let capturedHeaders: Headers | undefined;

    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      capturedHeaders = init?.headers as Headers;
      return Promise.resolve({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: () => Promise.resolve(mockResponse),
      });
    });

    const result = await api.getHealth();

    expect(result.status).toBe("healthy");
    expect(capturedHeaders?.get("X-User-ID")).toBe("dev_user_default");
  });

  it("correctly unwraps APIResponse envelope", async () => {
    const mockCaseList = {
      success: true,
      data: {
        items: [
          {
            case_id: "case_123",
            user_id: "dev_user_default",
            title: "Test Breach Case",
            description: "Test description",
            status: "READY",
            tags: ["test"],
            evidence_count: 1,
            metadata: {},
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ],
        pagination: { page: 1, limit: 20, total: 1, pages: 1 },
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () => Promise.resolve(mockCaseList),
    });

    const response = await api.listCases();
    expect(response.items).toHaveLength(1);
    expect(response.items[0].case_id).toBe("case_123");
    expect(response.pagination.total).toBe(1);
  });

  it("throws ApiError when response is not ok", async () => {
    const errorBody = {
      success: false,
      error: {
        code: "CASE_NOT_FOUND",
        message: "Case 'case_999' was not found",
        details: [],
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: new Headers({ "content-type": "application/json" }),
      json: () => Promise.resolve(errorBody),
    });

    await expect(api.getCase("case_999")).rejects.toThrow(ApiError);
    await expect(api.getCase("case_999")).rejects.toMatchObject({
      status: 404,
      message: "Case 'case_999' was not found",
      code: "CASE_NOT_FOUND",
    });
  });

  it("formats query parameters properly for filtering", async () => {
    let capturedUrl = "";

    global.fetch = vi.fn().mockImplementation((url: string) => {
      capturedUrl = url;
      return Promise.resolve({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: () => Promise.resolve({ success: true, data: { items: [], pagination: { page: 1, limit: 10, total: 0, pages: 0 } } }),
      });
    });

    await api.listCaseEvents("case_123", {
      decision_state: "VALIDATED",
      event_type: "PAYMENT_SENT",
      page: 2,
      limit: 10,
    });

    expect(capturedUrl).toContain("/api/v1/cases/case_123/events?");
    expect(capturedUrl).toContain("decision_state=VALIDATED");
    expect(capturedUrl).toContain("event_type=PAYMENT_SENT");
    expect(capturedUrl).toContain("page=2");
    expect(capturedUrl).toContain("limit=10");
  });

  it("attaches Authorization Bearer token when token getter is registered", async () => {
    const { registerAuthTokenGetter } = await import("@/lib/api");
    registerAuthTokenGetter(async () => "mock_clerk_session_jwt_xyz");

    let capturedHeaders: Headers | undefined;
    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      capturedHeaders = init?.headers as Headers;
      return Promise.resolve({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: () =>
          Promise.resolve({
            success: true,
            data: { items: [], pagination: { page: 1, limit: 10, total: 0, pages: 0 } },
          }),
      });
    });

    await api.listCases();
    expect(capturedHeaders?.get("Authorization")).toBe("Bearer mock_clerk_session_jwt_xyz");

    // Clean up
    registerAuthTokenGetter(null);
  });

  it("handles token getter rejection gracefully without crashing request", async () => {
    const { registerAuthTokenGetter } = await import("@/lib/api");
    registerAuthTokenGetter(async () => {
      throw new Error("Clerk session expired");
    });

    let capturedHeaders: Headers | undefined;
    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      capturedHeaders = init?.headers as Headers;
      return Promise.resolve({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: () =>
          Promise.resolve({
            success: true,
            data: { items: [], pagination: { page: 1, limit: 10, total: 0, pages: 0 } },
          }),
      });
    });

    await api.listCases();
    expect(capturedHeaders?.get("Authorization")).toBeNull();

    // Clean up
    registerAuthTokenGetter(null);
  });
});
