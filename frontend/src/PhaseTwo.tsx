import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowRight, CheckCircle2, CircleAlert, Cloud, FileJson, FlaskConical, LoaderCircle, RefreshCw, ShieldCheck, Upload } from 'lucide-react';
import { useAuth } from './Auth';
import { request } from './api';
import type { ActivityWindow, Connector, ModelMetrics, ModelStatus, Provider, Scan } from './api';
import { dateTime, Drawer, EmptyState, ProviderMark, providerNames, providerShort } from './components';

export function ActivityAnalysis({ scan }: { scan: Scan }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [selected, setSelected] = useState<ActivityWindow | null>(null);
  const windows = scan.activity.windows;
  const filtered = windows.filter(w => (status === 'all' || w.status === status) && `${w.principal} ${w.provider} ${w.account}`.toLowerCase().includes(query.toLowerCase()));
  return <>
    <div className="phase-two-metrics">{[
      ['Normalized events', scan.activity.event_count], ['Hourly windows', windows.length],
      ['ML anomalies', windows.filter(w => w.status === 'anomaly').length], ['Insufficient data', windows.filter(w => w.status === 'insufficient_data').length],
    ].map(([label, value]) => <div className="metric-card" key={label}><span className="metric-note">{label}</span><strong className="metric-value">{value}</strong></div>)}</div>
    <div className="ml-notice"><Activity size={20} /><div><strong>{scan.activity.model ? `${scan.activity.model.algorithm} · ${scan.activity.model.id}` : 'No activity model in this historical scan'}</strong><p>{scan.activity.model?.provenance === 'synthetic' ? 'This model was trained on synthetic normal activity. Scores are experimental review signals, not attack probabilities.' : 'Scores measure unusual behavior relative to the model baseline. Review alerts with supporting audit events.'}</p></div></div>
    <section className="panel"><div className="filter-toolbar"><label className="search-control"><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search principals, clouds, or accounts…" aria-label="Search activity windows" /></label><label className="select-control"><select value={status} onChange={e => setStatus(e.target.value)} aria-label="Filter activity outcome"><option value="all">All outcomes</option><option value="anomaly">Anomalies</option><option value="normal">Normal</option><option value="insufficient_data">Insufficient data</option></select></label></div>{filtered.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Principal / account</th><th>Cloud</th><th>Window (local time)</th><th>Events</th><th>Model score</th><th>Outcome</th><th><span className="sr-only">Details</span></th></tr></thead><tbody>{filtered.map(w => <tr key={w.id}><td><button className="finding-link" onClick={() => setSelected(w)}><span className="resource-symbol"><Activity size={17} /></span><span><strong>{w.principal}</strong><small>{w.account}</small></span></button></td><td><span className="cloud-label"><ProviderMark provider={w.provider} small />{providerShort[w.provider]}</span></td><td>{dateTime(w.window_start)}</td><td>{w.features.event_count}</td><td>{w.score === null ? '—' : w.score.toFixed(3)}</td><td><span className={`check-status ${w.status === 'normal' ? 'pass' : w.status === 'anomaly' ? 'fail' : 'unknown'}`}>{w.status === 'normal' ? <CheckCircle2 size={15} /> : <CircleAlert size={15} />}{w.status.replaceAll('_', ' ')}</span></td><td><button className="icon-button" aria-label={`Inspect activity for ${w.principal}`} onClick={() => setSelected(w)}><ArrowRight size={16} /></button></td></tr>)}</tbody></table></div> : <EmptyState title={windows.length ? 'No activity matches your filters' : 'No activity in this snapshot'} detail="Run the activity demo or import an inventory with normalized events. Configuration-only snapshots remain supported." />}</section>
    <p className="page-footnote">Events are grouped by cloud, account, principal, and UTC hour. At least five events and complete features are required for scoring. Off-hours mean 22:00–05:59 UTC and are not automatically malicious.</p>
    {selected && <Drawer title="Activity window" onClose={() => setSelected(null)}><div className="drawer-badges"><span className="cloud-label"><ProviderMark provider={selected.provider} small />{providerNames[selected.provider]}</span><span className="subtle-tag">{selected.status.replaceAll('_', ' ')}</span></div><div className="detail-card"><dl><dt>Principal</dt><dd>{selected.principal}</dd><dt>Account</dt><dd>{selected.account}</dd><dt>UTC window</dt><dd>{selected.window_start}</dd><dt>Model score</dt><dd>{selected.score?.toFixed(6) ?? 'Not scored'}</dd><dt>Threshold</dt><dd>{selected.threshold.toFixed(6)}</dd></dl></div><h3 className="drawer-section-title">Feature evidence</h3><pre className="evidence">{JSON.stringify(selected.features, null, 2)}</pre>{selected.missing_features.length > 0 && <p className="drawer-help">Missing: {selected.missing_features.join(', ')}. Missing values are never treated as safe.</p>}<h3 className="drawer-section-title">Deviation signals</h3><p className="drawer-help">These compare features with the training baseline; they are review aids, not causal explanations of the model.</p><div className="check-list">{selected.signals.map(s => <div key={s.feature}><span><strong>{s.feature.replaceAll('_', ' ')}</strong><small>Observed value: {s.value}</small></span><span>{s.baseline_deviation.toFixed(2)}× baseline width</span></div>)}</div><h3 className="drawer-section-title">Observed operations</h3><pre className="evidence">{selected.actions.join('\n')}</pre></Drawer>}
  </>;
}

function EvaluationTable({ model }: { model: ModelStatus }) {
  const metrics: { key: keyof ModelMetrics; label: string; percent?: boolean }[] = [
    { key: 'precision', label: 'Precision', percent: true }, { key: 'recall', label: 'Recall', percent: true },
    { key: 'f1', label: 'F1 score', percent: true }, { key: 'false_positive_rate', label: 'False-positive rate', percent: true },
    { key: 'true_positive', label: 'True positives' }, { key: 'false_positive', label: 'False positives' },
    { key: 'false_negative', label: 'Missed anomalies' }, { key: 'true_negative', label: 'True negatives' }, { key: 'roc_auc', label: 'ROC AUC' },
  ];
  const format = (value: number | null, percent?: boolean) => value === null ? '—' : percent ? `${(value * 100).toFixed(1)}%` : value;
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>Held-out evaluation</th><th>Isolation Forest</th><th>Fixed activity baseline</th></tr></thead><tbody>{metrics.map(m => <tr key={m.key}><td>{m.label}</td><td><strong>{format(model.evaluation.model[m.key], m.percent)}</strong></td><td>{format(model.evaluation.activity_baseline[m.key], m.percent)}</td></tr>)}</tbody></table></div>;
}

export function ModelLab() {
  const { canManage } = useAuth();
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const upload = useRef<HTMLInputElement>(null);
  useEffect(() => { request<ModelStatus>('/model').then(setModel).catch(e => setError(e.message)); }, []);
  async function train(file?: File) {
    setBusy(true); setError('');
    try {
      if (file && file.size > 2 * 1024 * 1024) throw new Error('Training dataset must be smaller than 2 MB.');
      const data = file ? await file.text() : undefined;
      if (data) { try { JSON.parse(data); } catch { throw new Error('Choose a valid JSON training dataset.'); } }
      setModel(await request<ModelStatus>(file ? '/model/train' : '/model/train/demo', { method: 'POST', body: data, signal: AbortSignal.timeout(120000) }));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); if (upload.current) upload.current.value = ''; }
  }
  return <>
    {error && <div className="error-banner" role="alert"><CircleAlert size={18} /><p>{error}</p></div>}
    <div className="section-intro"><h2>Isolation Forest activity detector</h2><div className="heading-actions"><button className="button secondary small" disabled={busy || !canManage} onClick={() => upload.current?.click()}><Upload size={14} />Train from dataset</button><button className="button primary small" disabled={busy || !canManage} onClick={() => void train()}>{busy ? <LoaderCircle className="spinning" size={14} /> : <RefreshCw size={14} />}{busy ? 'Training…' : 'Retrain synthetic model'}</button></div></div>
    {!model ? <EmptyState title="Loading model details" detail="Model metadata and evaluation results are stored locally." /> : !model.ready ? <EmptyState title="Model is not ready" detail="Train the synthetic model or upload a reviewed dataset." /> : <>
      <div className="model-summary panel"><div><span className="eyebrow">UNSUPERVISED ANOMALY DETECTION</span><h2>{model.algorithm}</h2><p>{model.id} · {dateTime(model.created_at)}</p></div><span className="subtle-tag">{model.provenance === 'synthetic' ? 'Synthetic training & evaluation' : 'User-labeled dataset'}</span></div>
      <div className="phase-two-metrics">{[['Normal training rows', model.training_samples], ['Normal calibration rows', model.calibration_samples], ['Held-out evaluation rows', model.evaluation_samples], ['Decision threshold', model.threshold.toFixed(3)]].map(([label, value]) => <div className="metric-card" key={label}><span className="metric-note">{label}</span><strong className="metric-value">{value}</strong></div>)}</div>
      <div className="ml-notice"><FlaskConical size={21} /><div><strong>Measured results, with clear limits</strong><p>{model.notice} Training, calibration, and evaluation rows are separate. The model is not assumed to outperform the fixed baseline.</p></div></div>
      <section className="panel"><div className="panel-heading"><div><h2>Model versus activity baseline</h2><p>Both methods are evaluated on the same held-out activity labels</p></div></div><EvaluationTable model={model} /></section>
      <section className="panel phase-two-panel"><div className="panel-heading"><div><h2>Scenario coverage</h2><p>False positives and missed anomalies remain visible</p></div></div><div className="table-scroll"><table className="data-table"><thead><tr><th>Scenario</th><th>Samples</th><th>Actual anomalies</th><th>Flagged by model</th></tr></thead><tbody>{Object.entries(model.evaluation.scenarios).map(([name, value]) => <tr key={name}><td className="capitalize">{name.replaceAll('_', ' ')}</td><td>{value.samples}</td><td>{value.actual_anomalies}</td><td>{value.flagged}</td></tr>)}</tbody></table></div></section>
      <div className="import-note"><FileJson size={23} /><div><h3>Train on reviewed activity</h3><p>Upload JSON with independent train, calibration, and evaluation splits. Training and calibration require normal labels. Evaluation requires both labels. See the dataset contract in docs/model.md.</p></div></div>
    </>}
    <input className="sr-only" type="file" accept=".json,application/json" ref={upload} aria-label="Upload training dataset" onChange={e => { if (e.target.files?.[0]) void train(e.target.files[0]); }} />
  </>;
}

export function CloudConnections({ onCollected }: { onCollected: (scan: Scan) => Promise<void> }) {
  const { canMutate } = useAuth();
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [provider, setProvider] = useState<Provider>('aws');
  const [account, setAccount] = useState('');
  const [region, setRegion] = useState('ap-south-1');
  const [hours, setHours] = useState(24);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<Scan | null>(null);
  useEffect(() => { request<Connector[]>('/connectors').then(setConnectors).catch(e => setError(e.message)); }, []);
  async function collect() {
    setBusy(true); setError('');
    try {
      const scan = await request<Scan>('/scans/collect', { method: 'POST', body: JSON.stringify({ provider, region, account: account || null, lookback_hours: hours }), signal: AbortSignal.timeout(180000) });
      setResult(scan); await onCollected(scan);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <>
    <div className="ml-notice"><ShieldCheck size={21} /><div><strong>Read-only collection, started by you</strong><p>Credentials stay in your local provider SDK or CLI. This page accepts account identifiers only. A collection creates a live snapshot and never changes cloud infrastructure.</p></div></div>
    <div className="connection-grid">{connectors.map(c => <button className={`connection-card panel ${provider === c.provider ? 'selected' : ''}`} key={c.provider} onClick={() => { setProvider(c.provider); setAccount(''); setResult(null); }} disabled={busy}><ProviderMark provider={c.provider} /><h3>{providerNames[c.provider]}</h3><span className="subtle-tag">{c.configured ? 'Local configuration detected' : 'Local setup needed'}</span><p>{c.scope}</p><small>{c.credential_source}</small></button>)}</div>
    <section className="panel collection-form"><h2>Collect a configuration and activity snapshot</h2><p>{connectors.find(c => c.provider === provider)?.requires}</p><form onSubmit={e => { e.preventDefault(); void collect(); }}><label>{provider === 'azure' ? 'Subscription ID' : provider === 'gcp' ? 'Project ID' : 'Expected account ID (optional)'}<input value={account} maxLength={80} pattern="[a-zA-Z0-9-]+" onChange={e => setAccount(e.target.value)} placeholder={provider === 'aws' ? 'Use the active local AWS account' : 'Use form value or local environment variable'} disabled={busy} /></label>{provider === 'aws' && <label>AWS region<input value={region} pattern="[a-z0-9-]+" required onChange={e => setRegion(e.target.value)} disabled={busy} /></label>}<label>Activity lookback<select value={hours} onChange={e => setHours(Number(e.target.value))} disabled={busy}><option value={6}>Last 6 hours</option><option value={24}>Last 24 hours</option><option value={72}>Last 3 days</option><option value={168}>Last 7 days</option></select></label><button className="button primary" disabled={busy || !connectors.length || !canMutate}>{busy ? <LoaderCircle className="spinning" size={16} /> : <Cloud size={16} />}{busy ? 'Collecting…' : `Collect from ${providerShort[provider]}`}</button></form></section>
    {error && <div className="error-banner" role="alert"><CircleAlert size={19} /><p>{error}</p></div>}
    {result?.collection && <section className="panel phase-two-panel"><div className="panel-heading"><div><h2>Collection coverage</h2><p>{result.collection.partial ? 'Partial collection — review unavailable scopes before interpreting results' : 'Requested scopes collected'} · {result.resources.length} resources</p></div></div><div className="coverage-list">{result.collection.coverage.map((c, i) => <div key={i}><span className={`check-status ${c.status === 'collected' ? 'pass' : 'unknown'}`}>{c.status === 'collected' ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />}{c.status}</span><div><strong>{c.scope}</strong>{c.message && <p>{c.message}</p>}</div></div>)}</div></section>}
    <p className="page-footnote">Collectors are bounded and on demand. An unavailable scope is not safe. Azure/GCP CLI availability and AWS profile detection do not verify permissions. A failed collection preserves the latest valid scan.</p>
  </>;
}
