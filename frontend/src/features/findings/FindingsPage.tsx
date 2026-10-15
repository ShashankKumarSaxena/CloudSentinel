import { ChevronDown, Filter, Search } from 'lucide-react';
import type * as React from 'react';
import type { Finding, Scan, Severity, Status } from '../../shared/api/client';
import { severities } from '../../shared/constants';
import { EmptyState } from '../../shared/ui/components';

interface Props {
  severity: Severity | 'all';
  setSeverity: React.Dispatch<React.SetStateAction<'all' | Severity>>;
  scan: Scan;
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  providerSelect: React.ReactNode;
  status: Status | 'all';
  setStatus: React.Dispatch<React.SetStateAction<Status | 'all'>>;
  filteredFindings: Finding[];
  resetFilters: () => void;
  findingTable: (items: Finding[], compact?: boolean) => React.ReactNode;
}

/** Render one workspace view; data loading and navigation stay in the app shell. */
export function FindingsPage({
  severity,
  setSeverity,
  scan,
  query,
  setQuery,
  providerSelect,
  status,
  setStatus,
  filteredFindings,
  resetFilters,
  findingTable,
}: Props) {
  return (
    <>
      <div className="finding-summary">
        {severities.map((s) => (
          <button
            className={`severity-summary ${severity === s ? 'selected' : ''}`}
            key={s}
            onClick={() => setSeverity(severity === s ? 'all' : s)}
          >
            <span className={`legend-dot ${s}`} />
            <span className="capitalize">{s}</span>
            <strong>{scan.findings.filter((f) => f.severity === s).length}</strong>
          </button>
        ))}
      </div>
      <section className="panel">
        <div className="filter-toolbar">
          <label className="search-control">
            <Search size={17} />
            <input
              placeholder="Search findings, resources, or rule IDs…"
              aria-label="Search findings"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          {providerSelect}
          <label className="select-control">
            <Filter size={15} />
            <select
              aria-label="Filter finding status"
              value={status}
              onChange={(e) => setStatus(e.target.value as Status | 'all')}
            >
              <option value="all">All statuses</option>
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
            </select>
            <ChevronDown size={14} />
          </label>
        </div>
        <div className="results-heading">
          <span>
            <strong>{filteredFindings.length}</strong> findings
            {severity !== 'all' ? ` · ${severity} severity` : ''}
          </span>
          <button className="text-button" onClick={resetFilters}>
            Clear filters
          </button>
        </div>
        {filteredFindings.length ? (
          findingTable(filteredFindings)
        ) : (
          <EmptyState
            title="No findings match these filters"
            detail="Try a different provider, status, or search term."
            action={
              <button className="button secondary" onClick={resetFilters}>
                Clear filters
              </button>
            }
          />
        )}
      </section>
      <p className="page-footnote">
        Rule severity reflects the configuration baseline; ML anomalies are medium-severity review
        signals. A resolved status records team triage; it does not verify a cloud configuration
        change.
      </p>
    </>
  );
}
