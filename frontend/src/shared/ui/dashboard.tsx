import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import type { Finding } from '../api/client';
import { severities } from '../constants';

export function Metric({
  label,
  value,
  icon: Icon,
  tone,
  children,
}: {
  label: string;
  value: string | number;
  icon: LucideIcon;
  tone: string;
  children: ReactNode;
}) {
  return (
    <section className="metric-card">
      <div className="metric-top">
        <span>{label}</span>
        <span className={`metric-icon ${tone}`}>
          <Icon size={18} strokeWidth={1.8} />
        </span>
      </div>
      <strong className="metric-value">{value}</strong>
      {children}
    </section>
  );
}

export function Donut({ findings }: { findings: Finding[] }) {
  const colors = { critical: '#d85e65', high: '#edaa5b', medium: '#e7ce7e', low: '#6ca8c3' };
  let offset = 0;
  const stops = severities.map((s) => {
    const count = findings.filter((f) => f.severity === s).length;
    const start = offset;
    offset += findings.length ? (count / findings.length) * 100 : 0;
    return `${colors[s]} ${start}% ${offset}%`;
  });
  return (
    <div
      className="donut"
      role="img"
      aria-label={`${findings.length} findings: ${severities
        .map((s) => `${findings.filter((f) => f.severity === s).length} ${s}`)
        .join(', ')}`}
      style={{ background: findings.length ? `conic-gradient(${stops.join(',')})` : '#e8edeb' }}
    >
      <div>
        <strong>{findings.length}</strong>
        <span>Total findings</span>
      </div>
    </div>
  );
}

export function FlaskIcon() {
  return (
    <svg
      width="19"
      height="19"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      aria-hidden="true"
    >
      <path d="M9 3h6m-5 0v6l-6 10a1 1 0 0 0 1 2h14a1 1 0 0 0 1-2L14 9V3M7 15h10" />
      <path d="M10 18h.01M14 17h.01" />
    </svg>
  );
}
