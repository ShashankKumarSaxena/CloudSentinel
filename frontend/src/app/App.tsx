import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Clock3,
  Cloud,
  Layers3,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Menu,
  Play,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { TeamAccess } from '../features/access/TeamAccess';
import { ActivityAnalysis } from '../features/activity/ActivityAnalysis';
import { AlertCenter } from '../features/alerts/AlertCenter';
import { useAuth } from '../features/auth/AuthProvider';
import { CloudConnections } from '../features/cloud/CloudConnections';
import { ProjectBrief } from '../features/coverage/DetectionCoverage';
import { FindingsPage } from '../features/findings/FindingsPage';
import { HistoryPage } from '../features/history/HistoryPage';
import { InventoryPage } from '../features/inventory/InventoryPage';
import { ModelLab } from '../features/models/ModelLab';
import { Monitoring } from '../features/monitoring/Monitoring';
import { OverviewPage } from '../features/overview/OverviewPage';
import type {
  Finding,
  Provider,
  Resource,
  Rule,
  Scan,
  ScanRecord,
  Severity,
  Status,
  TriageEvent,
  WorkerStatus,
} from '../shared/api/client';
import { ApiError, downloadReport, request } from '../shared/api/client';
import type { SnapshotPointer } from '../shared/api/types';
import { providers } from '../shared/constants';
import {
  dateTime,
  Drawer,
  EmptyState,
  ProviderMark,
  providerNames,
  providerShort,
  ResourceIcon,
  resourceNames,
  SeverityBadge,
  StatusBadge,
  statusNames,
} from '../shared/ui/components';
import { FlaskIcon } from '../shared/ui/dashboard';
import type { Page } from './navigation';
const pages: { id: Page; label: string; icon: LucideIcon }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'findings', label: 'Security findings', icon: ShieldCheck },
  { id: 'inventory', label: 'Cloud inventory', icon: Layers3 },
  { id: 'activity', label: 'Activity analysis', icon: Activity },
  { id: 'model', label: 'Model lab', icon: Sparkles },
  { id: 'connections', label: 'Cloud connections', icon: Cloud },
  { id: 'monitoring', label: 'Monitoring', icon: Clock3 },
  { id: 'alerts', label: 'Alert inbox', icon: Bell },
  { id: 'access', label: 'Team & access', icon: Users },
  { id: 'history', label: 'Scan history', icon: Clock3 },
  { id: 'brief', label: 'Detection coverage', icon: BookOpen },
];

export default function App() {
  const { user, canMutate, canManage, signOut, mode } = useAuth();
  const [unreadAlerts, setUnreadAlerts] = useState(0);
  const [scope, setScope] = useState('latest');
  const [snapshots, setSnapshots] = useState<SnapshotPointer[]>([]);
  const requestGeneration = useRef(0);
  const [page, setPage] = useState<Page>('overview');
  const [scan, setScan] = useState<Scan | null>(null);
  const [history, setHistory] = useState<ScanRecord[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [query, setQuery] = useState('');
  const [provider, setProvider] = useState<Provider | 'all'>('all');
  const [severity, setSeverity] = useState<Severity | 'all'>('all');
  const [status, setStatus] = useState<Status | 'all'>('all');
  const [finding, setFinding] = useState<Finding | null>(null);
  const [resource, setResource] = useState<Resource | null>(null);
  const [pastScan, setPastScan] = useState<Scan | null>(null);
  const [events, setEvents] = useState<TriageEvent[]>([]);
  const [eventError, setEventError] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const upload = useRef<HTMLInputElement>(null);
  const pageHeading = useRef<HTMLHeadingElement>(null);

  // A generation guard prevents a slower response for a previous account from
  // replacing the snapshot selected by the user.
  const load = async (quiet = false) => {
    const generation = ++requestGeneration.current;
    if (!quiet) {
      setLoading(true);
      setError('');
    }
    try {
      const pointers = await request<SnapshotPointer[]>('/cloud/snapshots');
      const selected = pointers.find((p) => p.connection_id + ':' + p.region === scope);
      const snapshotPath =
        scope === 'latest' ? '/scans/latest' : selected ? '/scans/' + selected.scan_id : null;
      const latest = snapshotPath
        ? await request<Scan>(snapshotPath).catch((error) => {
            if (error instanceof ApiError && error.status === 404) return null;
            throw error;
          })
        : null;
      const [scans, catalog, operations] = await Promise.all([
        request<ScanRecord[]>('/scans'),
        request<Rule[]>('/rules'),
        request<WorkerStatus>('/operations'),
      ]);
      if (generation !== requestGeneration.current) return;
      setScan(latest);
      setHistory(scans);
      setRules(catalog);
      setSnapshots(pointers);
      setUnreadAlerts(operations.unread_alerts);
    } catch (error) {
      if (generation === requestGeneration.current) setError((error as Error).message);
    } finally {
      if (generation === requestGeneration.current) setLoading(false);
    }
  };
  useEffect(() => {
    setFinding(null);
    setResource(null);
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load(true);
    }, 30000);
    return () => {
      ++requestGeneration.current;
      window.clearInterval(timer);
    };
  }, [scope]);
  useEffect(() => {
    if (toast) {
      const timer = window.setTimeout(() => setToast(''), 5500);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    if (!finding) return;
    let active = true;
    setEvents([]);
    setEventError('');
    request<TriageEvent[]>(`/findings/${finding.id}/events`)
      .then((value) => {
        if (active) setEvents(value);
      })
      .catch(() => {
        if (active) setEventError('Triage history could not be loaded.');
      });
    return () => {
      active = false;
    };
  }, [finding]);

  const navigate = (next: Page) => {
    setPage(next);
    setQuery('');
    setProvider('all');
    setSeverity('all');
    setStatus('all');
    setMenuOpen(false);
    window.scrollTo({ top: 0 });
    window.setTimeout(() => pageHeading.current?.focus(), 0);
  };
  const filteredFindings = (scan?.findings ?? []).filter(
    (f) =>
      (provider === 'all' || f.provider === provider) &&
      (severity === 'all' || f.severity === severity) &&
      (status === 'all' || f.status === status) &&
      `${f.title} ${f.resource_name} ${f.rule_id} ${f.provider}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const filteredResources = (scan?.resources ?? []).filter(
    (r) =>
      (provider === 'all' || r.provider === provider) &&
      `${r.name} ${r.type} ${r.region} ${r.id}`.toLowerCase().includes(query.toLowerCase()),
  );
  const openFindings = scan?.findings.filter((f) => f.status === 'open') ?? [];
  const resetFilters = () => {
    setQuery('');
    setProvider('all');
    setSeverity('all');
    setStatus('all');
  };

  async function runDemo() {
    setBusy(true);
    setError('');
    try {
      const next = await request<Scan>('/scans/demo', { method: 'POST' });
      ++requestGeneration.current;
      setScope('latest');
      setScan(next);
      setHistory(await request<ScanRecord[]>('/scans'));
      setToast(
        `Demo scan complete · ${next.summary.resources} resources checked, ${next.findings.length} findings detected.`,
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function importInventory(file: File) {
    setBusy(true);
    setError('');
    try {
      if (file.size > 2 * 1024 * 1024)
        throw new Error('Choose a JSON inventory smaller than 2 MB.');
      const text = await file.text();
      try {
        JSON.parse(text);
      } catch {
        throw new Error(
          'This file is not valid JSON. Use the inventory example in data/demo_inventory.json.',
        );
      }
      const next = await request<Scan>('/scans/import', { method: 'POST', body: text });
      ++requestGeneration.current;
      setScope('latest');
      setScan(next);
      setHistory(await request<ScanRecord[]>('/scans'));
      resetFilters();
      setToast(`Inventory imported · ${next.summary.resources} resources scanned successfully.`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      if (upload.current) upload.current.value = '';
    }
  }
  async function updateStatus(next: Status) {
    if (!finding) return;
    setBusy(true);
    setError('');
    try {
      const updated = await request<Finding>(`/findings/${finding.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: next, scan_id: scan?.id }),
      });
      setFinding((current) => (current?.id === updated.id ? updated : current));
      setScan((current) =>
        current
          ? {
              ...current,
              findings: current.findings.map((f) => (f.id === updated.id ? updated : f)),
            }
          : current,
      );
      setToast(`Finding marked ${statusNames[next].toLowerCase()}.`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function exportReport() {
    setBusy(true);
    setError('');
    try {
      await downloadReport(scan?.id);
      setToast('Your scan report has been downloaded.');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function inspectScan(id: string) {
    setBusy(true);
    setError('');
    try {
      setPastScan(await request<Scan>(`/scans/${id}`));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const providerSelect = (
    <label className="select-control">
      <Cloud size={16} />
      <select
        aria-label="Filter by cloud provider"
        value={provider}
        onChange={(e) => setProvider(e.target.value as Provider | 'all')}
      >
        <option value="all">All cloud providers</option>
        {providers.map((p) => (
          <option key={p} value={p}>
            {providerShort[p]}
          </option>
        ))}
      </select>
      <ChevronDown size={14} />
    </label>
  );
  const findingTable = (items: Finding[], compact = false) => (
    <div className="table-scroll">
      <table className="data-table findings-table">
        <thead>
          <tr>
            <th>Finding</th>
            <th>Severity</th>
            <th>Cloud</th>
            {!compact && <th>Resource</th>}
            <th>Status</th>
            <th>
              <span className="sr-only">Details</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((f) => (
            <tr key={f.id}>
              <td>
                <button className="finding-link" onClick={() => setFinding(f)}>
                  <span className={`finding-symbol ${f.severity}`}>
                    <ResourceIcon type={f.resource_type} size={17} />
                  </span>
                  <span>
                    <strong>{f.title}</strong>
                    <small>
                      {compact
                        ? f.resource_name
                        : `${f.detection_method === 'ml' ? 'ML' : f.rule_id} · ${f.category}`}
                    </small>
                  </span>
                </button>
              </td>
              <td>
                <SeverityBadge severity={f.severity} />
              </td>
              <td>
                <span className="cloud-label">
                  <ProviderMark provider={f.provider} small />
                  {providerShort[f.provider]}
                </span>
              </td>
              {!compact && (
                <td>
                  <span className="resource-cell">
                    {f.resource_name}
                    <small>{f.region}</small>
                  </span>
                </td>
              )}
              <td>
                <StatusBadge status={f.status} />
              </td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`View ${f.title} on ${f.resource_name}`}
                  onClick={() => setFinding(f)}
                >
                  <ChevronRight size={17} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      {menuOpen && (
        <button
          className="mobile-scrim"
          aria-label="Close navigation"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside className={`sidebar ${menuOpen ? 'is-open' : ''}`}>
        <button
          className="brand"
          onClick={() => navigate('overview')}
          aria-label="CloudSentinel overview"
        >
          <span className="brand-icon">
            <ShieldCheck size={25} strokeWidth={1.7} />
          </span>
          <span>
            Cloud<span className="brand-light">Sentinel</span>
            <small>CLOUD SECURITY WORKSPACE</small>
          </span>
        </button>
        <div className="workspace">
          <span className="workspace-avatar">S</span>
          <div>
            <strong>{mode === 'demo' ? 'Demo workspace' : 'Security workspace'}</strong>
            <small>{mode === 'demo' ? 'Synthetic sandbox' : 'Organization workspace'}</small>
          </div>
          <Layers3 size={16} />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          {pages.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => navigate(id)}
              className={`nav-item ${page === id ? 'active' : ''}`}
              aria-current={page === id ? 'page' : undefined}
            >
              <Icon size={19} strokeWidth={1.7} />
              <span>{id === 'access' && !canManage ? 'Your account' : label}</span>
              {id === 'alerts' && unreadAlerts > 0 && (
                <span className="nav-count">{unreadAlerts}</span>
              )}
              {id === 'findings' && !!openFindings.length && (
                <span className="nav-count">{openFindings.length}</span>
              )}
              {id === 'brief' && <span className="nav-new">03</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace-tip">
            <span className="workspace-tip-icon">
              <Sparkles size={18} />
            </span>
            <strong>A strong foundation.</strong>
            <p>Multi-cloud visibility starts with a clear security baseline.</p>
            <button onClick={() => navigate('brief')}>
              Detection coverage <ArrowUpRight size={16} />
            </button>
          </div>
          <div className="local-status">
            <span className="online-dot" />
            Local workspace<span>v1.0.0</span>
          </div>
          <div className="profile">
            <div className="profile-avatar">{user.display_name.slice(0, 2).toUpperCase()}</div>
            <div>
              <strong>{user.display_name}</strong>
              <small className="capitalize">{user.role} access</small>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={() => void signOut().catch((e) => setError(e.message))}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMenuOpen(true)}
              aria-label="Open navigation"
            >
              <Menu size={22} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{pages.find((p) => p.id === page)?.label}</strong>
          </div>
          <div className="topbar-right">
            <span className="deployment-pill">
              <span />
              {mode === 'demo' ? 'Demo mode' : 'Production'}
            </span>
            <div className="header-avatar" title={user.display_name}>
              {user.display_name.slice(0, 2).toUpperCase()}
            </div>
          </div>
        </header>
        <main id="main-content">
          <div className="page-heading">
            <div>
              <span className="eyebrow">
                {page === 'overview'
                  ? 'YOUR SECURITY AT A GLANCE'
                  : page === 'brief'
                  ? 'BUILT WITH A CLEAR PURPOSE'
                  : 'CLOUD SECURITY WORKSPACE'}
              </span>
              <h1 ref={pageHeading} tabIndex={-1}>
                {
                  {
                    overview: 'Your cloud, in focus.',
                    findings: 'Security findings',
                    inventory: 'Cloud inventory',
                    history: 'Scan history',
                    activity: 'Understand cloud activity.',
                    model: 'A model you can inspect.',
                    connections: 'Connect your cloud accounts.',
                    alerts: 'Security signals, ready for review.',
                    monitoring: 'Keep your cloud in view.',
                    access: canManage ? 'Manage workspace access.' : 'Your account.',
                    brief: 'A foundation for safer clouds.',
                  }[page]
                }
              </h1>
              <p>
                {
                  {
                    overview:
                      'One workspace. Three clouds. A clearer picture of what needs attention.',
                    findings:
                      'Understand the risk, inspect the evidence, and plan your next action.',
                    inventory:
                      'A unified view of the resources in your latest configuration snapshot.',
                    history: 'Every baseline scan, preserved with its configuration and results.',
                    activity:
                      'Review hourly behavior patterns and the evidence behind anomaly signals.',
                    model: 'Train, calibrate, and evaluate the activity anomaly detector.',
                    connections: 'Collect read-only snapshots using your local cloud credentials.',
                    alerts:
                      'A persistent inbox for findings, monitoring failures, and collection coverage.',
                    monitoring: 'Schedule read-only scans and track background processing.',
                    access:
                      'Access controls and an audit trail for your shared security workspace.',
                    brief: 'The vision, the working prototype, and what comes next.',
                  }[page]
                }
              </p>
            </div>
            <div className="heading-actions">
              <button className="button secondary" onClick={exportReport} disabled={busy || !scan}>
                <ArrowDownToLine size={16} />
                Export report
              </button>
              {mode === 'demo' && (
                <button className="button primary" onClick={runDemo} disabled={busy || !canMutate}>
                  <span className={busy ? 'spinning' : ''}>
                    {busy ? <LoaderCircle size={17} /> : <Play size={15} fill="currentColor" />}
                  </span>
                  {busy ? 'Working…' : 'Run demo scan'}
                </button>
              )}
            </div>
          </div>
          <div className="provenance-banner">
            <span className="banner-icon">
              <FlaskIcon />
            </span>
            <p>
              <strong>
                {scan?.source === 'live'
                  ? 'Live cloud snapshot'
                  : scan?.source === 'import'
                  ? 'Imported snapshot'
                  : mode === 'demo'
                  ? 'Demo environment'
                  : 'Awaiting first cloud snapshot'}
              </strong>
              <span>
                {scan?.source === 'live'
                  ? 'Collected through read-only cloud APIs. Review coverage and model training provenance.'
                  : scan?.source === 'import'
                  ? 'Results use your uploaded configuration and activity snapshot.'
                  : mode === 'demo'
                  ? 'Explore synthetic AWS, Azure, and GCP configurations and activity. No credentials needed.'
                  : 'Queue a scan from an approved account to start reviewing evidence.'}
              </span>
            </p>
            <button onClick={() => navigate('brief')}>
              Detection coverage <ArrowRight size={14} />
            </button>
          </div>
          {snapshots.length > 0 && (
            <div className="scope-selector">
              <label>
                Account snapshot
                <select
                  value={scope}
                  disabled={busy}
                  onChange={(event) => setScope(event.target.value)}
                >
                  <option value="latest">Latest completed snapshot</option>
                  {snapshots.map((pointer) => (
                    <option
                      key={pointer.connection_id + ':' + pointer.region}
                      value={pointer.connection_id + ':' + pointer.region}
                    >
                      {pointer.connection_id} · {pointer.region}
                    </option>
                  ))}
                </select>
              </label>
              <span>
                Approved connections retain separate snapshots. Collection history is preserved.
              </span>
            </div>
          )}
          {error && (
            <div className="error-banner" role="alert">
              <CircleAlert size={20} />
              <p>{error}</p>
              <button className="button small secondary" onClick={() => void load()}>
                Retry connection
              </button>
              <button
                className="icon-button"
                onClick={() => setError('')}
                aria-label="Dismiss error"
              >
                <X size={17} />
              </button>
            </div>
          )}
          {loading ? (
            <div className="loading-state" role="status">
              <LoaderCircle className="spinning" size={28} />
              <p>Preparing your security workspace…</p>
            </div>
          ) : (
            <>
              {!scan &&
                ['overview', 'findings', 'inventory', 'history', 'activity'].includes(page) && (
                  <EmptyState
                    title="Connect your first cloud account"
                    detail="Select an approved connection and queue a read-only collection. Your results will appear here when the worker finishes."
                    action={
                      <button className="button primary" onClick={() => navigate('connections')}>
                        Open cloud accounts
                      </button>
                    }
                  />
                )}

              {scan && page === 'overview' && (
                <OverviewPage
                  scan={scan}
                  openFindings={openFindings}
                  navigate={navigate}
                  setProvider={setProvider}
                  setSeverity={setSeverity}
                  findingTable={findingTable}
                />
              )}
              {scan && page === 'findings' && (
                <FindingsPage
                  severity={severity}
                  setSeverity={setSeverity}
                  scan={scan}
                  query={query}
                  setQuery={setQuery}
                  providerSelect={providerSelect}
                  status={status}
                  setStatus={setStatus}
                  filteredFindings={filteredFindings}
                  resetFilters={resetFilters}
                  findingTable={findingTable}
                />
              )}
              {scan && page === 'inventory' && (
                <InventoryPage
                  scan={scan}
                  busy={busy}
                  canMutate={canMutate}
                  upload={upload}
                  query={query}
                  setQuery={setQuery}
                  providerSelect={providerSelect}
                  filteredResources={filteredResources}
                  setResource={setResource}
                  resetFilters={resetFilters}
                />
              )}
              {scan && page === 'history' && (
                <HistoryPage history={history} inspectScan={inspectScan} busy={busy} />
              )}
              {scan && page === 'activity' && <ActivityAnalysis scan={scan} />}
              {page === 'model' && <ModelLab />}
              {page === 'connections' && (
                <CloudConnections
                  onCollected={async (next) => {
                    ++requestGeneration.current;
                    setScan(next);
                    setScope(
                      next.collection?.connection_id
                        ? next.collection.connection_id + ':' + next.collection.region
                        : 'latest',
                    );
                    setHistory(await request<ScanRecord[]>('/scans'));
                    setToast('Read-only cloud collection completed. Review collection coverage.');
                  }}
                />
              )}
              {page === 'alerts' && <AlertCenter />}
              {page === 'monitoring' && (
                <Monitoring
                  onScanned={async (next) => {
                    ++requestGeneration.current;
                    setScan(next);
                    setScope(
                      next.collection?.connection_id
                        ? next.collection.connection_id + ':' + next.collection.region
                        : 'latest',
                    );
                    setHistory(await request<ScanRecord[]>('/scans'));
                    setToast('Monitoring run completed.');
                  }}
                />
              )}
              {page === 'access' && <TeamAccess />}
              {page === 'brief' && <ProjectBrief rules={rules} />}
            </>
          )}
        </main>
        <footer className="app-footer">
          <span>
            CloudSentinel <span className="footer-dot">·</span> Multi-cloud security posture &
            activity analysis
          </span>
          <span>Read-only monitoring · Auditable operations</span>
        </footer>
      </div>
      <input
        className="sr-only"
        ref={upload}
        type="file"
        accept=".json,application/json"
        aria-label="Import JSON inventory"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void importInventory(file);
        }}
      />
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={19} />
          <span>{toast}</span>
          <button
            className="icon-button"
            onClick={() => setToast('')}
            aria-label="Dismiss notification"
          >
            <X size={16} />
          </button>
        </div>
      )}
      {finding && (
        <Drawer title={finding.title} onClose={() => setFinding(null)}>
          <div className="drawer-badges">
            <SeverityBadge severity={finding.severity} />
            <StatusBadge status={finding.status} />
            <span className="subtle-tag">
              {finding.detection_method === 'ml' ? 'Isolation Forest' : finding.rule_id}
            </span>
          </div>
          <p className="drawer-description">{finding.description}</p>
          <div className="detail-card">
            <span className="eyebrow">AFFECTED RESOURCE</span>
            <h3>
              <ResourceIcon type={finding.resource_type} />
              {finding.resource_name}
            </h3>
            <dl>
              <dt>Cloud provider</dt>
              <dd>
                <ProviderMark provider={finding.provider} small />
                {providerNames[finding.provider]}
              </dd>
              <dt>Region</dt>
              <dd>{finding.region}</dd>
              <dt>Account</dt>
              <dd>{finding.account}</dd>
              <dt>Resource ID</dt>
              <dd className="mono">{finding.resource_id}</dd>
            </dl>
          </div>
          <h3 className="drawer-section-title">
            {finding.detection_method === 'ml' ? 'Activity evidence' : 'Configuration evidence'}
          </h3>
          <pre className="evidence">{JSON.stringify(finding.evidence, null, 2)}</pre>
          <div className="remediation-card">
            <div>
              <ShieldCheck size={20} />
              <h3>Recommended remediation</h3>
            </div>
            <p>{finding.remediation}</p>
            <small>Guidance only. No cloud configuration is changed.</small>
          </div>
          <h3 className="drawer-section-title">Team disposition</h3>
          <p className="drawer-help">
            Track your review. Resolving a finding does not change the saved scan score or verify
            remediation.
          </p>
          <div className="status-actions">
            {(['open', 'acknowledged', 'resolved'] as Status[]).map((s) => (
              <button
                key={s}
                disabled={
                  busy ||
                  !canMutate ||
                  finding.status === s ||
                  !scan?.findings.some((current) => current.id === finding.id)
                }
                className={`button small ${finding.status === s ? 'primary' : 'secondary'}`}
                onClick={() => void updateStatus(s)}
              >
                {finding.status === s && <Check size={14} />}
                {statusNames[s]}
              </button>
            ))}
          </div>
          <h3 className="drawer-section-title">Triage history</h3>
          {eventError ? (
            <p className="drawer-help">{eventError}</p>
          ) : events.length ? (
            <ol className="event-list">
              {events.map((e, i) => (
                <li key={`${e.created_at}-${i}`}>
                  <span>
                    {statusNames[e.previous_status]} <ArrowRight size={12} />{' '}
                    {statusNames[e.status]}
                  </span>
                  <small>{dateTime(e.created_at)}</small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="drawer-help">No triage changes recorded.</p>
          )}
        </Drawer>
      )}
      {resource && scan && (
        <Drawer title={resource.name} onClose={() => setResource(null)}>
          <div className="drawer-badges">
            <span className="cloud-label">
              <ProviderMark provider={resource.provider} small />
              {providerNames[resource.provider]}
            </span>
            <span className="subtle-tag">{resourceNames[resource.type]}</span>
          </div>
          <div className="detail-card">
            <dl>
              <dt>Region</dt>
              <dd>{resource.region}</dd>
              <dt>Account</dt>
              <dd>{resource.account}</dd>
              <dt>Resource ID</dt>
              <dd className="mono">{resource.id}</dd>
            </dl>
          </div>
          <h3 className="drawer-section-title">Normalized configuration</h3>
          <pre className="evidence">
            {JSON.stringify(
              Object.fromEntries(Object.entries(resource.config).filter(([, v]) => v !== null)),
              null,
              2,
            )}
          </pre>
          <h3 className="drawer-section-title">Baseline checks</h3>
          <div className="check-list">
            {scan.checks
              .filter(
                (c) =>
                  c.resource_id === resource.id &&
                  c.provider === resource.provider &&
                  (!c.account || c.account === resource.account),
              )
              .map((c) => (
                <div key={c.rule_id}>
                  <span>
                    <strong>{c.rule_id}</strong>
                    <small>{rules.find((r) => r.id === c.rule_id)?.title}</small>
                  </span>
                  <span className={`check-status ${c.outcome}`}>
                    {c.outcome === 'pass' ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />}
                    {c.outcome}
                  </span>
                </div>
              ))}
          </div>
          <p className="drawer-help">
            Null or omitted fields are unknown. Only applicable checks are evaluated.
          </p>
        </Drawer>
      )}
      {pastScan && (
        <Drawer title={pastScan.name} onClose={() => setPastScan(null)}>
          <div className="drawer-badges">
            <span className="subtle-tag">
              {pastScan.source === 'live'
                ? 'Live collection'
                : pastScan.source === 'demo'
                ? 'Synthetic demo'
                : 'Imported snapshot'}
            </span>
            <span className="muted">{dateTime(pastScan.created_at)}</span>
          </div>
          <div className="snapshot-stats">
            <div>
              <strong>{pastScan.summary.resources}</strong>
              <span>Resources</span>
            </div>
            <div>
              <strong>{pastScan.summary.findings ?? pastScan.summary.failed}</strong>
              <span>Findings</span>
            </div>
            <div>
              <strong>
                {pastScan.summary.posture_score ?? '—'}
                {pastScan.summary.posture_score !== null ? '%' : ''}
              </strong>
              <span>Posture</span>
            </div>
          </div>
          <h3 className="drawer-section-title">Immutable scan summary</h3>
          <pre className="evidence">{JSON.stringify(pastScan.summary, null, 2)}</pre>
          <h3 className="drawer-section-title">Detected findings</h3>
          {pastScan.findings.length ? (
            <div className="snapshot-findings">
              {pastScan.findings.map((f) => (
                <div key={f.id}>
                  <SeverityBadge severity={f.severity} />
                  <span>
                    <strong>{f.title}</strong>
                    <small>{f.resource_name}</small>
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="drawer-help">No failed checks in this snapshot.</p>
          )}
          <p className="drawer-help">Snapshot ID: {pastScan.id}</p>
        </Drawer>
      )}
    </div>
  );
}
