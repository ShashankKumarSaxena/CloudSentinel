import { CircleAlert, ShieldCheck } from 'lucide-react';
import type { Rule } from '../../shared/api/types';
import { SeverityBadge } from '../../shared/ui/components';
import { useAuth } from '../auth/AuthProvider';

/** Describe actual detection coverage rather than implying a compliance verdict. */
export function ProjectBrief({ rules }: { rules: Rule[] }) {
  const { mode } = useAuth();
  return (
    <div className="brief-content">
      <section className="brief-hero">
        <div className="brief-hero-icon">
          <ShieldCheck size={42} />
        </div>
        <span className="eyebrow">DETECTION METHODS & COVERAGE</span>
        <h2>Understand what each finding means.</h2>
        <p>
          CloudSentinel combines explicit configuration checks with optional hourly activity
          analysis. Each snapshot preserves the source, account scope, collection coverage, and
          evidence used to make its findings.
        </p>
        <span className="brief-stage">
          {mode === 'demo'
            ? 'Demo workspace · synthetic fixtures'
            : 'Production workspace · approved cloud accounts'}
        </span>
      </section>
      <div className="brief-grid">
        <section className="panel brief-panel">
          <h2>Configuration analysis</h2>
          <p>
            Supported storage, identity, network, and logging settings are checked against the rules
            below. Missing evidence remains unknown. The posture score measures evaluated
            configuration checks, not overall account security or compliance.
          </p>
        </section>
        <section className="panel brief-panel">
          <h2>Activity analysis</h2>
          <p>
            Isolation Forest highlights unusual hourly activity. Production ML is disabled by
            default and requires an explicitly enabled, reviewed non-synthetic model. Scores are not
            probabilities or proof of malicious activity.
          </p>
        </section>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Implemented configuration checks</h2>
          <span className="subtle-tag">{rules.length} rules</span>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Rule</th>
                <th>Check</th>
                <th>Severity</th>
                <th>Scope</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id}>
                  <td>{rule.id}</td>
                  <td>{rule.title}</td>
                  <td>
                    <SeverityBadge severity={rule.severity} />
                  </td>
                  <td>{rule.type}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <p className="scope-note">
        <CircleAlert size={18} />
        <span>
          Collection is read-only and bounded. Partial coverage, unknown settings, and failed reads
          remain visible. Review provider-native effective permissions and organization policies
          before acting. CloudSentinel does not automatically change infrastructure.
        </span>
      </p>
    </div>
  );
}
