import { ChevronRight, ShieldCheck } from 'lucide-react';
import type { ScanRecord } from '../../shared/api/client';
import { dateTime } from '../../shared/ui/components';

interface Props {
  history: ScanRecord[];
  inspectScan: (id: string) => Promise<void>;
  busy: boolean;
}

/** Render one workspace view; data loading and navigation stay in the app shell. */
export function HistoryPage({ history, inspectScan, busy }: Props) {
  return (
    <>
      <div className="section-intro">
        <h2>
          {history.length} saved {history.length === 1 ? 'scan' : 'scans'}
        </h2>
        <span>Latest 100 scans · stored locally</span>
      </div>
      <section className="panel">
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Scan</th>
                <th>Completed</th>
                <th>Source</th>
                <th>Resources</th>
                <th>Findings</th>
                <th>Posture</th>
                <th>
                  <span className="sr-only">Inspect</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {history.map((s, index) => (
                <tr key={s.id}>
                  <td>
                    <button className="finding-link" onClick={() => void inspectScan(s.id)}>
                      <span className="resource-symbol">
                        <ShieldCheck size={19} />
                      </span>
                      <span>
                        <strong>
                          {s.name}
                          {index === 0 && <span className="latest-tag">Latest</span>}
                        </strong>
                        <small>
                          {s.id.slice(0, 8)} · {s.duration_ms.toFixed(1)} ms analysis
                        </small>
                      </span>
                    </button>
                  </td>
                  <td>{dateTime(s.created_at)}</td>
                  <td>
                    <span className="subtle-tag">
                      {s.source === 'live'
                        ? 'Live collection'
                        : s.source === 'demo'
                        ? 'Demo snapshot'
                        : 'JSON import'}
                    </span>
                  </td>
                  <td>{s.summary.resources}</td>
                  <td>{s.summary.findings ?? s.summary.failed}</td>
                  <td>
                    <strong>
                      {s.summary.posture_score === null ? '—' : `${s.summary.posture_score}%`}
                    </strong>
                  </td>
                  <td>
                    <button
                      className="icon-button"
                      disabled={busy}
                      onClick={() => void inspectScan(s.id)}
                      aria-label={`Inspect scan ${s.id.slice(0, 8)}`}
                    >
                      <ChevronRight size={17} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <p className="page-footnote">
        Scan evidence and scores are saved as immutable snapshots. Finding statuses show the current
        team disposition across scans.
      </p>
    </>
  );
}
