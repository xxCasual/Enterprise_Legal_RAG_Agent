export type RiskLevel = "low" | "medium" | "high";
export type ReviewStatus = "pending_review" | "approved" | "rejected";
export type ReviewDecision = "approve" | "reject";

export interface HealthResponse {
  status: string;
}

export interface ToolTrace {
  name: string;
  status: "ok" | "error" | string;
  latency: number;
  route?: string;
  result_type?: string;
  risk_level?: RiskLevel;
  review_status?: "not_required" | "pending_review";
  answer_source?: string;
  context_count?: number;
  error?: string;
  args?: Record<string, string>;
}

export interface ContractFinding {
  clause_type: string;
  clause_name: string;
  status: "present" | "missing" | "unclear" | string;
  risk_level: RiskLevel;
  extracted_text: string;
  analysis: string;
  evidence: string[];
  suggestion: string;
}

export interface ContractReview {
  risk_level: RiskLevel;
  findings: ContractFinding[];
  evidence: string[];
  suggestions: string[];
  disclaimer: string;
  latency: number;
  review_status: "not_required" | "pending_review";
  review_id: string | null;
}

export interface ChatResponse {
  answer: string;
  citations: string[];
  route: string;
  intent: string;
  intent_source: string;
  intent_confidence: number;
  tools_used: string[];
  tool_trace: ToolTrace[];
  result_type: string;
  risk_level: RiskLevel | null;
  review_status: "not_required" | "pending_review" | null;
  review_id: string | null;
  contract_review: ContractReview | null;
  latency: number;
}

export interface DocumentRecord {
  doc_id: string;
  file_name: string;
  source_type: string;
  chunk_count: number;
  created_at: string;
}

export interface DocumentListResponse {
  documents: DocumentRecord[];
}

export interface PendingReviewRecord {
  review_id: string;
  source_type: string;
  status: ReviewStatus;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PendingReviewListResponse {
  reviews: PendingReviewRecord[];
}

export interface ReviewDecisionResponse {
  review_id: string;
  status: ReviewStatus;
  final_answer: Record<string, unknown> | null;
  message: string;
}

export type LoadingKey =
  | "health"
  | "chat"
  | "documents"
  | "upload"
  | "contract"
  | "reviews"
  | "approval";
