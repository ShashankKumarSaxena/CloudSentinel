import { useEffect, useState } from 'react';
import { Bell, CheckCircle2, CircleAlert, Clock3, LoaderCircle, Pause, Play, Plus, RefreshCw, ShieldCheck } from 'lucide-react';
import { request } from './api';
import type { AlertInbox, AlertRecord, AuthUser, AuditRecord, MonitorRun, MonitorSchedule, Provider, Scan, WorkerStatus } from './api';
import { useAuth } from './Auth';
import { dateTime, Drawer, EmptyState, SeverityBadge } from './components';

function ErrorNotice({ message }: { message: string }) { return message ? <div className="error-banner" role="alert"><CircleAlert size={18} /><p>{message}</p></div> : null; }

export function AlertCenter() {
  const { canMutate, canManage } = useAuth();
  const [inbox, setInbox] = useState<AlertInbox | null>(null);
  const [selected, setSelected] = useState<AlertRecord | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  async function load() { try { setInbox(await request<AlertInbox>(`/alerts?offset=${offset}`)); setError(''); } catch (e) { setError((e as Error).message); } }
  useEffect(() => { void load(); const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void load(); }, 30000); return () => window.clearInterval(timer); }, [offset]);
  async function retry(alert: AlertRecord) {
    setBusy(true); setError('');
    try { await request(`/alerts/${alert.id}/retry`, { method: 'POST' }); setSelected(null); await load(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function acknowledge(alert: AlertRecord) {
    setBusy(true); setError('');
    try { await request(`/alerts/${alert.id}/acknowledge`, { method: 'POST' }); setSelected(null); await load(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const items = (inbox?.items ?? []).filter(a => (!unreadOnly || !a.acknowledged_at) && `${a.title} ${a.source} ${a.severity}`.toLowerCase().includes(query.toLowerCase()));
  return <><div className="section-intro"><h2>{inbox?.unread ?? 0} alerts awaiting review</h2><button className="button secondary small" onClick={() => void load()}><RefreshCw size={14} />Refresh</button></div><ErrorNotice message={error} /><div className="ml-notice"><Bell size={20} /><div><strong>A durable inbox for security changes</strong><p>Findings, monitoring failures, and incomplete collection are recorded here. Repeated findings are deduplicated. Email delivery is optional and configured on the server.</p></div></div><section className="panel"><div className="filter-toolbar"><label className="search-control"><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search alerts, sources, or severity…" aria-label="Search alerts" /></label><label className="check-control"><input type="checkbox" checked={unreadOnly} onChange={e => setUnreadOnly(e.target.checked)} />Awaiting review only</label></div>{items.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Alert</th><th>Severity</th><th>Source</th><th>Delivery</th><th>Review</th><th>Created</th></tr></thead><tbody>{items.map(a => <tr key={a.id}><td><button className="finding-link" onClick={() => setSelected(a)}><span className="resource-symbol"><Bell size={17} /></span><span><strong>{a.title}</strong><small>{a.kind.replaceAll('_', ' ')}</small></span></button></td><td><SeverityBadge severity={a.severity} /></td><td>{a.source}</td><td className="capitalize">{a.delivery.replaceAll('_', ' ')}</td><td><span className={`check-status ${a.acknowledged_at ? 'pass' : 'unknown'}`}>{a.acknowledged_at ? 'Reviewed' : 'Awaiting review'}</span></td><td>{dateTime(a.created_at)}</td></tr>)}</tbody></table></div> : <EmptyState title="No alerts match this view" detail="Run a scan to populate the alert inbox, or clear your filters." />}</section><div className="pagination-row"><span>{inbox?.total ?? 0} alerts · page {Math.floor(offset / 200) + 1}</span><div className="inline-actions"><button className="button secondary small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 200))}>Previous</button><button className="button secondary small" disabled={offset + 200 >= (inbox?.total ?? 0)} onClick={() => setOffset(offset + 200)}>Next</button></div></div><p className="page-footnote">Alerts are paginated in groups of 200. Acknowledging an alert records review; it does not resolve a finding or verify remediation. Delivery retries are persistent and visible.</p>{selected && <Drawer title={selected.title} onClose={() => setSelected(null)}><div className="drawer-badges"><SeverityBadge severity={selected.severity} /><span className="subtle-tag">{selected.source}</span></div><div className="detail-card"><dl><dt>Created</dt><dd>{dateTime(selected.created_at)}</dd><dt>Review</dt><dd>{selected.acknowledged_at ? `Reviewed by ${selected.acknowledged_by}` : 'Awaiting review'}</dd><dt>Delivery</dt><dd>{selected.delivery.replaceAll('_', ' ')} · {selected.attempts} attempts</dd><dt>Scan</dt><dd className="mono">{selected.scan_id ?? 'Monitoring event'}</dd></dl></div><h3 className="drawer-section-title">Alert evidence</h3><pre className="evidence">{JSON.stringify(selected.detail, null, 2)}</pre>{selected.delivery_error && <p className="drawer-help">{selected.delivery_error}</p>}{canManage && selected.delivery === 'failed' && <button className="button secondary" disabled={busy} onClick={() => void retry(selected)}><RefreshCw size={16} />Retry email delivery</button>}{canMutate && !selected.acknowledged_at && <button className="button primary" disabled={busy} onClick={() => void acknowledge(selected)}><CheckCircle2 size={16} />{busy ? 'Saving…' : 'Mark as reviewed'}</button>}</Drawer>}</>;
}

export function Monitoring({ onScanned }: { onScanned: (scan: Scan) => Promise<void> }) {
  const { canManage } = useAuth();
  const [schedules, setSchedules] = useState<MonitorSchedule[]>([]);
  const [runs, setRuns] = useState<MonitorRun[]>([]);
  const [worker, setWorker] = useState<WorkerStatus | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState('');
  const [kind, setKind] = useState<'demo' | 'live'>('demo');
  const [provider, setProvider] = useState<Provider>('aws');
  const [account, setAccount] = useState('');
  const [region, setRegion] = useState('ap-south-1');
  const [interval, setInterval] = useState(3600);
  const [enabled, setEnabled] = useState(true);
  async function load() {
    try { const [a, b, c] = await Promise.all([request<MonitorSchedule[]>('/schedules'), request<MonitorRun[]>('/monitor/runs'), request<WorkerStatus>('/operations')]); setSchedules(a); setRuns(b); setWorker(c); setError(''); }
    catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { void load(); const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void load(); }, 15000); return () => window.clearInterval(timer); }, []);
  async function create() {
    setBusy(true); setError('');
    try { await request('/schedules', { method: 'POST', body: JSON.stringify({ name, kind, interval_seconds: interval, enabled, collection: kind === 'live' ? { provider, region, account: account || null, lookback_hours: 24 } : null }) }); setAdding(false); setName(''); await load(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function toggle(s: MonitorSchedule) {
    setBusy(true); setError('');
    try { await request(`/schedules/${s.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: !s.enabled }) }); await load(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function run(s: MonitorSchedule) {
    setBusy(true); setError('');
    try { const scan = await request<Scan>(`/schedules/${s.id}/run`, { method: 'POST', signal: AbortSignal.timeout(180000) }); await onScanned(scan); await load(); }
    catch (e) { await load(); setError((e as Error).message); } finally { setBusy(false); }
  }
  return <><div className="section-intro"><h2>Continuous monitoring, on your terms</h2><div className="heading-actions"><button className="button secondary small" onClick={() => void load()}><RefreshCw size={14} />Refresh</button>{canManage && <button className="button primary small" onClick={() => setAdding(!adding)}><Plus size={14} />New schedule</button>}</div></div><ErrorNotice message={error} /><div className="phase-two-metrics">{[['Active schedules', schedules.filter(s => s.enabled).length], ['Worker', worker?.running ? 'Running' : worker?.enabled ? 'Starting' : 'Disabled'], ['Awaiting review', worker?.unread_alerts ?? 0], ['Email delivery', worker?.email_enabled ? 'Configured' : 'Inbox only']].map(([label, value]) => <div className="metric-card" key={label}><span className="metric-note">{label}</span><strong className="metric-value operational-value">{value}</strong></div>)}</div>{worker?.last_error && <ErrorNotice message={worker.last_error} />}
    {adding && canManage && <section className="panel collection-form phase-three-form"><h2>Create a monitoring schedule</h2><p>Schedules persist across restarts. Live schedules use local provider credentials; synthetic schedules run the bundled fixture.</p><form onSubmit={e => { e.preventDefault(); void create(); }}><label>Schedule name<input value={name} onChange={e => setName(e.target.value)} required maxLength={100} placeholder="Daily storage review" /></label><label>Data source<select value={kind} onChange={e => setKind(e.target.value as 'demo' | 'live')}><option value="demo">Synthetic demo</option><option value="live">Live read-only cloud</option></select></label><label>Interval<select value={interval} onChange={e => setInterval(Number(e.target.value))}><option value={60}>Every minute</option><option value={300}>Every 5 minutes</option><option value={3600}>Every hour</option><option value={86400}>Every day</option></select></label>{kind === 'live' && <><label>Cloud<select value={provider} onChange={e => setProvider(e.target.value as Provider)}><option value="aws">AWS</option><option value="azure">Azure</option><option value="gcp">GCP</option></select></label><label>Account / subscription / project ID<input value={account} onChange={e => setAccount(e.target.value)} pattern="[a-zA-Z0-9-]+" maxLength={80} placeholder="Form value or local environment" /></label>{provider === 'aws' && <label>AWS region<input value={region} onChange={e => setRegion(e.target.value)} required pattern="[a-z0-9-]+" /></label>}</>}<label className="check-control"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />Enable after creation</label><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spinning" size={15} /> : <Clock3 size={15} />}Save schedule</button></form></section>}
    <section className="panel"><div className="panel-heading"><div><h2>Monitoring schedules</h2><p>Single worker · UTC scheduling · persistent retries</p></div></div>{schedules.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Schedule</th><th>Interval</th><th>Next run</th><th>Last outcome</th><th>Status</th>{canManage && <th>Actions</th>}</tr></thead><tbody>{schedules.map(s => <tr key={s.id}><td><span className="resource-cell">{s.name}<small>{s.kind === 'demo' ? 'Synthetic fixture' : `${s.collection?.provider.toUpperCase()} · ${s.collection?.account ?? 'Local account'}`}</small></span></td><td>{s.interval_seconds < 3600 ? `${s.interval_seconds / 60} min` : `${s.interval_seconds / 3600} hr`}</td><td>{s.enabled ? dateTime(s.next_run) : 'Paused'}</td><td className="capitalize">{s.last_status}</td><td><span className={`check-status ${s.enabled ? 'pass' : 'unknown'}`}>{s.enabled ? 'Enabled' : 'Paused'}</span></td>{canManage && <td><div className="inline-actions"><button className="button secondary small" disabled={busy || s.last_status === 'running'} onClick={() => void toggle(s)}>{s.enabled ? <Pause size={12} /> : <Play size={12} />}{s.enabled ? 'Pause' : 'Enable'}</button><button className="button secondary small" disabled={busy || s.last_status === 'running'} onClick={() => void run(s)}>Run now</button></div></td>}</tr>)}</tbody></table></div> : <EmptyState title="No schedules yet" detail="An administrator can create a synthetic or read-only cloud schedule. Nothing is collected automatically until a schedule is enabled." />}</section>
    <section className="panel phase-two-panel"><div className="panel-heading"><div><h2>Recent monitoring runs</h2><p>Success, failure, and interrupted work are preserved</p></div></div>{runs.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Schedule</th><th>Started</th><th>Outcome</th><th>Scan / detail</th></tr></thead><tbody>{runs.map(r => <tr key={r.id}><td>{schedules.find(s => s.id === r.schedule_id)?.name ?? r.schedule_id.slice(0, 8)}</td><td>{dateTime(r.started_at)}</td><td className="capitalize">{r.status}</td><td>{r.scan_id?.slice(0, 8) ?? r.error ?? 'In progress'}</td></tr>)}</tbody></table></div> : <EmptyState title="No scheduled runs recorded" detail="Run a schedule now or wait for its next scheduled time." />}</section><p className="page-footnote">Failure retries use increasing backoff. Pausing a running schedule is blocked until it finishes. Inbox findings are deduplicated; acknowledging an alert does not change scan evidence.</p></>;
}

export function TeamAccess() {
  const { user, canManage, signOut } = useAuth();
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [audit, setAudit] = useState<AuditRecord[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<AuthUser['role']>('viewer');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  async function load() { if (!canManage) return; try { const [a, b] = await Promise.all([request<AuthUser[]>('/users'), request<AuditRecord[]>('/audit')]); setUsers(a); setAudit(b); } catch (e) { setError((e as Error).message); } }
  useEffect(() => { void load(); }, [canManage]);
  async function createUser() {
    setBusy(true); setError('');
    try { await request('/users', { method: 'POST', body: JSON.stringify({ username, display_name: displayName, password, role }) }); setUsername(''); setDisplayName(''); setPassword(''); await load(); }
    catch (e) { setError((e as Error).message); setPassword(''); } finally { setBusy(false); }
  }
  async function updateUser(target: AuthUser, changes: object) {
    setBusy(true); setError('');
    try { await request(`/users/${target.id}`, { method: 'PATCH', body: JSON.stringify(changes) }); await load(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function changePassword() {
    setBusy(true); setError('');
    try { await request('/auth/password', { method: 'POST', body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }); window.dispatchEvent(new Event('cloudsentinel-session-expired')); }
    catch (e) { setError((e as Error).message); } finally { setCurrentPassword(''); setNewPassword(''); setBusy(false); }
  }
  return <><ErrorNotice message={error} /><div className="ml-notice"><ShieldCheck size={20} /><div><strong>{user.display_name} · {user.role}</strong><p>Administrators manage accounts, models, and schedules. Analysts scan and triage. Viewers inspect the shared workspace. Roles are enforced by the API.</p></div></div>
    {canManage && <><section className="panel collection-form phase-three-form"><h2>Create a workspace account</h2><form onSubmit={e => { e.preventDefault(); void createUser(); }}><label>Username<input required value={username} onChange={e => setUsername(e.target.value)} minLength={3} maxLength={60} pattern="[a-zA-Z0-9_.-]+" autoComplete="off" /></label><label>Display name<input required value={displayName} onChange={e => setDisplayName(e.target.value)} maxLength={80} /></label><label>Initial password<input required type="password" value={password} onChange={e => setPassword(e.target.value)} minLength={12} maxLength={256} autoComplete="new-password" /></label><label>Role<select value={role} onChange={e => setRole(e.target.value as AuthUser['role'])}><option value="viewer">Viewer</option><option value="analyst">Analyst</option><option value="admin">Administrator</option></select></label><button className="button primary" disabled={busy}><Plus size={15} />Create account</button></form></section><section className="panel"><div className="panel-heading"><h2>Workspace accounts</h2><span className="subtle-tag">{users.length} accounts</span></div><div className="table-scroll"><table className="data-table"><thead><tr><th>Account</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead><tbody>{users.map(u => <tr key={u.id}><td><span className="resource-cell">{u.display_name}<small>{u.username}</small></span></td><td>{u.id === user.id ? <span className="capitalize">{u.role}</span> : <select className="table-select" value={u.role} disabled={busy} aria-label={`Role for ${u.username}`} onChange={e => void updateUser(u, { role: e.target.value })}><option value="viewer">Viewer</option><option value="analyst">Analyst</option><option value="admin">Administrator</option></select>}</td><td>{u.enabled ? 'Enabled' : 'Disabled'}</td><td>{u.id !== user.id ? <button className="button secondary small" disabled={busy} onClick={() => void updateUser(u, { enabled: !u.enabled })}>{u.enabled ? 'Disable access' : 'Enable access'}</button> : <span className="subtle-tag">Your account</span>}</td></tr>)}</tbody></table></div></section></>}
    <section className="panel collection-form phase-three-form"><h2>Change your password</h2><p>A password change signs out all sessions for your account.</p><form onSubmit={e => { e.preventDefault(); void changePassword(); }}><label>Current password<input required type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} autoComplete="current-password" maxLength={256} /></label><label>New password<input required type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} autoComplete="new-password" minLength={12} maxLength={256} /></label><button className="button primary" disabled={busy}>Update password</button><button className="button secondary" type="button" onClick={() => void signOut().catch(e => setError(e.message))}>Sign out</button></form></section>
    {canManage && <section className="panel phase-two-panel"><div className="panel-heading"><div><h2>Operational audit log</h2><p>Latest 200 access and workspace actions</p></div><button className="text-button" onClick={() => void load()}>Refresh <RefreshCw size={13} /></button></div><div className="table-scroll"><table className="data-table"><thead><tr><th>Action</th><th>Actor</th><th>Target</th><th>Recorded</th></tr></thead><tbody>{audit.map(a => <tr key={a.id}><td>{a.action}</td><td>{a.actor}</td><td>{a.target ? a.target.slice(0, 16) : '—'}</td><td>{dateTime(a.created_at)}</td></tr>)}</tbody></table></div></section>}</>;
}
