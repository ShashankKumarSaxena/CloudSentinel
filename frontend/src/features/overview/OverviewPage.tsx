import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  Layers3,
  Shield,
  ShieldCheck,
} from 'lucide-react';
import type * as React from 'react';
import type { Page } from '../../app/navigation';
import type { Finding, Provider, Scan, Severity } from '../../shared/api/client';
import { providers, severities } from '../../shared/constants';
import { dateTime, EmptyState, ProviderMark, providerNames } from '../../shared/ui/components';
import { Donut, Metric } from '../../shared/ui/dashboard';

interface Props {
  scan: Scan;
  openFindings: Finding[];
  navigate: (next: Page) => void;
  setProvider: React.Dispatch<React.SetStateAction<Provider | 'all'>>;
  setSeverity: React.Dispatch<React.SetStateAction<'all' | Severity>>;
  findingTable: (items: Finding[], compact?: boolean) => React.ReactNode;
}

/** Render one workspace view; data loading and navigation stay in the app shell. */
export function OverviewPage({
  scan,
  openFindings,
  navigate,
  setProvider,
  setSeverity,
  findingTable,
}: Props) {
  return (
    <>
      <div className="section-intro">
        <h2>Security overview</h2>
        <span>
          <Clock3 size={14} />
          Last scan {dateTime(scan.created_at)}
        </span>
      </div>
      <div className="metric-grid">
        <Metric label="Open findings" value={openFindings.length} icon={Shield} tone="red">
          <span className="metric-note danger">
            <span />
            {openFindings.filter((f) => f.severity === 'critical').length} critical need attention
          </span>
        </Metric>
        <Metric label="Resources scanned" value={scan.summary.resources} icon={Layers3} tone="blue">
          <span className="metric-note">
            Across {new Set(scan.resources.map((r) => r.provider)).size} cloud providers
          </span>
        </Metric>
        <Metric
          label="Checks passed"
          value={`${scan.summary.passed}/${scan.summary.total_checks}`}
          icon={CheckCircle2}
          tone="green"
        >
          <span className="metric-note">
            {scan.summary.unknown
              ? `${scan.summary.unknown} checks need more data`
              : 'All configuration fields available'}
          </span>
        </Metric>
        <Metric
          label="Baseline posture"
          value={scan.summary.posture_score === null ? '—' : `${scan.summary.posture_score}%`}
          icon={Activity}
          tone="amber"
        >
          <span className="metric-note">Pass rate of evaluated checks</span>
        </Metric>
      </div>
      <button className="activity-overview-strip" onClick={() => navigate('activity')}>
        <span className="metric-icon green">
          <Activity size={20} />
        </span>
        <div>
          <strong>
            {scan.summary.anomalies ?? 0} activity anomalies · {scan.activity.event_count}{' '}
            normalized events
          </strong>
          <p>
            {scan.activity.model
              ? `${scan.activity.model.algorithm} · ${
                  scan.activity.model.provenance === 'synthetic'
                    ? 'Synthetic-trained model'
                    : 'Reviewed activity baseline'
                }`
              : 'This historical snapshot has no ML activity analysis'}
          </p>
        </div>
        <span>
          Review activity <ArrowRight size={16} />
        </span>
      </button>
      {scan.collection?.partial && (
        <div className="error-banner">
          <CircleAlert size={18} />
          <p>
            Partial cloud collection. Some scopes were unavailable or unsupported; these results do
            not represent a complete account review.
          </p>
        </div>
      )}
      <div className="overview-middle">
        <section className="panel provider-panel">
          <div className="panel-heading">
            <div>
              <h2>Your cloud landscape</h2>
              <p>Visibility across your configuration snapshot</p>
            </div>
            <span className="subtle-tag">
              {new Set(scan.resources.map((r) => r.provider)).size} providers
            </span>
          </div>
          <div className="provider-grid">
            {providers.map((p) => {
              const assets = scan.resources.filter((r) => r.provider === p);
              const findings = scan.findings.filter((f) => f.provider === p);
              return (
                <button
                  key={p}
                  className="provider-card"
                  onClick={() => {
                    navigate('inventory');
                    setProvider(p);
                  }}
                >
                  <div className="provider-card-top">
                    <ProviderMark provider={p} />
                    <ArrowUpRight size={17} />
                  </div>
                  <h3>{providerNames[p]}</h3>
                  <span className="snapshot-label">
                    <span />
                    {assets.length ? 'Snapshot available' : 'No resources'}
                  </span>
                  <div className="provider-card-stats">
                    <div>
                      <strong>{assets.length}</strong>
                      <small>Resources</small>
                    </div>
                    <div>
                      <strong className={findings.length ? 'text-danger' : ''}>
                        {findings.length}
                      </strong>
                      <small>Findings</small>
                    </div>
                  </div>
                  <div className="provider-card-footer">
                    {scan.source === 'live'
                      ? 'Live collected inventory'
                      : scan.source === 'demo'
                      ? 'Synthetic inventory'
                      : 'Imported inventory'}
                    <ChevronRight size={14} />
                  </div>
                </button>
              );
            })}
          </div>
        </section>
        <section className="panel severity-panel">
          <div className="panel-heading">
            <div>
              <h2>Severity breakdown</h2>
              <p>Detected in the latest scan</p>
            </div>
            <Shield size={18} />
          </div>
          <div className="severity-chart">
            <Donut findings={scan.findings} />
            <div className="severity-legend">
              {severities.map((s) => (
                <button
                  key={s}
                  onClick={() => {
                    navigate('findings');
                    setSeverity(s);
                  }}
                >
                  <span className={`legend-dot ${s}`} />
                  <span className="capitalize">{s}</span>
                  <strong>{scan.findings.filter((f) => f.severity === s).length}</strong>
                </button>
              ))}
            </div>
          </div>
          <div className="chart-note">
            <CircleAlert size={14} />
            Start with critical and high severity findings.
          </div>
        </section>
      </div>
      <section className="panel priority-panel">
        <div className="panel-heading">
          <div className="heading-inline">
            <h2>Priority findings</h2>
            <span className="count-pill">{openFindings.length} open</span>
          </div>
          <button className="text-button" onClick={() => navigate('findings')}>
            View all findings <ArrowRight size={16} />
          </button>
        </div>
        {openFindings.length ? (
          findingTable(openFindings.slice(0, 4), true)
        ) : (
          <EmptyState
            title="No open findings"
            detail="Review acknowledged and resolved findings, or run a new configuration scan."
          />
        )}
      </section>
      <div className="overview-footer">
        <span>
          <ShieldCheck size={16} />
          Read-only analysis. Your cloud infrastructure stays untouched.
        </span>
        <button onClick={() => navigate('brief')}>
          Built for multi-cloud security <ArrowUpRight size={14} />
        </button>
      </div>
    </>
  );
}
