import type { ReactNode } from 'react';
import type { ContextPart } from '../../types/agricultural';
import { formatRetrievedTime } from '../../utils/formatters';

export type SourceKey = 'weather' | 'soil' | 'yieldHistory';

/** A source's state on this page: the status the API returned, or still loading. */
export type SourceState = 'loading' | ContextPart<unknown>['status'];

export const SOURCE_META: Record<SourceKey, { provider: string; purpose: string; dot: string }> = {
  weather: { provider: 'NOAA NCEI', purpose: 'Weather', dot: 'bg-rain-500' },
  soil: { provider: 'USDA NRCS SSURGO', purpose: 'Soil', dot: 'bg-soil-500' },
  yieldHistory: { provider: 'USDA NASS Quick Stats', purpose: 'Yield history', dot: 'bg-leaf-600' },
};

const STATUS: Record<SourceState, { label: string; dot: string; text: string }> = {
  ok: { label: 'Connected', dot: 'bg-leaf-600', text: 'text-leaf-800' },
  unavailable: { label: 'Unavailable', dot: 'bg-stress-500', text: 'text-stress-700' },
  not_configured: { label: 'Not configured', dot: 'border border-faint', text: 'text-muted' },
  loading: { label: 'Checking…', dot: 'bg-faint ss-breathe', text: 'text-muted' },
};

/** The status the API reported for this source on this request. Never read from static metadata. */
export function StatusLabel({ state }: { state: SourceState }) {
  const s = STATUS[state];
  return (
    <span className={`inline-flex items-center gap-1.5 text-[13px] font-medium whitespace-nowrap ${s.text}`}>
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${s.dot}`} aria-hidden="true" />
      {s.label}
    </span>
  );
}

export function NotReported() {
  return <span className="text-faint">Not reported</span>;
}

/** Plain-language reason a source has no data, keeping the other panels usable. */
function Missing({ source, state, message }: { source: SourceKey; state: SourceState; message: string | null }) {
  const meta = SOURCE_META[source];
  const title =
    state === 'not_configured'
      ? `${meta.provider} requires an API key on the SoilSignal backend.`
      : `${meta.purpose} data temporarily unavailable`;
  return (
    <div className="rounded-xl border border-dashed border-line-strong px-5 py-6">
      <p className="text-[14px] font-medium text-ink">{title}</p>
      {message && <p className="mt-1 text-[13px] leading-relaxed text-muted">{message}</p>}
      <p className="mt-2 text-[13px] text-muted">The other sources on this page are unaffected.</p>
    </div>
  );
}

function Loading() {
  return (
    <div aria-busy="true" aria-label="Loading">
      <div className="ss-skeleton h-4 w-64 max-w-full rounded-md" />
      <div className="ss-skeleton mt-5 h-44 w-full rounded-lg" />
    </div>
  );
}

interface DataPanelProps {
  id: string;
  source: SourceKey;
  title: string;
  subtitle?: ReactNode;
  state: SourceState;
  /** The API's message for this source: why it is missing, or a note about a stale copy. */
  message: string | null;
  lineage?: ReactNode;
  children: ReactNode;
}

export function DataPanel({ id, source, title, subtitle, state, message, lineage, children }: DataPanelProps) {
  const meta = SOURCE_META[source];
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="scroll-mt-24 border-t border-line pt-8 sm:pt-10">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-[12px] font-medium tracking-wide text-muted uppercase">
            <span className={`h-2 w-2 rounded-full ${meta.dot}`} aria-hidden="true" />
            {meta.provider}
          </p>
          <h2 id={`${id}-heading`} className="mt-2 text-[20px] font-semibold tracking-[-0.01em] text-ink">
            {title}
          </h2>
          {subtitle && <div className="mt-1 text-[14px] leading-relaxed text-muted">{subtitle}</div>}
        </div>
        <StatusLabel state={state} />
      </div>

      <div className="mt-6">
        {state === 'loading' ? <Loading /> : state === 'ok' ? children : <Missing source={source} state={state} message={message} />}
      </div>

      {state === 'ok' && message && <p className="mt-4 text-[13px] text-sun-700">{message}</p>}
      {state === 'ok' && lineage}
    </section>
  );
}

interface LineageProps {
  source: string;
  retrievedAt: string;
  /** Values the source itself reports. */
  observed: string[];
  /** Values the SoilSignal backend calculates from them. */
  derived: string[];
}

/** Where a panel's data came from and what SoilSignal did with it. */
export function Lineage({ source, retrievedAt, observed, derived }: LineageProps) {
  return (
    <footer className="mt-8 rounded-xl bg-mist/50 px-5 py-4 text-[12px] leading-relaxed">
      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-3">
        <div>
          <dt className="text-muted">Source</dt>
          <dd className="mt-0.5 text-ink-soft">{source}</dd>
        </div>
        <div>
          <dt className="text-muted">Retrieved</dt>
          <dd className="data mt-0.5 text-ink-soft">{formatRetrievedTime(retrievedAt)}</dd>
        </div>
        <div>
          <dt className="text-muted">Processed by</dt>
          <dd className="mt-0.5 text-ink-soft">SoilSignal backend · normalized and cached</dd>
        </div>
        <div className="sm:col-span-3">
          <dt className="text-muted">Observed by the source</dt>
          <dd className="mt-1.5 flex flex-wrap gap-1.5">
            {observed.map((item) => (
              <span key={item} className="rounded-full border border-line-strong bg-surface px-2 py-0.5 text-ink-soft">
                {item}
              </span>
            ))}
          </dd>
        </div>
        <div className="sm:col-span-3">
          <dt className="text-muted">Derived by SoilSignal</dt>
          <dd className="mt-1.5 flex flex-wrap gap-1.5">
            {derived.map((item) => (
              <DerivedTag key={item}>{item}</DerivedTag>
            ))}
          </dd>
        </div>
      </dl>
    </footer>
  );
}

/** Dashed outline marks a value SoilSignal calculated rather than one the source reported. */
export function DerivedTag({ children }: { children: ReactNode }) {
  return <span className="rounded-full border border-dashed border-faint px-2 py-0.5 text-ink-soft">{children}</span>;
}

export interface Column<Row> {
  key: string;
  label: string;
  numeric?: boolean;
  render: (row: Row) => ReactNode;
}

/** The normalized values as a plain table (the Data view). */
export function DataTable<Row>({ caption, columns, rows, rowKey }: { caption: string; columns: Column<Row>[]; rows: Row[]; rowKey: (row: Row) => string }) {
  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <table className="w-full min-w-max border-collapse text-[13px]">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line-strong">
            {columns.map((c) => (
              <th key={c.key} scope="col" className={`px-3 py-2 font-medium whitespace-nowrap text-muted first:pl-0 ${c.numeric ? 'text-right' : 'text-left'}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-line last:border-b-0 hover:bg-mist/50">
              {columns.map((c) => (
                <td key={c.key} className={`px-3 py-2.5 text-ink first:pl-0 ${c.numeric ? 'data text-right tabular-nums' : ''}`}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
