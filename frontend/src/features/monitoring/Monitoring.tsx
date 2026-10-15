import { CircleAlert, Clock3, LoaderCircle, Pause, Play, Plus, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import type {
  MonitorRun,
  MonitorSchedule,
  Provider,
  Scan,
  WorkerStatus,
} from '../../shared/api/client';
import { request } from '../../shared/api/client';
import type { ApprovedAccount } from '../../shared/api/types';
import { dateTime, EmptyState } from '../../shared/ui/components';
import { useAuth } from '../auth/AuthProvider';

function ErrorNotice({ message }: { message: string }) {
  return message ? (
    <div className="error-banner" role="alert">
      <CircleAlert size={18} />
      <p>{message}</p>
    </div>
  ) : null;
}

export function Monitoring({ onScanned }: { onScanned: (scan: Scan) => Promise<void> }) {
  const { canManage, mode } = useAuth();
  const [schedules, setSchedules] = useState<MonitorSchedule[]>([]);
  const [runs, setRuns] = useState<MonitorRun[]>([]);
  const [worker, setWorker] = useState<WorkerStatus | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [kind, setKind] = useState<'demo' | 'live'>(mode === 'production' ? 'live' : 'demo');
  const [accounts, setAccounts] = useState<ApprovedAccount[]>([]);
  const [connectionId, setConnectionId] = useState('');
  const [provider, setProvider] = useState<Provider>('aws');
  const [account, setAccount] = useState('');
  const [region, setRegion] = useState('ap-south-1');
  const [interval, setInterval] = useState(3600);
  const [enabled, setEnabled] = useState(true);
  async function load() {
    try {
      const [a, b, c] = await Promise.all([
        request<MonitorSchedule[]>('/schedules'),
        request<MonitorRun[]>('/monitor/runs'),
        request<WorkerStatus>('/operations'),
      ]);
      setSchedules(a);
      setRuns(b);
      setWorker(c);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    request<ApprovedAccount[]>('/cloud/accounts')
      .then(setAccounts)
      .catch((error) => setError(error.message));
    if (mode === 'production') setKind('live');
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);
  async function create() {
    if (kind === 'live' && !connectionId) {
      setError('Select an approved cloud account.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await request('/schedules', {
        method: 'POST',
        body: JSON.stringify({
          name,
          kind,
          interval_seconds: interval,
          enabled,
          collection:
            kind === 'live'
              ? {
                  provider,
                  region,
                  account: account || null,
                  connection_id: connectionId || null,
                  lookback_hours: 24,
                }
              : null,
        }),
      });
      setAdding(false);
      setName('');
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function toggle(s: MonitorSchedule) {
    setBusy(true);
    setError('');
    try {
      await request(`/schedules/${s.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled: !s.enabled }),
      });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function run(s: MonitorSchedule) {
    setBusy(true);
    setError('');
    try {
      if (mode === 'production') {
        await request(`/schedules/${s.id}/run`, { method: 'POST' });
        await load();
        return;
      }
      const scan = await request<Scan>(`/schedules/${s.id}/run`, {
        method: 'POST',
        signal: AbortSignal.timeout(180000),
      });
      await onScanned(scan);
      await load();
    } catch (e) {
      await load();
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="section-intro">
        <h2>Continuous monitoring, on your terms</h2>
        <div className="heading-actions">
          <button className="button secondary small" onClick={() => void load()}>
            <RefreshCw size={14} />
            Refresh
          </button>
          {canManage && (
            <button className="button primary small" onClick={() => setAdding(!adding)}>
              <Plus size={14} />
              New schedule
            </button>
          )}
        </div>
      </div>
      <ErrorNotice message={error} />
      <div className="feature-metrics">
        {[
          ['Active schedules', schedules.filter((s) => s.enabled).length],
          ['Worker', worker?.running ? 'Running' : worker?.enabled ? 'Starting' : 'Disabled'],
          ['Awaiting review', worker?.unread_alerts ?? 0],
          ['Email delivery', worker?.email_enabled ? 'Configured' : 'Inbox only'],
        ].map(([label, value]) => (
          <div className="metric-card" key={label}>
            <span className="metric-note">{label}</span>
            <strong className="metric-value operational-value">{value}</strong>
          </div>
        ))}
      </div>
      {worker?.last_error && <ErrorNotice message={worker.last_error} />}
      {adding && canManage && (
        <section className="panel collection-form settings-form">
          <h2>Create a monitoring schedule</h2>
          <p>
            Schedules persist across restarts. Live schedules use local provider credentials;
            synthetic schedules run the bundled fixture.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void create();
            }}
          >
            <label>
              Schedule name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={100}
                placeholder="Daily storage review"
              />
            </label>
            <label>
              Data source
              <select value={kind} onChange={(e) => setKind(e.target.value as 'demo' | 'live')}>
                {mode === 'demo' && <option value="demo">Synthetic demo</option>}
                <option value="live">Live read-only cloud</option>
              </select>
            </label>
            <label>
              Interval
              <select value={interval} onChange={(e) => setInterval(Number(e.target.value))}>
                <option value={60}>Every minute</option>
                <option value={300}>Every 5 minutes</option>
                <option value={3600}>Every hour</option>
                <option value={86400}>Every day</option>
              </select>
            </label>
            {kind === 'live' && (
              <>
                <label>
                  Approved cloud account
                  <select
                    value={connectionId}
                    required
                    onChange={(event) => {
                      const selected = accounts.find(
                        (account) => account.id === event.target.value,
                      );
                      setConnectionId(event.target.value);
                      if (selected) {
                        setProvider(selected.provider);
                        setAccount(selected.account);
                        setRegion(selected.regions[0]);
                      }
                    }}
                  >
                    <option value="">Choose an approved connection</option>
                    {accounts
                      .filter((account) => account.enabled)
                      .map((account) => (
                        <option key={account.id} value={account.id}>
                          {account.name} · {account.account}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Approved region
                  <select value={region} onChange={(event) => setRegion(event.target.value)}>
                    {accounts
                      .find((account) => account.id === connectionId)
                      ?.regions.map((region) => (
                        <option key={region} value={region}>
                          {region}
                        </option>
                      ))}
                  </select>
                </label>
              </>
            )}
            <label className="check-control">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              Enable after creation
            </label>
            <button className="button primary" disabled={busy}>
              {busy ? <LoaderCircle className="spinning" size={15} /> : <Clock3 size={15} />}Save
              schedule
            </button>
          </form>
        </section>
      )}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Monitoring schedules</h2>
            <p>Single worker · UTC scheduling · persistent retries</p>
          </div>
        </div>
        {schedules.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Schedule</th>
                  <th>Interval</th>
                  <th>Next run</th>
                  <th>Last outcome</th>
                  <th>Status</th>
                  {canManage && <th>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {schedules.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <span className="resource-cell">
                        {s.name}
                        <small>
                          {s.kind === 'demo'
                            ? 'Synthetic fixture'
                            : `${s.collection?.provider.toUpperCase()} · ${
                                s.collection?.account ?? 'Local account'
                              }`}
                        </small>
                      </span>
                    </td>
                    <td>
                      {s.interval_seconds < 3600
                        ? `${s.interval_seconds / 60} min`
                        : `${s.interval_seconds / 3600} hr`}
                    </td>
                    <td>{s.enabled ? dateTime(s.next_run) : 'Paused'}</td>
                    <td className="capitalize">{s.last_status}</td>
                    <td>
                      <span className={`check-status ${s.enabled ? 'pass' : 'unknown'}`}>
                        {s.enabled ? 'Enabled' : 'Paused'}
                      </span>
                    </td>
                    {canManage && (
                      <td>
                        <div className="inline-actions">
                          <button
                            className="button secondary small"
                            disabled={busy || s.last_status === 'running'}
                            onClick={() => void toggle(s)}
                          >
                            {s.enabled ? <Pause size={12} /> : <Play size={12} />}
                            {s.enabled ? 'Pause' : 'Enable'}
                          </button>
                          <button
                            className="button secondary small"
                            disabled={
                              busy ||
                              s.last_status === 'running' ||
                              (mode === 'production' && !s.enabled)
                            }
                            title={
                              mode === 'production' && !s.enabled
                                ? 'Enable this schedule before requesting a run.'
                                : undefined
                            }
                            onClick={() => void run(s)}
                          >
                            Run now
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No schedules yet"
            detail="An administrator can create a synthetic or read-only cloud schedule. Nothing is collected automatically until a schedule is enabled."
          />
        )}
      </section>
      <section className="panel feature-panel">
        <div className="panel-heading">
          <div>
            <h2>Recent monitoring runs</h2>
            <p>Success, failure, and interrupted work are preserved</p>
          </div>
        </div>
        {runs.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Schedule</th>
                  <th>Started</th>
                  <th>Outcome</th>
                  <th>Scan / detail</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>
                      {schedules.find((s) => s.id === r.schedule_id)?.name ??
                        r.schedule_id.slice(0, 8)}
                    </td>
                    <td>{dateTime(r.started_at)}</td>
                    <td className="capitalize">{r.status}</td>
                    <td>{r.scan_id?.slice(0, 8) ?? r.error ?? 'In progress'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No scheduled runs recorded"
            detail="Run a schedule now or wait for its next scheduled time."
          />
        )}
      </section>
      <p className="page-footnote">
        Failure retries use increasing backoff. Pausing a running schedule is blocked until it
        finishes. Inbox findings are deduplicated; acknowledging an alert does not change scan
        evidence.
      </p>
    </>
  );
}
