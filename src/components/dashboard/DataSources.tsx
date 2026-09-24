import type { DataSource } from '../../types/agricultural';
import { DataBadge } from '../common/DataBadge';

interface DataSourcesProps {
  sources: DataSource[];
}

/**
 * Provenance, stated plainly: what the challenge provides and which external
 * enrichments are only candidates. Nothing here claims a live connection.
 */
export function DataSources({ sources }: DataSourcesProps) {
  const challenge = sources.filter((s) => s.role === 'challenge');
  const candidates = sources.filter((s) => s.role === 'candidate');

  return (
    <section aria-labelledby="provenance-heading">
      <h2 id="provenance-heading" className="text-[16px] font-semibold tracking-[-0.01em] text-ink">
        Data provenance
      </h2>

      <div className="mt-5">
        <h3 className="text-[12px] font-medium tracking-wide text-muted uppercase">Challenge-provided</h3>
        <ul className="mt-2">
          {challenge.map((s) => (
            <li key={s.id} className="flex flex-col gap-1 border-t border-line py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
              <div>
                <div className="text-[14px] font-medium text-ink">{s.name}</div>
                <p className="mt-0.5 text-[13px] leading-relaxed text-muted">{s.detail}</p>
              </div>
              <DataBadge variant="challenge" className="self-start" />
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-5">
        <h3 className="text-[12px] font-medium tracking-wide text-muted uppercase">Candidate external enrichment</h3>
        <ul className="mt-2">
          {candidates.map((s) => (
            <li key={s.id} className="flex items-baseline justify-between gap-6 border-t border-line py-2.5">
              <span className="text-[14px] text-ink">{s.name}</span>
              <span className="text-right text-[13px] text-muted">{s.statusLabel}</span>
            </li>
          ))}
        </ul>
      </div>

      <p className="mt-4 text-[12px] leading-relaxed text-muted">
        Candidate sources are not connected yet. The challenge rules and the actual dataset will determine the final
        integrations.
      </p>
    </section>
  );
}
