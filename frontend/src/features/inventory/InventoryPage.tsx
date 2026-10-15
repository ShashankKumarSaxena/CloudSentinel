import {
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  FileJson,
  Plus,
  Search,
  Upload,
} from 'lucide-react';
import type * as React from 'react';
import type { Resource, Scan } from '../../shared/api/client';
import {
  EmptyState,
  ProviderMark,
  providerShort,
  ResourceIcon,
  resourceNames,
} from '../../shared/ui/components';

interface Props {
  scan: Scan;
  busy: boolean;
  canMutate: boolean;
  upload: React.RefObject<HTMLInputElement | null>;
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  providerSelect: React.ReactNode;
  filteredResources: Resource[];
  setResource: React.Dispatch<React.SetStateAction<Resource | null>>;
  resetFilters: () => void;
}

/** Render one workspace view; data loading and navigation stay in the app shell. */
export function InventoryPage({
  scan,
  busy,
  canMutate,
  upload,
  query,
  setQuery,
  providerSelect,
  filteredResources,
  setResource,
  resetFilters,
}: Props) {
  return (
    <>
      <div className="section-intro">
        <h2>{scan.summary.resources} resources in your snapshot</h2>
        <button
          className="button secondary small"
          disabled={busy || !canMutate}
          onClick={() => upload.current?.click()}
        >
          <Upload size={15} />
          Import inventory
        </button>
      </div>
      <section className="panel">
        <div className="filter-toolbar">
          <label className="search-control">
            <Search size={17} />
            <input
              placeholder="Search by name, region, or resource type…"
              aria-label="Search resources"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          {providerSelect}
          <span className="toolbar-note">{filteredResources.length} resources</span>
        </div>
        {filteredResources.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Resource</th>
                  <th>Cloud provider</th>
                  <th>Region</th>
                  <th>Baseline result</th>
                  <th>Findings</th>
                  <th>
                    <span className="sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredResources.map((r) => {
                  const checks = scan.checks.filter(
                    (c) =>
                      c.resource_id === r.id &&
                      c.provider === r.provider &&
                      (!c.account || c.account === r.account),
                  );
                  const findings = scan.findings.filter(
                    (f) => f.resource_id === r.id && f.provider === r.provider,
                  );
                  const outcome = checks.some((c) => c.outcome === 'fail')
                    ? 'fail'
                    : checks.some((c) => c.outcome === 'unknown')
                    ? 'unknown'
                    : 'pass';
                  return (
                    <tr key={`${r.provider}:${r.id}`}>
                      <td>
                        <button className="finding-link" onClick={() => setResource(r)}>
                          <span className="resource-symbol">
                            <ResourceIcon type={r.type} />
                          </span>
                          <span>
                            <strong>{r.name}</strong>
                            <small>{resourceNames[r.type]}</small>
                          </span>
                        </button>
                      </td>
                      <td>
                        <span className="cloud-label">
                          <ProviderMark provider={r.provider} small />
                          {providerShort[r.provider]}
                        </span>
                      </td>
                      <td>{r.region}</td>
                      <td>
                        <span className={`check-status ${outcome}`}>
                          {outcome === 'pass' ? (
                            <CheckCircle2 size={15} />
                          ) : (
                            <CircleAlert size={15} />
                          )}
                          {outcome === 'pass'
                            ? 'Passed'
                            : outcome === 'unknown'
                            ? 'Unknown fields'
                            : 'Needs attention'}
                        </span>
                      </td>
                      <td>
                        <span className={findings.length ? 'finding-count' : 'muted'}>
                          {findings.length}
                        </span>
                      </td>
                      <td>
                        <button
                          className="icon-button"
                          onClick={() => setResource(r)}
                          aria-label={`Inspect ${r.name}`}
                        >
                          <ChevronRight size={17} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No resources match your search"
            detail="Clear your filters to see all resources in this snapshot."
            action={
              <button className="button secondary" onClick={resetFilters}>
                Clear filters
              </button>
            }
          />
        )}
      </section>
      <div className="import-note">
        <FileJson size={24} />
        <div>
          <h3>Bring your own configuration snapshot</h3>
          <p>
            Import a normalized JSON inventory (up to 2 MB and 1,000 resources). Use{' '}
            <code>data/demo_inventory.json</code> as the schema example. An import creates a new
            scan and becomes the latest inventory.
          </p>
        </div>
        <button
          className="text-button"
          disabled={busy || !canMutate}
          onClick={() => upload.current?.click()}
        >
          Choose JSON file <Plus size={16} />
        </button>
      </div>
    </>
  );
}
