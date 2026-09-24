import type { DataSource } from '../../types/agricultural';
import { DataBadge } from '../common/DataBadge';

interface DataSourcesProps {
  sources: DataSource[];
}

/**
 * Provenance, stated plainly: what the challenge provides, which public datasets
 * are already connected, and which enrichments are only candidates.
 */
export function DataSources({ sources }: DataSourcesProps) {
  const challenge = sources.filter((s) => s.role === 'challenge');
  const connected = sources.filter((s) => s.role === 'public');
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

      {connected.length > 0 && (
        <div className="mt-5">
          <h3 className="text-[12px] font-medium tracking-wide text-muted uppercase">Connected public data</h3>
          <ul className="mt-2">
            {connected.map((s) => (
              <li key={s.id} className="flex flex-col gap-1 border-t border-line py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
                <div>
                  <div className="text-[14px] font-medium text-ink">{s.name}</div>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-muted">{s.detail}</p>
                </div>
                <DataBadge variant="public" className="self-start" />
              </li>
            ))}
          </ul>
        </div>
      )}

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
        Connected sources are looked up from each field's coordinates by the SoilSignal backend. Candidate sources are not
        connected yet; the challenge rules and the actual dataset will determine the final integrations.
      </p>
    </section>
  );
}
