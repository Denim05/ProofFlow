/**
 * ProofFlow API Client
 * Connects Next.js frontend to the FastAPI backend.
 * Uses NEXT_PUBLIC_API_URL and attaches X-User-ID for local development.
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

export type TokenGetter = () => Promise<string | null>;

let activeTokenGetter: TokenGetter | null = null;

export function registerAuthTokenGetter(getter: TokenGetter | null): void {
  activeTokenGetter = getter;
}

export async function getAuthToken(): Promise<string | null> {
  if (activeTokenGetter) {
    try {
      return await activeTokenGetter();
    } catch {
      return null;
    }
  }
  return null;
}

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>;
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers, ...restOptions } = options;

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

  // Attach bearer token if authenticated session is present and targeting API
  const isApiRequest = url.startsWith(API_BASE_URL);
  if (isApiRequest && !requestHeaders.has("Authorization")) {
    const token = await getAuthToken();
    if (token) {
      requestHeaders.set("Authorization", `Bearer ${token}`);
    } else if (process.env.NODE_ENV !== "production") {
      // In development, pass dev identity header accepted by backend dev bypass
      if (!requestHeaders.has("X-User-ID")) {
        requestHeaders.set("X-User-ID", DEV_USER_ID);
      }
    }
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

export const api = {
  // System Health
  async getHealth(): Promise<HealthStatus> {
    return request<HealthStatus>("/health");
  },

  async getDbHealth(): Promise<HealthStatus> {
    return request<HealthStatus>("/health/db");
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
      const token = await getAuthToken();
      return new Promise<EvidenceUploadResponse>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", url);

        if (token) {
          xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        } else if (process.env.NODE_ENV !== "production") {
          xhr.setRequestHeader("X-User-ID", DEV_USER_ID);
        }
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
};
