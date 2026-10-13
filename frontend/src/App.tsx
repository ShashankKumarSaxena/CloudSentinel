import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, BookOpen, Check, CheckCircle2, ChevronDown, ChevronRight, CircleAlert, Clock3, Cloud, FileJson, Filter, Layers3, LayoutDashboard, LoaderCircle, Menu, Play, Plus, Search, Shield, ShieldCheck, Sparkles, Upload, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { downloadReport, request } from './api';
import type { Finding, Provider, Resource, Rule, Scan, ScanRecord, Severity, Status, TriageEvent } from './api';
import { ActivityAnalysis, CloudConnections, ModelLab } from './PhaseTwo';
import { dateTime, Drawer, EmptyState, ProviderMark, providerNames, providerShort, ResourceIcon, resourceNames, SeverityBadge, StatusBadge, statusNames } from './components';

type Page = 'overview' | 'findings' | 'inventory' | 'history' | 'activity' | 'model' | 'connections' | 'brief';
const pages: { id: Page; label: string; icon: LucideIcon }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'findings', label: 'Security findings', icon: ShieldCheck },
  { id: 'inventory', label: 'Cloud inventory', icon: Layers3 },
  { id: 'activity', label: 'Activity analysis', icon: Activity },
  { id: 'model', label: 'Model lab', icon: Sparkles },
  { id: 'connections', label: 'Cloud connections', icon: Cloud },
  { id: 'history', label: 'Scan history', icon: Clock3 },
  { id: 'brief', label: 'Project brief', icon: BookOpen },
];
const providers: Provider[] = ['aws', 'azure', 'gcp'];
const severities: Severity[] = ['critical', 'high', 'medium', 'low'];

export default function App() {
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

  const load = async () => {
    setLoading(true); setError('');
    try {
      const [latest, scans, catalog] = await Promise.all([
        request<Scan>('/scans/latest'), request<ScanRecord[]>('/scans'), request<Rule[]>('/rules'),
      ]);
      setScan(latest); setHistory(scans); setRules(catalog);
    } catch (err) { setError((err as Error).message); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  useEffect(() => { if (toast) { const timer = window.setTimeout(() => setToast(''), 5500); return () => clearTimeout(timer); } }, [toast]);
  useEffect(() => {
    if (!finding) return;
    let active = true;
    setEvents([]); setEventError('');
    request<TriageEvent[]>(`/findings/${finding.id}/events`).then(value => { if (active) setEvents(value); })
      .catch(() => { if (active) setEventError('Triage history could not be loaded.'); });
    return () => { active = false; };
  }, [finding]);

  const navigate = (next: Page) => {
    setPage(next); setQuery(''); setProvider('all'); setSeverity('all'); setStatus('all'); setMenuOpen(false);
    window.scrollTo({ top: 0 });
    window.setTimeout(() => pageHeading.current?.focus(), 0);
  };
  const filteredFindings = (scan?.findings ?? []).filter(f =>
    (provider === 'all' || f.provider === provider) && (severity === 'all' || f.severity === severity) &&
    (status === 'all' || f.status === status) && `${f.title} ${f.resource_name} ${f.rule_id} ${f.provider}`.toLowerCase().includes(query.toLowerCase()));
  const filteredResources = (scan?.resources ?? []).filter(r =>
    (provider === 'all' || r.provider === provider) && `${r.name} ${r.type} ${r.region} ${r.id}`.toLowerCase().includes(query.toLowerCase()));
  const openFindings = scan?.findings.filter(f => f.status === 'open') ?? [];
  const resetFilters = () => { setQuery(''); setProvider('all'); setSeverity('all'); setStatus('all'); };

  async function runDemo() {
    setBusy(true); setError('');
    try {
      const next = await request<Scan>('/scans/demo', { method: 'POST' });
      setScan(next); setHistory(await request<ScanRecord[]>('/scans'));
      setToast(`Demo scan complete · ${next.summary.resources} resources checked, ${next.findings.length} findings detected.`);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  async function importInventory(file: File) {
    setBusy(true); setError('');
    try {
      if (file.size > 2 * 1024 * 1024) throw new Error('Choose a JSON inventory smaller than 2 MB.');
      const text = await file.text();
      try { JSON.parse(text); } catch { throw new Error('This file is not valid JSON. Use the inventory example in data/demo_inventory.json.'); }
      const next = await request<Scan>('/scans/import', { method: 'POST', body: text });
      setScan(next); setHistory(await request<ScanRecord[]>('/scans')); resetFilters();
      setToast(`Inventory imported · ${next.summary.resources} resources scanned successfully.`);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); if (upload.current) upload.current.value = ''; }
  }
  async function updateStatus(next: Status) {
    if (!finding) return;
    setBusy(true); setError('');
    try {
      const updated = await request<Finding>(`/findings/${finding.id}`, { method: 'PATCH', body: JSON.stringify({ status: next }) });
      setFinding(current => current?.id === updated.id ? updated : current);
      setScan(current => current ? { ...current, findings: current.findings.map(f => f.id === updated.id ? updated : f) } : current);
      setToast(`Finding marked ${statusNames[next].toLowerCase()}.`);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  async function exportReport() {
    setBusy(true); setError('');
    try { await downloadReport(); setToast('Your scan report has been downloaded.'); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  async function inspectScan(id: string) {
    setBusy(true); setError('');
    try { setPastScan(await request<Scan>(`/scans/${id}`)); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  const providerSelect = <label className="select-control"><Cloud size={16} /><select aria-label="Filter by cloud provider" value={provider} onChange={e => setProvider(e.target.value as Provider | 'all')}><option value="all">All cloud providers</option>{providers.map(p => <option key={p} value={p}>{providerShort[p]}</option>)}</select><ChevronDown size={14} /></label>;
  const findingTable = (items: Finding[], compact = false) => <div className="table-scroll"><table className="data-table findings-table">
    <thead><tr><th>Finding</th><th>Severity</th><th>Cloud</th>{!compact && <th>Resource</th>}<th>Status</th><th><span className="sr-only">Details</span></th></tr></thead>
    <tbody>{items.map(f => <tr key={f.id}><td><button className="finding-link" onClick={() => setFinding(f)}><span className={`finding-symbol ${f.severity}`}><ResourceIcon type={f.resource_type} size={17} /></span><span><strong>{f.title}</strong><small>{compact ? f.resource_name : `${f.detection_method === 'ml' ? 'ML' : f.rule_id} · ${f.category}`}</small></span></button></td><td><SeverityBadge severity={f.severity} /></td><td><span className="cloud-label"><ProviderMark provider={f.provider} small />{providerShort[f.provider]}</span></td>{!compact && <td><span className="resource-cell">{f.resource_name}<small>{f.region}</small></span></td>}<td><StatusBadge status={f.status} /></td><td><button className="icon-button" aria-label={`View ${f.title} on ${f.resource_name}`} onClick={() => setFinding(f)}><ChevronRight size={17} /></button></td></tr>)}</tbody>
  </table></div>;

  return <div className="app-shell">
    <a href="#main-content" className="skip-link">Skip to content</a>
    {menuOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
    <aside className={`sidebar ${menuOpen ? 'is-open' : ''}`}>
      <button className="brand" onClick={() => navigate('overview')} aria-label="CloudSentinel overview"><span className="brand-icon"><ShieldCheck size={25} strokeWidth={1.7} /></span><span>Cloud<span className="brand-light">Sentinel</span><small>CLOUD SECURITY WORKSPACE</small></span></button>
      <div className="workspace"><span className="workspace-avatar">S</span><div><strong>Sandbox workspace</strong><small>Phase 2 · Local environment</small></div><Layers3 size={16} /></div>
      <p className="nav-label">WORKSPACE</p>
      <nav aria-label="Main navigation">{pages.map(({ id, label, icon: Icon }) => <button key={id} onClick={() => navigate(id)} className={`nav-item ${page === id ? 'active' : ''}`} aria-current={page === id ? 'page' : undefined}><Icon size={19} strokeWidth={1.7} /><span>{label}</span>{id === 'findings' && !!openFindings.length && <span className="nav-count">{openFindings.length}</span>}{id === 'brief' && <span className="nav-new">02</span>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="phase-card"><span className="phase-icon"><Sparkles size={18} /></span><strong>A strong foundation.</strong><p>Multi-cloud visibility starts with a clear security baseline.</p><button onClick={() => navigate('brief')}>Explore Phase 2 <ArrowUpRight size={16} /></button></div><div className="local-status"><span className="online-dot" />Local workspace<span>v0.2.0</span></div><div className="profile"><div className="profile-avatar">ST</div><div><strong>Project team</strong><small>Academic prototype</small></div><Shield size={17} /></div></div>
    </aside>
    <div className="workspace-main">
      <header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu size={22} /></button><span>Workspace</span><ChevronRight size={14} /><strong>{pages.find(p => p.id === page)?.label}</strong></div><div className="topbar-right"><span className="phase-pill"><span />Phase 2 prototype</span><div className="header-avatar" title="Project team">ST</div></div></header>
      <main id="main-content">
        <div className="page-heading"><div><span className="eyebrow">{page === 'overview' ? 'YOUR SECURITY AT A GLANCE' : page === 'brief' ? 'BUILT WITH A CLEAR PURPOSE' : 'CLOUD SECURITY WORKSPACE'}</span><h1 ref={pageHeading} tabIndex={-1}>{({ overview: 'Your cloud, in focus.', findings: 'Security findings', inventory: 'Cloud inventory', history: 'Scan history', activity: 'Understand cloud activity.', model: 'A model you can inspect.', connections: 'Connect your cloud accounts.', brief: 'A foundation for safer clouds.' })[page]}</h1><p>{({ overview: 'One workspace. Three clouds. A clearer picture of what needs attention.', findings: 'Understand the risk, inspect the evidence, and plan your next action.', inventory: 'A unified view of the resources in your latest configuration snapshot.', history: 'Every baseline scan, preserved with its configuration and results.', activity: 'Review hourly behavior patterns and the evidence behind anomaly signals.', model: 'Train, calibrate, and evaluate the activity anomaly detector.', connections: 'Collect read-only snapshots using your local cloud credentials.', brief: 'The vision, the working prototype, and what comes next.' })[page]}</p></div><div className="heading-actions"><button className="button secondary" onClick={exportReport} disabled={busy || !scan}><ArrowDownToLine size={16} />Export report</button><button className="button primary" onClick={runDemo} disabled={busy}><span className={busy ? 'spinning' : ''}>{busy ? <LoaderCircle size={17} /> : <Play size={15} fill="currentColor" />}</span>{busy ? 'Working…' : 'Run demo scan'}</button></div></div>
        <div className="provenance-banner"><span className="banner-icon"><FlaskIcon /></span><p><strong>{scan?.source === 'live' ? 'Live cloud snapshot' : scan?.source === 'import' ? 'Imported snapshot' : 'Demo environment'}</strong><span>{scan?.source === 'live' ? 'Collected through read-only cloud APIs. Review coverage and model training provenance.' : scan?.source === 'import' ? 'Results use your uploaded configuration and activity snapshot.' : 'Explore synthetic AWS, Azure, and GCP configurations and activity. No credentials needed.'}</span></p><button onClick={() => navigate('brief')}>About this phase <ArrowRight size={14} /></button></div>
        {error && <div className="error-banner" role="alert"><CircleAlert size={20} /><p>{error}</p><button className="button small secondary" onClick={() => void load()}>Retry connection</button><button className="icon-button" onClick={() => setError('')} aria-label="Dismiss error"><X size={17} /></button></div>}
        {loading ? <div className="loading-state" role="status"><LoaderCircle className="spinning" size={28} /><p>Preparing your security workspace…</p></div> : !scan ? <EmptyState title="Your workspace is ready to connect" detail="Start the local backend and retry to load the synthetic inventory." action={<button className="button primary" onClick={() => void load()}>Retry connection</button>} /> : <>
          {page === 'overview' && <>
            <div className="section-intro"><h2>Security overview</h2><span><Clock3 size={14} />Last scan {dateTime(scan.created_at)}</span></div>
            <div className="metric-grid">
              <Metric label="Open findings" value={openFindings.length} icon={Shield} tone="red"><span className="metric-note danger"><span />{openFindings.filter(f => f.severity === 'critical').length} critical need attention</span></Metric>
              <Metric label="Resources scanned" value={scan.summary.resources} icon={Layers3} tone="blue"><span className="metric-note">Across {new Set(scan.resources.map(r => r.provider)).size} cloud providers</span></Metric>
              <Metric label="Checks passed" value={`${scan.summary.passed}/${scan.summary.total_checks}`} icon={CheckCircle2} tone="green"><span className="metric-note">{scan.summary.unknown ? `${scan.summary.unknown} checks need more data` : 'All configuration fields available'}</span></Metric>
              <Metric label="Baseline posture" value={scan.summary.posture_score === null ? '—' : `${scan.summary.posture_score}%`} icon={Activity} tone="amber"><span className="metric-note">Pass rate of evaluated checks</span></Metric>
            </div>
            <button className="activity-overview-strip" onClick={() => navigate('activity')}><span className="metric-icon green"><Activity size={20} /></span><div><strong>{scan.summary.anomalies ?? 0} activity anomalies · {scan.activity.event_count} normalized events</strong><p>{scan.activity.model ? `${scan.activity.model.algorithm} · ${scan.activity.model.provenance === 'synthetic' ? 'Synthetic-trained model' : 'Reviewed activity baseline'}` : 'This historical snapshot has no ML activity analysis'}</p></div><span>Review activity <ArrowRight size={16} /></span></button>
            {scan.collection?.partial && <div className="error-banner"><CircleAlert size={18} /><p>Partial cloud collection. Some scopes were unavailable or unsupported; these results do not represent a complete account review.</p></div>}
            <div className="overview-middle">
              <section className="panel provider-panel"><div className="panel-heading"><div><h2>Your cloud landscape</h2><p>Visibility across your configuration snapshot</p></div><span className="subtle-tag">{new Set(scan.resources.map(r => r.provider)).size} providers</span></div><div className="provider-grid">{providers.map(p => {
                const assets = scan.resources.filter(r => r.provider === p);
                const findings = scan.findings.filter(f => f.provider === p);
                return <button key={p} className="provider-card" onClick={() => { navigate('inventory'); setProvider(p); }}><div className="provider-card-top"><ProviderMark provider={p} /><ArrowUpRight size={17} /></div><h3>{providerNames[p]}</h3><span className="snapshot-label"><span />{assets.length ? 'Snapshot available' : 'No resources'}</span><div className="provider-card-stats"><div><strong>{assets.length}</strong><small>Resources</small></div><div><strong className={findings.length ? 'text-danger' : ''}>{findings.length}</strong><small>Findings</small></div></div><div className="provider-card-footer">{scan.source === 'live' ? 'Live collected inventory' : scan.source === 'demo' ? 'Synthetic inventory' : 'Imported inventory'}<ChevronRight size={14} /></div></button>;
              })}</div></section>
              <section className="panel severity-panel"><div className="panel-heading"><div><h2>Severity breakdown</h2><p>Detected in the latest scan</p></div><Shield size={18} /></div><div className="severity-chart"><Donut findings={scan.findings} /><div className="severity-legend">{severities.map(s => <button key={s} onClick={() => { navigate('findings'); setSeverity(s); }}><span className={`legend-dot ${s}`} /><span className="capitalize">{s}</span><strong>{scan.findings.filter(f => f.severity === s).length}</strong></button>)}</div></div><div className="chart-note"><CircleAlert size={14} />Start with critical and high severity findings.</div></section>
            </div>
            <section className="panel priority-panel"><div className="panel-heading"><div className="heading-inline"><h2>Priority findings</h2><span className="count-pill">{openFindings.length} open</span></div><button className="text-button" onClick={() => navigate('findings')}>View all findings <ArrowRight size={16} /></button></div>{openFindings.length ? findingTable(openFindings.slice(0, 4), true) : <EmptyState title="No open findings" detail="Review acknowledged and resolved findings, or run a new configuration scan." />}</section>
            <div className="overview-footer"><span><ShieldCheck size={16} />Read-only analysis. Your cloud infrastructure stays untouched.</span><button onClick={() => navigate('brief')}>Built for multi-cloud security <ArrowUpRight size={14} /></button></div>
          </>}
          {page === 'findings' && <>
            <div className="finding-summary">{severities.map(s => <button className={`severity-summary ${severity === s ? 'selected' : ''}`} key={s} onClick={() => setSeverity(severity === s ? 'all' : s)}><span className={`legend-dot ${s}`} /><span className="capitalize">{s}</span><strong>{scan.findings.filter(f => f.severity === s).length}</strong></button>)}</div>
            <section className="panel"><div className="filter-toolbar"><label className="search-control"><Search size={17} /><input placeholder="Search findings, resources, or rule IDs…" aria-label="Search findings" value={query} onChange={e => setQuery(e.target.value)} /></label>{providerSelect}<label className="select-control"><Filter size={15} /><select aria-label="Filter finding status" value={status} onChange={e => setStatus(e.target.value as Status | 'all')}><option value="all">All statuses</option><option value="open">Open</option><option value="acknowledged">Acknowledged</option><option value="resolved">Resolved</option></select><ChevronDown size={14} /></label></div><div className="results-heading"><span><strong>{filteredFindings.length}</strong> findings{severity !== 'all' ? ` · ${severity} severity` : ''}</span><button className="text-button" onClick={resetFilters}>Clear filters</button></div>{filteredFindings.length ? findingTable(filteredFindings) : <EmptyState title="No findings match these filters" detail="Try a different provider, status, or search term." action={<button className="button secondary" onClick={resetFilters}>Clear filters</button>} />}</section><p className="page-footnote">Rule severity reflects the configuration baseline; ML anomalies are medium-severity review signals. A resolved status records team triage; it does not verify a cloud configuration change.</p>
          </>}
          {page === 'inventory' && <>
            <div className="section-intro"><h2>{scan.summary.resources} resources in your snapshot</h2><button className="button secondary small" disabled={busy} onClick={() => upload.current?.click()}><Upload size={15} />Import inventory</button></div>
            <section className="panel"><div className="filter-toolbar"><label className="search-control"><Search size={17} /><input placeholder="Search by name, region, or resource type…" aria-label="Search resources" value={query} onChange={e => setQuery(e.target.value)} /></label>{providerSelect}<span className="toolbar-note">{filteredResources.length} resources</span></div>{filteredResources.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Resource</th><th>Cloud provider</th><th>Region</th><th>Baseline result</th><th>Findings</th><th><span className="sr-only">Details</span></th></tr></thead><tbody>{filteredResources.map(r => {
              const checks = scan.checks.filter(c => c.resource_id === r.id && c.provider === r.provider);
              const findings = scan.findings.filter(f => f.resource_id === r.id && f.provider === r.provider);
              const outcome = checks.some(c => c.outcome === 'fail') ? 'fail' : checks.some(c => c.outcome === 'unknown') ? 'unknown' : 'pass';
              return <tr key={`${r.provider}:${r.id}`}><td><button className="finding-link" onClick={() => setResource(r)}><span className="resource-symbol"><ResourceIcon type={r.type} /></span><span><strong>{r.name}</strong><small>{resourceNames[r.type]}</small></span></button></td><td><span className="cloud-label"><ProviderMark provider={r.provider} small />{providerShort[r.provider]}</span></td><td>{r.region}</td><td><span className={`check-status ${outcome}`}>{outcome === 'pass' ? <CheckCircle2 size={15} /> : <CircleAlert size={15} />}{outcome === 'pass' ? 'Passed' : outcome === 'unknown' ? 'Unknown fields' : 'Needs attention'}</span></td><td><span className={findings.length ? 'finding-count' : 'muted'}>{findings.length}</span></td><td><button className="icon-button" onClick={() => setResource(r)} aria-label={`Inspect ${r.name}`}><ChevronRight size={17} /></button></td></tr>;
            })}</tbody></table></div> : <EmptyState title="No resources match your search" detail="Clear your filters to see all resources in this snapshot." action={<button className="button secondary" onClick={resetFilters}>Clear filters</button>} />}</section>
            <div className="import-note"><FileJson size={24} /><div><h3>Bring your own configuration snapshot</h3><p>Import a normalized JSON inventory (up to 2 MB and 1,000 resources). Use <code>data/demo_inventory.json</code> as the schema example. An import creates a new scan and becomes the latest inventory.</p></div><button className="text-button" disabled={busy} onClick={() => upload.current?.click()}>Choose JSON file <Plus size={16} /></button></div>
          </>}
          {page === 'history' && <>
            <div className="section-intro"><h2>{history.length} saved {history.length === 1 ? 'scan' : 'scans'}</h2><span>Latest 100 scans · stored locally</span></div>
            <section className="panel"><div className="table-scroll"><table className="data-table"><thead><tr><th>Scan</th><th>Completed</th><th>Source</th><th>Resources</th><th>Findings</th><th>Posture</th><th><span className="sr-only">Inspect</span></th></tr></thead><tbody>{history.map((s, index) => <tr key={s.id}><td><button className="finding-link" onClick={() => void inspectScan(s.id)}><span className="resource-symbol"><ShieldCheck size={19} /></span><span><strong>{s.name}{index === 0 && <span className="latest-tag">Latest</span>}</strong><small>{s.id.slice(0, 8)} · {s.duration_ms.toFixed(1)} ms analysis</small></span></button></td><td>{dateTime(s.created_at)}</td><td><span className="subtle-tag">{s.source === 'live' ? 'Live collection' : s.source === 'demo' ? 'Demo snapshot' : 'JSON import'}</span></td><td>{s.summary.resources}</td><td>{s.summary.findings ?? s.summary.failed}</td><td><strong>{s.summary.posture_score === null ? '—' : `${s.summary.posture_score}%`}</strong></td><td><button className="icon-button" disabled={busy} onClick={() => void inspectScan(s.id)} aria-label={`Inspect scan ${s.id.slice(0, 8)}`}><ChevronRight size={17} /></button></td></tr>)}</tbody></table></div></section><p className="page-footnote">Scan evidence and scores are saved as immutable snapshots. Finding statuses show the current team disposition across scans.</p>
          </>}
          {page === 'activity' && <ActivityAnalysis scan={scan} />}
          {page === 'model' && <ModelLab />}
          {page === 'connections' && <CloudConnections onCollected={async next => { setScan(next); setHistory(await request<ScanRecord[]>('/scans')); setToast('Read-only cloud collection completed. Review collection coverage.'); }} />}
          {page === 'brief' && <ProjectBrief rules={rules} />}
        </>}
      </main>
      <footer className="app-footer"><span>CloudSentinel <span className="footer-dot">·</span> AI-Based Automated Multi-Cloud Vulnerability Detector</span><span>Phase 2 / Configuration + activity</span></footer>
    </div>
    <input className="sr-only" ref={upload} type="file" accept=".json,application/json" aria-label="Import JSON inventory" onChange={e => { const file = e.target.files?.[0]; if (file) void importInventory(file); }} />
    {toast && <div className="toast" role="status"><CheckCircle2 size={19} /><span>{toast}</span><button className="icon-button" onClick={() => setToast('')} aria-label="Dismiss notification"><X size={16} /></button></div>}
    {finding && <Drawer title={finding.title} onClose={() => setFinding(null)}><div className="drawer-badges"><SeverityBadge severity={finding.severity} /><StatusBadge status={finding.status} /><span className="subtle-tag">{finding.detection_method === 'ml' ? 'Isolation Forest' : finding.rule_id}</span></div><p className="drawer-description">{finding.description}</p><div className="detail-card"><span className="eyebrow">AFFECTED RESOURCE</span><h3><ResourceIcon type={finding.resource_type} />{finding.resource_name}</h3><dl><dt>Cloud provider</dt><dd><ProviderMark provider={finding.provider} small />{providerNames[finding.provider]}</dd><dt>Region</dt><dd>{finding.region}</dd><dt>Account</dt><dd>{finding.account}</dd><dt>Resource ID</dt><dd className="mono">{finding.resource_id}</dd></dl></div><h3 className="drawer-section-title">{finding.detection_method === 'ml' ? 'Activity evidence' : 'Configuration evidence'}</h3><pre className="evidence">{JSON.stringify(finding.evidence, null, 2)}</pre><div className="remediation-card"><div><ShieldCheck size={20} /><h3>Recommended remediation</h3></div><p>{finding.remediation}</p><small>Guidance only. No cloud configuration is changed.</small></div><h3 className="drawer-section-title">Team disposition</h3><p className="drawer-help">Track your review. Resolving a finding does not change the saved scan score or verify remediation.</p><div className="status-actions">{(['open', 'acknowledged', 'resolved'] as Status[]).map(s => <button key={s} disabled={busy || finding.status === s} className={`button small ${finding.status === s ? 'primary' : 'secondary'}`} onClick={() => void updateStatus(s)}>{finding.status === s && <Check size={14} />}{statusNames[s]}</button>)}</div><h3 className="drawer-section-title">Triage history</h3>{eventError ? <p className="drawer-help">{eventError}</p> : events.length ? <ol className="event-list">{events.map((e, i) => <li key={`${e.created_at}-${i}`}><span>{statusNames[e.previous_status]} <ArrowRight size={12} /> {statusNames[e.status]}</span><small>{dateTime(e.created_at)}</small></li>)}</ol> : <p className="drawer-help">No triage changes recorded.</p>}</Drawer>}
    {resource && scan && <Drawer title={resource.name} onClose={() => setResource(null)}><div className="drawer-badges"><span className="cloud-label"><ProviderMark provider={resource.provider} small />{providerNames[resource.provider]}</span><span className="subtle-tag">{resourceNames[resource.type]}</span></div><div className="detail-card"><dl><dt>Region</dt><dd>{resource.region}</dd><dt>Account</dt><dd>{resource.account}</dd><dt>Resource ID</dt><dd className="mono">{resource.id}</dd></dl></div><h3 className="drawer-section-title">Normalized configuration</h3><pre className="evidence">{JSON.stringify(Object.fromEntries(Object.entries(resource.config).filter(([, v]) => v !== null)), null, 2)}</pre><h3 className="drawer-section-title">Baseline checks</h3><div className="check-list">{scan.checks.filter(c => c.resource_id === resource.id && c.provider === resource.provider).map(c => <div key={c.rule_id}><span><strong>{c.rule_id}</strong><small>{rules.find(r => r.id === c.rule_id)?.title}</small></span><span className={`check-status ${c.outcome}`}>{c.outcome === 'pass' ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />}{c.outcome}</span></div>)}</div><p className="drawer-help">Null or omitted fields are unknown. Only applicable checks are evaluated.</p></Drawer>}
    {pastScan && <Drawer title={pastScan.name} onClose={() => setPastScan(null)}><div className="drawer-badges"><span className="subtle-tag">{pastScan.source === 'live' ? 'Live collection' : pastScan.source === 'demo' ? 'Synthetic demo' : 'Imported snapshot'}</span><span className="muted">{dateTime(pastScan.created_at)}</span></div><div className="snapshot-stats"><div><strong>{pastScan.summary.resources}</strong><span>Resources</span></div><div><strong>{pastScan.summary.findings ?? pastScan.summary.failed}</strong><span>Findings</span></div><div><strong>{pastScan.summary.posture_score ?? '—'}{pastScan.summary.posture_score !== null ? '%' : ''}</strong><span>Posture</span></div></div><h3 className="drawer-section-title">Immutable scan summary</h3><pre className="evidence">{JSON.stringify(pastScan.summary, null, 2)}</pre><h3 className="drawer-section-title">Detected findings</h3>{pastScan.findings.length ? <div className="snapshot-findings">{pastScan.findings.map(f => <div key={f.id}><SeverityBadge severity={f.severity} /><span><strong>{f.title}</strong><small>{f.resource_name}</small></span></div>)}</div> : <p className="drawer-help">No failed checks in this snapshot.</p>}<p className="drawer-help">Snapshot ID: {pastScan.id}</p></Drawer>}
  </div>;
}

function Metric({ label, value, icon: Icon, tone, children }: { label: string; value: string | number; icon: LucideIcon; tone: string; children: ReactNode }) {
  return <section className="metric-card"><div className="metric-top"><span>{label}</span><span className={`metric-icon ${tone}`}><Icon size={18} strokeWidth={1.8} /></span></div><strong className="metric-value">{value}</strong>{children}</section>;
}
function Donut({ findings }: { findings: Finding[] }) {
  const colors = { critical: '#d85e65', high: '#edaa5b', medium: '#e7ce7e', low: '#6ca8c3' };
  let offset = 0;
  const stops = severities.map(s => { const count = findings.filter(f => f.severity === s).length; const start = offset; offset += findings.length ? count / findings.length * 100 : 0; return `${colors[s]} ${start}% ${offset}%`; });
  return <div className="donut" role="img" aria-label={`${findings.length} findings: ${severities.map(s => `${findings.filter(f => f.severity === s).length} ${s}`).join(', ')}`} style={{ background: findings.length ? `conic-gradient(${stops.join(',')})` : '#e8edeb' }}><div><strong>{findings.length}</strong><span>Total findings</span></div></div>;
}
function FlaskIcon() {
  return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M9 3h6m-5 0v6l-6 10a1 1 0 0 0 1 2h14a1 1 0 0 0 1-2L14 9V3M7 15h10"/><path d="M10 18h.01M14 17h.01" /></svg>;
}

function ProjectBrief({ rules }: { rules: Rule[] }) {
  return <div className="brief-content"><section className="brief-hero"><div className="brief-hero-icon"><ShieldCheck size={42} strokeWidth={1.4} /></div><span className="eyebrow">AI-BASED AUTOMATED MULTI-CLOUD VULNERABILITY DETECTOR</span><h2>Three clouds. One security perspective.</h2><p>Configuration visibility and activity analysis in one workspace. Phase 2 adds read-only collection and an inspectable anomaly model to the existing security baseline.</p><span className="brief-stage"><CheckCircle2 size={15} />Phase 2 · Collection and anomaly detection</span></section>
    <div className="brief-grid"><section className="panel brief-panel"><h2>The problem we are solving</h2><p>AWS, Azure, and GCP use different security models. Fragmented tools make it difficult to review storage exposure, permissions, and unusual access together.</p><p>Configuration rules detect defined weaknesses. Isolation Forest detects unusual hourly activity relative to a trained baseline. Both methods retain their evidence and provenance.</p></section><section className="panel brief-panel"><h2>Phase 2 capabilities</h2><ul className="deliverable-list">{['Read-only AWS, Azure, and GCP API collectors', 'Normalized events and hourly activity feature windows', 'Isolation Forest inference with insufficient-data handling', 'Independent training, calibration, and held-out evaluation', 'Model lab, activity review, and collection coverage'].map(item => <li key={item}><CheckCircle2 size={16} />{item}</li>)}</ul></section></div>
    <section className="panel architecture-panel"><div className="panel-heading"><div><h2>From cloud data to reviewable evidence</h2><p>The Phase 2 data flow</p></div><span className="subtle-tag">Local-first</span></div><div className="architecture-flow">{[{ icon: Cloud, title: 'Collect or import', text: 'Read-only APIs or JSON' }, { icon: Layers3, title: 'Normalize', text: 'Resources + activity windows' }, { icon: ShieldCheck, title: 'Analyze', text: 'Baseline rules + Isolation Forest' }, { icon: LayoutDashboard, title: 'Review', text: 'Evidence, triage, and reports' }].map(({ icon: Icon, title, text }, i) => <div className="flow-step" key={title}><div><Icon size={22} /><strong>{title}</strong><small>{text}</small></div>{i < 3 && <ArrowRight size={20} />}</div>)}</div></section>
    <section className="panel"><div className="panel-heading"><div><h2>Configuration baseline</h2><p>Six deterministic checks run alongside activity analysis</p></div><span className="subtle-tag">{rules.length} rules</span></div><div className="table-scroll"><table className="data-table"><thead><tr><th>Rule</th><th>Configuration check</th><th>Category</th><th>Severity</th></tr></thead><tbody>{rules.map(r => <tr key={r.id}><td className="mono">{r.id}</td><td><strong>{r.title}</strong></td><td>{r.category}</td><td><SeverityBadge severity={r.severity} /></td></tr>)}</tbody></table></div></section>
    <div className="roadmap"><div><span className="roadmap-number">01</span><div><span className="eyebrow">FOUNDATION</span><h3>Configuration baseline</h3><p>Normalized inventory, rule findings, persistent snapshots, triage, and reports.</p></div><span className="subtle-tag complete"><Check size={13} />Implemented</span></div><div className="roadmap-current"><span className="roadmap-number">02</span><div><span className="eyebrow">CURRENT PHASE</span><h3>Cloud collection and anomaly detection</h3><p>Read-only adapters, activity features, model training, scoring, and measured synthetic evaluation.</p></div><span className="subtle-tag complete"><Check size={13} />Implemented</span></div><div><span className="roadmap-number">03</span><div><span className="eyebrow">FUTURE WORK</span><h3>Continuous monitoring and hardening</h3><p>Scheduled collection, authentication, alerts, deployment, and validation on real accounts.</p></div><span className="subtle-tag">Planned</span></div></div>
    <p className="scope-note"><CircleAlert size={18} /><span>Collectors are tested with mocked provider APIs; no live-account verification is claimed. Synthetic model evaluation does not prove real-world accuracy or improvement over rules. Continuous monitoring and automatic remediation remain future work.</span></p></div>;
}
