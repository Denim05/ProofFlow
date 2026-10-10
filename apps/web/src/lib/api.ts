/**
 * ProofFlow API Client
 * Connects Next.js frontend to the FastAPI backend.
 * Uses NEXT_PUBLIC_API_URL and attaches a Clerk session token as an
 * Authorization Bearer header. Protected requests are never sent without a
 * token unless the explicit development identity opt-in is enabled.
 */

import {
  APIResponse,
  CaseCreateRequest,
  CaseListResponse,
  CaseResponse,
  CaseStatus,
  EventListResponse,
  EvidenceListResponse,
  EvidenceResponse,
  EvidenceStatus,
  EvidenceUploadResponse,
  FindingListResponse,
  FindingResponse,
  FindingReviewCreateRequest,
  FindingReviewHistoryResponse,
  FindingReviewListResponse,
  FindingReviewResponse,
  DossierResponse,
  HealthStatus,
} from "@/types/api";

export class ApiError extends Error {
  public status: number;
  public code?: string;
  public details?: Array<{ field?: string | null; issue: string }>;

  constructor(
    message: string,
    status: number,
    code?: string,
    details?: Array<{ field?: string | null; issue: string }>
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || "http://localhost:8000";

const DEV_USER_ID =
  process.env.NEXT_PUBLIC_DEV_USER_ID || "dev_user_default";

/** Maximum time a request waits for Clerk to finish initializing. */
export const AUTH_READY_TIMEOUT_MS = 5000;

/**
 * Development identity injection is explicit opt-in only and never available
 * in production builds. It must mirror backend ALLOW_DEV_AUTH_BYPASS=true.
 */
function isDevIdentityEnabled(): boolean {
  return (
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true"
  );
}

export type TokenGetter = () => Promise<string | null>;

let activeTokenGetter: TokenGetter | null = null;

export function registerAuthTokenGetter(getter: TokenGetter | null): void {
  activeTokenGetter = getter;
}

/** Clears the active getter only if it is still the one supplied (prevents stale cleanup races). */
export function clearAuthTokenGetter(getter: TokenGetter): void {
  if (activeTokenGetter === getter) {
    activeTokenGetter = null;
  }
}

// ---------------------------------------------------------------------------
// Auth readiness gate
// "idle": no auth bridge mounted (e.g. unit tests) -> no waiting.
// "pending": Clerk is initializing -> requests wait (bounded) for readiness.
// "ready": Clerk has loaded -> requests read the token immediately.
// ---------------------------------------------------------------------------
type AuthReadyState = "idle" | "pending" | "ready";

let authReadyState: AuthReadyState = "idle";
let authReadyPromise: Promise<void> | null = null;
let resolveAuthReady: (() => void) | null = null;

export function markAuthPending(): void {
  if (authReadyState === "pending") return;
  authReadyState = "pending";
  authReadyPromise = new Promise<void>((resolve) => {
    resolveAuthReady = resolve;
  });
}

export function markAuthReady(): void {
  authReadyState = "ready";
  const resolve = resolveAuthReady;
  resolveAuthReady = null;
  authReadyPromise = null;
  resolve?.();
}

/** Test helper: restores the initial auth state. */
export function resetAuthStateForTests(): void {
  const resolve = resolveAuthReady;
  activeTokenGetter = null;
  authReadyState = "idle";
  authReadyPromise = null;
  resolveAuthReady = null;
  resolve?.();
}

async function waitForAuthReady(): Promise<void> {
  if (authReadyState !== "pending" || !authReadyPromise) return;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<void>((resolve) => {
    timer = setTimeout(resolve, AUTH_READY_TIMEOUT_MS);
  });
  try {
    await Promise.race([authReadyPromise, timeout]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

export async function getAuthToken(): Promise<string | null> {
  await waitForAuthReady();
  const getter = activeTokenGetter;
  if (!getter) return null;
  try {
    const token = await getter();
    return typeof token === "string" && token.trim() ? token : null;
  } catch {
    return null;
  }
}

/**
 * Resolves authentication headers for a protected request.
 * Throws ApiError(401) locally, without contacting the backend, when no
 * session token is available and dev identity is not explicitly enabled.
 */
async function resolveAuthHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  if (isDevIdentityEnabled()) {
    return { "X-User-ID": DEV_USER_ID };
  }
  throw new ApiError(
    "Authentication required: no active session token. Please sign in again.",
    401,
    "AUTH_REQUIRED"
  );
}

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>;
  /** Public endpoints (e.g. health) skip authentication entirely. */
  skipAuth?: boolean;
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers, skipAuth, ...restOptions } = options;

  let url = `${API_BASE_URL}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      url += `?${queryString}`;
    }
  }

  const requestHeaders = new Headers(headers);

  // Protected API requests require a Clerk session token (or explicit dev opt-in)
  const isApiRequest = url.startsWith(API_BASE_URL);
  if (isApiRequest && !skipAuth && !requestHeaders.has("Authorization")) {
    const authHeaders = await resolveAuthHeaders();
    Object.entries(authHeaders).forEach(([key, value]) => requestHeaders.set(key, value));
  }

  // Set Accept header
  if (!requestHeaders.has("Accept")) {
    requestHeaders.set("Accept", "application/json");
  }

  const response = await fetch(url, {
    ...restOptions,
    headers: requestHeaders,
  });

  let responseData: any;
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    responseData = await response.json();
  } else {
    responseData = await response.text();
  }

  if (!response.ok) {
    const errorPayload = responseData?.error;
    const message =
      errorPayload?.message ||
      (typeof responseData === "string" ? responseData : response.statusText) ||
      "API request failed";
    throw new ApiError(
      message,
      response.status,
      errorPayload?.code,
      errorPayload?.details
    );
  }

  // Backend envelopes data in APIResponse { success, data, error, timestamp }
  if (responseData && typeof responseData === "object" && "success" in responseData) {
    const apiEnvelope = responseData as APIResponse<T>;
    if (!apiEnvelope.success && apiEnvelope.error) {
      throw new ApiError(
        apiEnvelope.error.message,
        response.status,
        apiEnvelope.error.code,
        apiEnvelope.error.details
      );
    }
    return apiEnvelope.data as T;
  }

  return responseData as T;
}

async function requestBlob(endpoint: string, options: RequestOptions = {}): Promise<Blob> {
  const { params, headers, skipAuth, ...restOptions } = options;

  let url = `${API_BASE_URL}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      url += `?${queryString}`;
    }
  }

  const requestHeaders = new Headers(headers);

  const isApiRequest = url.startsWith(API_BASE_URL);
  if (isApiRequest && !skipAuth && !requestHeaders.has("Authorization")) {
    const authHeaders = await resolveAuthHeaders();
    Object.entries(authHeaders).forEach(([key, value]) => requestHeaders.set(key, value));
  }

  const response = await fetch(url, {
    ...restOptions,
    headers: requestHeaders,
  });

  if (!response.ok) {
    let msg = response.statusText || "Failed to download file";
    try {
      const errJson = await response.json();
      if (errJson?.error?.message) msg = errJson.error.message;
    } catch {
      // non-JSON response fallback
    }
    throw new ApiError(msg, response.status);
  }

  return response.blob();
}

export const api = {
  // System Health
  async getHealth(): Promise<HealthStatus> {
    return request<HealthStatus>("/health", { skipAuth: true });
  },

  async getDbHealth(): Promise<HealthStatus> {
    return request<HealthStatus>("/health/db", { skipAuth: true });
  },

  // Case Management
  async listCases(params?: {
    page?: number;
    limit?: number;
    status?: CaseStatus;
  }): Promise<CaseListResponse> {
    return request<CaseListResponse>("/api/v1/cases", { params });
  },

  async getCase(caseId: string): Promise<CaseResponse> {
    return request<CaseResponse>(`/api/v1/cases/${caseId}`);
  },

  async createCase(payload: CaseCreateRequest): Promise<CaseResponse> {
    return request<CaseResponse>("/api/v1/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  // Evidence Management
  async uploadEvidence(
    caseId: string,
    file: File,
    onProgress?: (percentage: number) => void
  ): Promise<EvidenceUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);

    const url = `${API_BASE_URL}/api/v1/cases/${caseId}/evidence`;

    // If onProgress is supplied and XMLHttpRequest is available in browser
    if (onProgress && typeof XMLHttpRequest !== "undefined") {
      const authHeaders = await resolveAuthHeaders();
      return new Promise<EvidenceUploadResponse>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", url);

        Object.entries(authHeaders).forEach(([key, value]) =>
          xhr.setRequestHeader(key, value)
        );
        xhr.setRequestHeader("Accept", "application/json");

        xhr.upload.onprogress = (evt) => {
          if (evt.lengthComputable) {
            const pct = Math.round((evt.loaded / evt.total) * 100);
            onProgress(pct);
          }
        };

        xhr.onload = () => {
          try {
            const data = JSON.parse(xhr.responseText);
            if (xhr.status >= 200 && xhr.status < 300) {
              if (data && typeof data === "object" && "data" in data) {
                resolve(data.data as EvidenceUploadResponse);
              } else {
                resolve(data as EvidenceUploadResponse);
              }
            } else {
              const errPayload = data?.error;
              reject(
                new ApiError(
                  errPayload?.message || xhr.statusText || "Upload failed",
                  xhr.status,
                  errPayload?.code,
                  errPayload?.details
                )
              );
            }
          } catch {
            reject(new ApiError(xhr.statusText || "Upload failed", xhr.status));
          }
        };

        xhr.onerror = () => {
          reject(new ApiError("Network error during file upload", 0));
        };

        xhr.send(formData);
      });
    }

    return request<EvidenceUploadResponse>(`/api/v1/cases/${caseId}/evidence`, {
      method: "POST",
      body: formData,
    });
  },

  async listEvidence(
    caseId: string,
    params?: {
      page?: number;
      limit?: number;
      status?: EvidenceStatus;
    }
  ): Promise<EvidenceListResponse> {
    return request<EvidenceListResponse>(`/api/v1/cases/${caseId}/evidence`, {
      params,
    });
  },

  async getEvidence(
    caseId: string,
    evidenceId: string
  ): Promise<EvidenceResponse> {
    return request<EvidenceResponse>(
      `/api/v1/cases/${caseId}/evidence/${evidenceId}`
    );
  },

  async retryEvidence(
    caseId: string,
    evidenceId: string
  ): Promise<EvidenceResponse> {
    return request<EvidenceResponse>(
      `/api/v1/cases/${caseId}/evidence/${evidenceId}/retry`,
      {
        method: "POST",
      }
    );
  },

  // Event & Timeline Management
  async listCaseEvents(
    caseId: string,
    params?: {
      evidence_id?: string;
      decision_state?: string;
      event_type?: string;
      page?: number;
      limit?: number;
    }
  ): Promise<EventListResponse> {
    return request<EventListResponse>(`/api/v1/cases/${caseId}/events`, {
      params,
    });
  },

  async listEvidenceEvents(
    caseId: string,
    evidenceId: string,
    params?: {
      decision_state?: string;
      event_type?: string;
      page?: number;
      limit?: number;
    }
  ): Promise<EventListResponse> {
    return request<EventListResponse>(
      `/api/v1/cases/${caseId}/evidence/${evidenceId}/events`,
      { params }
    );
  },

  // Findings & Cross-Evidence Analysis
  async getCaseFindings(caseId: string): Promise<FindingListResponse> {
    return request<FindingListResponse>(`/api/v1/cases/${caseId}/findings`);
  },

  // Finding Reviews & Human-in-the-Loop Adjudication
  async recordFindingReview(
    caseId: string,
    findingId: string,
    payload: FindingReviewCreateRequest
  ): Promise<FindingReviewResponse> {
    return request<FindingReviewResponse>(
      `/api/v1/cases/${caseId}/findings/${findingId}/review`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    );
  },

  async getFindingReviews(
    caseId: string,
    findingId: string
  ): Promise<FindingReviewHistoryResponse> {
    return request<FindingReviewHistoryResponse>(
      `/api/v1/cases/${caseId}/findings/${findingId}/reviews`
    );
  },

  async listCaseReviews(caseId: string): Promise<FindingReviewListResponse> {
    return request<FindingReviewListResponse>(`/api/v1/cases/${caseId}/reviews`);
  },

  // Dispute Dossier Exports
  async exportCaseJson(caseId: string): Promise<DossierResponse> {
    return request<DossierResponse>(`/api/v1/cases/${caseId}/export/json`);
  },

  async exportCasePdf(caseId: string): Promise<Blob> {
    return requestBlob(`/api/v1/cases/${caseId}/export/pdf`);
  },
};
