import { Activity, ArrowRight, CheckCircle2, CircleAlert } from 'lucide-react';
import { useState } from 'react';
import type { ActivityWindow, Scan } from '../../shared/api/client';
import {
  dateTime,
  Drawer,
  EmptyState,
  ProviderMark,
  providerNames,
  providerShort,
} from '../../shared/ui/components';

export function ActivityAnalysis({ scan }: { scan: Scan }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [selected, setSelected] = useState<ActivityWindow | null>(null);
  const windows = scan.activity.windows;
  const filtered = windows.filter(
    (w) =>
      (status === 'all' || w.status === status) &&
      `${w.principal} ${w.provider} ${w.account}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      {scan.analysis && !scan.analysis.ml_enabled && (
        <div className="ml-notice">
          <CircleAlert size={20} />
          <p>{scan.analysis.notice}</p>
        </div>
      )}
      <div className="feature-metrics">
        {[
          ['Normalized events', scan.activity.event_count],
          ['Hourly windows', windows.length],
          ['ML anomalies', windows.filter((w) => w.status === 'anomaly').length],
          ['Insufficient data', windows.filter((w) => w.status === 'insufficient_data').length],
        ].map(([label, value]) => (
          <div className="metric-card" key={label}>
            <span className="metric-note">{label}</span>
            <strong className="metric-value">{value}</strong>
          </div>
        ))}
      </div>
      <div className="ml-notice">
        <Activity size={20} />
        <div>
          <strong>
            {scan.activity.model
              ? `${scan.activity.model.algorithm} · ${scan.activity.model.id}`
              : 'No activity model in this historical scan'}
          </strong>
          <p>
            {scan.activity.model?.provenance === 'synthetic'
              ? 'This model was trained on synthetic normal activity. Scores are experimental review signals, not attack probabilities.'
              : 'Scores measure unusual behavior relative to the model baseline. Review alerts with supporting audit events.'}
          </p>
        </div>
      </div>
      <section className="panel">
        <div className="filter-toolbar">
          <label className="search-control">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search principals, clouds, or accounts…"
              aria-label="Search activity windows"
            />
          </label>
          <label className="select-control">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              aria-label="Filter activity outcome"
            >
              <option value="all">All outcomes</option>
              <option value="anomaly">Anomalies</option>
              <option value="normal">Normal</option>
              <option value="insufficient_data">Insufficient data</option>
            </select>
          </label>
        </div>
        {filtered.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Principal / account</th>
                  <th>Cloud</th>
                  <th>Window (local time)</th>
                  <th>Events</th>
                  <th>Model score</th>
                  <th>Outcome</th>
                  <th>
                    <span className="sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((w) => (
                  <tr key={w.id}>
                    <td>
                      <button className="finding-link" onClick={() => setSelected(w)}>
                        <span className="resource-symbol">
                          <Activity size={17} />
                        </span>
                        <span>
                          <strong>{w.principal}</strong>
                          <small>{w.account}</small>
                        </span>
                      </button>
                    </td>
                    <td>
                      <span className="cloud-label">
                        <ProviderMark provider={w.provider} small />
                        {providerShort[w.provider]}
                      </span>
                    </td>
                    <td>{dateTime(w.window_start)}</td>
                    <td>{w.features.event_count}</td>
                    <td>{w.score === null ? '—' : w.score.toFixed(3)}</td>
                    <td>
                      <span
                        className={`check-status ${
                          w.status === 'normal'
                            ? 'pass'
                            : w.status === 'anomaly'
                            ? 'fail'
                            : 'unknown'
                        }`}
                      >
                        {w.status === 'normal' ? (
                          <CheckCircle2 size={15} />
                        ) : (
                          <CircleAlert size={15} />
                        )}
                        {w.status.replaceAll('_', ' ')}
                      </span>
                    </td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`Inspect activity for ${w.principal}`}
                        onClick={() => setSelected(w)}
                      >
                        <ArrowRight size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title={
              windows.length ? 'No activity matches your filters' : 'No activity in this snapshot'
            }
            detail="Run the activity demo or import an inventory with normalized events. Configuration-only snapshots remain supported."
          />
        )}
      </section>
      <p className="page-footnote">
        Events are grouped by cloud, account, principal, and UTC hour. At least five events and
        complete features are required for scoring. Off-hours mean 22:00–05:59 UTC and are not
        automatically malicious.
      </p>
      {selected && (
        <Drawer title="Activity window" onClose={() => setSelected(null)}>
          <div className="drawer-badges">
            <span className="cloud-label">
              <ProviderMark provider={selected.provider} small />
              {providerNames[selected.provider]}
            </span>
            <span className="subtle-tag">{selected.status.replaceAll('_', ' ')}</span>
          </div>
          <div className="detail-card">
            <dl>
              <dt>Principal</dt>
              <dd>{selected.principal}</dd>
              <dt>Account</dt>
              <dd>{selected.account}</dd>
              <dt>UTC window</dt>
              <dd>{selected.window_start}</dd>
              <dt>Model score</dt>
              <dd>{selected.score?.toFixed(6) ?? 'Not scored'}</dd>
              <dt>Threshold</dt>
              <dd>{selected.threshold.toFixed(6)}</dd>
            </dl>
          </div>
          <h3 className="drawer-section-title">Feature evidence</h3>
          <pre className="evidence">{JSON.stringify(selected.features, null, 2)}</pre>
          {selected.missing_features.length > 0 && (
            <p className="drawer-help">
              Missing: {selected.missing_features.join(', ')}. Missing values are never treated as
              safe.
            </p>
          )}
          <h3 className="drawer-section-title">Deviation signals</h3>
          <p className="drawer-help">
            These compare features with the training baseline; they are review aids, not causal
            explanations of the model.
          </p>
          <div className="check-list">
            {selected.signals.map((s) => (
              <div key={s.feature}>
                <span>
                  <strong>{s.feature.replaceAll('_', ' ')}</strong>
                  <small>Observed value: {s.value}</small>
                </span>
                <span>{s.baseline_deviation.toFixed(2)}× baseline width</span>
              </div>
            ))}
          </div>
          <h3 className="drawer-section-title">Observed operations</h3>
          <pre className="evidence">{selected.actions.join('\n')}</pre>
        </Drawer>
      )}
    </>
  );
}
