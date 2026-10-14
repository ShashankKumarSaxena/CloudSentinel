export type Provider = 'aws' | 'azure' | 'gcp';
export type Severity = 'critical' | 'high' | 'medium' | 'low';
export type Status = 'open' | 'acknowledged' | 'resolved';
export type ResourceType = 'storage' | 'identity' | 'firewall' | 'audit';
export interface Resource {
  id: string; name: string; provider: Provider; type: ResourceType;
  region: string; account: string; config: Record<string, unknown>;
}
export interface Finding {
  id: string; rule_id: string; title: string; severity: Severity;
  category: string; resource_id: string; resource_name: string;
  resource_type: ResourceType; provider: Provider; region: string;
  account: string; description: string; remediation: string;
  evidence: Record<string, unknown>; status: Status; updated_at: string | null;
  detection_method: 'rule' | 'ml';
}
export interface Summary {
  resources: number; total_checks: number; passed: number; failed: number;
  unknown: number; posture_score: number | null;
  anomalies?: number; findings?: number;
}
export interface ScanRecord {
  id: string; created_at: string; source: 'demo' | 'import' | 'live'; phase: number;
  name: string; duration_ms: number; summary: Summary;
}
export interface Check {
  rule_id: string; resource_id: string; provider: Provider;
  outcome: 'pass' | 'fail' | 'unknown'; evidence: Record<string, unknown>;
}
export interface Scan extends ScanRecord {
  resources: Resource[]; findings: Finding[]; checks: Check[];
  activity: { event_count: number; windows: ActivityWindow[]; model: ModelStatus | null };
  collection: { provider: Provider; account: string; read_only: boolean; partial: boolean; coverage: Coverage[] } | null;
}
export interface Coverage { scope: string; status: string; message?: string }
export interface ActivityWindow {
  id: string; provider: Provider; account: string; principal: string; window_start: string;
  features: Record<string, number | null>; actions: string[];
  status: 'normal' | 'anomaly' | 'insufficient_data'; score: number | null; threshold: number;
  signals: { feature: string; value: number; baseline_deviation: number }[]; missing_features: string[];
}
export interface ModelMetrics { precision: number; recall: number; f1: number; false_positive_rate: number; true_positive: number; false_positive: number; true_negative: number; false_negative: number; roc_auc: number | null }
export interface ModelStatus {
  ready?: boolean; id: string; algorithm: string; type: string; feature_version: string; features: string[];
  created_at: string; dataset: string; provenance: 'synthetic' | 'user_labeled'; threshold: number;
  training_samples: number; calibration_samples: number; evaluation_samples: number;
  evaluation: { model: ModelMetrics; activity_baseline: ModelMetrics; scenarios: Record<string, { samples: number; flagged: number; actual_anomalies: number }> };
  notice: string;
}
export interface Connector { provider: Provider; credential_source: string; configured: boolean; scope: string; requires: string }
export interface Rule {
  id: string; title: string; severity: Severity; category: string;
  type: ResourceType; description: string; remediation: string; fields: string[];
}
export interface TriageEvent { previous_status: Status; status: Status; created_at: string }
export interface AuthUser { id: string; username: string; display_name: string; role: 'admin' | 'analyst' | 'viewer'; enabled: boolean; created_at: string }
export interface AuthSession { user: AuthUser; csrf_token: string; expires_at: string }
export interface AlertRecord { id: string; created_at: string; kind: string; severity: Severity; title: string; source: string; scan_id: string | null; finding_id: string | null; detail: Record<string, unknown>; acknowledged_at: string | null; acknowledged_by: string | null; delivery: string; attempts: number; delivery_error: string | null }
export interface AlertInbox { items: AlertRecord[]; total: number; unread: number }
export interface MonitorSchedule { id: string; name: string; kind: 'demo' | 'live'; collection: { provider: Provider; region: string; account: string | null; lookback_hours: number } | null; interval_seconds: number; enabled: boolean; next_run: string; last_run: string | null; last_status: string; last_error: string | null; failures: number }
export interface MonitorRun { id: string; schedule_id: string; started_at: string; finished_at: string | null; status: string; scan_id: string | null; error: string | null }
export interface WorkerStatus { enabled: boolean; running: boolean; last_tick: string | null; last_error: string | null; email_enabled: boolean; schedules: number; unread_alerts: number }
export interface AuditRecord { id: number; created_at: string; actor: string; action: string; target: string; detail: Record<string, unknown> }

let csrfToken = '';
export function setSessionToken(token: string) { csrfToken = token; }

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...options, credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...(csrfToken && options?.method && options.method !== 'GET' ? { 'X-CSRF-Token': csrfToken } : {}), ...options?.headers },
      signal: options?.signal ?? AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error('Could not reach the local API. Make sure the backend is running on port 8000, then try again.');
  }
  if (!response.ok) {
    if (response.status === 401 && csrfToken && path !== '/auth/login') {
      setSessionToken(''); window.dispatchEvent(new Event('cloudsentinel-session-expired'));
    }
    const body = await response.json().catch(() => ({}));
    const fields = body.errors?.map((e: {field: string; message: string}) => `${e.field}: ${e.message}`).slice(0, 3).join(' · ');
    throw new Error(`${typeof body.detail === 'string' ? body.detail : 'The request could not be completed.'}${fields ? ` ${fields}` : ''}`);
  }
  return response.json();
}

export async function downloadReport() {
  const report = await request<unknown>('/export');
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url; link.download = 'cloudsentinel-report.json'; link.click();
  URL.revokeObjectURL(url);
}
