/**
 * ProofFlow API TypeScript Types
 * Accurately mirrored from FastAPI Pydantic models & database enums.
 */

export type CaseStatus = "PROCESSING" | "READY" | "REVIEW_NEEDED" | "ARCHIVED";

export interface CaseCreateRequest {
  title: string;
  description?: string;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export interface CaseResponse {
  case_id: string;
  user_id: string;
  title: string;
  description: string;
  status: CaseStatus;
  tags: string[];
  evidence_count: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PaginationMeta {
  page: number;
  limit: number;
  total: number;
  pages: number;
}

export interface CaseListResponse {
  items: CaseResponse[];
  pagination: PaginationMeta;
}

export type EvidenceStatus =
  | "UPLOADED"
  | "QUEUED"
  | "EXTRACTING"
  | "STRUCTURING"
  | "ANALYZING"
  | "READY"
  | "REVIEW_NEEDED"
  | "FAILED"
  | "INTERRUPTED";

export type MLProcessingMode =
  | "NEURAL_DEBERTA_GPU"
  | "NEURAL_DEBERTA_CPU"
  | "DETERMINISTIC_FALLBACK"
  | "MODEL_UNAVAILABLE";

export interface EvidenceUploadResponse {
  evidence_id: string;
  case_id: string;
  original_filename: string;
  media_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  status: EvidenceStatus;
  is_duplicate: boolean;
  created_at: string;
}

export interface EvidenceResponse {
  evidence_id: string;
  case_id: string;
  original_filename: string;
  media_type: string;
  file_size_bytes: number;
  sha256_hash: string;
  status: EvidenceStatus;
  processing_mode: MLProcessingMode;
  processing_version: number;
  active_processing_version?: number | null;
  extraction_summary?: Record<string, unknown> | null;
  error_code?: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvidenceListResponse {
  items: EvidenceResponse[];
  pagination: PaginationMeta;
}

export interface EventResponse {
  event_id: string;
  case_id: string;
  evidence_id: string;
  processing_version: number;
  processing_run_id?: string | null;
  is_active: boolean;
  event_type: string;
  decision_state: string;
  review_reasons: string[];
  trigger_raw_text: string;
  char_start: number;
  char_end: number;
  page_number?: number | null;
  bounding_box?: number[] | null;
  actor?: string | null;
  amount_currency?: string | null;
  amount_value?: string | number | null;
  order_reference?: string | null;
  transaction_reference?: string | null;
  polarity: string;
  modality: string;
  tense: string;
  model_confidence: number;
  model_metadata: Record<string, unknown>;
  created_at: string;
}

export interface EventListResponse {
  items: EventResponse[];
  pagination: PaginationMeta;
}

export interface HealthStatus {
  status: "healthy" | "degraded";
  database: "connected" | "disconnected";
  service: string;
  version: string;
  timestamp: string;
}

export interface ErrorDetail {
  field?: string | null;
  issue: string;
}

export interface ErrorPayload {
  code: string;
  message: string;
  details: ErrorDetail[];
}

export interface APIResponse<T> {
  success: boolean;
  data?: T;
  error?: ErrorPayload;
  timestamp: string;
}

export interface EvidenceCitation {
  evidence_id: string;
  original_filename: string;
  page_number?: number | null;
  char_start?: number | null;
  char_end?: number | null;
  trigger_raw_text: string;
  event_id?: string | null;
}

export interface FieldDifference {
  field: string;
  value_a: string;
  source_a: string;
  value_b: string;
  source_b: string;
}

export interface FindingResponse {
  finding_id: string;
  case_id: string;
  finding_type: string;
  title: string;
  summary: string;
  severity: "LOW" | "MEDIUM" | "HIGH";
  conflict_state:
    | "DIRECT_CONTRADICTION"
    | "POTENTIAL_CONFLICT"
    | "CONTEXTUALLY_COMPATIBLE"
    | "INSUFFICIENT_CONTEXT";
  citations: EvidenceCitation[];
  field_diff?: FieldDifference | null;
  model_confidence: number;
  model_name: string;
  created_at: string;
}

export interface FindingListResponse {
  items: FindingResponse[];
  total: number;
  case_id: string;
}
