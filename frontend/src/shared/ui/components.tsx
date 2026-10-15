import { Cloud, Database, Fingerprint, Network, ScrollText, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { useEffect, useRef } from 'react';
import type { Provider, ResourceType, Severity, Status } from '../api/client';

export const providerNames: Record<Provider, string> = {
  aws: 'Amazon Web Services',
  azure: 'Microsoft Azure',
  gcp: 'Google Cloud',
};
export const providerShort: Record<Provider, string> = { aws: 'AWS', azure: 'Azure', gcp: 'GCP' };
export const resourceNames: Record<ResourceType, string> = {
  storage: 'Object storage',
  identity: 'Identity',
  firewall: 'Network firewall',
  audit: 'Audit trail',
};
export const statusNames: Record<Status, string> = {
  open: 'Open',
  acknowledged: 'Acknowledged',
  resolved: 'Resolved',
};

export function ProviderMark({ provider, small = false }: { provider: Provider; small?: boolean }) {
  return (
    <span
      aria-label={providerShort[provider]}
      className={`provider-mark ${provider} ${small ? 'small' : ''}`}
    >
      {provider === 'aws' ? (
        <span className="aws-word">
          aws
          <span className="aws-smile" />
        </span>
      ) : provider === 'azure' ? (
        <svg viewBox="0 0 28 28" aria-hidden="true">
          <path d="M11 3h8L7 25H1Z" fill="#087dd1" />
          <path d="m19 3 8 22H9l4-7h7l-5-10Z" fill="#31a4ed" />
        </svg>
      ) : (
        <svg viewBox="0 0 32 28" aria-hidden="true">
          <path
            d="M9 22h14a7 7 0 0 0 0-14 9 9 0 0 0-15-2"
            fill="none"
            stroke="#4285f4"
            strokeWidth="5"
          />
          <path d="M8 6a9 9 0 0 1 15 2" fill="none" stroke="#ea4335" strokeWidth="5" />
          <path d="M8 6a9 9 0 0 0-2 8" fill="none" stroke="#fbbc04" strokeWidth="5" />
          <path d="M6 14a4 4 0 0 0 3 8h5" fill="none" stroke="#34a853" strokeWidth="5" />
        </svg>
      )}
    </span>
  );
}

export function ResourceIcon({ type, size = 18 }: { type: ResourceType; size?: number }) {
  const Icon =
    { storage: Database, identity: Fingerprint, firewall: Network, audit: ScrollText }[type] ??
    Cloud;
  return <Icon size={size} aria-hidden="true" />;
}
export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`badge severity-${severity}`}>
      <span className="badge-dot" />
      {severity}
    </span>
  );
}
export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`status status-${status}`}>
      <span />
      {statusNames[status]}
    </span>
  );
}
export function dateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}
export function EmptyState({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Cloud size={28} />
      </div>
      <h3>{title}</h3>
      <p>{detail}</p>
      {action}
    </div>
  );
}

export function Drawer({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const panel = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close.current();
      if (event.key !== 'Tab') return;
      const items = panel.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), a[href], select, input, [tabindex="0"]',
      );
      if (!items?.length) {
        event.preventDefault();
        return;
      }
      const first = items[0],
        last = items[items.length - 1];
      if (
        event.shiftKey &&
        (document.activeElement === first || document.activeElement === panel.current)
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || document.activeElement === panel.current)
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKey);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        tabIndex={-1}
        ref={panel}
      >
        <header>
          <span className="eyebrow">INSPECT & UNDERSTAND</span>
          <button className="icon-button" onClick={onClose} aria-label="Close details">
            <X size={20} />
          </button>
        </header>
        <h2 id="drawer-title">{title}</h2>
        {children}
      </section>
    </div>
  );
}
