import { CheckCircle2, CircleAlert, Cloud, LoaderCircle, RefreshCw } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { request } from '../../shared/api/client';
import type { ApprovedAccount, CollectionJob, JobPage, Scan } from '../../shared/api/types';
import { dateTime, EmptyState, ProviderMark } from '../../shared/ui/components';
import { useAuth } from '../auth/AuthProvider';

/** Submit bounded jobs; the API never holds an HTTP request open for cloud I/O. */
export function CloudConnections({ onCollected }: { onCollected: (scan: Scan) => Promise<void> }) {
  const { canMutate, mode } = useAuth();
  const submission = useRef<{ payload: string; key: string } | null>(null);
  const [accounts, setAccounts] = useState<ApprovedAccount[]>([]);
  const [jobs, setJobs] = useState<JobPage>({ items: [], total: 0 });
  const [connectionId, setConnectionId] = useState('');
  const [region, setRegion] = useState('');
  const [hours, setHours] = useState(24);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [result, setResult] = useState<Scan | null>(null);
  const selected = accounts.find((account) => account.id === connectionId);

  async function refresh() {
    try {
      const [registry, page] = await Promise.all([
        request<ApprovedAccount[]>('/cloud/accounts'),
        request<JobPage>('/cloud/jobs'),
      ]);
      setAccounts(registry);
      setJobs(page);
    } catch (error) {
      setError((error as Error).message);
    }
  }
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh();
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  function select(account: ApprovedAccount) {
    setConnectionId(account.id);
    setRegion(account.regions[0]);
    setNotice('');
  }
  async function submit() {
    if (!selected || !region) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const payload = JSON.stringify({
        connection_id: selected.id,
        provider: selected.provider,
        account: selected.account,
        region,
        lookback_hours: hours,
      });
      // Preserve the key after a lost response so Retry cannot queue the same
      // request twice. A confirmed submission starts a new intentional attempt.
      if (submission.current?.payload !== payload)
        submission.current = { payload, key: crypto.randomUUID() };
      const job = await request<CollectionJob>('/cloud/jobs', {
        method: 'POST',
        headers: { 'Idempotency-Key': submission.current.key },
        body: payload,
      });
      submission.current = null;
      setNotice(
        `Collection queued · ${job.id.slice(0, 8)}. You can leave this page while the worker runs.`,
      );
      await refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function cancel(job: CollectionJob) {
    setBusy(true);
    setError('');
    try {
      await request(`/cloud/jobs/${job.id}/cancel`, { method: 'POST' });
      await refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function inspect(job: CollectionJob) {
    if (!job.scan_id) return;
    setBusy(true);
    setError('');
    try {
      const scan = await request<Scan>(`/scans/${job.scan_id}`);
      setResult(scan);
      await onCollected(scan);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="section-intro">
        <h2>Approved cloud accounts</h2>
        <button className="button secondary small" onClick={() => void refresh()}>
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>
      <div className="ml-notice">
        <Cloud size={21} />
        <div>
          <strong>Read-only access, explicitly scoped</strong>
          <p>
            Your administrator approves each account, credential method, and region. Cloud
            credentials stay in the worker. Collection jobs persist across service restarts.
          </p>
        </div>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          <CircleAlert size={18} />
          <p>{error}</p>
        </div>
      )}
      {notice && (
        <div className="ml-notice" role="status">
          <CheckCircle2 size={18} />
          <p>{notice}</p>
        </div>
      )}
      {accounts.length ? (
        <div className="connection-grid">
          {accounts.map((account) => (
            <button
              key={account.id}
              disabled={!account.enabled || busy}
              className={`connection-card panel ${connectionId === account.id ? 'selected' : ''}`}
              onClick={() => select(account)}
            >
              <ProviderMark provider={account.provider} />
              <h3>{account.name}</h3>
              <span className="subtle-tag">{account.enabled ? 'Approved' : 'Disabled'}</span>
              <p>{account.account}</p>
              <small>
                {account.regions.join(', ')} · {account.auth.replaceAll('_', ' ')}
              </small>
            </button>
          ))}
        </div>
      ) : (
        <section className="panel">
          <EmptyState
            title="No approved cloud connections yet"
            detail={
              mode === 'demo'
                ? 'This demo runs offline. Use Run demo scan to explore the workspace with synthetic data.'
                : 'Ask your administrator to register an account with read-only workload credentials. Cloud credentials are never entered on this page.'
            }
          />
        </section>
      )}
      {selected && (
        <section className="panel collection-form">
          <h2>Queue a collection</h2>
          <p>
            {selected.name} · {selected.account}
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <label>
              Approved region
              <select value={region} onChange={(event) => setRegion(event.target.value)}>
                {selected.regions.map((region) => (
                  <option key={region} value={region}>
                    {region}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Activity lookback
              <select value={hours} onChange={(event) => setHours(Number(event.target.value))}>
                <option value={6}>Last 6 hours</option>
                <option value={24}>Last 24 hours</option>
                <option value={72}>Last 3 days</option>
                <option value={168}>Last 7 days</option>
              </select>
            </label>
            <button className="button primary" disabled={busy || !canMutate || !selected.enabled}>
              {busy ? <LoaderCircle className="spinning" size={16} /> : <Cloud size={16} />}Queue
              read-only scan
            </button>
          </form>
        </section>
      )}
      <section className="panel feature-panel">
        <div className="panel-heading">
          <div>
            <h2>Collection jobs</h2>
            <p>{jobs.total} total · latest 100 · refreshes every 5 seconds</p>
          </div>
        </div>
        {jobs.items.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Account / region</th>
                  <th>Requested</th>
                  <th>Status</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {jobs.items.map((job) => (
                  <tr key={job.id}>
                    <td>
                      <span className="resource-cell">
                        {accounts.find((account) => account.id === job.request.connection_id)
                          ?.name ?? job.request.connection_id}
                        <small>
                          {job.request.region} · {job.created_by}
                        </small>
                      </span>
                    </td>
                    <td>{dateTime(job.created_at)}</td>
                    <td className="capitalize">{job.status}</td>
                    <td>
                      {job.scan_id ? (
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => void inspect(job)}
                        >
                          Inspect snapshot
                        </button>
                      ) : job.status === 'pending' && canMutate ? (
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => void cancel(job)}
                        >
                          Cancel
                        </button>
                      ) : (
                        job.error ?? 'Awaiting worker'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No collection jobs"
            detail="Choose an approved account to queue a scan. Your existing snapshots are preserved if a collection fails."
          />
        )}
      </section>
      {result?.collection && (
        <section className="panel feature-panel">
          <div className="panel-heading">
            <div>
              <h2>Collection coverage</h2>
              <p>
                {result.collection.partial
                  ? 'Partial collection — review unavailable scopes'
                  : 'Requested supported scopes collected'}{' '}
                · {result.resources.length} resources
              </p>
            </div>
          </div>
          <div className="coverage-list">
            {result.collection.coverage.map((coverage, index) => (
              <div key={index}>
                <span
                  className={`check-status ${coverage.status === 'collected' ? 'pass' : 'unknown'}`}
                >
                  {coverage.status}
                </span>
                <div>
                  <strong>{coverage.scope}</strong>
                  {coverage.message && <p>{coverage.message}</p>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      <p className="page-footnote">
        Each snapshot covers one approved account and region. Unknown or unavailable scopes are not
        a clean-account verdict. Use the account snapshot selector to review other accounts.
      </p>
    </>
  );
}
