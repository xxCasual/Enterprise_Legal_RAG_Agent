import type {
  AdminSessionResponse,
  ChatResponse,
  ContractReview,
  DocumentListResponse,
  DocumentRecord,
  HealthResponse,
  PendingReviewListResponse,
  ReadyResponse,
  ReviewDecision,
  ReviewDecisionResponse
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers
  });
  const text = await response.text();
  const payload = text ? safeParseJson(text) : {};

  if (!response.ok) {
    const detail = getErrorDetail(payload, response.statusText);
    throw new Error(detail);
  }

  return payload as T;
}

function safeParseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function getErrorDetail(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    const detail = record.detail ?? record.error;
    if (typeof detail === "string") return detail;
    if (detail !== undefined) return JSON.stringify(detail);
  }
  return fallback;
}

export function checkHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/api/health");
}

export function checkReady(): Promise<ReadyResponse> {
  return requestJson<ReadyResponse>("/api/ready");
}

export function checkAdminSession(): Promise<AdminSessionResponse> {
  return requestJson<AdminSessionResponse>("/api/admin/me");
}

export function loginAdmin(token: string): Promise<AdminSessionResponse> {
  return requestJson<AdminSessionResponse>("/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token })
  });
}

export function logoutAdmin(): Promise<AdminSessionResponse> {
  return requestJson<AdminSessionResponse>("/api/admin/logout", {
    method: "POST"
  });
}

export function sendChat(query: string): Promise<ChatResponse> {
  return requestJson<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query })
  });
}

export function reviewContract(
  contractText: string,
  includeEvidence = false
): Promise<ContractReview> {
  return requestJson<ContractReview>("/api/review/contract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contract_text: contractText, include_evidence: includeEvidence })
  });
}

export async function uploadDocument(file: File): Promise<DocumentRecord> {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson<DocumentRecord>("/api/documents/upload", {
    method: "POST",
    body: formData
  });
}

export function listDocuments(): Promise<DocumentListResponse> {
  return requestJson<DocumentListResponse>("/api/documents");
}

export function listPendingReviews(): Promise<PendingReviewListResponse> {
  return requestJson<PendingReviewListResponse>("/api/reviews/pending");
}

export function decideReview(
  reviewId: string,
  decision: ReviewDecision
): Promise<ReviewDecisionResponse> {
  return requestJson<ReviewDecisionResponse>(
    `/api/reviews/${encodeURIComponent(reviewId)}/${decision}`,
    { method: "POST" }
  );
}
