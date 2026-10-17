const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8020";

const TOKEN_KEY = "aip_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Storage unavailable (private browsing, etc.) — the user will just be asked
    // to log in again; this is a per-viewer convenience, not a source of truth.
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      // response had no JSON body
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function apiPostForm<T>(path: string, formData: FormData): Promise<T> {
  return request<T>(path, { method: "POST", body: formData });
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export interface Engagement {
  id: string;
  name: string;
  client_name: string;
  status: string;
  created_at: string;
}

export interface ImportPreviewRow {
  row_number: number;
  mapped: Record<string, string | null>;
  errors: string[];
}

export interface ImportPreviewResponse {
  import_run_id: string;
  source_file_id: string;
  total_rows: number;
  valid_row_count: number;
  error_row_count: number;
  sample_rows: ImportPreviewRow[];
}

export interface AutoRunControlResult {
  control_code: string;
  status: "completed" | "skipped";
  finding_count: number | null;
  skip_reason: string | null;
}

export interface CommitImportResponse {
  dataset_version_id: string;
  version_number: number;
  row_count: number;
  auto_run_control_results: AutoRunControlResult[];
}

export interface ControlConfiguration {
  control_code: string;
  control_name: string;
  description: string;
  enabled: boolean;
  parameters: Record<string, unknown>;
  required_parameters_hint: string[];
  updated_at: string | null;
}

export interface ControlRun {
  id: string;
  status: string;
  finding_count: number;
  skipped_row_count: number;
  parameters: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
}

export interface Finding {
  id: string;
  severity: string;
  status: string;
  summary: string;
  evidence_record_ids: string[];
  created_at: string;
}

export interface TransactionRecordOut {
  id: string;
  source_row_number: number;
  supplier_name: string | null;
  invoice_reference: string | null;
  currency: string | null;
  amount: string | null;
  transaction_date: string | null;
}

export interface ObservedFact {
  text: string;
  evidence_ids: string[];
}

export interface Inference {
  text: string;
  basis_evidence_ids: string[];
  limitations: string;
}

export interface RecommendedNextStep {
  text: string;
  requires_human_approval: boolean;
}

export interface InvestigationResult {
  summary: string;
  observed_facts: ObservedFact[];
  inferences: Inference[];
  missing_checks: string[];
  recommended_next_steps: RecommendedNextStep[];
  uncertainties: string[];
}

export interface InvestigationRun {
  id: string;
  status: "pending" | "completed" | "failed";
  model_id: string;
  requested_at: string;
  completed_at: string | null;
  result: InvestigationResult | null;
  tool_call_log: { tool_name: string; result_summary: string; is_error: boolean }[];
  token_usage: { input_tokens?: number; output_tokens?: number };
  error_message: string | null;
}

export interface ReportDisposition {
  status: string;
  rationale: string;
  recorded_at: string;
  recorded_by: string | null;
}

export interface ReportFinding {
  id: string;
  severity: string;
  status: string;
  summary: string;
  evidence_record_ids: string[];
  created_at: string;
  control_code: string;
  control_version: number;
  dataset_version_number: number;
  disposition: ReportDisposition | null;
  latest_investigation: { id: string; model_id: string; completed_at: string | null; result: InvestigationResult | null } | null;
}

export interface ReportControlRun {
  id: string;
  control_code: string;
  control_name: string;
  control_version: number;
  parameters: Record<string, unknown>;
  dataset_version_number: number;
  finding_count: number;
  skipped_row_count: number;
  started_at: string;
  finished_at: string | null;
}

export interface ReportDatasetVersion {
  id: string;
  version_number: number;
  source_file_sha256: string;
  mapping_snapshot: Record<string, unknown>;
  committed_at: string;
}

export interface EngagementReport {
  engagement_id: string;
  engagement_name: string;
  client_name: string;
  generated_at: string;
  dataset_versions: ReportDatasetVersion[];
  control_runs: ReportControlRun[];
  findings: ReportFinding[];
  limitations: string[];
}

export interface FindingsByControl {
  control_code: string;
  control_name: string;
  finding_count: number;
}

export interface SupplierSummary {
  supplier_name: string;
  transaction_count: number;
  total_amount_by_currency: Record<string, string>;
  flagged_transaction_count: number;
}

export interface EngagementAnalytics {
  dataset_version_id: string | null;
  dataset_version_number: number | null;
  findings_by_severity: Record<string, number>;
  findings_by_status: Record<string, number>;
  findings_by_control: FindingsByControl[];
  supplier_summary: SupplierSummary[];
  supplier_risk_scores: SupplierRisk[];
}

export interface ExternalRecordBatch {
  id: string;
  source_label: string;
  version_number: number;
  committed_at: string;
}

export interface ExternalRecordOut {
  id: string;
  source_row_number: number;
  counterparty_name: string | null;
  reference: string | null;
  currency: string | null;
  amount: string | null;
  transaction_date: string | null;
}

export interface CommitExternalImportResponse {
  external_record_batch_id: string;
  version_number: number;
  row_count: number;
}

export interface ReconciliationRun {
  id: string;
  method: string;
  status: string;
  matched_count: number;
  unmatched_transaction_count: number;
  unmatched_external_count: number;
  parameters: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
}

export interface ReconciliationMatch {
  id: string;
  match_status: "matched" | "unmatched_transaction" | "unmatched_external";
  match_basis: string | null;
  transaction_record: TransactionRecordOut | null;
  external_record: ExternalRecordOut | null;
  created_at: string;
}

export interface SupplierRisk {
  supplier_name: string;
  risk_score: number;
  controls_hit: string[];
  total_finding_count: number;
  severity_breakdown: Record<string, number>;
}

export interface AuditEvent {
  id: string;
  event_type: string;
  actor_email: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}
