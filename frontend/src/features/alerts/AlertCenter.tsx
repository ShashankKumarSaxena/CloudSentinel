import { Bell, CheckCircle2, CircleAlert, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { AlertInbox, AlertRecord } from '../../shared/api/client';
import { request } from '../../shared/api/client';
import { dateTime, Drawer, EmptyState, SeverityBadge } from '../../shared/ui/components';
import { useAuth } from '../auth/AuthProvider';

function ErrorNotice({ message }: { message: string }) {
  return message ? (
    <div className="error-banner" role="alert">
      <CircleAlert size={18} />
      <p>{message}</p>
    </div>
  ) : null;
}

export function AlertCenter() {
  const { canMutate, canManage } = useAuth();
  const [inbox, setInbox] = useState<AlertInbox | null>(null);
  const [selected, setSelected] = useState<AlertRecord | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  async function load() {
    try {
      setInbox(await request<AlertInbox>(`/alerts?offset=${offset}`));
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [offset]);
  async function retry(alert: AlertRecord) {
    setBusy(true);
    setError('');
    try {
      await request(`/alerts/${alert.id}/retry`, { method: 'POST' });
      setSelected(null);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function acknowledge(alert: AlertRecord) {
    setBusy(true);
    setError('');
    try {
      await request(`/alerts/${alert.id}/acknowledge`, { method: 'POST' });
      setSelected(null);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const items = (inbox?.items ?? []).filter(
    (a) =>
      (!unreadOnly || !a.acknowledged_at) &&
      `${a.title} ${a.source} ${a.severity}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      <div className="section-intro">
        <h2>{inbox?.unread ?? 0} alerts awaiting review</h2>
        <button className="button secondary small" onClick={() => void load()}>
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>
      <ErrorNotice message={error} />
      <div className="ml-notice">
        <Bell size={20} />
        <div>
          <strong>A durable inbox for security changes</strong>
          <p>
            Findings, monitoring failures, and incomplete collection are recorded here. Repeated
            findings are deduplicated. Email delivery is optional and configured on the server.
          </p>
        </div>
      </div>
      <section className="panel">
        <div className="filter-toolbar">
          <label className="search-control">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search alerts, sources, or severity…"
              aria-label="Search alerts"
            />
          </label>
          <label className="check-control">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
            />
            Awaiting review only
          </label>
        </div>
        {items.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Alert</th>
                  <th>Severity</th>
                  <th>Source</th>
                  <th>Delivery</th>
                  <th>Review</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <button className="finding-link" onClick={() => setSelected(a)}>
                        <span className="resource-symbol">
                          <Bell size={17} />
                        </span>
                        <span>
                          <strong>{a.title}</strong>
                          <small>{a.kind.replaceAll('_', ' ')}</small>
                        </span>
                      </button>
                    </td>
                    <td>
                      <SeverityBadge severity={a.severity} />
                    </td>
                    <td>{a.source}</td>
                    <td className="capitalize">{a.delivery.replaceAll('_', ' ')}</td>
                    <td>
                      <span className={`check-status ${a.acknowledged_at ? 'pass' : 'unknown'}`}>
                        {a.acknowledged_at ? 'Reviewed' : 'Awaiting review'}
                      </span>
                    </td>
                    <td>{dateTime(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No alerts match this view"
            detail="Run a scan to populate the alert inbox, or clear your filters."
          />
        )}
      </section>
      <div className="pagination-row">
        <span>
          {inbox?.total ?? 0} alerts · page {Math.floor(offset / 200) + 1}
        </span>
        <div className="inline-actions">
          <button
            className="button secondary small"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 200))}
          >
            Previous
          </button>
          <button
            className="button secondary small"
            disabled={offset + 200 >= (inbox?.total ?? 0)}
            onClick={() => setOffset(offset + 200)}
          >
            Next
          </button>
        </div>
      </div>
      <p className="page-footnote">
        Alerts are paginated in groups of 200. Acknowledging an alert records review; it does not
        resolve a finding or verify remediation. Delivery retries are persistent and visible.
      </p>
      {selected && (
        <Drawer title={selected.title} onClose={() => setSelected(null)}>
          <div className="drawer-badges">
            <SeverityBadge severity={selected.severity} />
            <span className="subtle-tag">{selected.source}</span>
          </div>
          <div className="detail-card">
            <dl>
              <dt>Created</dt>
              <dd>{dateTime(selected.created_at)}</dd>
              <dt>Review</dt>
              <dd>
                {selected.acknowledged_at
                  ? `Reviewed by ${selected.acknowledged_by}`
                  : 'Awaiting review'}
              </dd>
              <dt>Delivery</dt>
              <dd>
                {selected.delivery.replaceAll('_', ' ')} · {selected.attempts} attempts
              </dd>
              <dt>Scan</dt>
              <dd className="mono">{selected.scan_id ?? 'Monitoring event'}</dd>
            </dl>
          </div>
          <h3 className="drawer-section-title">Alert evidence</h3>
          <pre className="evidence">{JSON.stringify(selected.detail, null, 2)}</pre>
          {selected.delivery_error && <p className="drawer-help">{selected.delivery_error}</p>}
          {canManage && selected.delivery === 'failed' && (
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => void retry(selected)}
            >
              <RefreshCw size={16} />
              Retry email delivery
            </button>
          )}
          {canMutate && !selected.acknowledged_at && (
            <button
              className="button primary"
              disabled={busy}
              onClick={() => void acknowledge(selected)}
            >
              <CheckCircle2 size={16} />
              {busy ? 'Saving…' : 'Mark as reviewed'}
            </button>
          )}
        </Drawer>
      )}
    </>
  );
}
