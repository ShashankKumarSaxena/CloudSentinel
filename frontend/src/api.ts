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

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...options,
      headers: { 'Content-Type': 'application/json', ...options?.headers },
      signal: options?.signal ?? AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error('Could not reach the local API. Make sure the backend is running on port 8000, then try again.');
  }
  if (!response.ok) {
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
