import { useEffect, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import type { FinalResults, SitePerformance } from '../../types/results';
import type { TrialSite } from '../../types/sites';
import { getFinalResults, imageryGain, plateauStage } from '../../services/results';
import { getTrialSites } from '../../services/sites';
import { Link } from '../../utils/router';
import { Reveal } from '../common/Reveal';

const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];
const count = (n: number) => WORDS[n] ?? n.toLocaleString('en-US');

interface Finding {
  site: SitePerformance;
  name: string;
  preR2: number;
  r2: number;
  dap: number;
  preWidth: number | null;
  width: number | null;
}

/**
 * The published results in a few sentences, every number read from them: the sites where
 * satellite imagery changed the forecast most, the site where it changed least, and the
 * matched UAV comparison. Hidden until the results exist.
 */
export function ResultsSummary() {
  const [results, setResults] = useState<FinalResults | null>(null);
  const [sites, setSites] = useState<TrialSite[]>([]);

  useEffect(() => {
    let active = true;
    getFinalResults()
      .then((r) => active && setResults(r))
      .catch(() => undefined);
    getTrialSites()
      .then((list) => active && setSites(list))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  if (results?.status !== 'ready' || results.sitePerformance.length === 0) return null;

  const name = (id: string) => sites.find((s) => s.id.toLowerCase() === id.toLowerCase())?.name ?? id;
  const plots = results.plotCounts.reduce((n, c) => n + c.plots, 0);
  const season = results.plotCounts[0]?.season;
  const findings: Finding[] = results.sitePerformance
    .map((site) => {
      const at = plateauStage(site, 'r2');
      if (!at || at.r2 == null || site.preseason?.r2 == null) return null;
      return {
        site,
        name: name(site.site),
        preR2: site.preseason.r2,
        r2: at.r2,
        dap: at.dap,
        preWidth: site.preseason.medianIntervalWidth ?? null,
        width: at.medianIntervalWidth ?? null,
      };
    })
    .filter((f): f is Finding => f !== null)
    .sort((a, b) => b.r2 - b.preR2 - (a.r2 - a.preR2));
  const strongest = findings.slice(0, 2).filter((f) => f.r2 - f.preR2 >= 0.1);
  const flat = results.sitePerformance
    .map((site) => ({ site, last: site.stages[site.stages.length - 1] }))
    .find(({ site, last }) => imageryGain(site.preseason, last) === 'little');
  const uav = results.uav?.matched ? results.uav : null;
  const level = results.interval?.level ? `${Math.round(results.interval.level * 100)}%` : null;
  const coverage = results.interval?.coverage;

  return (
    <section className="mx-auto max-w-6xl px-4 pt-14 sm:px-6 sm:pt-20" aria-labelledby="results-heading">
      <Reveal>
        <p className="text-[13px] font-medium text-leaf-700">Results</p>
        <h2 id="results-heading" className="mt-2 text-[28px] leading-tight font-semibold tracking-[-0.025em] text-ink sm:text-[34px]">
          What the {season} trials showed
        </h2>
        <p className="mt-4 max-w-3xl text-[16px] leading-relaxed text-pretty text-muted sm:text-[17px]">
          Across <span className="data text-ink">{plots.toLocaleString('en-US')}</span> maize plots at{' '}
          {count(results.plotCounts.length)} {season} trial sites, SoilSignal&rsquo;s site-specific forecasts generally improved
          as satellite observations accumulated, then levelled off. The useful window differed by site.
        </p>
      </Reveal>

      <ul className="mt-8 grid gap-4 md:grid-cols-3">
        {strongest.map((f) => (
          <Reveal key={f.site.site} as="li" className="rounded-2xl border border-line bg-surface p-5 sm:p-6">
            <p className="text-[13px] font-medium tracking-[0.06em] text-muted uppercase">{f.name}</p>
            <p className="mt-3 flex items-baseline gap-2 text-ink">
              <span className="data text-[26px] font-medium text-muted">{f.preR2.toFixed(2)}</span>
              <ArrowRight className="h-4 w-4 self-center text-faint" aria-hidden="true" />
              <span className="data text-[32px] font-semibold tracking-[-0.02em]">{f.r2.toFixed(2)}</span>
              <span className="text-[13px] text-muted">R²</span>
            </p>
            <p className="mt-3 text-[14px] leading-relaxed text-ink-soft">
              R² rose from {f.preR2.toFixed(2)} before any imagery to {f.r2.toFixed(2)} by about day{' '}
              <span className="data">{f.dap}</span> after planting
              {f.preWidth != null && f.width != null && f.width < f.preWidth && (
                <>
                  , while the typical {level ?? ''} prediction range narrowed from about{' '}
                  <span className="data">{Math.round(f.preWidth)}</span> to <span className="data">{Math.round(f.width)}</span>{' '}
                  bu/ac
                </>
              )}
              .
            </p>
          </Reveal>
        ))}
        {uav && (
          <Reveal as="li" className="rounded-2xl border border-dashed border-line-strong bg-surface p-5 sm:p-6">
            <p className="text-[13px] font-medium tracking-[0.06em] text-muted uppercase">Satellite vs UAV</p>
            <p className="mt-3 flex items-baseline gap-2 text-ink">
              <span className="data text-[26px] font-medium text-muted">{uav.satelliteOnly.mae.toFixed(2)}</span>
              <ArrowRight className="h-4 w-4 self-center text-faint" aria-hidden="true" />
              <span className="data text-[32px] font-semibold tracking-[-0.02em]">{uav.satellitePlusUav.mae.toFixed(2)}</span>
              <span className="text-[13px] text-muted">MAE, bu/ac</span>
            </p>
            <p className="mt-3 text-[14px] leading-relaxed text-ink-soft">
              In a matched {uav.plots ? `${uav.plots.toLocaleString('en-US')}-plot ` : ''}comparison, adding UAV imagery reduced
              typical error from {uav.satelliteOnly.mae.toFixed(2)} to {uav.satellitePlusUav.mae.toFixed(2)} bu/ac. UAV helped, but
              only marginally beyond satellite imagery.
            </p>
          </Reveal>
        )}
      </ul>

      <Reveal className="mt-5 flex flex-col gap-3 text-[14px] leading-relaxed text-muted sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-3xl">
          {flat &&
            `At ${name(flat.site.site)}, imagery added little beyond the field records: typical error ${flat.site.preseason!.mae!.toFixed(1)} → ${flat.last.mae!.toFixed(1)} bu/ac. `}
          {coverage != null &&
            `${Math.round(coverage * 100)}% of harvested yields fell inside the ${level ?? ''} prediction ranges in out-of-fold validation.`}
        </p>
        <Link to="methodology" className="inline-flex shrink-0 items-center gap-1 font-medium text-leaf-700 hover:text-leaf-800">
          Validation by site <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </Reveal>
    </section>
  );
}
