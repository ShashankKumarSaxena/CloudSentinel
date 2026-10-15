import { CircleAlert, FileJson, FlaskConical, LoaderCircle, RefreshCw, Upload } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { ModelMetrics, ModelStatus } from '../../shared/api/client';
import { request } from '../../shared/api/client';
import { dateTime, EmptyState } from '../../shared/ui/components';
import { useAuth } from '../auth/AuthProvider';

function EvaluationTable({ model }: { model: ModelStatus }) {
  const metrics: { key: keyof ModelMetrics; label: string; percent?: boolean }[] = [
    { key: 'precision', label: 'Precision', percent: true },
    { key: 'recall', label: 'Recall', percent: true },
    { key: 'f1', label: 'F1 score', percent: true },
    { key: 'false_positive_rate', label: 'False-positive rate', percent: true },
    { key: 'true_positive', label: 'True positives' },
    { key: 'false_positive', label: 'False positives' },
    { key: 'false_negative', label: 'Missed anomalies' },
    { key: 'true_negative', label: 'True negatives' },
    { key: 'roc_auc', label: 'ROC AUC' },
  ];
  const format = (value: number | null, percent?: boolean) =>
    value === null ? '—' : percent ? `${(value * 100).toFixed(1)}%` : value;
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Held-out evaluation</th>
            <th>Isolation Forest</th>
            <th>Fixed activity baseline</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={m.key}>
              <td>{m.label}</td>
              <td>
                <strong>{format(model.evaluation.model[m.key], m.percent)}</strong>
              </td>
              <td>{format(model.evaluation.activity_baseline[m.key], m.percent)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ModelLab() {
  const { canManage, mode } = useAuth();
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const upload = useRef<HTMLInputElement>(null);
  useEffect(() => {
    request<ModelStatus>('/model')
      .then(setModel)
      .catch((e) => setError(e.message));
  }, []);
  async function train(file?: File) {
    setBusy(true);
    setError('');
    try {
      if (file && file.size > 2 * 1024 * 1024)
        throw new Error('Training dataset must be smaller than 2 MB.');
      const data = file ? await file.text() : undefined;
      if (data) {
        try {
          JSON.parse(data);
        } catch {
          throw new Error('Choose a valid JSON training dataset.');
        }
      }
      setModel(
        await request<ModelStatus>(file ? '/model/train' : '/model/train/demo', {
          method: 'POST',
          body: data,
          signal: AbortSignal.timeout(120000),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      if (upload.current) upload.current.value = '';
    }
  }
  return (
    <>
      {error && (
        <div className="error-banner" role="alert">
          <CircleAlert size={18} />
          <p>{error}</p>
        </div>
      )}
      <div className="section-intro">
        <h2>Isolation Forest activity detector</h2>
        <div className="heading-actions">
          <button
            className="button secondary small"
            disabled={busy || !canManage || mode === 'production'}
            onClick={() => upload.current?.click()}
          >
            <Upload size={14} />
            Train from dataset
          </button>
          <button
            className="button primary small"
            disabled={busy || !canManage || mode === 'production'}
            onClick={() => void train()}
          >
            {busy ? <LoaderCircle className="spinning" size={14} /> : <RefreshCw size={14} />}
            {busy ? 'Training…' : 'Retrain synthetic model'}
          </button>
        </div>
      </div>
      {!model ? (
        <EmptyState
          title="Loading model details"
          detail="Model metadata and evaluation results are stored locally."
        />
      ) : !model.ready ? (
        <EmptyState
          title="Model is not ready"
          detail={
            mode === 'demo'
              ? 'Train the synthetic model or upload a reviewed dataset.'
              : 'Configuration checks are active. Review and install a non-synthetic model offline before explicitly enabling production activity scoring.'
          }
        />
      ) : (
        <>
          <div className="model-summary panel">
            <div>
              <span className="eyebrow">UNSUPERVISED ANOMALY DETECTION</span>
              <h2>{model.algorithm}</h2>
              <p>
                {model.id} · {dateTime(model.created_at)}
              </p>
            </div>
            <span className="subtle-tag">
              {model.provenance === 'synthetic'
                ? 'Synthetic training & evaluation'
                : 'User-labeled dataset'}
            </span>
          </div>
          <div className="feature-metrics">
            {[
              ['Normal training rows', model.training_samples],
              ['Normal calibration rows', model.calibration_samples],
              ['Held-out evaluation rows', model.evaluation_samples],
              ['Decision threshold', model.threshold.toFixed(3)],
            ].map(([label, value]) => (
              <div className="metric-card" key={label}>
                <span className="metric-note">{label}</span>
                <strong className="metric-value">{value}</strong>
              </div>
            ))}
          </div>
          <div className="ml-notice">
            <FlaskConical size={21} />
            <div>
              <strong>Measured results, with clear limits</strong>
              <p>
                {model.notice} Training, calibration, and evaluation rows are separate. The model is
                not assumed to outperform the fixed baseline.
              </p>
            </div>
          </div>
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Model versus activity baseline</h2>
                <p>Both methods are evaluated on the same held-out activity labels</p>
              </div>
            </div>
            <EvaluationTable model={model} />
          </section>
          <section className="panel feature-panel">
            <div className="panel-heading">
              <div>
                <h2>Scenario coverage</h2>
                <p>False positives and missed anomalies remain visible</p>
              </div>
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Scenario</th>
                    <th>Samples</th>
                    <th>Actual anomalies</th>
                    <th>Flagged by model</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(model.evaluation.scenarios).map(([name, value]) => (
                    <tr key={name}>
                      <td className="capitalize">{name.replaceAll('_', ' ')}</td>
                      <td>{value.samples}</td>
                      <td>{value.actual_anomalies}</td>
                      <td>{value.flagged}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <div className="import-note">
            <FileJson size={23} />
            <div>
              <h3>Train on reviewed activity</h3>
              <p>
                Upload JSON with independent train, calibration, and evaluation splits. Training and
                calibration require normal labels. Evaluation requires both labels. See the dataset
                contract in docs/model.md.
              </p>
            </div>
          </div>
        </>
      )}
      <input
        className="sr-only"
        type="file"
        accept=".json,application/json"
        ref={upload}
        aria-label="Upload training dataset"
        onChange={(e) => {
          if (e.target.files?.[0]) void train(e.target.files[0]);
        }}
      />
    </>
  );
}
