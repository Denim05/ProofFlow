import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  api,
  ApiError,
  AUTH_READY_TIMEOUT_MS,
  clearAuthTokenGetter,
  markAuthPending,
  markAuthReady,
  registerAuthTokenGetter,
  resetAuthStateForTests,
} from "@/lib/api";

const TEST_TOKEN = "mock_clerk_session_jwt_xyz";

const emptyPage = {
  success: true,
  data: { items: [], pagination: { page: 1, limit: 10, total: 0, pages: 0 } },
};

function mockFetchCapturing(body: unknown = emptyPage) {
  const calls: Array<{ url: string; headers: Headers }> = [];
  const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    calls.push({ url, headers: init?.headers as Headers });
    return Promise.resolve({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () => Promise.resolve(body),
    });
  });
  global.fetch = fn as unknown as typeof fetch;
  return { fn, calls };
}

describe("ProofFlow API Client", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    resetAuthStateForTests();
    // Default: a signed-in Clerk session is available.
    registerAuthTokenGetter(async () => TEST_TOKEN);
  });

  afterEach(() => {
    global.fetch = originalFetch;
    resetAuthStateForTests();
    vi.unstubAllEnvs();
    vi.useRealTimers();
  });

  it("does not attach any identity to public health requests", async () => {
    resetAuthStateForTests(); // no session at all
    const { calls } = mockFetchCapturing({
      success: true,
      data: {
        status: "healthy",
        database: "connected",
        service: "ProofFlow API",
        version: "0.1.0",
        timestamp: new Date().toISOString(),
      },
    });

    const result = await api.getHealth();

    expect(result.status).toBe("healthy");
    expect(calls[0].headers.get("Authorization")).toBeNull();
    expect(calls[0].headers.get("X-User-ID")).toBeNull();
  });

  it("attaches dev identity header only with explicit non-production opt-in", async () => {
    resetAuthStateForTests(); // no session token
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH_BYPASS", "true");
    const { calls } = mockFetchCapturing();

    await api.listCases();

    expect(calls[0].headers.get("X-User-ID")).toBe("dev_user_default");
    expect(calls[0].headers.get("Authorization")).toBeNull();
  });

  it("never uses dev identity in production even if opt-in is set", async () => {
    resetAuthStateForTests();
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_DEV_AUTH_BYPASS", "true");
    const { fn } = mockFetchCapturing();

    await expect(api.listCases()).rejects.toMatchObject({ status: 401, code: "AUTH_REQUIRED" });
    expect(fn).not.toHaveBeenCalled();
  });

  it("correctly unwraps APIResponse envelope", async () => {
    const mockCaseList = {
      success: true,
      data: {
        items: [
          {
            case_id: "case_123",
            user_id: "user_abc",
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
    mockFetchCapturing(mockCaseList);

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
    const { calls } = mockFetchCapturing();

    await api.listCaseEvents("case_123", {
      decision_state: "VALIDATED",
      event_type: "PAYMENT_SENT",
      page: 2,
      limit: 10,
    });

    const capturedUrl = calls[0].url;
    expect(capturedUrl).toContain("/api/v1/cases/case_123/events?");
    expect(capturedUrl).toContain("decision_state=VALIDATED");
    expect(capturedUrl).toContain("event_type=PAYMENT_SENT");
    expect(capturedUrl).toContain("page=2");
    expect(capturedUrl).toContain("limit=10");
  });

  it("attaches Authorization Bearer token when token getter is registered", async () => {
    const { calls } = mockFetchCapturing();

    await api.listCases();

    expect(calls[0].headers.get("Authorization")).toBe(`Bearer ${TEST_TOKEN}`);
    expect(calls[0].headers.get("X-User-ID")).toBeNull();
  });

  it("requests a fresh token from the getter for every protected request", async () => {
    let n = 0;
    registerAuthTokenGetter(async () => `token_${++n}`);
    const { calls } = mockFetchCapturing();

    await api.listCases();
    await api.listCases();

    expect(calls[0].headers.get("Authorization")).toBe("Bearer token_1");
    expect(calls[1].headers.get("Authorization")).toBe("Bearer token_2");
  });

  it("refuses protected requests locally when the token getter rejects", async () => {
    registerAuthTokenGetter(async () => {
      throw new Error("Clerk session expired");
    });
    const { fn } = mockFetchCapturing();

    await expect(api.listCases()).rejects.toMatchObject({ status: 401, code: "AUTH_REQUIRED" });
    expect(fn).not.toHaveBeenCalled();
  });

  it("treats an empty token as missing and refuses the request", async () => {
    registerAuthTokenGetter(async () => "   ");
    const { fn } = mockFetchCapturing();

    await expect(api.listCases()).rejects.toMatchObject({ status: 401, code: "AUTH_REQUIRED" });
    expect(fn).not.toHaveBeenCalled();
  });

  it("refuses protected requests for signed-out users after Clerk is ready", async () => {
    resetAuthStateForTests();
    markAuthPending();
    registerAuthTokenGetter(null);
    markAuthReady();
    const { fn } = mockFetchCapturing();

    await expect(api.listCases()).rejects.toMatchObject({ status: 401, code: "AUTH_REQUIRED" });
    expect(fn).not.toHaveBeenCalled();
  });

  it("waits for Clerk initialization before sending a protected request", async () => {
    resetAuthStateForTests();
    markAuthPending();
    const { fn, calls } = mockFetchCapturing();

    const pending = api.listCases();
    await Promise.resolve();
    await Promise.resolve();
    expect(fn).not.toHaveBeenCalled();

    registerAuthTokenGetter(async () => TEST_TOKEN);
    markAuthReady();
    await pending;

    expect(fn).toHaveBeenCalledTimes(1);
    expect(calls[0].headers.get("Authorization")).toBe(`Bearer ${TEST_TOKEN}`);
  });

  it("refuses the request without sending it when Clerk readiness times out", async () => {
    vi.useFakeTimers();
    resetAuthStateForTests();
    markAuthPending();
    const { fn } = mockFetchCapturing();

    const pending = api.listCases();
    const assertion = expect(pending).rejects.toMatchObject({ status: 401, code: "AUTH_REQUIRED" });

    await vi.advanceTimersByTimeAsync(AUTH_READY_TIMEOUT_MS - 1);
    expect(fn).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);

    await assertion;
    expect(fn).not.toHaveBeenCalled();
  });

  it("does not let a stale cleanup clear a newer token getter", async () => {
    const stale = async () => "stale_token";
    const fresh = async () => "fresh_token";
    registerAuthTokenGetter(stale);
    registerAuthTokenGetter(fresh);
    clearAuthTokenGetter(stale);
    const { calls } = mockFetchCapturing();

    await api.listCases();

    expect(calls[0].headers.get("Authorization")).toBe("Bearer fresh_token");
  });

  it("refuses XHR evidence uploads without a token before opening a connection", async () => {
    resetAuthStateForTests();
    const xhrCtor = vi.fn();
    vi.stubGlobal("XMLHttpRequest", xhrCtor);
    const file = new File(["%PDF-1.4"], "a.pdf", { type: "application/pdf" });

    await expect(api.uploadEvidence("case_1", file, () => {})).rejects.toMatchObject({
      status: 401,
      code: "AUTH_REQUIRED",
    });
    expect(xhrCtor).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("submits finding adjudication review with correct payload and method", async () => {
    const mockReview = {
      success: true,
      data: {
        review_id: "rev_123",
        case_id: "case_1",
        finding_id: "fnd_abc",
        reviewer_id: "user_reviewer",
        decision: "RESOLVED",
        reason: "Supplier credit verified",
        version: 1,
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    };
    const { calls } = mockFetchCapturing(mockReview);

    const result = await api.recordFindingReview("case_1", "fnd_abc", {
      decision: "RESOLVED",
      reason: "Supplier credit verified",
    });

    expect(result.review_id).toBe("rev_123");
    expect(result.decision).toBe("RESOLVED");
    expect(calls[0].url).toContain("/api/v1/cases/case_1/findings/fnd_abc/review");
  });

  it("retrieves finding review history and case reviews", async () => {
    const mockHistory = {
      success: true,
      data: {
        items: [
          {
            review_id: "rev_1",
            case_id: "case_1",
            finding_id: "fnd_abc",
            reviewer_id: "user_reviewer",
            decision: "CONFIRMED_INCONSISTENCY",
            version: 1,
            is_active: true,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ],
        total: 1,
        finding_id: "fnd_abc",
        case_id: "case_1",
      },
    };
    const { calls } = mockFetchCapturing(mockHistory);

    const history = await api.getFindingReviews("case_1", "fnd_abc");
    expect(history.items).toHaveLength(1);
    expect(calls[0].url).toContain("/api/v1/cases/case_1/findings/fnd_abc/reviews");

    const caseReviews = await api.listCaseReviews("case_1");
    expect(caseReviews.items).toBeDefined();
  });

  it("exports case dispute dossier as JSON", async () => {
    const mockDossier = {
      report_version: "1.0.0",
      generated_at: new Date().toISOString(),
      manifest_hash: "abc123hash",
      case: { case_id: "case_1", title: "Test Case" },
      executive_summary: "Test summary",
      document_inventory: [],
      events_timeline: [],
      findings: [],
      human_reviews: [],
      evidence_gaps: [],
      methodology: { system_name: "ProofFlow" },
    };
    const { calls } = mockFetchCapturing(mockDossier);

    const dossier = await api.exportCaseJson("case_1");
    expect(dossier.report_version).toBe("1.0.0");
    expect(dossier.manifest_hash).toBe("abc123hash");
    expect(calls[0].url).toContain("/api/v1/cases/case_1/export/json");
  });

  it("exports case dispute dossier as PDF blob", async () => {
    const mockBlob = new Blob(["%PDF-1.4 test data"], { type: "application/pdf" });
    const calls: Array<{ url: string; headers: Headers }> = [];
    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      calls.push({ url, headers: init?.headers as Headers });
      return Promise.resolve({
        ok: true,
        headers: new Headers({ "content-type": "application/pdf" }),
        blob: () => Promise.resolve(mockBlob),
      });
    });

    const blob = await api.exportCasePdf("case_1");
    expect(blob).toBeDefined();
    expect(blob.type).toBe("application/pdf");
    expect(calls[0].url).toContain("/api/v1/cases/case_1/export/pdf");
  });
});
